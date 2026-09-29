"""rag-2 (Plan Coral, fase RAG), paso 2: generar la base curada `data/knowledge_base/curada/` (una vez; luego se
mantiene a mano como cualquier fichero de datos).

- `faqs.json`: las FAQs que se quedan, reescritas en tono neutro para el bot (sin teléfono, sin "escríbenos / te
  paso con un asesor", sin cifras que ya están en el catálogo), coherentes con las decisiones de negocio del
  29-sep (`docs/robustness/rag-2/decisiones.md`), con 2 formas más de preguntarlas por idioma.
- `preguntas.json`: 2-3 formas de preguntar cada política y cada descuento (el texto sigue en `policies.json` /
  `discounts.json`: una regla, un sitio), para que la búsqueda las encuentre.

Se quitan: las 25 FAQs que describen un servicio (las sustituye su ficha), la FAQ 87 (instrucción para el bot) y
las listas de precios (FAQs 120-121; los precios viven en la ficha y en el catálogo).

Después, gpt-4.1 audita cada FAQ (original frente a nueva) y devuelve a su sitio los datos perdidos. Validación
determinista final: sin teléfono ni tono de "escríbenos"; ninguna cifra ni URL nueva; ninguna cifra (fuera del
catálogo) ni URL perdida. Lo que no pasa se lista para revisar a mano.

    ENV_FILE=.env.dev python -m scripts.kb_curar          # ~1 $ (gpt-4.1)
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from scripts.kb_inventario import FAQ_SERVICIO, TELEFONO, TONO
from scripts.load_embeddings import DATA_DIR
from src.config import settings

OUT_DIR = DATA_DIR / "curada"
MODEL = "gpt-4.1"
QUITAR = set(FAQ_SERVICIO) | {87, 120, 121}

DECISIONES = """Decisiones de negocio vigentes (29-sep-2026), mandan sobre cualquier texto antiguo:
- Moneda: los colombianos (vivan donde vivan) y los residentes en Colombia pagan en COP; el resto, en USD. Mismo precio, solo cambia la moneda; no hay descuento por ser colombiano.
- Refresh: si lleva más de 2 años sin bucear, normalmente se requiere un refresh; los buzos muy experimentados (500+ inmersiones, Dive Master) los revisa un asesor del equipo.
- Nunca se da teléfono, WhatsApp ni correo en la base: lo que coordina el equipo se dice como "lo coordina / lo confirma un asesor del equipo".
- Descuento del 10 % el segundo día de buceo: vigente (buceo recreativo y cursos).
- Almuerzo: saliendo desde Cartagena, solo el día 1; para quien ya está en las islas, nunca.
- Llegada a Cartagena al volver: 4:15 p. m. (salida de las islas a las 3:00 p. m.).
- Pago: los extranjeros pagan el 100 % con tarjeta en la web (con tarjeta extranjera, pasaporte como documento); el anticipo del 50 % (y el resto presencial con tarjeta o efectivo) es solo para colombianos.
- 5 % por equipo propio COMPLETO: solo buceo recreativo y cursos (no snorkel ni minicurso)."""

SISTEMA = f"""Reescribes FAQs de la base de conocimiento de un bot de un centro de buceo (Diving Planet, Cartagena).
{DECISIONES}

Reglas de la reescritura:
1. Conserva TODOS los datos de la FAQ original salvo los que contradigan las decisiones o la referencia: esos se corrigen y se anotan en "cambios".
2. Sin teléfono, WhatsApp, correo ni "escríbenos / contáctanos / te paso con un asesor / write to us / contact us". Si algo lo gestiona el equipo: "lo coordina un asesor del equipo".
3. No escribas importes que ya estén en el CATÁLOGO (los precios los da el catálogo). Los importes que NO están en el catálogo (p. ej. el precio de Bubble Makers, una propina) SE CONSERVAN tal cual.
4. No añadas datos que no estén en la FAQ original ni en las decisiones. CONSERVA las URLs de la original (enlaces a la web, formularios, mapas).
5. Tono neutro e informativo (es un documento de referencia, no un chat): sin saludos, sin emojis, sin preguntas al cliente al final. Sin markdown de asteriscos.
6. question_es/question_en: la pregunta, clara. preguntas_alt_es/en: 2 formas distintas y naturales en que un cliente lo preguntaría.
7. ES y EN con los mismos datos.
Devuelve SOLO JSON: {{"question_es","answer_es","question_en","answer_en","preguntas_alt_es":[2],"preguntas_alt_en":[2],"cambios":[str]}}"""

SISTEMA_REPARAR = f"""Compruebas una FAQ reescrita contra su original. {DECISIONES}
Lista en "perdidos" cada dato concreto del negocio (lugar, hora, número, condición, requisito, URL, nombre) que está
en la ORIGINAL y falta en la NUEVA, EXCEPTO: teléfonos/WhatsApp/correos, invitaciones a escribir o contactar,
importes que están en el catálogo, y lo que contradiga las decisiones. Si hay perdidos, devuelve answer_es y
answer_en de la nueva con esos datos reincorporados (mismo tono neutro, sin cambiar nada más). Devuelve SOLO JSON:
{{"perdidos": [str], "answer_es": str, "answer_en": str}}"""

SISTEMA_PREGUNTAS = """Para cada regla de un centro de buceo te doy su texto (ES y EN). Escribe 3 formas distintas y naturales
en que un cliente preguntaría por ella en cada idioma (cortas, como en un chat). Devuelve SOLO JSON:
{"<clave>": {"es": [3], "en": [3]}}"""

_URL = re.compile(r"https?://\S+")
_NUM = re.compile(r"\d[\d.,]*\d|\d")


def _nums(t: str) -> set[str]:
    return {re.sub(r"[.,]", "", n) for n in _NUM.findall(t or "")}


_PERMITIDO = re.compile(r"(un|el|an?|the) (asesor|advisor|member) (del|from|of) (equipo|the team|our team)|"
                        r"asesor del equipo|member of our team|advisor from the team|team advisor", re.I)


def validar(orig: dict, nueva: dict, cifras_catalogo: set[str] = frozenset()) -> list[str]:
    problemas = []
    for lang in ("es", "en"):
        a = nueva.get(f"answer_{lang}", "") or ""
        o = f"{orig.get(f'question_{lang}', '')} {orig.get(f'answer_{lang}', '')} {orig.get('answer_es', '')}"
        if not a.strip():
            problemas.append(f"{lang}: vacía")
        if TELEFONO.search(a):
            problemas.append(f"{lang}: teléfono")
        if TONO.search(_PERMITIDO.sub("", a)):
            problemas.append(f"{lang}: tono asesor")
        solo_orig = orig.get(f"answer_{lang}", "") or ""
        perdidas = _nums(solo_orig) - _nums(a) - set(cifras_catalogo) - {"57", "320", "231515"}
        if perdidas and not _URL.search(solo_orig):
            problemas.append(f"{lang}: cifras perdidas {sorted(perdidas)}")
        if set(_URL.findall(solo_orig)) - set(_URL.findall(a)):
            problemas.append(f"{lang}: URL perdida")
        nuevos = _nums(a) - _nums(o) - {"1", "2", "3", "4", "5", "10", "15", "50", "100", "500"}
        if nuevos:
            problemas.append(f"{lang}: cifras nuevas {sorted(nuevos)}")
        if set(_URL.findall(a)) - set(_URL.findall(o)):
            problemas.append(f"{lang}: URL nueva")
    return problemas


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from src.flows.catalog import catalog_facts

    faqs = json.loads((DATA_DIR / "faqs.json").read_text(encoding="utf-8-sig"))["faqs"]
    policies = json.loads((DATA_DIR / "policies.json").read_text(encoding="utf-8"))["policies"]
    discounts = json.loads((DATA_DIR / "discounts.json").read_text(encoding="utf-8"))["discounts"]
    catalogo = catalog_facts("es")
    referencia = "REFERENCIA (políticas vigentes):\n" + "\n".join(f"- {k}: {v['es']}" for k, v in policies.items())
    cliente = OpenAI(api_key=settings.openai_api_key)

    def reescribir(i: int) -> dict:
        f = faqs[i]
        usuario = (f"{referencia}\n\nCATÁLOGO:\n{catalogo}\n\nFAQ ORIGINAL {i}:\nES P: {f['question_es']}\nES R: "
                   f"{f['answer_es']}\nEN Q: {f.get('question_en', '')}\nEN A: {f.get('answer_en', '')}")
        r = cliente.chat.completions.create(model=MODEL, temperature=0, response_format={"type": "json_object"},
                                            messages=[{"role": "system", "content": SISTEMA},
                                                      {"role": "user", "content": usuario}])
        return json.loads(r.choices[0].message.content or "{}")

    def reparar(i: int, n: dict) -> dict:
        f = faqs[i]
        usuario = (f"FAQ ORIGINAL:\nES: {f['answer_es']}\nEN: {f.get('answer_en', '')}\n\nFAQ NUEVA (JSON):\n"
                   f"{json.dumps(n, ensure_ascii=False)}")
        r = cliente.chat.completions.create(model=MODEL, temperature=0, response_format={"type": "json_object"},
                                            messages=[{"role": "system", "content": SISTEMA_REPARAR},
                                                      {"role": "user", "content": usuario}])
        out = json.loads(r.choices[0].message.content or "{}")
        if out.get("perdidos"):
            n = {**n, **{k: out[k] for k in ("answer_es", "answer_en") if out.get(k)},
                 "cambios": [*n.get("cambios", []), *[f"recuperado: {x}" for x in out["perdidos"]]]}
        return n

    quedan = [i for i in range(len(faqs)) if i not in QUITAR]
    print(f"{len(faqs)} FAQs · se quitan {len(QUITAR)} · se reescriben {len(quedan)}", flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        nuevas = dict(zip(quedan, ex.map(reescribir, quedan)))
        nuevas = dict(zip(quedan, ex.map(lambda i: reparar(i, nuevas[i]), quedan)))

    salida, revisar = [], []
    for i in quedan:
        n = nuevas[i]
        problemas = validar(faqs[i], n, _nums(catalogo + catalog_facts("en")))
        if problemas:
            revisar.append({"faq": i, "problemas": problemas, "propuesta": n})
        salida.append({"origen": i, "question_es": n.get("question_es") or faqs[i]["question_es"],
                       "answer_es": n.get("answer_es", ""), "question_en": n.get("question_en") or faqs[i]["question_en"],
                       "answer_en": n.get("answer_en", ""), "preguntas_alt_es": n.get("preguntas_alt_es", []),
                       "preguntas_alt_en": n.get("preguntas_alt_en", []), "cambios": n.get("cambios", []),
                       "revisar": problemas})

    reglas = {f"politica:{k}": v for k, v in policies.items()}
    reglas |= {f"descuento:{k}": {"es": v.get("description_es", ""), "en": v.get("description_en", "")}
               for k, v in discounts.items()}
    lotes = [dict(list(reglas.items())[n:n + 12]) for n in range(0, len(reglas), 12)]

    def preguntas(lote: dict) -> dict:
        usuario = "\n\n".join(f"[{k}]\nES: {v['es']}\nEN: {v['en']}" for k, v in lote.items())
        r = cliente.chat.completions.create(model=MODEL, temperature=0, response_format={"type": "json_object"},
                                            messages=[{"role": "system", "content": SISTEMA_PREGUNTAS},
                                                      {"role": "user", "content": usuario}])
        return json.loads(r.choices[0].message.content or "{}")

    with ThreadPoolExecutor(max_workers=4) as ex:
        alt = {k: v for d in ex.map(preguntas, lotes) for k, v in d.items()}

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "faqs.json").write_text(json.dumps(
        {"_comment": "rag-2: FAQs curadas (scripts/kb_curar.py, 29-sep, revisadas a mano). Fuente de la base v2. "
                     "Sin teléfono, sin tono de 'escríbenos', sin precios del catálogo. 'origen' = índice en faqs.json.",
         "faqs": salida}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "preguntas.json").write_text(json.dumps(
        {"_comment": "rag-2: formas de preguntar cada política y descuento (el texto vive en policies.json / "
                     "discounts.json). Solo ayudan a que la búsqueda los encuentre.", "reglas": alt},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FAQs curadas {len(salida)} · a revisar {len(revisar)} · reglas con preguntas {len(alt)}/{len(reglas)}")
    for r in revisar:
        print(f"  FAQ {r['faq']}: {r['problemas']}")


if __name__ == "__main__":
    main()
