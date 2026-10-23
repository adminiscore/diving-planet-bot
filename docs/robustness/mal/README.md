# «#mal»: marcar un fallo al probar el bot (mej-8, 24-oct)

## Para quien prueba

1. Habla con el bot como un cliente normal.
2. Si una respuesta está mal, escribe en el chat **`#mal`** y, detrás, qué esperabas. Por ejemplo:
   - `#mal no me dio el enlace para reservar`
   - `#mal: el precio online era otro`
   - `#mal` a secas también vale, pero con una frase ayuda mucho más.
3. El bot contesta «📝 Anotado como fallo…». Ese mensaje no cuenta como parte de la charla: sigue hablando con
   normalidad.

Va justo **después** de la respuesta mala: el `#mal` marca la última respuesta del bot.

## Para el equipo

- Interruptor `MARCAR_MAL` (APAGADO por defecto). Hay que encenderlo en el entorno donde se prueba.
- Con él encendido, el bot no contesta el `#mal` ni lo guarda en lo que recuerda de la charla. Pone la etiqueta
  `mal` a la conversación en Chatwoot y acusa recibo (`src/channels/marca_mal.py`, `src/channels/chatwoot.py`).
- Sacar los casos (solo lee Chatwoot, sin gasto de modelos):

  ```
  python -m scripts.exportar_mal                 # -> docs/robustness/mal/banco-mal.json
  python -m scripts.exportar_mal --desde 2026-10-24
  ```

  Cada caso lleva el mensaje del cliente, la respuesta mala, la charla hasta ahí y lo que escribió quien prueba
  (`pedia`). Todo pasa por `redact_pii`. Al volver a exportar, los casos que ya estaban no se pisan: se puede
  corregir `pedia` a mano.
- Medir un arreglo contra esos casos: `python -m scripts.banco_fallos medir --banco docs/robustness/mal/banco-mal.json
  --etiqueta mal-A --reps 3` (gasta: reproduce en PRE y juzga con el verificador).
- Antes de subir el banco al repo, revísalo: son charlas de personas reales (familia, equipo) y `redact_pii` no lo
  tapa todo.
