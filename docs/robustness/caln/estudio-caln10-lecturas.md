# CALN-10 · Lecturas estables de Haiku — estudio (29-oct)

Rumbo de Gadea (29-oct): las lecturas del extractor varían (el mismo mensaje sale distinto en cada pasada) y eso explica
repreguntas sueltas y, en el sparring, la moneda: «soy de Cali» y «nací en Colombia» salían USD o COP según la pasada.

## 1. ¿Viene de que OpenRouter reparta las llamadas entre proveedores?

`settings.openrouter_proveedores` deja a OpenRouter elegir por latencia; Haiku lo sirven Amazon Bedrock, Google Vertex y
Anthropic. Sonda (`scripts/sonda_proveedor_haiku.py <pasadas> <proveedor>`): 12 casos sensibles del banco ex0 + 5 frases nuestras del sparring,
×8, el reparto de siempre frente a un solo proveedor, intercalados.

| Haiku servido por | Salidas distintas (17 casos ×8) | Inventos (ex0) | is_colombian = false en Cali / nacer / residente (de 24) |
|---|---|---|---|
| Reparto de siempre (3 pasadas) | 35-38 | 6-7 | 5-6 |
| Solo Amazon Bedrock | 34 | 8 | 5 |
| Solo Google Vertex | 29 | 20 | 0 |
| Solo Anthropic | 31 | 31 | 0 |

- Las cifras del reparto de siempre son las de Bedrock: parece caer casi siempre ahí (la sonda no guarda el proveedor;
  es inferencia). El prompt del extractor se ha ido ajustando, sin saberlo, con lo que responde Bedrock.
- Si Bedrock va lento, OpenRouter salta a Vertex o Anthropic, que con nuestro prompt inventan 3-4 veces más: parte del
  ruido entre rondas y de que la calidad cambie con la hora (como la latencia).
- Dentro de un mismo proveedor Haiku sigue variando (~2 salidas distintas por caso): fijar el proveedor no lo quita.

## 2. Propuesta

- **10a (sin coste):** para Haiku, Bedrock primero y los demás solo de respaldo si falla. Conserva lo de hoy y evita los
  saltos a los proveedores que inventan más. Toca `config.py` (los proveedores son por modelo). Medir con ex0 ×3 + los
  casos sensibles ×10, contando inventos.
- **10b (cuesta, decisión de Gadea):** para la nacionalidad, el dato solo si dos lecturas coinciden (si no, null: las
  dos monedas y se pregunta). Duplica las llamadas del extractor (+~16 % del gasto por turno; en paralelo, sin latencia).
