# u3-4, escalón 0 de los arreglos — lectura a mano de los 16 casos (25-sep, Gonzalo)

Salida cruda: `triaje-v3.txt` (de `scripts/replay_diff_triage.py`, que aparta el ruido objetivo:
9 turnos sin pregunta y 5 con estado previo ya distinto entre pasadas). Aquí van los 16 que
quedan, leídos uno a uno. El juez (`gpt-5-mini`) marcó 30 «INVENTADO» de 51 turnos con dato de
más; **de esos 30, reales son 5**.

## Mapeo de producto correcto — el juez es estricto, no es un error (7)

El catálogo mapea "buceo"/"fun dive"/"paquete de 5 buceos"/"5 dive package" a `certified_diving`.
El juez pide que el cliente diga literalmente "soy certificado" y por eso los marca.

| caso | mensaje | dato |
|---|---|---|
| `acompanante-madre-desde-cartagena#3` | "Mi madre puede acompañarme en **el buceo**…" | `certified_diving` |
| `cambio-fecha-por-enfermedad#1` | "so excited for **diving** with your team on Monday" | `certified_diving` |
| `desde-islas-buzo-certificado#1` | "I would love to dive here… **fun dives**" | `certified_diving` |
| `equipaje-mochilas-y-almacenamiento#1` | "we just booked a **5 dive package**" | `certified_diving` |
| `paquete-5-buceos-cop-refresh-y-hoteles#1` | "Quiero hacer el **paquete de 5 buceos**" | `certified_diving` |
| `regreso-otro-dia-paquete-5#1` | "tomaremos el **paquete de 5 buceos** para 2 personas" | `certified_diving` |
| `reserva-paquete-5-buceos-solicita#1` | "reserva para el **paquete de 5 buceos**" | `certified_diving` |

## Inferencia de negocio legítima (1)

- `descuento-online-sin-codigo#1` — "trying to checkout to take PADI Open Water Diver certification
  course": `padi_open_water` (el juez lo acepta) y `is_certified=False`. Querer el curso de
  certificación implica no estar certificado; es la regla de `_activity_has_textual_backing`, no
  una invención.

## Errores reales — nacionalidad, familia de **u3-5** (2)

Ya existen sin el flag y Gadea los dejó fuera de u3-4 a propósito (24-sep).

- `moneda-precios-principiante-y-snorkel#5` — "¿el precio está en dólares o pesos colombianos?" → `is_colombian=False`.
- `open-water-precio-para-colombianos-corrige-mito#1` — "¿Cuál es el costo para colombianos?" → `is_colombian=True`.

Nota: el juez se contradice consigo mismo — en `paquete-5-buceos-cop-refresh-y-hoteles#1`, con la
MISMA frase ("costo para colombianos"), **acepta** `is_colombian=True`. Otra razón para no leer su
recuento agregado como si fuera una medida.

## Errores reales — el dato hipotético, que es justo lo que el arreglo 2 debía matar (3)

- `curso-open-water-transporte-y-regreso-otro-dia#1` — "**in case I decided to do** PADI Open Water
  Diver certification course, correct?" → `padi_open_water`.
- `recogida-ubuntu-comida-y-certificacion#3` — "Is it possible for my son a PADI certificat?" →
  `padi_open_water` + `is_certified=False`, pisando el minicurso que ya tenían reservado.
- `curso-open-water-principiantes-idioma-frances-anticipacion#1` — "más información acerca de los
  **cursos** de buceo… primera vez" → `minicourse`. Misma familia que el "curso básico → minicurso"
  que ya estaba documentado: el regex resuelve por cadena `if/elif`.

## Dudosos (3)

- `familia-mixta-precio-descuento-refresher#1` — `detected_group_size=3` con 6 personas en el
  mensaje (3 bucean, 3 snorkel). Depende de si el campo cuenta el grupo entero o los buceadores.
- `paquete-5-buceos-islas-residente-sin-recogida#4` — "Va quiero comprar sin ir de cartagena" →
  `location=island`. En contexto (residente en las islas) parece correcto.
- `paquete-5-buceos-precio-overnight-isla-grande-baru#1` — "a 2 day dive package at the rosario
  islands" estando en Cartagena → `location=island`. Aquí el juez tiene razón: el destino no es el
  punto de salida.
