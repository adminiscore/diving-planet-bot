"""Coral: el chat entre los Claude de Gadea, Álvaro y Gonzalo (y ellos mismos desde el navegador).

Un solo proceso con SQLite en /data. Caddy lo sirve en https://pre.is-core.dev/coral/ (quita el prefijo `/coral`).
Cada persona tiene su token (`CORAL_TOKENS="gadea:xxx,alvaro:yyy,gonzalo:zzz"`): el token dice quién habla.

Además del chat guarda el estado de cada uno (tarea, rama, ficheros con cambios, si está midiendo o subiendo a PRE)
para que el Claude de otro pueda saberlo sin preguntar, y detecta cuándo dos personas tienen cambios en el mismo
fichero. La bandeja se entrega UNA vez por persona (cursor `entregado`), y se puede esperar a que llegue algo
(`esperar`, long-poll): así la escucha de Claude Code (herramienta Monitor) recibe cada mensaje al momento.
"""

import asyncio
import hmac
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

HORA_LOCAL = ZoneInfo("Europe/Madrid")
MINUTOS_PRE = {"midiendo": 60, "subiendo": 15}  # caducan solos: un proceso muerto no deja PRE "ocupado" para siempre
HORAS_ACTIVO = 3  # los ficheros de quien no da señales en 3 h no cuentan como solape
MAX_POR_VENTANA = 20  # mensajes por persona cada 10 min: corta cualquier bucle entre Claudes
MAX_HILO = 6  # mensajes encadenados por `responde_a`: más largo es una discusión, y esa la cierran las personas
PAGINA = Path(__file__).with_name("pagina.html")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS mensajes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, de TEXT NOT NULL, para TEXT NOT NULL, tipo TEXT NOT NULL,
    texto TEXT NOT NULL, origen TEXT NOT NULL, responde_a INTEGER);
CREATE TABLE IF NOT EXISTS estado (
    persona TEXT PRIMARY KEY, tarea TEXT NOT NULL DEFAULT '', nota TEXT NOT NULL DEFAULT '',
    rama TEXT NOT NULL DEFAULT '', ficheros TEXT NOT NULL DEFAULT '[]',
    pre TEXT NOT NULL DEFAULT 'libre', pre_hasta TEXT, visto TEXT, entregado INTEGER NOT NULL DEFAULT 0);
"""


class NuevoMensaje(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)
    para: str | None = None  # por defecto: a quien escribió el mensaje al que respondes, o a todos
    tipo: Literal["aviso", "pregunta", "respuesta", "propuesta", "resultado"] = "aviso"
    origen: Literal["claude", "persona"] = "claude"
    responde_a: int | None = None


class CambioEstado(BaseModel):
    tarea: str | None = Field(default=None, max_length=200)
    nota: str | None = Field(default=None, max_length=500)
    pre: Literal["libre", "midiendo", "subiendo"] | None = None
    minutos: int | None = Field(default=None, ge=1, le=24 * 60)


class Latido(BaseModel):
    rama: str | None = Field(default=None, max_length=200)
    ficheros: list[str] | None = Field(default=None, max_length=200)
    bandeja: bool = True


def _ahora() -> datetime:
    return datetime.now(UTC)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _hora(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(HORA_LOCAL).strftime("%H:%M")


def leer_tokens(texto: str) -> dict[str, str]:
    """`"gadea:xxx,alvaro:yyy"` -> {token: persona}."""
    pares = (p.split(":", 1) for p in texto.split(",") if ":" in p)
    return {tok.strip(): nombre.strip().lower() for nombre, tok in pares if tok.strip() and nombre.strip()}


def crear_app(db: str | None = None, tokens: dict[str, str] | None = None) -> FastAPI:
    tokens = tokens if tokens is not None else leer_tokens(os.environ.get("CORAL_TOKENS", ""))
    personas = sorted(set(tokens.values()))
    con = sqlite3.connect(db or os.environ.get("CORAL_DB", ":memory:"), check_same_thread=False,
                          isolation_level=None)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    cambio = {"ev": asyncio.Event()}  # se sustituye en cada cambio: quien espera se queda con el de antes

    def avisar_cambio() -> None:
        cambio["ev"].set()
        cambio["ev"] = asyncio.Event()

    def persona_del_token(authorization: str = Header(default="")) -> str:
        dado = authorization.removeprefix("Bearer ").strip()
        for tok, nombre in tokens.items():
            if dado and hmac.compare_digest(dado, tok):
                return nombre
        raise HTTPException(401, "token no válido")

    def fila(persona: str) -> sqlite3.Row:
        """El estado de `persona`; la primera vez nace con la bandeja al día (no le cae todo el historial)."""
        f = con.execute("SELECT * FROM estado WHERE persona = ?", (persona,)).fetchone()
        if f is None:
            ultimo = con.execute("SELECT COALESCE(MAX(id), 0) FROM mensajes").fetchone()[0]
            con.execute("INSERT INTO estado (persona, entregado) VALUES (?, ?)", (persona, ultimo))
            f = con.execute("SELECT * FROM estado WHERE persona = ?", (persona,)).fetchone()
        return f

    def visto(persona: str) -> None:
        fila(persona)
        con.execute("UPDATE estado SET visto = ? WHERE persona = ?", (_iso(_ahora()), persona))

    def pre_vigente(f: sqlite3.Row) -> str:
        if f["pre"] != "libre" and f["pre_hasta"] and datetime.fromisoformat(f["pre_hasta"]) < _ahora():
            return "libre"
        return f["pre"]

    def como_estado(f: sqlite3.Row) -> dict:
        pre = pre_vigente(f)
        return {"persona": f["persona"], "tarea": f["tarea"], "nota": f["nota"], "rama": f["rama"],
                "ficheros": json.loads(f["ficheros"]), "pre": pre,
                "pre_hasta": f["pre_hasta"] if pre != "libre" else None, "visto": f["visto"]}

    def equipo() -> list[dict]:
        for p in personas:
            fila(p)
        return [como_estado(f) for f in con.execute("SELECT * FROM estado ORDER BY persona")]

    def solapes(persona: str) -> list[dict]:
        mios = set(json.loads(fila(persona)["ficheros"]))
        limite = _ahora() - timedelta(hours=HORAS_ACTIVO)
        salida = []
        for e in equipo():
            if e["persona"] == persona or not e["visto"] or datetime.fromisoformat(e["visto"]) < limite:
                continue
            comunes = sorted(mios & set(e["ficheros"]))
            if comunes:
                salida.append({"persona": e["persona"], "ficheros": comunes})
        return salida

    def guardar(de: str, m: NuevoMensaje, origen: str | None = None) -> dict:
        cur = con.execute(
            "INSERT INTO mensajes (ts, de, para, tipo, texto, origen, responde_a) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_iso(_ahora()), de, m.para, m.tipo, m.texto.strip(), origen or m.origen, m.responde_a))
        avisar_cambio()
        return dict(con.execute("SELECT * FROM mensajes WHERE id = ?", (cur.lastrowid,)).fetchone())

    def bandeja(persona: str, marcar: bool) -> list[dict]:
        desde = fila(persona)["entregado"]
        filas = con.execute(
            "SELECT * FROM mensajes WHERE id > ? AND de != ? AND para IN (?, 'todos') ORDER BY id LIMIT 50",
            (desde, persona, persona)).fetchall()
        if marcar and filas:
            con.execute("UPDATE estado SET entregado = ? WHERE persona = ?", (filas[-1]["id"], persona))
        return [dict(f) for f in filas]

    app = FastAPI(title="Coral", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/salud")
    async def salud() -> dict:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def pagina() -> str:
        return PAGINA.read_text(encoding="utf-8")

    @app.get("/api/yo")
    async def yo(persona: str = Depends(persona_del_token)) -> dict:
        visto(persona)
        return {"persona": persona, "personas": personas}

    def hilo(id_: int | None) -> list[sqlite3.Row]:
        """El mensaje `id_` y los que tiene encima por `responde_a`, del más reciente al primero."""
        cadena = []
        while id_ is not None and len(cadena) <= MAX_HILO:
            f = con.execute("SELECT * FROM mensajes WHERE id = ?", (id_,)).fetchone()
            if f is None:
                break
            cadena.append(f)
            id_ = f["responde_a"]
        return cadena

    def validar(persona: str, m: NuevoMensaje) -> None:
        """Las reglas de la conversación, aquí y no solo en las normas, para que dos Claudes no entren en bucle:
        a una pregunta o propuesta se responde UNA vez; a avisos, respuestas y resultados no se contesta; un rechazo
        se rebate una sola vez; y un hilo de más de MAX_HILO mensajes ya es cosa de las personas."""
        if m.para not in ("todos", *personas):
            raise HTTPException(400, f"'para' tiene que ser 'todos' o una de: {', '.join(personas)}")
        cadena = hilo(m.responde_a)
        if m.responde_a is not None and not cadena:
            raise HTTPException(400, f"no existe el mensaje #{m.responde_a}")
        if len(cadena) >= MAX_HILO:
            raise HTTPException(400, "este hilo ya es muy largo: no hay acuerdo, decídselo a vuestras personas")
        original = cadena[0] if cadena else None
        if m.tipo == "respuesta":
            if original is None or original["tipo"] not in ("pregunta", "propuesta"):
                raise HTTPException(400, "una respuesta lleva 'responde_a' con el id de una pregunta o una propuesta "
                                         "(a los avisos, respuestas y resultados no se contesta)")
            if original["de"] == persona or original["para"] not in ("todos", persona):
                raise HTTPException(400, f"#{original['id']} no es para ti")
            ya = con.execute("SELECT 1 FROM mensajes WHERE tipo = 'respuesta' AND responde_a = ? AND de = ?",
                             (original["id"], persona)).fetchone()
            if ya:
                raise HTTPException(400, f"ya respondiste a #{original['id']}: lo que venga después va como resultado")
        elif m.tipo == "propuesta" and original is not None:
            # Rebatir: solo contra la respuesta que rechazó TU propuesta, y una vez por hilo.
            if (original["tipo"] != "respuesta" or len(cadena) < 2 or cadena[1]["tipo"] != "propuesta"
                    or cadena[1]["de"] != persona):
                raise HTTPException(400, "una propuesta va suelta o rebate la respuesta a una propuesta tuya")
            if sum(f["tipo"] == "propuesta" for f in cadena) >= 2:
                raise HTTPException(400, "ya rebatiste una vez: si seguís sin acuerdo, decídselo a vuestras personas")
        elif m.tipo == "resultado" and original is not None and original["tipo"] not in ("pregunta", "propuesta"):
            raise HTTPException(400, "un resultado va suelto o cierra una pregunta o propuesta")

    @app.post("/api/mensajes")
    async def decir(m: NuevoMensaje, persona: str = Depends(persona_del_token)) -> dict:
        if m.para is None:
            original = hilo(m.responde_a)[:1]
            m.para = original[0]["de"] if original and m.tipo in ("respuesta", "resultado") else "todos"
        validar(persona, m)
        hace_10 = _iso(_ahora() - timedelta(minutes=10))
        recientes = con.execute("SELECT COUNT(*) FROM mensajes WHERE de = ? AND ts > ? AND origen != 'sistema'",
                                (persona, hace_10)).fetchone()[0]
        if recientes >= MAX_POR_VENTANA:
            raise HTTPException(429, f"más de {MAX_POR_VENTANA} mensajes en 10 minutos: ¿hay un bucle?")
        visto(persona)
        return guardar(persona, m)

    @app.get("/api/mensajes")
    async def mensajes(desde: int = 0, limite: int = Query(100, ge=1, le=500), esperar: float = Query(0, ge=0, le=30),
                       persona: str = Depends(persona_del_token)) -> list[dict]:
        """El historial de todos (lo que ve la página). Con `desde`, solo lo nuevo; con `esperar`, aguarda a que
        llegue algo."""
        def leer() -> list[sqlite3.Row]:
            if desde:
                return con.execute("SELECT * FROM mensajes WHERE id > ? ORDER BY id LIMIT ?", (desde, limite)).fetchall()
            return con.execute("SELECT * FROM mensajes ORDER BY id DESC LIMIT ?", (limite,)).fetchall()[::-1]

        visto(persona)
        ev_antes = cambio["ev"]
        filas = leer()
        if not filas and esperar:
            try:
                await asyncio.wait_for(ev_antes.wait(), timeout=esperar)
            except TimeoutError:
                pass
            filas = leer()
        return [dict(f) for f in filas]

    @app.get("/api/bandeja")
    async def leer_bandeja(esperar: float = Query(0, ge=0, le=30), marcar: bool = True,
                           persona: str = Depends(persona_del_token)) -> list[dict]:
        """Lo que es para ti (a ti o a todos, no tuyo) y aún no se te entregó."""
        visto(persona)
        ev_antes = cambio["ev"]
        filas = bandeja(persona, marcar)
        if not filas and esperar:
            try:
                await asyncio.wait_for(ev_antes.wait(), timeout=esperar)
            except TimeoutError:
                pass
            filas = bandeja(persona, marcar)
        return filas

    @app.get("/api/equipo")
    async def ver_equipo(persona: str = Depends(persona_del_token)) -> dict:
        visto(persona)
        return {"yo": persona, "equipo": equipo(), "solapes": solapes(persona)}

    @app.put("/api/estado")
    async def cambiar_estado(c: CambioEstado, persona: str = Depends(persona_del_token)) -> dict:
        antes = fila(persona)
        pre_antes = pre_vigente(antes)
        if c.tarea is not None:
            con.execute("UPDATE estado SET tarea = ? WHERE persona = ?", (c.tarea.strip(), persona))
        if c.nota is not None:
            con.execute("UPDATE estado SET nota = ? WHERE persona = ?", (c.nota.strip(), persona))
        if c.pre is not None:
            hasta = None
            if c.pre != "libre":
                hasta = _iso(_ahora() + timedelta(minutes=c.minutos or MINUTOS_PRE[c.pre]))
            con.execute("UPDATE estado SET pre = ?, pre_hasta = ? WHERE persona = ?", (c.pre, hasta, persona))
            # El aviso lo da el servidor: así lo anuncian igual el hook del push, las medidas y la página.
            detalle = (c.nota or antes["tarea"] or "").strip()
            if c.pre != "libre":
                texto = f"PRE: {c.pre} hasta las {_hora(hasta)}" + (f" ({detalle})" if detalle else "")
                guardar(persona, NuevoMensaje(texto=texto, para="todos"), origen="sistema")
            elif pre_antes != "libre":
                guardar(persona, NuevoMensaje(texto="PRE: libre", para="todos"), origen="sistema")
        visto(persona)
        return como_estado(fila(persona))

    @app.post("/api/latido")
    async def latido(lat: Latido, persona: str = Depends(persona_del_token)) -> dict:
        """Lo que mandan los hooks de Claude Code: rama y ficheros con cambios. Devuelve lo nuevo de la bandeja,
        los solapes y el equipo, todo en una sola llamada."""
        fila(persona)
        if lat.rama is not None:
            con.execute("UPDATE estado SET rama = ? WHERE persona = ?", (lat.rama, persona))
        if lat.ficheros is not None:
            con.execute("UPDATE estado SET ficheros = ? WHERE persona = ?",
                        (json.dumps(sorted(set(lat.ficheros))[:200]), persona))
        visto(persona)
        return {"yo": persona, "mensajes": bandeja(persona, True) if lat.bandeja else [],
                "solapes": solapes(persona), "equipo": equipo()}

    return app


app = crear_app()
