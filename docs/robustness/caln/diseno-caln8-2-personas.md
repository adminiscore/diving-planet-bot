# CALN-8 (2) · El grupo solo en `personas` — diseño (28-oct)

Para Gadea y el equipo, antes de tocar código. Es el paso 3-4 de `diseno-caln2-grupo.md` («la pregunta desde la
lista; fuera las esperas»), aprobado como CALN-8 (2) en #2311. Regla de CALN-8: cada pieza dice qué quita.

## 1. Qué queda fuera de la lista hoy (rama feature/caln8-g26-alvaro 6d02a89)

`personas` guarda ya el reparto (`{"actividad", "cantidad"}`; `detected_group_allocation` es su fachada). CALN-8 (1)
quitó `pending_companion_queue` y `pending_split_total`. Siguen aparte, cada uno con su regla de cuándo se rellena y se
vacía:

| Campo | Qué dice | En la lista sería |
|---|---|---|
| `pending_undecided_qty` | cuántos no han elegido (fuera del reparto, para que no «cuadre») | entradas con `actividad: None` y cantidad |
| `needs_companion_activity` | hay que preguntar qué hará alguien | hay alguna entrada con `actividad: None` |
| `pending_companion_activity` | alguien eligió X y falta cuántos («¿cuántos para snorkel?») | entrada con actividad y `cantidad: None` |
| `sin_decidir_certificados` | los que no han elegido, ¿certificados? | `certificado` de esas entradas |
| `acompanante_sin_certificar`, `acompanante_certificado_inactivo` | otra persona no está certificada / lo está pero sin bucear hace tiempo | `certificado` / `inactivo` de las entradas que no son quien escribe |
| `pending_companion_in_group` | «él quiere snorkel»: ¿ya estaba contado? | entrada con `contada: None` (se pregunta el total) |

Lo que existe solo para tenerlos de acuerdo entre sí: el «circuit-breaker» `_group_allocation_fully_resolved` y sus
3 sitios de limpieza (extraction ×2, slotfill_close), `_merge_pending_undecided`, `grupo.sin_decidir_aparte`, parte de
`_take_undecided_members` y de `_add_or_ask_companion`. Unas 150 líneas, y los bucles de la pregunta del acompañante
vienen de ahí (el orden en que se vacían decide qué se pregunta).

## 2. Propuesta

Las entradas de `personas` llevan lo que se sabe de cada una — `actividad` (None = sin elegir), `cantidad` (None = no se
sabe cuántos), `certificado`, `inactivo`, `quien` — y los campos de arriba pasan a ser **propiedades derivadas** de la
lista, como ya es `detected_group_allocation`. Quien los lee no cambia; quien los escribe, escribe en la lista.

- `pending_undecided_qty` = suma de las entradas sin actividad con cantidad; `needs_companion_activity` = hay alguna sin
  actividad. Elegir es poner la actividad en esa entrada: no hay nada que «fusionar» ni que limpiar.
- `pending_companion_activity` = la entrada con actividad y sin cantidad; contestar «3» es poner su cantidad.
- Las certificaciones, en sus entradas: lo que hoy lee el lector del grupo (y deja en `sin_decidir_certificados`) va a
  la persona de la que habla.
- `detected_group_allocation` (la fachada) deja fuera a quien no ha elegido, como hoy deja `pending_undecided_qty`.

## 3. Por pasos, cada uno medido (una pasada por lado, a la misma hora)

| Paso | Qué | Quita | Cómo se mide |
|---|---|---|---|
| 2a | Sin elegir: `pending_undecided_qty` y `needs_companion_activity` derivados | 2 campos del estado y `sin_decidir_aparte` (el reparto ya deja fuera a quien no ha elegido); +50 líneas de src por las funciones de la lista, que 2b compensa | suite + banco-grupo A/B + lectura |
| 2b | Sin cantidad: `pending_companion_activity` derivado; elegir es poner la actividad en la entrada | `_merge_pending_undecided` y los 3 circuit-breakers | suite + banco-grupo A/B |
| 2c | Certificaciones por persona (`sin_decidir_certificados`, `acompanante_*`) | 3 campos sueltos | suite + banco-grupo + políticas (las notas del RAG los leen) |
| 2d | `pending_companion_in_group` como entrada sin contar | el último campo de espera | suite + banco-grupo (g-«se suma») |

Cada paso: 0 interruptores nuevos, campos del estado a la baja (`scripts/complejidad.py`), foto de prompts sin cambio.

## 4. Riesgos

- **Estados guardados en Redis:** al cargar una conversación vieja, sus campos se convierten en entradas (como hizo
  CALN-2 paso 1 con el reparto en `state_store.deserialize_state`); los que ya no existen se descartan solos.
- **El extractor no cambia** (el 3b de CALN-2 enseñó que un campo más en su esquema le hace dejar el reparto): escribe
  en la lista el código que ya lee su salida y la del lector.
- Toca `conversational_core` y el núcleo, que se iban a partir (CALN-8 (5)): este paso va antes y lo deja más corto.
