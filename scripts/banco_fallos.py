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


def _reproducir_en_pre(turnos: list[str]) -> dict | None:
    """Reproduce la conversación DENTRO de PRE (1 vez) y devuelve el último turno: respuesta y contexto del revisor."""
    from scripts.pre_access import docker_python, pre_ssh
    from scripts.reproducir_juez_pre import _REMOTO

    script = f"TURNOS_JSON = {json.dumps(turnos, ensure_ascii=False)!r}\nN_REPS = 1\nFLAGS = []\n{_REMOTO}"
    r = pre_ssh(docker_python({}), input_text=script, timeout=240 + 60 * len(turnos))
    filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    return filas[-1] if filas and filas[-1]["turn"] == len(turnos) else None


async def _verificar(f: dict, hoy: dict) -> dict:
    from openai import AsyncOpenAI

    from src.config import settings

    contexto = "\n\n".join(j["context"] for j in hoy.get("juicios") or []) or "(el turno no pasó por el revisor: sin contexto)"
    usuario = (f"CRITERIO: {f['criterio']}\nLO QUE PEDÍA: {f['pedia']}\nPOR QUÉ FALLÓ EN LA RONDA: {f['motivo_juez']}\n\n"
               f"MENSAJE DEL CLIENTE: {f['mensaje_cliente']}\n\nRESPUESTA DE HOY: {hoy['reply']}\n\n"
               f"CONTEXTO QUE TENÍA (cortado a 60.000 caracteres):\n{contexto[:60000]}")
    resp = await AsyncOpenAI(api_key=settings.openai_api_key).chat.completions.create(
        model="gpt-4.1", temperature=0, response_format={"type": "json_object"},
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
        hoy = _reproducir_en_pre(_turnos_del_caso(f))
        if hoy is None:
            f["diagnostico"] = {"causa_medida": "error_reproduccion"}
            print(f"  {f['id']} {f['dialogo'][:40]}: no se pudo reproducir")
            continue
        v = asyncio.run(_verificar(f, hoy))
        f["diagnostico"] = {**v, "causa_medida": _causa_medida(v), "respuesta_hoy": hoy["reply"],
                            "con_contexto": bool(hoy.get("juicios"))}
        print(f"  {f['id']} {f['dialogo'][:40]:40} {f['criterio'][:28]:28} → {f['diagnostico']['causa_medida']}")
        BANCO.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")  # sobre la marcha


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("accion", choices=["construir", "diagnosticar"])
    ap.add_argument("--ids", help="solo estos casos (cal-01,cal-05…)")
    args = ap.parse_args()
    if args.accion == "construir":
        banco = construir()
        sin_turno = [b["id"] for b in banco if not b["turno"]]
        print(f"{len(banco)} fallos → {BANCO.relative_to(ROOT)} (sin turno: {len(sin_turno)})")
        return
    diagnosticar(args.ids.split(",") if args.ids else None)


if __name__ == "__main__":
    main()
