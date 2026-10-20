# gen-7: el refresher (20-oct-2026)

Fase GEN de Plan Coral. En G9, la causa «refresher incompleto» sumaba unos 6 fallos:
- no decía que se reserva como minicurso;
- no decía la excepción de 500+ inmersiones o Dive Master;
- no decía que el formulario médico llega con la reserva;
- a veces pasaba a un asesor.

Este diagnóstico usa un banco propio, `dialogos-gen7.json` (10 diálogos ×2), con frases nuestras y sin abrir el examen.
Se pasó con `reproducir_juez_pre --banco` contra PRE `af165db`. Salida: `2026-10-20-gen7-base.jsonl`.

## Lo que sale bien: la pregunta directa (el RAG)

Con la base de hoy (ficha `refresher:minicourse`, políticas `refresh_requirement` y `medical_restrictions`), el RAG
contesta completo:
- se reserva como **Minicurso de Buceo**, con su precio y lo que incluye;
- un refresh o un PADI ReActivate hecho en otro centro **cuenta**;
- con Dive Master o 500+ inmersiones, **lo revisa un asesor**;
- el **formulario médico de curso**, aunque sea buzo certificado;
- si no dice cuánto hace, **pregunta cuánto hace**.

## El fallo: dentro de la reserva

A la pregunta del flujo «¿Ha pasado *más de 2 años* desde la última inmersión de **alguno del grupo**?», el cliente
contesta «**sí, uno de nosotros no bucea desde hace 4 años**». El bot responde «entiendo que uno de ustedes no bucea
desde hace 4 años» y **vuelve a hacer la misma pregunta** (2 de 2). El refresher nunca llega.

La causa, reproducida en local con los registros del flujo:
1. El extractor lee `last_dive_over_2_years=True` y, además, `otro_certificado_inactivo` (es otra persona del grupo, no
   quien escribe).
2. Como el dato es de otra persona, `_restore_main_diver_fields` devuelve los datos de quien escribe a como estaban, y
   `last_dive_over_2_years` vuelve a `None`.
3. `next_missing_slot` solo mira `last_dive_over_2_years` (el de quien escribe), así que la pregunta de seguridad sigue
   «sin contestar» y se repite.

La pregunta es de **grupo** y el refresher se cobra «por persona que lo necesite»: la respuesta tiene que contar a
cualquiera del grupo.

## Arreglo (global, sin regex)

- **`SEGURIDAD_DE_GRUPO`**: `conversational_core.refresh_en_el_grupo(state)` es un punto único. Vale `True` si quien
  escribe o alguien del grupo lleva más de 2 años sin bucear, `False` si nadie y `None` si no se sabe. Lo usan
  `next_missing_slot` (para la pregunta de seguridad y para la del refresher) y la red de U3-6.
- **`REFRESHER_COMPLETO`**: el texto fijo del refresher dice lo que dice la base: se reserva como *Minicurso de Buceo*
  y lleva el formulario médico de curso, aunque estén certificados, porque el enlace llega con la reserva.

En local: «sí, uno de nosotros…» → el refresher completo → «sí, lo queremos» → queda apuntado → la reserva sigue con
la nacionalidad.

Ya no hay `sois` en este texto (se arregló antes con los textos de Cartagena).

## Resultado: PROMOCIONADO (20-oct, HISTORY 0.31.73)

- **Banco gen-7:** «uno de nosotros, hace 4 años» pasa de repetir la pregunta (0/2) a dar el refresher completo (2/2).
  El control (buceó el año pasado) no cambia.
- **Ronda core:** gen7-B 96,1 % 25/32 frente a textos-B 97,4 % 26/32. Los 6 criterios que empeoran no pasan por el
  cambio. El del referral sale igual sin los flags (atribución 3+3); los demás ya habían variado en otras rondas de hoy.
