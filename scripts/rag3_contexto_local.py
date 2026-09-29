"""rag-3, escalon 0 LOCAL y GRATIS: ¿llega el dato al contexto por el estado?

`scripts/rag_piezas.py` es el instrumento bueno, pero corre dentro del contenedor de PRE por SSH y
gasta credito de la cuenta que tambien sirve a PRE. Para el cambio de rag-3 no hace falta: lo que
cambia es lo que `_build_extra_context` mete en el prompt, y eso se construye ENTERO en local, sin
base vectorial y sin una sola llamada al LLM.

Lo que mide, por caso del set visible (`docs/robustness/rag-piezas/preguntas.json`): con el estado
de ese caso, ¿aparece cada dato que la respuesta necesita en el contexto que arma el estado? Usa
las mismas anclas y la misma normalizacion que `rag_piezas`, para que los numeros se puedan leer
juntos.

Lo que NO mide: la busqueda (top-8), la redaccion y el juez. Un dato que no salga aqui puede
llegar igualmente por la busqueda. Por eso esto NO sustituye a `rag_piezas`: responde una sola
pregunta, la del cambio -- si el dato que faltaba por busqueda ahora entra por el estado.

    python -m scripts.rag3_contexto_local
    python -m scripts.rag3_contexto_local --casos ow-horario-dia1,referido-datos-centro
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scripts.rag_piezas import PREGUNTAS, norm, presente  # noqa: E402
from src.agents import supervisor  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402


def contexto_de(caso: dict) -> str:
    st = ConversationState(conversation_id="rag3-local", language=caso["lang"])
    st.history = list(caso.get("historial") or [])
    for k, v in (caso.get("estado") or {}).items():
        setattr(st, k, v)
    return supervisor._build_extra_context(st) or ""


def mide(casos: list[dict], flag: bool) -> dict:
    settings.rag_ficha_del_servicio = flag
    total = con = 0
    detalle = []
    for c in casos:
        ctx_n = norm(contexto_de(c))
        for h in c["necesita"]:
            if h.get("calculo"):
                continue  # un calculo no "esta" en el contexto: lo hace el modelo
            total += 1
            ok = presente(h, ctx_n)
            con += bool(ok)
            detalle.append((c["id"], h["id"], bool(ok)))
    return {"total": total, "en_contexto": con, "detalle": detalle}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--casos", help="ids separados por coma")
    a = ap.parse_args()
    casos = json.loads(Path(PREGUNTAS).read_text(encoding="utf-8"))["casos"]
    if a.casos:
        ids = {x.strip() for x in a.casos.split(",")}
        casos = [c for c in casos if c["id"] in ids]

    off = mide(casos, False)
    on = mide(casos, True)
    settings.rag_ficha_del_servicio = False

    print(f"casos {len(casos)} · datos comprobables {off['total']}")
    print(f"  flag APAGADO   en contexto por el estado: {off['en_contexto']:>3} "
          f"({off['en_contexto'] / off['total']:.0%})")
    print(f"  flag ENCENDIDO en contexto por el estado: {on['en_contexto']:>3} "
          f"({on['en_contexto'] / on['total']:.0%})")

    antes = {(c, h): v for c, h, v in off["detalle"]}
    gana = [(c, h) for c, h, v in on["detalle"] if v and not antes[(c, h)]]
    pierde = [(c, h) for c, h, v in on["detalle"] if not v and antes[(c, h)]]
    print(f"\n  GANA {len(gana)} datos · PIERDE {len(pierde)}")
    for c, h in gana:
        print(f"    + {c} · {h}")
    for c, h in pierde:
        print(f"    - {c} · {h}   <-- REGRESION")


if __name__ == "__main__":
    main()
