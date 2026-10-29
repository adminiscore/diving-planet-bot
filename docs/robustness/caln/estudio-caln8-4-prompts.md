# CALN-8 (4) · Adelgazar los prompts del extractor y de Jev — estudio (29-oct)

Decisión de Gadea (28-oct): después de la 5.ª. El turno gasta ~28.000 tokens de entrada; el extractor (Haiku) ~9.900
por llamada (34 %) y Jev ~8.100 (27 %).

## 1. Qué lleva el prompt de sistema del extractor

Capturado con un cliente falso (`extraer_turno(..., client=...)`), contado con cl100k (Haiku cuenta algo más):

| Parte | Tokens | % |
|---|---|---|
| El esquema JSON (19 campos, con su descripción y la de la cita) | 2.823 | 43 |
| «Reglas» (33 líneas; 14 campos con su propia regla) | 2.583 | 39 |
| La lista de hoteles e islas del Rosario | 1.081 | 16 |
| La presentación | 88 | 1 |
| **Total** | **6.575** | |

## 2. Paso 1: fuera la descripción del esquema de los campos que ya tienen regla — DESCARTADO

Parecía un duplicado (p. ej. `quiere_bucear`: 151 tokens de descripción y 99 de regla que dicen casi lo mismo).
Quitarla: 6.575 → 5.994 tokens (−9 %).

- Banco ex0 de diseño (200 casos) ×3, respuesta modal: aciertos 101 → 103, perdidos 14 → 12, inventados 8 → 11. Parecía
  neutro o mejor.
- **Los 12 casos que cambiaban, ×10, base / paso 1 intercalados:** inventados **2 → 52**, equivocados 2 → 9.
  «quiero bucear certificado» → is_certified true 10/10 (regla de Gadea: bucear certificado ≠ certificado);
  «hicimos 2 buceos con uds» → 20 inventos; el reparto del grupo, 10/10.

Las descripciones del esquema NO eran redundantes para Haiku: llevan el «YA es buzo certificado» y los matices del
reparto. Se queda como estaba.

## 3. La frase de la moneda en el extractor (CALN-3c c) — DESCARTADA

«tengo (la) extranjería es tener esa cédula» en la regla de is_colombian. Banco ex0 ×3: aciertos 101 → 104, inventados
8 → 11. **Los 12 casos ×10:** inventados 2 → 23, equivocados 2 → 14 (colombianos-precio-minicurso 10/10,
grupo-cambia-dos-veces 8/10). Mueve otras lecturas, como ya se vio en la mini-ronda de la 5.ª (15 fallos frente a 13).
Queda por medir aparte la parte de la POLÍTICA (`colombian_pricing`: nacer en Colombia no basta), que va al escritor.

## 4. Lo que se aprende (método)

- El prompt de Haiku es muy sensible a la redacción: quitar o añadir una frase mueve campos que no se tocan.
- **El banco ex0 ×3 modal no basta**: la respuesta más frecuente de 3 esconde los inventos. Para un cambio del prompt
  del extractor: el banco ×3 para encontrar los casos que cambian y **esos casos ×10, variantes intercaladas, contando
  inventos y equivocados**. Coste: ~0,4 $ por comparación de 3 variantes.
- Siguiente candidato: la lista de hoteles (1.081 tokens) al código (el extractor da el nombre del hotel y el código lo
  busca en su lista); medido igual.
