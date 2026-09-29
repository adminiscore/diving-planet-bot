"""rag-2 (Plan Coral, fase RAG), paso 1: inventario de la base de conocimiento ANTES de curarla.

Qué saca (a `docs/robustness/rag-2/inventario.json`):
- Marcas por documento de la base de hoy (lo que genera `scripts/load_embeddings.load_knowledge_base`): teléfono,
  tono de "escríbenos/te paso con un asesor", precios metidos en el texto, instrucciones para el bot.
- Por servicio: lo que dicen `services.json`, su FAQ de "¿cómo es el plan X?" y el catálogo del prompt → gpt-4.1
  lista contradicciones y datos que SOLO están en la FAQ (para no perderlos al quitarla).
- Por tema (moneda, descuentos, recogida, horarios…): todas las fuentes que lo tocan, incluido el prompt de
  sistema → contradicciones entre fuentes.
- Paridad ES/EN de FAQs y políticas: datos que están en un idioma y no en el otro, o distintos.

No toca la base ni PRE. Coste ~1 $ (gpt-4.1). Necesita OPENAI_API_KEY (ENV_FILE=.env.dev).

    ENV_FILE=.env.dev python -m scripts.kb_inventario
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from scripts.load_embeddings import DATA_DIR, load_knowledge_base
from src.config import settings

OUT = Path(__file__).resolve().parent.parent / "docs/robustness/rag-2/inventario.json"
MODEL = "gpt-4.1"

TELEFONO = re.compile(r"\+?57\s?3\d{2}|whats\s?app|\b320\s?231", re.I)
TONO = re.compile(r"escr[ií]b[ea]nos|te paso|cont[aá]ct(a|e)nos|con un asesor|write to us|contact us|message us|an advisor", re.I)
PRECIO = re.compile(r"U?\$\s?\d[\d.,]*|\d[\d.,]{2,}\s?(COP|USD)\b", re.I)
PARA_EL_BOT = re.compile(r"\bel bot\b|\bthe bot\b|debe responder|should respond", re.I)

# FAQ -> servicio que describe (las 25 FAQs "¿cómo es el plan X desde Cartagena / si ya estoy en las islas?").
FAQ_SERVICIO = {
    31: "2_dives_1_day", 32: "2_dives_1_day_already_on_island", 33: "minicourse_already_on_island",
    34: "snorkeling_already_on_island", 35: "3_dives_1_day_already_on_island", 36: "5_dives_2_days_already_on_island",
    37: "7_dives_3_days_already_on_island", 38: "open_water_already_on_island", 39: "advanced_already_on_island",
    40: "fish_identification_specialty_already_on_island", 41: "nitrox_specialty_already_on_island",
    42: "naturalist_specialty_already_on_island", 43: "buoyancy_specialty_already_on_island", 44: "referral",
    45: "mindful_diving", 46: "naturalist_specialty", 47: "fish_identification_specialty", 48: "buoyancy_specialty",
    49: "nitrox_specialty", 50: "open_water", 51: "advanced", 52: "rescue", 53: "5_dives_2_days",
    54: "7_dives_3_days", 55: "9_dives_4_days",
}

TEMAS = {
    "moneda": r"colombian|residen|moneda|currency|c[eé]dula|pesos|d[oó]lares|\bCOP\b",
    "descuentos": r"descuento|discount|c[oó]digo|\bcode\b|grupo de 5|5 personas|equipo propio|segundo d[ií]a",
    "recogida_hoteles": r"recog|pick-?up|acceso mar|muelle propio|hotel",
    "horarios_punto_encuentro": r"punto de encuentro|bodeguita|8:00|regreso|llegada|horario|4:15|4:00 p|3:00 p",
    "refresh": r"refresh|inactiv|2 a[nñ]os|mucho tiempo sin",
    "pago_reserva": r"\bpag|transferencia|tarjeta|anticipo|4:30|reserva|link",
    "formularios": r"formulario|exoneraci|seguro|carn[eé]|carnet",
    "contacto_asesor": r"whats\s?app|\+57|asesor|escr[ií]b|tel[eé]fono|equipo te",
    "clima_cancelacion": r"clima|capitan|reembolso|cancel|reprogram",
    "alojamiento_pernocta": r"alojamiento|pernoct|dormir|noche|hosped",
    "comida": r"almuerzo|comida|vegetar|men[uú]",
    "edad_ninos": r"edad|ni[nñ]os|menores|bubble|a[nñ]os\b",
    "fotos": r"foto|video|propina",
}

_SISTEMA_SERVICIO = (
    "Auditas la base de conocimiento de un centro de buceo (Diving Planet, Cartagena). Te doy TODAS las fuentes "
    "que describen UN servicio. Devuelve SOLO JSON: {\"contradicciones\": [{\"dato\": str, \"fuente_a\": str, "
    "\"dice_a\": str, \"fuente_b\": str, \"dice_b\": str}], \"solo_en_faq\": [str]}. 'contradicciones' = el mismo "
    "dato con valores incompatibles entre fuentes (precio, hora, qué incluye, pernocta, duración, requisitos); no "
    "cuentes diferencias de redondeo de céntimos ni de formato. 'solo_en_faq' = datos concretos del negocio que "
    "están en la FAQ y NO en services.json (para no perderlos si se quita la FAQ). Español.")

_SISTEMA_TEMA = (
    "Auditas la base de conocimiento de un centro de buceo (Diving Planet, Cartagena) y las reglas del prompt del "
    "bot. Te doy todas las fuentes que tocan UN tema. Devuelve SOLO JSON: {\"contradicciones\": [{\"dato\": str, "
    "\"fuente_a\": str, \"dice_a\": str, \"fuente_b\": str, \"dice_b\": str, \"gravedad\": \"alta|media|baja\"}], "
    "\"vagas\": [{\"fuente\": str, \"dice\": str, \"precisa\": str}]}. 'contradicciones' = afirmaciones "
    "incompatibles entre fuentes. 'vagas' = una fuente dice una versión imprecisa de una regla que otra fuente "
    "da precisa (p. ej. 'residentes' frente a 'extranjeros con cédula de extranjería'). No inventes: cita. Español.")

_SISTEMA_PARIDAD = (
    "Comparas pares de textos ES/EN de la base de conocimiento de un centro de buceo. Devuelve SOLO JSON: "
    "{\"diferencias\": [{\"id\": str, \"que\": str}]} con cada par donde un DATO del negocio (precio, hora, "
    "requisito, qué incluye, regla) está en un idioma y falta o es distinto en el otro. Ignora estilo y "
    "traducción libre. Español.")


def _llm(cliente: OpenAI, sistema: str, usuario: str) -> dict:
    r = cliente.chat.completions.create(model=MODEL, temperature=0, response_format={"type": "json_object"},
                                        messages=[{"role": "system", "content": sistema},
                                                  {"role": "user", "content": usuario}])
    try:
        return json.loads(r.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {"error": r.choices[0].message.content}


def marcas(doc: dict) -> list[str]:
    t = doc["content"]
    out = []
    if TELEFONO.search(t):
        out.append("telefono")
    if TONO.search(t):
        out.append("tono_asesor")
    if PRECIO.search(t):
        out.append("precio_en_texto")
    if PARA_EL_BOT.search(t):
        out.append("instruccion_para_el_bot")
    return out


def _doc_id(doc: dict) -> str:
    m = doc["metadata"]
    return f"{m['source']}:{m.get('key') or m.get('index', '')}{':' + m['section'] if m.get('section') else ''}:{m['lang']}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from src.agents.rag_agent import build_system_prompt
    from src.flows.catalog import catalog_booking_links, catalog_facts

    docs = load_knowledge_base()
    faqs = json.loads((DATA_DIR / "faqs.json").read_text(encoding="utf-8-sig"))["faqs"]
    policies = json.loads((DATA_DIR / "policies.json").read_text(encoding="utf-8-sig"))["policies"]
    services = json.loads((DATA_DIR / "services.json").read_text(encoding="utf-8-sig"))["services"]
    discounts = json.loads((DATA_DIR / "discounts.json").read_text(encoding="utf-8-sig"))
    catalogo = catalog_facts("es") + "\n" + catalog_booking_links("es")
    prompt = build_system_prompt("es", query="precio")

    por_doc = [{"id": _doc_id(d), "chars": len(d["content"]), "marcas": marcas(d)} for d in docs]
    resumen_marcas = {}
    for d in por_doc:
        for m in d["marcas"]:
            resumen_marcas[m] = resumen_marcas.get(m, 0) + 1

    cliente = OpenAI(api_key=settings.openai_api_key)
    trabajos = {}

    for sid, svc in services.items():
        faq_idx = [i for i, s in FAQ_SERVICIO.items() if s == sid]
        linea = [ln for ln in catalogo.splitlines() if svc.get("name_es", "@@") in ln]
        usuario = (f"SERVICIO {sid}\n\n[services.json]\n{json.dumps(svc, ensure_ascii=False, indent=0)}\n\n"
                   + "".join(f"[FAQ {i}] {faqs[i]['question_es']}\n{faqs[i]['answer_es']}\n\n" for i in faq_idx)
                   + f"[catálogo del prompt]\n{chr(10).join(linea) or '(no aparece)'}")
        trabajos[("servicio", sid)] = (_SISTEMA_SERVICIO, usuario)

    fuentes_tema = (
        [(f"FAQ {i}", f"{f['question_es']}\n{f['answer_es']}") for i, f in enumerate(faqs) if i not in FAQ_SERVICIO]
        + [(f"política {k}", v.get("es", "")) for k, v in policies.items()]
        + [(f"descuento {k}", v.get("description_es", "")) for k, v in discounts.get("discounts", {}).items()]
        + [("catálogo del prompt", catalogo), ("prompt de sistema del RAG", prompt)]
        + [(f"services.json {k} requisitos", "\n".join(v.get("requirements_es") or [])) for k, v in services.items()]
    )
    for tema, patron in TEMAS.items():
        rx = re.compile(patron, re.I)
        trozos = [(n, t) for n, t in fuentes_tema if rx.search(t)]
        usuario = f"TEMA: {tema}\n\n" + "\n\n".join(f"[{n}]\n{t}" for n, t in trozos)
        trabajos[("tema", tema)] = (_SISTEMA_TEMA, usuario)

    pares = [(f"FAQ {i}", f"{f['question_es']}\n{f['answer_es']}", f"{f.get('question_en', '')}\n{f.get('answer_en', '')}")
             for i, f in enumerate(faqs) if i not in FAQ_SERVICIO]
    pares += [(f"política {k}", v.get("es", ""), v.get("en", "")) for k, v in policies.items()]
    for n in range(0, len(pares), 15):
        lote = pares[n:n + 15]
        usuario = "\n\n".join(f"[{i}]\nES: {es}\nEN: {en}" for i, es, en in lote)
        trabajos[("paridad", str(n // 15))] = (_SISTEMA_PARIDAD, usuario)

    print(f"{len(docs)} documentos · {len(trabajos)} consultas a {MODEL}…", flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futuros = {k: ex.submit(_llm, cliente, s, u) for k, (s, u) in trabajos.items()}
        res = {k: f.result() for k, f in futuros.items()}

    out = {
        "documentos": len(docs), "por_fuente": {}, "marcas": resumen_marcas, "por_doc": por_doc,
        "faq_servicio": {str(k): v for k, v in FAQ_SERVICIO.items()},
        "servicios": {k[1]: v for k, v in res.items() if k[0] == "servicio"},
        "temas": {k[1]: v for k, v in res.items() if k[0] == "tema"},
        "paridad": [d for k, v in res.items() if k[0] == "paridad" for d in v.get("diferencias", [])],
    }
    for d in docs:
        s = d["metadata"]["source"]
        out["por_fuente"][s] = out["por_fuente"].get(s, 0) + 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    n_serv = sum(len(v.get("contradicciones", [])) for v in out["servicios"].values())
    n_faq = sum(len(v.get("solo_en_faq", [])) for v in out["servicios"].values())
    n_tema = sum(len(v.get("contradicciones", [])) for v in out["temas"].values())
    n_vaga = sum(len(v.get("vagas", [])) for v in out["temas"].values())
    print(f"por fuente {out['por_fuente']} · marcas {resumen_marcas}")
    print(f"servicios: {n_serv} contradicciones, {n_faq} datos solo en FAQ · temas: {n_tema} contradicciones, "
          f"{n_vaga} reglas vagas · paridad ES/EN: {len(out['paridad'])} diferencias → {OUT}")


if __name__ == "__main__":
    main()
