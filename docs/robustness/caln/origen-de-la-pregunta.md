# CALN · El origen de la pregunta: los barrios de Cartagena (30-oct)

Encargo de Gadea (#2673). En el sparring, el cliente alojado en un barrio de Cartagena recibía otra vez «¿saldrías
desde Cartagena?»: «Estamos en Bocagrande» (s30a familia t1), «I'm staying in Getsemaní» (s30a refresher-en t1),
«we're at the hotel in the old town» (s30e hoy-mismo t1) y «We're staying in Getsemaní» (s30e cambia-plan t2).

## 1. Hecho (987634e4): la cita de un barrio nombra un lugar

En dos de los cuatro casos el extractor sí leía `cartagena`, pero el código lo tiraba: «la cita no nombra un lugar».
`lugares.json` gana `barrios_de_cartagena`, una lista cerrada sin los nombres que son también otra cosa (Manga, San
Diego, Marbella, Crespo). `nombra_un_lugar` acepta esos barrios, y una cita que solo nombra un barrio y sale `island`
se corrige a `cartagena`, como Barú. La foto de prompts no cambia.

Sonda directa ×10, primer turno, con esto:

| Frase | location |
|---|---|
| «Estamos en Bocagrande» | cartagena 9/10 |
| «We're in the walled city» | cartagena 8/10 |
| «I'm staying in Getsemaní» | null 10/10 |
| «we're at the hotel in the old town» | null 10/10 |
| «nos quedamos en un hotel de Castillogrande» | null 10/10 |
| «estamos alojados en el centro histórico» | null 10/10 |
| «We'll be visiting Cartagena» (control) | null 10/10 |
| «Estamos en Isla Grande, en el hotel Cocoliso» (control) | island 10/10 |

En los cuatro null, el extractor calla: no sabe que esos sitios son de Cartagena.

## 2. Probado y NO guardado: la lista de barrios en el prompt del extractor

Método de Gadea: la sonda ×10 y el banco ex0 de diseño (200 casos), 5 pasadas por caso, en los dos órdenes (A, B, B, A)
y a la misma hora. Llamadas directas, sin PRE. Resultados en `docs/robustness/regex/banco-ex0/estabilidad-barrios*-*.json`
y `sonda-barrios-variante*.txt`.

| | Sin lista (A) | Variante 1: línea aparte, como la de las islas | Variante 2: dentro de la regla de location |
|---|---|---|---|
| Getsemaní, walled city, centro histórico, Bocagrande | 0-9/10 | 10/10 | 10/10 |
| old town / Castillogrande | 0/10 | 10/10 | 3/10 · 6/10 |
| ex0 modal: acierto · equivocado · inventado | 100-102 · 0-1 · 8 | 101/100 · 1/1 · 8/9 | 99/99 · 1/1 · 9/9 |
| «yo soy residente» (is_colombian true) | 8/10 por la mañana, 4/10 por la tarde | 0/10 | 0/10 |
| «family of 6, 3 dive and 3 snorkel» | 10/10 | 3/10 | 10/10 |

Ninguna sale limpia. Las dos arreglan los barrios, pero mueven casos que no tienen que ver, sobre todo el residente, que
decide la moneda. Es la clase de efecto lateral de `prompt-extractor-efectos-laterales`.

## 3. Para decidir (Gadea)

(a) Dejarlo en lo de §1: Bocagrande y walled city ya van; Getsemaní, el centro y Castillogrande siguen con la
    confirmación «¿saldrías desde Cartagena?», que el cliente contesta en un turno.
(b) Por código, sin tocar el prompt: si el extractor calla el lugar y el mensaje nombra un barrio de la lista
    (`lugares.barrio_nombrado`), `location = cartagena` con el barrio de cita. Es lo mismo que ya hace `_solo_baru` con
    Barú: el código pone lo que sabemos del sitio, de una lista de datos. No mueve el extractor. Pero es leer el texto
    con una lista cerrada, y la regla es no poner parches con patrones de texto.
(c) Otra redacción del prompt, medida igual (~20 min, céntimos).

Mi recomendación: (b). Es una lista de nombres propios, no de frases; no mueve nada más, y la confirmación de hoy cuesta
un turno a cada cliente alojado en Cartagena.
