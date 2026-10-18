# CAL-F · Golden visible completo (17-18 oct)

Ronda `docs/robustness/synthetic-runs/2026-10-17-calf-completa.jsonl` (465/465 turnos, PRE con lo promocionado hasta
CAL-C y r6-2), foto `docs/robustness/snapshots/2026-10-17-calf-completa.json`. Juez del golden (gpt-5-mini, medium).

## Resultado (18-oct, juzgado entero)

**95,8 % de criterios cumplidos (36 fallos de 849), 86/116 diálogos sin fallos**, 6 a revisar
(`docs/robustness/golden-set/results/2026-10-17-calf-completa__gpt-5-mini-medium.json`; 1,10 $). Las rondas
completas anteriores rondaban el 91 % (g10-B 91,2 %, est3-B 91,3 %), aunque con otras referencias del juez.
Por categoría, lo más flojo: pago 84,2 %, refresher 86,7 %, deflection 88,9 % (el teléfono: error de la referencia),
descuentos 92,6 %, nacionalidad 92,7 %.

Fallos (además de la tabla de abajo, que eran los 14 primeros): precio-desde-islas-vs-cartagena,
contacto-hoteles-cocoliso-san-pedro (alojamiento directo), certificado-profundidad (profundidad según nivel),
paquete-5-buceos-precio-overnight-isla-grande-baru y curso-mas-paquetes (repreguntas), tours-diarios-isla-grande
(pickup en las islas), refresher-que-completar-antes (tiempo sin bucear), grupo-mixto-cotiza-y-pide-link y
link-pago-extranjeros-sin-cedula (enlace), punto-encuentro-corrige-todo-mar-y-hora, pareja-certificados-cop-descuento
(descuentos vigentes), open-water-hoteles-noche (pernocta), descuento-online-sin-codigo, minicurso-precio-colombianos
(origen), recogida-ubuntu (comida desde islas, minicurso no certifica), moneda-precios-principiante-y-snorkel,
precios-y-disponibilidad-con-negociacion (cierre 4:30), curso-open-water-principiantes-idioma-frances (idioma),
principiante-precio-y-evaluacion-medica, pareja-reactivate-y-refresh-cartagena (repregunta). Siguiente: atribuir
cada uno a su zona con `reproducir_juez_pre` (3 reps), empezando por los del RAG que tocan el origen.

## Estado (17-oct, histórico)

El juez quedó **a medias**: la primera vez lo cortó el `timeout 3000` (50 min); la segunda, el crédito de OpenAI
(21:31, 429 `credit_balance_exhausted`). Juzgados **403 de 703** criterios LLM (más los automáticos).

**Cuidado con la caché:** la referencia del juez sale de los ficheros de la base (`load_reference`), así que cualquier
cambio en `data/knowledge_base/` (los de G3-07b y G3-08 de hoy) cambia la clave y la caché deja de valer para esta
ronda. Esta ronda se hizo con la base del commit 1479d7e: se juzga desde un worktree en ese commit, con la caché
copiada, y luego se vuelve a copiar la caché al repo:

```
git -c core.longpaths=true worktree add -f <dir> 1479d7e
cp docs/robustness/synthetic-runs/2026-10-17-calf-completa.jsonl <dir>/docs/robustness/synthetic-runs/
cp docs/robustness/golden-set/results/judge-cache.jsonl <dir>/docs/robustness/golden-set/results/
cd <dir> && ENV_FILE=<repo>/.env.dev python -m scripts.judge_golden_set --run docs/robustness/synthetic-runs/2026-10-17-calf-completa.jsonl
# después: copiar <dir>/docs/robustness/golden-set/results/* al repo
```

## Lo juzgado el 17-oct (403/703, desde la caché, sin gastar)

69 diálogos completos: **58 sin fallos**. 14 fallos en 638 criterios con veredicto.

| Diálogo | Criterio | Qué | Zona |
|---|---|---|---|
| pide-telefono | sin-invenciones | se niega a dar un teléfono y pasa a una persona | **error del juez**: la referencia trae el WhatsApp de `escalation_rules.json`; Gadea decidió que no se dan teléfonos |
| confirmacion-salida-y-pago-sin-concepto | confirmacion-por-pago-enlace | no dice "queda confirmada al pagar" | **criterio viejo**: Gadea decidió que el pago se registra y el equipo lo concilia (no "confirmada al pagar") |
| confirmacion-salida-y-pago-sin-concepto | operamos-diario-clima | no dice que se opera todos los días | RAG (Gadea) |
| reserva-ingles | idioma | "Muelle de la Bodeguita" en una respuesta en inglés | **error del juez** (nombre propio) |
| humano-con-carrito | sin-invenciones | "las salidas desde Cartagena son ida y vuelta el mismo día" en general | RAG (Gadea) |
| paquete-5-buceos-cop-refresh-y-hoteles | sin-invenciones | dormir una noche obligatorio sin saber el origen | RAG (Gadea) |
| reserva-paquete-5-buceos-solicita | origen-cartagena-o-islas | precio y enlace antes de preguntar el origen | RAG/flujo |
| regateo-grupo-6 | sin-invenciones | enlace "desde Cartagena" sin que dijera el origen | RAG/flujo |
| certificado-fecha-precio-cop-descuento-transferencia | sin-invenciones | ofrece el 50 % de anticipo a quien tiene cédula de extranjería | por confirmar con Gadea (¿residente = COP y 50 %?) |
| grupo-mixto-precio-cop-total | sin-invenciones | "1 buzo avanzado" leído como el Curso Avanzado | extractor/flujo (Álvaro) |
| grupo-mixto-precio-cop-total | sin-repreguntas | vuelve a preguntar si los del bautismo no tienen certificación | flujo (Álvaro) |
| refresher-rechaza-acepta | coste | "el refresher tiene un costo" sin dar el precio | RAG/flujo |
| refresher-rechaza-acepta | final-con-refresher | el plan final no incluye el refresher aceptado | flujo (Álvaro) |
| certificado-fechas-fotos-y-reserva | sin-invenciones (revisar) | "¿noviembre?" sin que el cliente dijera el mes | a revisar a mano |

Patrón que se repite (3 casos, RAG): **dar por supuesto el origen** (Cartagena o "dormir en las islas") cuando el
cliente no lo ha dicho. Es la misma familia que G3-06 (plan que nadie pidió) y la regla del origen (s4-22) no basta.

## Antes de la ronda core B y de G9 (referencia del juez)

1. Referencia: que el juez sepa las decisiones de negocio que no están en los datos (no se dan teléfonos; la reserva
   la concilia el equipo; otro idioma → inglés; sin totales…). Cambia la clave de la caché: hacerlo DESPUÉS de juzgar
   CAL-F y ANTES de la ronda core B (A y B con la misma referencia).
2. Golden visible: el criterio `confirmacion-por-pago-enlace` dice lo contrario de la decisión de Gadea.
