"""mej-8 (24-oct): las conversaciones que quien prueba el bot marcó con «#mal» (etiqueta `mal` en Chatwoot,
`src/channels/marca_mal.py`), como casos del banco de fallos.

Cada «#mal» es un caso: la respuesta del bot justo antes, el mensaje del cliente que la pidió, la conversación hasta
ahí y lo que escribió quien prueba detrás de la marca (`pedia`: qué esperaba). Todo pasa por `redact_pii`. Los casos
que ya estaban en el fichero se quedan como están (si alguien corrigió `pedia` a mano, no se pisa).

    python -m scripts.exportar_mal                       # -> docs/robustness/mal/banco-mal.json
    python -m scripts.exportar_mal --desde 2026-10-24 --out otra/ruta.json
    python -m scripts.banco_fallos medir --banco docs/robustness/mal/banco-mal.json --etiqueta mal-A --reps 3

Lee Chatwoot con SYNTH_CHATWOOT_URL / SYNTH_CHATWOOT_TOKEN / SYNTH_CHATWOOT_ACCOUNT (entorno o ENV_FILE), como
`scripts/charla_pre.py`. Solo lee: no escribe nada en Chatwoot ni llama a ningún modelo (sin gasto)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.channels import marca_mal
from src.privacy import redact_pii

ROOT = Path(__file__).resolve().parent.parent
SALIDA = ROOT / "docs/robustness/mal/banco-mal.json"


def _lineas(mensajes: list[dict]) -> list[dict]:
    """Los mensajes de Chatwoot, en orden, como {role, content, at, marca}: fuera notas privadas, actividad y acuses;
    las burbujas seguidas del bot, juntas (una respuesta del bot puede salir en varios mensajes)."""
    out: list[dict] = []
    for m in sorted(mensajes, key=lambda m: int(m.get("id") or 0)):
        texto = (m.get("content") or "").strip()
        if m.get("private") or not texto or marca_mal.es_acuse(texto):
            continue
        tipo = m.get("message_type")
        if tipo in (0, "incoming"):
            out.append({"role": "user", "content": texto, "at": m.get("created_at"), "marca": marca_mal.es_marca(texto)})
        elif tipo in (1, "outgoing"):
            if out and out[-1]["role"] == "assistant":
                out[-1]["content"] += "\n\n" + texto
            else:
                out.append({"role": "assistant", "content": texto, "at": m.get("created_at"), "marca": False})
    return out


def casos_de_la_conversacion(conv: int | str, mensajes: list[dict]) -> list[dict]:
    """Un caso por cada «#mal» que va detrás de una respuesta del bot."""
    lineas = _lineas(mensajes)
    charla = [x for x in lineas if not x["marca"]]  # la conversación sin las marcas
    casos = []
    for i, x in enumerate(lineas):
        if not x["marca"]:
            continue
        antes = [y for y in lineas[:i] if not y["marca"]]
        if len(antes) < 2 or antes[-1]["role"] != "assistant" or antes[-2]["role"] != "user":
            continue  # una marca sin respuesta del bot delante no dice qué falló
        respuesta, cliente = antes[-1], antes[-2]
        historial = [{"role": y["role"], "content": redact_pii(y["content"])} for y in antes[:-2]]
        n = len(casos) + 1
        casos.append({
            "id": f"mal-{conv}-{n}",
            "tarea": "mal",
            "dialogo": f"chatwoot-{conv}",
            "criterio": "marcado con #mal",
            "pedia": redact_pii(marca_mal.comentario(x["content"])) or "(sin comentario: revisar qué falló)",
            "motivo_juez": "",
            "turno": sum(1 for y in antes if y["role"] == "user"),
            "mensaje_cliente": redact_pii(cliente["content"]),
            "respuesta_mala": redact_pii(respuesta["content"]),
            "historial": historial,
            "marcado_en": datetime.fromtimestamp(int(x["at"]), UTC).isoformat() if x.get("at") else None,
            "turnos_dialogo": sum(1 for y in charla if y["role"] == "user"),
        })
    return casos


def juntar(viejos: list[dict], nuevos: list[dict]) -> list[dict]:
    """Los que ya estaban se quedan como están (pueden tener `pedia` corregido a mano); se añaden los nuevos."""
    vistos = {f["id"] for f in viejos}
    return viejos + [f for f in nuevos if f["id"] not in vistos]


def _cliente():
    from scripts.run_synthetic_pre import Chatwoot, _env  # lazy: solo para leer Chatwoot

    token = _env("SYNTH_CHATWOOT_TOKEN")
    if not token:
        sys.exit("Falta SYNTH_CHATWOOT_TOKEN (entorno o ENV_FILE).")
    return Chatwoot(_env("SYNTH_CHATWOOT_URL") or "https://chatwoot.is-core.dev", token,
                    int(_env("SYNTH_CHATWOOT_ACCOUNT") or 1), int(_env("SYNTH_CHATWOOT_INBOX") or 2))


def _conversaciones_marcadas(cw) -> list[dict]:
    out, pagina = [], 1
    while True:
        datos = cw._req("GET", f"/conversations?status=all&labels%5B%5D={marca_mal.ETIQUETA}&page={pagina}")
        lote = (datos.get("data") or {}).get("payload") or []
        if not lote:
            return out
        out += lote
        pagina += 1


def _mensajes(cw, conv: int) -> list[dict]:
    """Todos los mensajes (Chatwoot los da de 20 en 20, de los más nuevos hacia atrás)."""
    todos, antes = [], None
    while True:
        lote = cw._req("GET", f"/conversations/{conv}/messages" + (f"?before={antes}" if antes else ""))["payload"]
        if not lote:
            return todos
        todos += lote
        antes = min(int(m["id"]) for m in lote)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--desde", help="solo las marcas desde esta fecha (AAAA-MM-DD)")
    ap.add_argument("--out", type=Path, default=SALIDA)
    args = ap.parse_args()
    cw = _cliente()
    nuevos = []
    for c in _conversaciones_marcadas(cw):
        casos = casos_de_la_conversacion(c["id"], _mensajes(cw, int(c["id"])))
        if args.desde:
            casos = [f for f in casos if (f["marcado_en"] or "") >= args.desde]
        nuevos += casos
        print(f"  conversación {c['id']}: {len(casos)} caso(s)")
    viejos = json.loads(args.out.read_text(encoding="utf-8"))["fallos"] if args.out.exists() else []
    fallos = juntar(viejos, nuevos)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"about": __doc__.split("\n\n")[0], "fallos": fallos}, ensure_ascii=False,
                                   indent=1) + "\n", encoding="utf-8")
    print(f"{len(fallos) - len(viejos)} casos nuevos, {len(fallos)} en total -> {args.out}")


if __name__ == "__main__":
    main()
