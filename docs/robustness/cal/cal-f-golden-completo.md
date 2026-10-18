# CAL-F · Golden visible completo (17-18 oct)

Ronda `docs/robustness/synthetic-runs/2026-10-17-calf-completa.jsonl` (465/465 turnos, PRE con lo promocionado hasta
CAL-C y r6-2), foto `docs/robustness/snapshots/2026-10-17-calf-completa.json`. Juez del golden (gpt-5-mini, medium).

## Resultado (18-oct, juzgado entero)

**95,8 % de criterios cumplidos (36 fallos de 849), 86/116 diálogos sin fallos**, 6 a revisar
(`docs/robustness/golden-set/results/2026-10-17-calf-completa__gpt-5-mini-medium.json`; 1,10 $). Las rondas
completas anteriores rondaban el 91 % (g10-B 91,2 %, est3-B 91,3 %), aunque con otras referencias del juez.
Por categoría, lo más flojo: pago 84,2 %, refresher 86,7 %, deflection 88,9 % (el teléfono: error de la referencia),
descuentos 92,6 %, nacionalidad 92,7 %.

Por suite: **visible 95.8 % (71/95 diálogos sin fallos)**; examen oculto 95.5 % (12/21).
**9 de los 33 diálogos con fallo son del EXAMEN OCULTO** (gastado): se cuentan en la nota, pero NO se atribuyen ni se
arreglan (norma; `reproducir_juez_pre` se niega a repetirlos). Sus ids no se listan aquí a propósito.

Fallos de la parte VISIBLE además de la tabla de abajo: precio-desde-islas-vs-cartagena, contacto-hoteles-cocoliso-san-pedro
(alojamiento directo), paquete-5-buceos-precio-overnight-isla-grande-baru (repregunta), tours-diarios-isla-grande
(pickup en las islas), refresher-que-completar-antes (tiempo sin bucear), pareja-certificados-cop-descuento
(descuentos vigentes), open-water-hoteles-noche (pernocta), descuento-online-sin-codigo, minicurso-precio-colombianos
(origen), recogida-ubuntu (comida desde islas, minicurso no certifica), moneda-precios-principiante-y-snorkel,
precios-y-disponibilidad-con-negociacion (cierre 4:30), curso-open-water-principiantes-idioma-frances (idioma).
Estabilidad (18-oct, 3 reps en PRE de cada uno con el juez al día): ver la sección siguiente.

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

## Estabilidad de los fallos visibles (18-oct, PRE 08f138e, 3 reps cada diálogo, juez con la referencia al día)

`reproducir_juez_pre` de los 24 diálogos VISIBLES con fallo (los 9 del oculto no se repiten). **20 criterios
estables** (2-3 de 3), 16 ruido (1 de 3) y 5 que ya no fallan (0 de 3: humano-con-carrito, pide-telefono, reserva-ingles,
precio-desde-islas-vs-cartagena y la repregunta de paquete-5-buceos-…-baru). Lista de trabajo, por zona:

**RAG / datos (Gadea):**
- confirmacion-salida-y-pago-sin-concepto: `confirmacion-por-pago-enlace` 3/3 y `operamos-diario-clima` 2/3: el turno
  acaba en el pase ("esto tiene que revisarlo una persona") y no dice que se paga por el enlace ni que se opera a diario
  (es cal-14 de CAL-A, sin cerrar).
- pareja-certificados-cop-descuento-almuerzo: `precio-moneda-cartagena-cop` 3/3 (no da el precio) y
  `descuentos-vigentes` 3/3 (no nombra el 5 % por equipo completo; criterio exigente).
- tours-diarios-isla-grande: `pickup-islas` 3/3 (no dice que desde un hotel de las islas se coordina la recogida).
- recogida-ubuntu-comida-y-certificacion: `minicurso-no-certifica` 3/3 (si se van mañana a mediodía, no dice que no
  da tiempo a certificarse) y `comida-desde-islas` 2/3 (no menciona comprar comida en el hotel; criterio exigente).
- refresher-que-completar-antes: `valida-tiempo-sin-bucear` 2/3 (no pregunta hace cuánto no bucea) y
  `formulario-medico-refresher` 2/3 (no dice que el formulario llega tras reservar).
- contacto-hoteles-cocoliso-san-pedro: `alojamiento-directo` 2/3 (no dice que el hotel se reserva directamente).
- ~~descuento-online-sin-codigo: `escala-si-no-aparece` 3/3~~ **Decidido por Gadea (18-oct): solo se explica** que el 10 % es automático, sin pasar a un asesor. El bot ya lo hace; el criterio pasa a `solo-explica-si-no-aparece`.
- certificado-fechas-fotos-y-reserva y precios-y-disponibilidad-con-negociacion: `sin-invenciones` 2/3 (pone un mes,
  una fecha o "a esta hora el sistema ya cerró" que el cliente no dijo).
- paquete-5-buceos-precio-overnight-isla-grande-baru: `sin-invenciones` 2/3 (llama "certified diver" a quien dijo
  ser principiante; se contradice sobre si el paquete cabe en la estancia).
- moneda-precios-principiante-y-snorkel: `moneda-por-nacionalidad` 2/3 (explica la regla pero no pregunta la
  nacionalidad).
- certificado-fecha-precio-cop-descuento-transferencia: `sin-invenciones` 2/3 (ofrece el 50 % de anticipo a quien
  tiene cédula de extranjería: **pregunta de negocio para Gadea**).

**Flujo / extractor (Álvaro):**
- refresher-rechaza-acepta: `final-con-refresher` 3/3 y `coste` 2/3 (el plan final no lleva la salida además del
  refresher aceptado; pide el origen en vez de dar el precio).
- grupo-mixto-precio-cop-total: `precio-total-cop-grupo-mixto` 2/3 (cotiza el Curso Avanzado por "1 buzo avanzado").
- curso-open-water-principiantes-idioma-frances-anticipacion: `global:idioma` 2/3 (el cliente pide francés y el bot
  sigue en español; la regla es inglés).
