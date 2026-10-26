"""CAL-0 (fase CAL, 15-oct): el banco de fallos del examen ex-10, reproducible, y POR QUÉ falla cada uno.

Junta en un solo fichero, por fallo: el diálogo, el criterio y lo que pedía (`check` del golden), el TURNO que lo
causó y la pieza que lo escribió (`scripts/fallos_por_turno.py`), la causa con la que lo clasificó Gadea
(`docs/robustness/ex10/fallos-ex10-por-causa.json`), el mensaje del cliente, la respuesta del bot y la conversación
REAL hasta ese turno (de la ronda `2026-10-15-ex10-completa`). El examen oculto del 2-oct quedó GASTADO en ex-10
(decisión de Gadea): sus casos entran aquí como el resto.

    python -m scripts.banco_fallos construir          # sin API: docs/robustness/cal/banco-fallos.json
    python -m scripts.banco_fallos diagnosticar       # en PRE: búsqueda / redacción / no se reproduce (ver abajo)

`diagnosticar` (solo los fallos de turnos del RAG): reproduce cada conversación DENTRO de PRE hasta el turno que
falla (`reproducir_juez_pre`, mismo código, base, modelos e interruptores), guarda el contexto que vio el revisor y la
respuesta, y un verificador (gpt-4.1, temperatura 0) dice si lo que pedía el criterio estaba en el CONTEXTO y si está
en la RESPUESTA:
  busqueda        no estaba en el contexto (el dato no llegó)
  redaccion       estaba en el contexto y la respuesta no lo dice
  no_se_reproduce la respuesta de hoy sí lo dice (variación de la ronda)
La cuenta de OpenAI es la de PRE: si se acaba, PRE no contesta.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAL = ROOT / "docs/robustness/cal"
RONDA = "2026-10-15-ex10-completa"
GOLDEN = ROOT / "docs/robustness/golden-set/golden-dialogues.json"
BANCO = CAL / "banco-fallos.json"


def _checks() -> dict:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    dialogos = golden["dialogues"]
    globales = {f"global:{c['id']}": c.get("check", "") for c in golden.get("global_criteria") or []}
    out = {}
    for d in dialogos:
        for gid, check in globales.items():
            out[(d["id"], gid)] = check
        for c in d.get("criteria") or []:
            out[(d["id"], c["id"])] = c.get("check", "")
    return out


def _conversaciones() -> dict:
    por_tag: dict[str, list[dict]] = {}
    for linea in (ROOT / f"docs/robustness/synthetic-runs/{RONDA}.jsonl").read_text(encoding="utf-8").splitlines():
        if linea.strip():
            r = json.loads(linea)
            por_tag.setdefault(r["tag"], []).append(r)
    return {t: sorted(v, key=lambda r: r["turn"]) for t, v in por_tag.items()}


def construir() -> list[dict]:
    por_turno = json.loads((CAL / "fallos-por-turno-ex10.json").read_text(encoding="utf-8"))
    gadea = {(x["dialogo"], x["criterio"]): x for x in
             json.loads((ROOT / "docs/robustness/ex10/fallos-ex10-por-causa.json").read_text(encoding="utf-8"))}
    checks, convs = _checks(), _conversaciones()
    banco = []
    for i, f in enumerate(por_turno, 1):
        g = gadea.get((f["dialogo"], f["criterio"]), {})
        turnos = convs.get(f["dialogo"], [])
        hasta = f.get("turno") or len(turnos)
        historial = []
        for r in turnos[: max(hasta - 1, 0)]:
            historial += [{"role": "user", "content": r["msg"]}, {"role": "assistant", "content": r["reply"]}]
        banco.append({
            "id": f"cal-{i:02d}",
            "grupo": g.get("grupo", ""),
            "dialogo": f["dialogo"],
            "criterio": f["criterio"],
            "pedia": checks.get((f["dialogo"], f["criterio"]), "") or g.get("check", ""),
            "veredicto": f["veredicto"],
            "causa_gadea": g.get("causa", ""),
            "resumen": g.get("resumen", ""),
            "motivo_juez": f.get("motivo", ""),
            "turno": f.get("turno"),
            "pieza": f.get("tipo"),
            "mensaje_cliente": f.get("mensaje_cliente", ""),
            "respuesta_ex10": f.get("respuesta", ""),
            "historial": historial,
            "turnos_dialogo": len(turnos),
        })
    CAL.mkdir(parents=True, exist_ok=True)
    BANCO.write_text(json.dumps({"about": __doc__.split("\n\n")[0], "ronda": RONDA, "fallos": banco},
                                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return banco


VERIFICADOR = """Eres un revisor de calidad de Coral, el asistente de reservas de un centro de buceo.
Te paso UN fallo que encontró el juez en una conversación: lo que el criterio pedía y por qué falló. Te paso también
cómo es HOY ese mismo turno: la respuesta del bot y el CONTEXTO entero que tenía para escribirla.

Contesta en JSON con:
- "se_reproduce": "si" si la respuesta de HOY sigue cometiendo el mismo fallo, "no" si ya no, "parcial" si a medias.
- "falta_informacion": true si el fallo es que FALTA decir algo (un dato, una política, una aclaración) o que se dice
  algo equivocado que la base contradice; false si el fallo es de entender al cliente (repreguntar algo que ya dijo,
  suponer algo que no dijo, no pedir un dato) o de otro tipo.
- "dato": en una frase, la información que hacía falta (vacío si no aplica).
- "en_contexto": solo si falta_informacion: "si" si esa información está en el CONTEXTO, "no" si no está, "parcial".
- "explicacion": una o dos frases, citando el contexto si está.
"""


def _turnos_del_caso(f: dict) -> list[str]:
    return [h["content"] for h in f["historial"] if h["role"] == "user"] + [f["mensaje_cliente"]]


def _reproducir_en_pre(turnos: list[str], *, reps: int = 1, flags: list[str] | None = None,
                       codigo: str | None = None, entorno: dict | None = None) -> list[dict]:
    """Reproduce la conversación DENTRO de PRE `reps` veces y devuelve el último turno de cada una: respuesta y
    contexto del revisor. `flags`: interruptores encendidos solo en ese proceso; `codigo`: la copia del código local."""
    from scripts.pre_access import docker_python, pre_ssh
    from scripts.reproducir_juez_pre import _REMOTO

    # 26-oct: el script de PRE recibe una LISTA de diálogos ([id, turnos]) desde arq-1d (22-oct); con el nombre viejo
    # (TURNOS_JSON) cada caso moría con NameError y la medida salía «0 casos medidos».
    dialogos = [["caso", turnos]]
    script = (f"DIALOGOS_JSON = {json.dumps(dialogos, ensure_ascii=False)!r}\nN_REPS = {reps}\n"
              f"FLAGS = {flags or []!r}\n{_REMOTO}")
    r = pre_ssh(docker_python(entorno or {}, codigo_local=codigo), input_text=script,
                timeout=240 + 60 * len(turnos) * reps)
    filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    ultimos = [f for f in filas if f["turn"] == len(turnos)]
    if not ultimos:
        # 17-oct: sin esto, una medida que fallaba (la conexión, el contenedor, un error dentro de PRE) devolvía una
        # lista vacía y el caso quedaba como "falla 0/0", indistinguible de un caso que pasa: en la medida del banco
        # entero, 62 de 71 casos salieron así y el total (3/9) parecía buenísimo. Un fallo de medida tiene que verse.
        raise RuntimeError(
            f"la reproducción en PRE no devolvió ningún turno (código {r.returncode}): "
            f"{((r.stderr or r.stdout) or '').strip()[-400:]}")
    return ultimos


# 17-oct (Álvaro, a propuesta de Gadea): el verificador es lo que más gasta de cada medida (hasta 60.000 caracteres de
# contexto por respuesta con gpt-4.1). `--verificador` elige el modelo y `--comparar-verificador` juzga las MISMAS
# respuestas con un segundo modelo y dice en cuántas coinciden: cambiar de verificador cambia el instrumento, así que
# antes se mide que diga lo mismo.
# mod-8 (18-oct, acordado con Álvaro): Luna coincide con gpt-4.1 en 27/30 veredictos y es igual de exigente (14 fallos
# frente a 15; DeepSeek, 12: benévolo). Las medidas anteriores dicen en su JSON qué verificador usaron.
VERIFICADOR_MODELO = "gpt-6-luna"


async def _verificar(f: dict, hoy: dict, modelo: str = VERIFICADOR_MODELO) -> dict:
    from openai import AsyncOpenAI

    from src.config import settings
    from src.llm_client import trace_openai

    contexto = "\n\n".join(j["context"] for j in hoy.get("juicios") or []) or "(el turno no pasó por el revisor: sin contexto)"
    usuario = (f"CRITERIO: {f['criterio']}\nLO QUE PEDÍA: {f.get('pedia_corregido') or f['pedia']}\n"
               f"POR QUÉ FALLÓ EN LA RONDA: {f['motivo_juez']}\n\n"
               f"MENSAJE DEL CLIENTE: {f['mensaje_cliente']}\n\nRESPUESTA DE HOY: {hoy['reply']}\n\n"
               f"CONTEXTO QUE TENÍA (cortado a 60.000 caracteres):\n{contexto[:60000]}")
    # MOD-8 (18-oct): por el cliente del bot (`trace_openai`), que adapta los parámetros al modelo y saca por OpenRouter
    # los modelos con proveedor ("deepseek/…"): así se puede comparar el verificador con candidatos fuera de gpt-4.
    resp = await trace_openai(AsyncOpenAI(api_key=settings.openai_api_key)).chat.completions.create(
        model=modelo, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": VERIFICADOR}, {"role": "user", "content": usuario}])
    return json.loads(resp.choices[0].message.content or "{}")


def _causa_medida(v: dict) -> str:
    if v.get("se_reproduce") == "no":
        return "no_se_reproduce"
    if not v.get("falta_informacion"):
        return "entendimiento"
    return {"no": "busqueda", "parcial": "busqueda_parcial"}.get(v.get("en_contexto"), "redaccion")


def diagnosticar(ids: list[str] | None) -> None:
    import asyncio

    datos = json.loads(BANCO.read_text(encoding="utf-8"))
    for f in datos["fallos"]:
        if f["pieza"] != "rag" or not f["turno"] or (ids and f["id"] not in ids):
            continue
        hoy = (_reproducir_en_pre(_turnos_del_caso(f)) or [None])[0]
        if hoy is None:
            f["diagnostico"] = {"causa_medida": "error_reproduccion"}
            print(f"  {f['id']} {f['dialogo'][:40]}: no se pudo reproducir")
            continue
        v = asyncio.run(_verificar(f, hoy))
        f["diagnostico"] = {**v, "causa_medida": _causa_medida(v), "respuesta_hoy": hoy["reply"],
                            "con_contexto": bool(hoy.get("juicios"))}
        print(f"  {f['id']} {f['dialogo'][:40]:40} {f['criterio'][:28]:28} → {f['diagnostico']['causa_medida']}")
        BANCO.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")  # sobre la marcha


def medir(etiqueta: str, ids: list[str] | None, tarea: str | None, reps: int, flags: list[str],
          codigo_local: bool, verificador: str = VERIFICADOR_MODELO, comparar: list[str] | None = None,
          banco: Path | None = None, entorno: dict | None = None) -> None:
    """Mide un arreglo de CAL sobre el banco: cada caso `reps` veces en PRE (con `flags` y, si se pide, el código
    local) y el verificador dice si el fallo se repite. Usa `pedia_corregido` si lo hay (criterio actualizado a una
    decisión de Gadea). Salida: `docs/robustness/cal/medidas/<etiqueta>.json` y, por pantalla, cuántas veces falla."""
    import asyncio

    from scripts.pre_access import subir_codigo_local

    # `banco` (17-oct, r6-2): otro fichero con el mismo formato, p. ej. el banco de inyecciones de seguridad.
    datos = json.loads((banco or BANCO).read_text(encoding="utf-8"))
    casos = [f for f in datos["fallos"] if f["turno"] and (not ids or f["id"] in ids) and (not tarea or f.get("tarea") == tarea)]
    codigo = subir_codigo_local() if codigo_local else None
    # 18-oct: `entorno` (--env CLAVE=VALOR), variables solo para ese proceso: probar otro modelo sin desplegar.
    salida = {"etiqueta": etiqueta, "reps": reps, "flags": flags, "env": entorno or {}, "codigo_local": codigo_local,
              "verificador": verificador, "casos": []}
    # 18-oct (mod-8): `comparar` admite varios modelos; todos juzgan las MISMAS respuestas que el principal.
    comparar = comparar or []
    if comparar:
        salida["verificadores_comparados"] = comparar
    fallan_total = comparados = 0
    coinciden = {m: 0 for m in comparar}
    fallan_otro_total = {m: 0 for m in comparar}
    roto: list[str] = []
    for f in casos:
        try:
            filas = _reproducir_en_pre(_turnos_del_caso(f), reps=reps, flags=flags, codigo=codigo,
                                       entorno=entorno)
        except RuntimeError as exc:
            # 17-oct: un DEPLOY a PRE a mitad de medida reinicia el contenedor y se lleva por delante la copia del
            # codigo en /tmp ("chdir to cwd ... no such file or directory"): la medida moria y 62 casos se quedaban
            # sin medir. Si la copia ya no esta, se vuelve a subir y se reintenta el caso una vez.
            if codigo and "no such file or directory" in str(exc):
                print(f"  {f['id']}: la copia del codigo ya no esta (deploy a mitad?): la subo otra vez")
                try:
                    codigo = subir_codigo_local()
                    filas = _reproducir_en_pre(_turnos_del_caso(f), reps=reps, flags=flags, codigo=codigo,
                                       entorno=entorno)
                except RuntimeError as otra:
                    print(f"  {f['id']} NO MEDIDO: {otra}")
                    roto.append(f["id"])
                    continue
            else:
                # El caso se queda SIN medir y se dice al final: no cuenta como 0 fallos (17-oct).
                print(f"  {f['id']} NO MEDIDO: {exc}")
                roto.append(f["id"])
                continue
        async def _todas(f=f, filas=filas):  # un solo bucle por caso (antes: "Event loop is closed" al cerrar clientes)
            principal = asyncio.gather(*(_verificar(f, hoy, verificador) for hoy in filas))
            otros = [asyncio.gather(*(_verificar(f, hoy, m) for hoy in filas)) for m in comparar]
            todos = await asyncio.gather(principal, *otros)
            return todos[0], todos[1:]

        veredictos, otros = asyncio.run(_todas())
        falla = [v.get("se_reproduce") in ("si", "parcial") for v in veredictos]
        fallan = sum(falla)
        fallan_total += fallan
        caso = {"id": f["id"], "dialogo": f["dialogo"], "criterio": f["criterio"], "repeticiones": len(filas),
                "fallan": fallan, "respuestas": [h["reply"] for h in filas],
                "explicaciones": [v.get("explicacion", "") for v in veredictos],
                # lat-9 paso 2 (26-oct): el tiempo del turno medido y las líneas del flujo, para la latencia por camino.
                "segundos": [h.get("segundos") for h in filas], "trazas": [h.get("traza") or [] for h in filas]}
        linea = f"  {f['id']} {f['dialogo'][:40]:40} {f['criterio'][:28]:28} falla {fallan}/{len(filas)}"
        if comparar:
            comparados += len(falla)
            caso["comparados"] = {}
        for m, vs in zip(comparar, otros):
            falla_otro = [v.get("se_reproduce") in ("si", "parcial") for v in vs]
            caso["comparados"][m] = {"fallan": sum(falla_otro), "explicaciones": [v.get("explicacion", "") for v in vs]}
            fallan_otro_total[m] += sum(falla_otro)
            coinciden[m] += sum(a == b for a, b in zip(falla, falla_otro))
            linea += f"  ({m}: {sum(falla_otro)}/{len(filas)})"
        salida["casos"].append(caso)
        print(linea)
    destino = CAL / "medidas" / f"{etiqueta}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    total = sum(c["repeticiones"] for c in salida["casos"])
    salida["sin_medir"] = roto
    if comparar and comparados:
        salida["coincidencia_verificadores"] = {
            m: {"coinciden": coinciden[m], "de": comparados, "fallan_principal": fallan_total,
                "fallan_comparado": fallan_otro_total[m]} for m in comparar}
        for m in comparar:
            print(f"verificadores: {verificador} y {m} coinciden en {coinciden[m]}/{comparados} veredictos "
                  f"(fallan {fallan_total} con {verificador}, {fallan_otro_total[m]} con {m})")
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    medidos = len(casos) - len(roto)
    print(f"{etiqueta}: fallan {fallan_total}/{total} repeticiones en {medidos} casos medidos "
          f"→ {destino.relative_to(ROOT)}")
    if roto:
        print(f"  ⚠️  {len(roto)} casos SIN MEDIR (no cuentan como buenos): {', '.join(roto)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("accion", choices=["construir", "diagnosticar", "medir"])
    ap.add_argument("--ids", help="solo estos casos (cal-01,cal-05…)")
    ap.add_argument("--tarea", help="medir: solo los casos de esta tarea (CAL-B…)")
    ap.add_argument("--etiqueta", help="medir: nombre de la medida")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--flag", action="append", default=[],
                    help="medir: interruptor encendido solo en ese proceso ('no:X' lo APAGA: para medir igual que la "
                         "base aunque PRE sirva la rama de otro con sus flags encendidos)")
    ap.add_argument("--codigo-local", action="store_true", help="medir: con el código local (sin desplegar)")
    ap.add_argument("--verificador", default=VERIFICADOR_MODELO, help="medir: modelo del verificador (gpt-6-luna)")
    ap.add_argument("--comparar-verificador", action="append", default=[],
                    help="medir: juzga las mismas respuestas también con este modelo (repetible)")
    ap.add_argument("--banco", help="medir: otro banco con el mismo formato (p. ej. docs/robustness/seguridad/"
                                    "banco-inyeccion.json)")
    ap.add_argument("--env", action="append", default=[], metavar="CLAVE=VALOR",
                    help="medir: variable de entorno solo para ese proceso (p. ej. PREGUNTA_SOLA_MODEL=...); repetible")
    args = ap.parse_args()
    if args.accion == "medir":
        medir(args.etiqueta or "medida", args.ids.split(",") if args.ids else None, args.tarea, args.reps, args.flag,
              args.codigo_local, args.verificador, args.comparar_verificador,
              Path(args.banco) if args.banco else None, dict(e.split("=", 1) for e in args.env))
        return
    if args.accion == "construir":
        banco = construir()
        sin_turno = [b["id"] for b in banco if not b["turno"]]
        print(f"{len(banco)} fallos → {BANCO.relative_to(ROOT)} (sin turno: {len(sin_turno)})")
        return
    diagnosticar(args.ids.split(",") if args.ids else None)


if __name__ == "__main__":
    main()
