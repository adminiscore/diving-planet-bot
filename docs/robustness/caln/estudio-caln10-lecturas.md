# CALN-10 · Lecturas estables de Haiku — estudio (29-oct)

Rumbo de Gadea (29-oct): las lecturas del extractor varían (el mismo mensaje sale distinto en cada pasada) y eso explica
repreguntas sueltas y, en el sparring, la moneda: «soy de Cali» y «nací en Colombia» salían USD o COP según la pasada.

## 1. ¿Viene de que OpenRouter reparta las llamadas entre proveedores?

Haiku lo sirven Amazon Bedrock, Google Vertex y Anthropic. Para los modelos `anthropic/` el orden ya es fijo desde ARQ-2b
(22-oct, por la caché): `cache_anthropic_proveedor` = Bedrock primero y los demás solo si Bedrock falla
(`llm_client.parametros_openrouter`); para el resto de modelos, OpenRouter elige por latencia. Sonda (`scripts/sonda_proveedor_haiku.py <pasadas> <proveedor>`): 12 casos sensibles del banco ex0 + 5 frases nuestras del sparring,
×8, el reparto de siempre frente a un solo proveedor, intercalados.

| Haiku servido por | Salidas distintas (17 casos ×8) | Inventos (ex0) | is_colombian = false en Cali / nacer / residente (de 24) |
|---|---|---|---|
| Reparto de siempre (3 pasadas) | 35-38 | 6-7 | 5-6 |
| Solo Amazon Bedrock | 34 | 8 | 5 |
| Solo Google Vertex | 29 | 20 | 0 |
| Solo Anthropic | 31 | 31 | 0 |

- El reparto de siempre YA es Bedrock (orden fijo de ARQ-2b): por eso sus cifras son las de «solo Bedrock» (la diferencia
  entre las dos filas es ruido). El prompt del extractor se ha ido ajustando con lo que responde Bedrock.
- Vertex y Anthropic, con nuestro prompt, inventan 3-4 veces más: solo entran si Bedrock falla (raro), así que no son
  la fuente de la variación de cada día.
- La variación es de Haiku en Bedrock (~2 salidas distintas por caso): fijar el proveedor no la quita.

## 2. Propuesta

- **10a, Bedrock primero: YA ESTÁ** (ARQ-2b, 22-oct). Visto el 30-oct al ir a hacerlo; no hay nada que cambiar.
- **10b (cuesta, decisión de Gadea):** para la nacionalidad, el dato solo si dos lecturas coinciden (si no, null: las
  dos monedas y se pregunta). Duplica las llamadas del extractor (+~16 % del gasto por turno; en paralelo, sin latencia).

## 3. 10b medido (30-oct): la nacionalidad solo si dos lecturas coinciden

`scripts/sonda_nacionalidad_10b.py 12 15`, llamadas directas al extractor (sin PRE): los 17 casos del banco ex0 (diseño)
que esperan `is_colombian`, 15 casos al azar que no la dicen (para contar inventos) y «soy de Cali» y «nací en Colombia
pero vivo en Madrid» del sparring; ×12. La variante 10b se arma con las lecturas de dos en dos (si no coinciden, null).

| | Bien | **Equivocada** (moneda que no es) | Inventa (sin que lo diga) | Pregunta (null) |
|---|---|---|---|---|
| Una lectura (hoy), 408 | 89,0 % | **2,5 %** (10) | 2,9 % | 5,6 % |
| Dos que coinciden (10b), 204 | 85,3 % | **0 %** (0) | 2,9 % | 11,8 % |

- Las equivocadas salen de dos frases casi al 50 %: «soy de Cali» (True 7 / False 5; la regla del extractor ya dice que
  la ciudad de Colombia cuenta) y el residente de snorkel-precio-residente t5 (True 6 / False 5). No falta la regla: es
  la lectura de Haiku.
- 10b convierte las equivocadas en preguntas (5,6 → 11,8 %). Con lecturas independientes se esperaría ~0,7 % de
  equivocadas (las dos fallan igual); en la muestra salieron 0.
- Los inventos no bajan (2,9 % = 2,9 %): cuando inventa, las dos lecturas inventan lo mismo.
- Coste: una llamada más al extractor solo mientras no se sabe el origen (~0,0014 $ por llamada); se espera a la más
  lenta de las dos.

