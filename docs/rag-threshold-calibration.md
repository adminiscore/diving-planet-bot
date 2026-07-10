# Calibración de `RAG_MIN_SCORE` (2026-07-09)

## Por qué

Veníamos fijando el umbral a ojo (PRE corría `0.50`). Un coseno crudo **no está
calibrado**: con `text-embedding-3-small`, una pregunta corta contra un FAQ largo
puntúa ~0.45-0.55 aunque la coincidencia sea perfecta, así que un umbral absoluto
alto descarta respuestas correctas (fue la causa del bug "¿qué animales se ven?"
→ fallback tras el cierre de reserva).

Lo hicimos como se hace en serio: **set de evaluación etiquetado + barrido de
umbral**, no intuición.

## Método (reproducible)

`scripts/calibrate_rag_threshold.py` + `docs/rag-eval-set.json`.

- **Positivos (135)**: consultas realistas de cliente generadas sintéticamente
  desde 45 FAQs de la KB con un LLM (*synthetic query generation* — la técnica
  estándar cuando tienes documentos pero no logs de consultas), cada una
  etiquetada con el FAQ "gold" que la responde. ES + EN.
- **Negativos (16)**: preguntas plausibles que la KB **no** puede responder
  ("¿tienen sucursal en Medellín?", "who founded diving planet?", "¿capital de
  Francia?"). El bot DEBE derivar en estas.
- Se recupera **una vez** por consulta y se barre el umbral offline, midiendo la
  decisión binaria "¿esta consulta obtiene contexto fiable?".

Re-generar (`--generate`) cuando cambie la KB o el modelo de embeddings.

## Resultado del barrido (`rag_min_bm25_rank=0.05`)

| umbral | recall@gold | contexto en positivos | contexto en negativos |
|-------:|------------:|----------------------:|----------------------:|
| 0.300  | 91.9% | 100.0% | 75.0% |
| 0.350  | 90.4% |  99.3% | 75.0% |
| **0.400** | **88.1%** | **97.0%** | **62.5%** |
| 0.450  | 83.7% |  93.3% | 56.2% |
| 0.500  | 79.3% |  90.4% | 25.0% |
| 0.550  | 72.6% |  83.7% | 12.5% |
| 0.650  | 52.6% |  64.4% |  0.0% |

## Validación end-to-end (lo que de verdad decide)

`false-ctx(neg)` mide si entra contexto irrelevante, **no** si el bot responde
mal — para eso está el juez de grounding aguas abajo. Así que medimos la
respuesta real del bot sobre los 16 negativos:

- **0.50** → 0/16 responden de más (todos derivan).
- **0.40** → 3/16 "responden", pero **ninguno alucina**: "¿sucursal en Medellín?"
  → *"No, solo estamos en Cartagena"* (correcto); las otras 2 son desvíos amables
  que no inventan datos. El juez + la honestidad del modelo los cubren.

Y en precios, sin degradación: minicurso = $528.000 COP idéntico a 0.40 y 0.50.

## Decisión: `RAG_MIN_SCORE = 0.40`

Es el **codo de la curva de recall**: por encima de 0.45 el recall se desploma;
por debajo de 0.40 apenas se gana (+2-4 pp) a cambio de más contexto marginal.
Frente a 0.50, **0.40 recupera +8.8 pp de preguntas reales** (88.1% vs 79.3%) sin
introducir alucinaciones dañinas.

Razón de fondo: el umbral es solo un filtro **grueso**; detrás están BM25
híbrido, los guards deterministas (precios/URLs/capacidad) y el juez de grounding
(desde v0.20.8, activo **también** en el camino del agente). Con un verificador
fuerte detrás, lo correcto es un umbral **permisivo** que favorezca el recall y
dejar que el juez cace lo malo — un documento descartado no se recupera, pero uno
marginal aún tiene que sobrevivir al juez.

Coincide con el default del código (`src/config.py`) y con el valor con el que se
validó la batería de 176 casos. La calibración **confirma** 0.40 con evidencia, en
vez de dejarlo como corazonada.
