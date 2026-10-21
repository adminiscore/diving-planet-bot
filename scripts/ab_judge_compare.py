"""A/B del juez: compara criterio a criterio dos resultados de `judge_golden_set`.

    python -m scripts.ab_judge_compare 2026-09-24-u34-A 2026-09-24-u34-B
    ENV_FILE=.env.dev python -m scripts.ab_judge_compare A B --rejuzgar 2 [--tambien-mejoras]

Imprime el resumen de cada ronda, las MEJORAS y las REGRESIONES con el motivo del juez.
Regla del protocolo: leer el TEXTO del bot de cada regresión antes de concluir (el juez
tiene ruido: a veces marca en B lo que en A era idéntico).

G-9 (14-oct, ronda atencion-B2: de 9 "regresiones", 2 eran la conversación guionada que no llega al punto que mira el
criterio y 2 el mismo texto del bot juzgado distinto en A y en B). El comparador separa el ruido sin tocar el juez:
- `cumple <-> no_aplica` no es mejora ni regresión: va a NO COMPARABLES.
- Si la cita del bot con la que B suspende también está en la conversación de A (donde cumplía), o la de A en B, se
  marca SOSPECHA DE RUIDO (el mismo texto, juzgado distinto).
- `--rejuzgar N`: cada criterio que cambia se juzga N veces más en A y en B, sin caché, y cuenta la MAYORÍA (con el
  veredicto original). Si la mayoría coincide en A y B, es RUIDO DEL JUEZ. Solo las regresiones, salvo
  `--tambien-mejoras` (céntimos: ~0,004 $ por juicio con gpt-5-mini).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from scripts import judge_golden_set as juez

R = "docs/robustness/golden-set/results/{}__gpt-5-mini-medium.json"


def _veredicto_mayoritario(veredictos: list[str]) -> str:
    """La mayoría de los veredictos; `revisar` cuenta como suspenso (no se da por bueno). Empate: el original."""
    normal = ["no_cumple" if v == "revisar" else v for v in veredictos]
    (top, n), *resto = Counter(normal).most_common()
    return normal[0] if resto and resto[0][1] == n else top


def _conversaciones(resultado: dict) -> dict[str, list[dict]]:
    return juez.latest_conversations(resultado["run_file"])


def _texto_del_bot(records: list[dict]) -> str:
    return "\n".join(b for r in records for b in juez.bot_bubbles(r))


def _misma_cita_en_la_otra(c_mal: dict, records_otra: list[dict] | None) -> bool:
    """La cita del bot con la que suspende está también en la conversación donde ese criterio cumplía."""
    cita = c_mal.get("evidencia_bot")
    return bool(cita and records_otra and juez.quote_found(cita, _texto_del_bot(records_otra)))


def _rejuzgar(resultado: dict, golden: dict, conversaciones: dict, dialogo: str, criterio: str, n: int, client) -> list[str]:
    """N veredictos nuevos del mismo criterio sobre la misma conversación (sin caché), como lo juzga `judge_golden_set`."""
    definicion = next(d for d in golden["dialogues"] if d["id"] == dialogo)
    records = conversaciones.get(dialogo)
    todos = juez.criteria_for(definicion, golden["global_criteria"])
    crit = next((c for c in todos if c["id"] == criterio), None)
    if crit is None or crit.get("auto") or not records:
        return []  # los automáticos son deterministas: no hay ruido que medir
    referencia = juez.load_reference(resultado.get("referencia", juez.REFERENCIA_POR_DEFECTO))
    previos = {c["id"]: c for d in resultado["dialogues"] if d["id"] == dialogo for c in d["criteria"]}
    contados = juez.counted_failures(todos, previos) if juez.is_general(crit) else None
    salida = []
    for _ in range(n):
        r = juez.evaluate_criterion(client, resultado["model"], resultado["effort"], referencia, definicion, records, crit,
                                 todos, contados)
        if contados is not None:
            r = juez.discount_counted(r, contados, records)
        salida.append(r["verdict"])
    return salida


def comparar(res_a: dict, res_b: dict) -> dict:
    """Clasifica cada criterio que cambia entre A y B (sin llamar a ningún juez)."""
    va = {(d["id"], c["id"]): c for d in res_a["dialogues"] for c in d["criteria"]}
    vb = {(d["id"], c["id"]): c for d in res_b["dialogues"] for c in d["criteria"]}
    out = {"mejoras": [], "regresiones": [], "no_comparables": []}
    for k in sorted(set(va) & set(vb)):
        a, b = va[k]["verdict"], vb[k]["verdict"]
        if a == b:
            continue
        if {a, b} == {"cumple", "no_aplica"}:
            out["no_comparables"].append((k, a, b, vb[k]))
        elif a != "cumple" and b == "cumple":
            out["mejoras"].append((k, a, b, va[k]))
        elif a == "cumple" and b != "cumple":
            out["regresiones"].append((k, a, b, vb[k]))
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--rejuzgar", type=int, default=0, help="juicios nuevos por criterio que cambia (0 = sin API)")
    p.add_argument("--tambien-mejoras", action="store_true", help="re-juzgar también las mejoras, no solo regresiones")
    p.add_argument("--golden", help="otro fichero de diálogos (los exámenes de control G9/G10), como en judge_golden_set")
    args = p.parse_args(argv)
    res_a, res_b = (json.load(open(R.format(n), encoding="utf-8")) for n in (args.a, args.b))
    # 6-oct: el juez tiene dos referencias del negocio (judge_golden_set.REFERENCIAS); los resultados de antes no la
    # apuntan y son de la antigua. Con referencias distintas la comparacion mide el juez, no el bot.
    ref_a, ref_b = res_a.get("referencia", "antigua"), res_b.get("referencia", "antigua")
    if ref_a != ref_b:
        print(f"!! OJO: A se juzgo con la referencia '{ref_a}' y B con '{ref_b}'. Re-juzgad una con la otra "
              "(judge_golden_set --referencia) antes de sacar conclusiones.\n")
    for n, d in (("A", res_a), ("B", res_b)):
        s = d["summary"]
        print(f"{n}: dialogos {s['dialogues_passed']}/{s['dialogues']} ({s['dialogues_pass_pct']}%) | criterios "
              f"{s['criteria_judged'] - s['criteria_failed']}/{s['criteria_judged']} ({s['criteria_pass_pct']}%) | "
              f"revisar {s['to_review']} | coste {d['cost_usd']} | cache {d['cache']}")
    cambios = comparar(res_a, res_b)
    conv_a, conv_b = _conversaciones(res_a), _conversaciones(res_b)
    client, golden = None, None
    if args.rejuzgar:
        from openai import OpenAI  # lazy: sin --rejuzgar no hace falta clave

        client = OpenAI(api_key=juez._env("OPENAI_API_KEY"))
        golden = json.loads((Path(args.golden) if args.golden else juez.GOLDEN_FILE).read_text(encoding="utf-8"))

    def clasificar(k, a, b, c_mal, records_otra, rejuzgar: bool) -> tuple[str, str]:
        nota = " [misma cita en la otra ronda]" if _misma_cita_en_la_otra(c_mal, records_otra) else ""
        if not (rejuzgar and client):
            return ("sospecha" if nota else "real"), nota
        ra = [a] + _rejuzgar(res_a, golden, conv_a, k[0], k[1], args.rejuzgar, client)
        rb = [b] + _rejuzgar(res_b, golden, conv_b, k[0], k[1], args.rejuzgar, client)
        ma, mb = _veredicto_mayoritario(ra), _veredicto_mayoritario(rb)
        nota += f" [A {'/'.join(ra)} -> {ma} · B {'/'.join(rb)} -> {mb}]"
        return ("ruido" if ma == mb else "real"), nota

    for nombre, signo, otra in (("MEJORAS", "+", conv_b), ("REGRESIONES", "-", conv_a)):
        clave = "mejoras" if signo == "+" else "regresiones"
        rejuzgar = bool(args.rejuzgar) and (clave == "regresiones" or args.tambien_mejoras)
        filas = []
        for k, a, b, c in cambios[clave]:
            # La cita que se busca es la del veredicto que SUSPENDE (el de B en una regresión, el de A en una mejora), en
            # la conversación de la otra ronda, donde ese criterio cumplía.
            tipo, nota = clasificar(k, a, b, c, otra.get(k[0]), rejuzgar)
            filas.append((tipo, k, a, b, c, nota))
        reales = [f for f in filas if f[0] == "real"]
        dudosas = [f for f in filas if f[0] != "real"]
        print(f"\n{nombre} ({len(filas)}: {len(reales)} reales, {len(dudosas)} ruido o sospecha)")
        for tipo, k, a, b, c, nota in reales + dudosas:
            marca = signo if tipo == "real" else "~"
            etiqueta = {"real": "", "ruido": " RUIDO DEL JUEZ", "sospecha": " SOSPECHA DE RUIDO"}[tipo]
            motivo = f" | {c.get('reason', '')[:240]}" if signo == "-" else ""
            print(f"  {marca} {k[0]} / {k[1]}: {a} -> {b}{etiqueta}{nota}{motivo}")
    print(f"\nNO COMPARABLES ({len(cambios['no_comparables'])}): cumple <-> no_aplica (la conversación no llega al punto)")
    for k, a, b, _c in cambios["no_comparables"]:
        print(f"  · {k[0]} / {k[1]}: {a} -> {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
