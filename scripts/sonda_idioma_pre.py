"""G-10 (14-oct): sonda del idioma contra PRE. El golden no tiene diálogos escritos ENTEROS en otro idioma, así que la
mini-ronda no mide la regla de Gadea ("otro idioma -> inglés"). Tres conversaciones cortas por Chatwoot (como
`run_synthetic_pre`) y el idioma de cada respuesta del bot, leído con el extractor de la fase EX.

    ENV_FILE=.env.dev python -m scripts.sonda_idioma_pre

Guarda `docs/robustness/idioma/sonda-pre-<fecha>.json`. Esperado: portugués y francés -> respuestas en inglés;
español con dos palabras en portugués -> español.
"""
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.run_synthetic_pre import Chatwoot, _env, run_turn

CASOS = [
    ("idioma-pt", "en", ["Olá! Quero fazer mergulho com minha esposa em junho, quanto custa?",
                         "Nunca mergulhamos antes"]),
    ("idioma-fr", "en", ["Bonjour, nous voudrions faire de la plongée près de Carthagène, c'est combien ?",
                         "Nous sommes deux, déjà certifiés"]),
    ("idioma-es-con-pt", "es", ["Busco el seguinte: vamos en família a Cartagena, 1 buzo avanzado y 2 para bautismo"]),
]


async def _idioma(texto: str) -> str | None:
    from src.agents.extractor_turno import extraer_turno  # lazy: necesita la clave de OpenAI

    datos = await extraer_turno(texto, lang="en")
    return (datos or {}).get("idioma")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cw = Chatwoot(_env("SYNTH_CHATWOOT_URL") or "https://chatwoot.is-core.dev", _env("SYNTH_CHATWOOT_TOKEN"),
                  int(_env("SYNTH_CHATWOOT_ACCOUNT") or 1), int(_env("SYNTH_CHATWOOT_INBOX") or 2))
    filas, bien = [], 0
    for tag, esperado, turnos in CASOS:
        conv = cw.new_conversation(tag)
        for i, texto in enumerate(turnos, 1):
            r = run_turn(cw, conv, texto)
            idioma = asyncio.run(_idioma(r["reply"])) if r["reply"] else None
            ok = idioma == esperado
            bien += ok
            filas.append({"tag": tag, "conv": conv, "turn": i, "msg": texto, "esperado": esperado, "idioma_respuesta": idioma,
                          "ok": ok, "reply": r["reply"]})
            print(f"{'OK ' if ok else 'MAL'} {tag} t{i}: respuesta en {idioma!r} (esperado {esperado!r})", flush=True)
    out = Path("docs/robustness/idioma") / f"sonda-pre-{datetime.now(UTC):%Y-%m-%d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"bien": bien, "total": len(filas), "filas": filas}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{bien}/{len(filas)} respuestas en el idioma esperado ({out})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
