"""Trazador de regex: sustituye `re` en los módulos estudiados por un proxy que apunta cada evaluación (quién la
llama, qué patrón, si casó) y envuelve los patrones compilados de módulo y de clase. No cambia ningún resultado."""
import re as _re
import sys
from collections import defaultdict

from src.utils.text import strip_accents

_ESTE = __file__
CTX = {"i": None, "ctx": None}
# (modulo, nombre_patron, funcion_llamadora) -> {"evals", "hits", "msgs": set, "msgs_eval": set, "ctx": {ctx: set}}
REC: dict = defaultdict(lambda: {"evals": 0, "hits": 0, "msgs": set(), "msgs_eval": set(), "ctx": defaultdict(set)})
_NOMBRES: dict[str, dict[str, str]] = {}  # modulo -> {texto_del_patron: nombre}


def _llamador():
    f = sys._getframe(1)
    while f is not None and f.f_code.co_filename == _ESTE:
        f = f.f_back
    if f is None:
        return "?", 0
    linea = f.f_lineno
    while f is not None and f.f_code.co_name.startswith("<") and f.f_back is not None:
        f = f.f_back
    return f.f_code.co_name, linea


def _apunta(modulo: str, nombre: str, casa: bool) -> None:
    func, _linea = _llamador()
    r = REC[(modulo, nombre, func)]
    r["evals"] += 1
    if CTX["i"] is not None:
        r["msgs_eval"].add(CTX["i"])
    if casa:
        r["hits"] += 1
        if CTX["i"] is not None:
            r["msgs"].add(CTX["i"])
            r["ctx"][CTX["ctx"]].add(CTX["i"])


def _nombre(modulo: str, patron) -> str:
    if isinstance(patron, PatronTrazado):
        return patron._nombre
    texto = patron.pattern if hasattr(patron, "pattern") else patron
    n = _NOMBRES.get(modulo, {}).get(texto)
    if n:
        return n
    func, linea = _llamador()
    return f"local:{func}:{linea}"


class PatronTrazado:
    def __init__(self, modulo: str, nombre: str, compilado):
        self._modulo, self._nombre, self._c = modulo, nombre, compilado

    def __getattr__(self, a):
        return getattr(self._c, a)

    def search(self, *a, **k):
        m = self._c.search(*a, **k)
        _apunta(self._modulo, self._nombre, m is not None)
        return m

    def match(self, *a, **k):
        m = self._c.match(*a, **k)
        _apunta(self._modulo, self._nombre, m is not None)
        return m

    def fullmatch(self, *a, **k):
        m = self._c.fullmatch(*a, **k)
        _apunta(self._modulo, self._nombre, m is not None)
        return m

    def findall(self, *a, **k):
        m = self._c.findall(*a, **k)
        _apunta(self._modulo, self._nombre, bool(m))
        return m

    def finditer(self, *a, **k):
        m = list(self._c.finditer(*a, **k))
        _apunta(self._modulo, self._nombre, bool(m))
        return iter(m)

    def sub(self, repl, string, *a, **k):
        m = self._c.sub(repl, string, *a, **k)
        _apunta(self._modulo, self._nombre, m != string)
        return m

    def subn(self, repl, string, *a, **k):
        m = self._c.subn(repl, string, *a, **k)
        _apunta(self._modulo, self._nombre, m[1] > 0)
        return m

    def split(self, string, *a, **k):
        m = self._c.split(string, *a, **k)
        _apunta(self._modulo, self._nombre, len(m) > 1)
        return m


def _desenvuelve(p):
    return p._c if isinstance(p, PatronTrazado) else p


class ReTrazado:
    """Proxy del módulo `re` para un módulo concreto."""

    def __init__(self, modulo: str):
        self._modulo = modulo

    def __getattr__(self, a):
        return getattr(_re, a)

    def compile(self, pattern, flags=0):
        c = _re.compile(_desenvuelve(pattern), flags)
        return PatronTrazado(self._modulo, _nombre(self._modulo, pattern), c)

    def _f(self, fn, pattern, string, flags, casa_fn, *extra):
        nombre = _nombre(self._modulo, pattern)
        p = _desenvuelve(pattern)
        res = fn(p, string, *extra, flags=flags) if not hasattr(p, "search") else getattr(p, fn.__name__)(string, *extra)
        if fn is _re.finditer:
            res = list(res)
            _apunta(self._modulo, nombre, bool(res))
            return iter(res)
        _apunta(self._modulo, nombre, casa_fn(res))
        return res

    def search(self, pattern, string, flags=0):
        return self._f(_re.search, pattern, string, flags, lambda r: r is not None)

    def match(self, pattern, string, flags=0):
        return self._f(_re.match, pattern, string, flags, lambda r: r is not None)

    def fullmatch(self, pattern, string, flags=0):
        return self._f(_re.fullmatch, pattern, string, flags, lambda r: r is not None)

    def findall(self, pattern, string, flags=0):
        return self._f(_re.findall, pattern, string, flags, bool)

    def finditer(self, pattern, string, flags=0):
        return self._f(_re.finditer, pattern, string, flags, bool)

    def split(self, pattern, string, maxsplit=0, flags=0):
        nombre = _nombre(self._modulo, pattern)
        res = _re.split(_desenvuelve(pattern), string, maxsplit=maxsplit, flags=flags)
        _apunta(self._modulo, nombre, len(res) > 1)
        return res

    def sub(self, pattern, repl, string, count=0, flags=0):
        nombre = _nombre(self._modulo, pattern)
        res = _re.sub(_desenvuelve(pattern), repl, string, count=count, flags=flags)
        _apunta(self._modulo, nombre, res != string)
        return res


def _indexa(modulo_nombre: str, espacio: dict, prefijo: str = "") -> dict:
    idx = _NOMBRES.setdefault(modulo_nombre, {})
    contenedores = {}
    for nombre, val in list(espacio.items()):
        if nombre.startswith("__"):
            continue
        if isinstance(val, str) and len(val) > 2:
            for v in (val, strip_accents(val)):
                idx.setdefault(v, prefijo + nombre)  # el nombre más específico (la variable de texto) gana
        elif isinstance(val, (list, tuple)):
            contenedores[nombre] = val
        elif isinstance(val, dict):
            contenedores[nombre] = list(val.values())
    for nombre, val in contenedores.items():
        for el in val:
            for x in (el if isinstance(el, (list, tuple)) else [el]):
                if isinstance(x, str) and len(x) > 2:
                    for v in (x, strip_accents(x)):
                        idx.setdefault(v, prefijo + nombre)
    return idx


def instala(modulo) -> None:
    """Pone el proxy en `modulo.re` y envuelve los patrones compilados de módulo y de sus clases."""
    nombre_mod = modulo.__name__
    _indexa(nombre_mod, vars(modulo))
    for nombre, val in list(vars(modulo).items()):
        if isinstance(val, _re.Pattern):
            setattr(modulo, nombre, PatronTrazado(nombre_mod, nombre, val))
            _NOMBRES[nombre_mod].setdefault(val.pattern, nombre)
        elif isinstance(val, type) and val.__module__ == nombre_mod:
            _indexa(nombre_mod, dict(vars(val)), prefijo="")
            for an, av in list(vars(val).items()):
                if isinstance(av, _re.Pattern):
                    setattr(val, an, PatronTrazado(nombre_mod, an, av))
                    _NOMBRES[nombre_mod].setdefault(av.pattern, an)
        elif isinstance(val, (list, tuple)) and val and all(isinstance(x, _re.Pattern) for x in val):
            setattr(modulo, nombre, type(val)(PatronTrazado(nombre_mod, nombre, x) for x in val))
        elif (isinstance(val, (list, tuple)) and val and all(isinstance(x, tuple) and x and isinstance(x[0], _re.Pattern)
                                                          for x in val)):
            setattr(modulo, nombre, type(val)((PatronTrazado(nombre_mod, nombre, x[0]), *x[1:]) for x in val))
    if hasattr(modulo, "re"):
        modulo.re = ReTrazado(nombre_mod)


def reinicia() -> None:
    REC.clear()
