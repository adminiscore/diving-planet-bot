"""G2 (Fase G): mapa de cobertura del golden-set y seleccion del golden CORE.

Lee golden-dialogues.json (cada dialogo con su `cobertura`) y escribe coverage.json con:
- `intents`: por intencion, cuantos dialogos la cubren (reales / sinteticos / core) y con que
  frecuencia aparece en los chats REALES del cliente (la distribucion de referencia);
- `gaps`: intenciones frecuentes en lo real con pocos casos, o sin ninguno en el core;
- `core`: los ids del golden core y por que entra cada uno.

El core es para el dia a dia (antes/despues de un cambio): una ronda completa de la v7 son ~80 min y
~3.800 peticiones; el core ~1/4. La ronda completa se deja para los hitos (cierre de fase).

    python docs/robustness/golden-set/coverage.py
"""

import collections
import json
from pathlib import Path

HERE = Path(__file__).parent
GOLDEN = HERE / "golden-dialogues.json"
OUT = HERE / "coverage.json"

TURN_BUDGET = 130  # turnos del core (~25 min en serie contra PRE)
MIN_EN_SHARE = 0.25  # en los chats reales ~30 % es ingles
PER_INTENT = 2  # cada intencion que exista en el golden, al menos 2 veces en el core (si hay)

# Fijos: la muestra rapida de latencia (m0-2), seguridad/adversarial, regresiones de fallos ya
# vistos y los casos mas dificiles de grupos. Un core que no los tenga no sirve de red de seguridad.
PINNED = {
    "saludo-cortesia": "muestra rapida (m0-2) + regresion del saludo doble",
    "reserva-solo-link": "muestra rapida (m0-2): reserva completa con link",
    "edad-minima-open-water": "muestra rapida (m0-2): RAG",
    "punto-encuentro": "muestra rapida (m0-2): RAG",
    "embarazo": "muestra rapida (m0-2): escalado medico",
    "cancelacion-indirecta": "muestra rapida (m0-2): cambios",
    "es-un-bot": "muestra rapida (m0-2): deflection",
    "inyeccion-system-prompt": "seguridad: inyeccion",
    "inyeccion-json-admin": "seguridad: inyeccion (en ingles)",
    "queja": "escalado: queja",
    "link-roto-carrito": "escalado con carrito abierto",
    "reserva-ingles": "reserva completa en ingles",
    "grupo-3-actividades": "grupo mixto de 3 actividades (lo mas dificil del flujo)",
    "manual-acompanante-mayor": "regresion S4-17..19 (tras el link)",
    "manual-duracion-curso": "regresion S4-17..19 (tras el link)",
    "equipaje-maleta-y-bolso-en-lancha": "fallo real visto el 22-sep (responde disponibilidad)",
}


def n_turns(d: dict, batch_turns: dict) -> int:
    return len(d.get("turns") or batch_turns[d["source"]["tag"]])


def is_real(d: dict) -> bool:
    return d.get("source", {}).get("kind") == "whatsapp"


def is_en(d: dict) -> bool:
    return d.get("cobertura", {}).get("idioma", "es").startswith("en")


def select_core(dialogues: list[dict], batch_turns: dict) -> dict[str, str]:
    by_id = {d["id"]: d for d in dialogues}
    core = {i: why for i, why in PINNED.items() if i in by_id}
    turns = sum(n_turns(by_id[i], batch_turns) for i in core)

    def count(intent: str) -> int:
        return sum(intent in by_id[i]["cobertura"]["intents"] for i in core)

    def en_share() -> float:
        return sum(is_en(by_id[i]) for i in core) / max(len(core), 1)

    pool = [d for d in dialogues if d["id"] not in core]
    while pool:
        need = {i for d in pool for i in d["cobertura"]["intents"] if count(i) < PER_INTENT}
        want_en = en_share() < MIN_EN_SHARE

        def score(d: dict) -> tuple:
            gain = len(set(d["cobertura"]["intents"]) & need)
            return (
                gain,
                want_en and is_en(d),
                is_real(d),  # a igualdad, lo real (es lo que pasa de verdad)
                -n_turns(d, batch_turns),
                d["id"],
            )

        best = max(pool, key=score)
        gain = set(best["cobertura"]["intents"]) & need
        if not gain and not (want_en and is_en(best)):
            break
        if turns + n_turns(best, batch_turns) > TURN_BUDGET:
            pool.remove(best)
            continue
        reason = "cubre " + ", ".join(sorted(gain)) if gain else "sube la proporcion de ingles"
        core[best["id"]] = reason
        turns += n_turns(best, batch_turns)
        pool.remove(best)
    return core


def main() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    batches = json.loads(
        Path("docs/robustness/synthetic-runs/batches.json").read_text(encoding="utf-8")
    )["batches"]
    batch_turns = {c["tag"]: c["turns"] for v in batches.values() for c in v["cases"]}
    dialogues = golden["dialogues"]
    missing = [d["id"] for d in dialogues if "cobertura" not in d]
    if missing:
        raise SystemExit(f"dialogos sin cobertura: {missing}")

    core = select_core(dialogues, batch_turns)
    real = [d for d in dialogues if is_real(d)]
    intents = sorted({i for d in dialogues for i in d["cobertura"]["intents"]})
    table = {}
    for intent in intents:
        with_it = [d for d in dialogues if intent in d["cobertura"]["intents"]]
        table[intent] = {
            "real_freq": round(
                sum(intent in d["cobertura"]["intents"] for d in real) / len(real), 3
            ),
            "golden": len(with_it),
            "golden_real": sum(is_real(d) for d in with_it),
            "golden_sintetico": sum(not is_real(d) for d in with_it),
            "core": sum(d["id"] in core for d in with_it),
        }
    gaps = [
        {"intent": i, "motivo": "frecuente en lo real (>=10 %) con menos de 5 casos"}
        for i, t in table.items()
        if t["real_freq"] >= 0.10 and t["golden"] < 5
    ] + [{"intent": i, "motivo": "no esta en el core"} for i, t in table.items() if t["core"] == 0]

    def dist(key: str, subset: list[dict]) -> dict:
        return dict(collections.Counter(d["cobertura"].get(key, "?") for d in subset).most_common())

    by_id = {d["id"]: d for d in dialogues}
    core_list = [by_id[i] for i in core]
    report = {
        "about": __doc__.split("\n\n")[0],
        "golden_version": golden["version"],
        "totales": {
            "golden": {
                "dialogos": len(dialogues),
                "turnos": sum(n_turns(d, batch_turns) for d in dialogues),
            },
            "core": {
                "dialogos": len(core),
                "turnos": sum(n_turns(d, batch_turns) for d in core_list),
            },
        },
        "idioma": {
            "golden": dist("idioma", dialogues),
            "core": dist("idioma", core_list),
            "real": dist("idioma", real),
        },
        "etapa": {"golden": dist("etapa", dialogues), "core": dist("etapa", core_list)},
        "perfil": {"golden": dist("perfil", dialogues), "core": dist("perfil", core_list)},
        "actividad": {"golden": dist("actividad", dialogues), "core": dist("actividad", core_list)},
        "intents": dict(sorted(table.items(), key=lambda kv: -kv[1]["real_freq"])),
        "gaps": gaps,
        "core": core,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    t = report["totales"]
    print(
        f"golden {t['golden']['dialogos']} dialogos / {t['golden']['turnos']} turnos; "
        f"core {t['core']['dialogos']} / {t['core']['turnos']} turnos; huecos: {len(gaps)} -> {OUT}"
    )


if __name__ == "__main__":
    main()
