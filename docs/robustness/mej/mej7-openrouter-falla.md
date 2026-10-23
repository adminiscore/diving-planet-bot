# mej-7: qué pasa cuando OpenRouter falla

23-oct, Gonzalo con Claude, encargo de Gadea (#1566). Análisis sin gastar: código (`src/llm_client.py`,
`src/agents/jev_router.py`) y las métricas de las rondas ya hechas (`docs/robustness/synthetic-runs/*.metricas`).

## Cómo sale cada llamada hoy

- **Por dónde sale.** Un modelo con prefijo de proveedor (`deepseek/…`, `anthropic/…`) sale por OpenRouter
  (`llm_client._por_proveedor`). Los demás (`gpt-6-luna`, `gpt-5.4-*`, embeddings) salen por OpenAI.
- **Si OpenRouter falla.** Con cualquier error (crédito, clave, caída, error del proveedor) se repite la MISMA petición
  con `respaldo_si_openrouter_falla` (gpt-5.4-mini en config; en la ronda del 21-oct era Luna). Si OpenRouter tarda más
  de `openrouter_respaldo_segundos` (5 s), sale también por OpenAI y gana la primera que acabe bien.
- **Jev** (`typesafe/jev-1.13`) va por la API de decisiones de OpenRouter con su propio cliente HTTP y un tope de 2 s.
  Si falla, no hay respaldo: el turno lo decide el router LLM (`senales_router`, DeepSeek, que a su vez cae a OpenAI).

| Pieza | Modelo | Proveedor | Si su proveedor falla |
|---|---|---|---|
| jev | typesafe/jev-1.13 | OpenRouter | router LLM; **se pierden las intenciones y las señales del turno** |
| senales_router (router LLM) | deepseek-v4.1-flash | OpenRouter | gpt-5.4-mini |
| extractor, extractor_paso6, resolutor | claude-haiku-5.5 | OpenRouter | crear_con_respaldo / gpt-5.4-mini |
| reescritura, pregunta_sola, idioma, resumen, notas | deepseek-v4.1-flash | OpenRouter | gpt-5.4-mini |
| revisor (grounding_v3) | deepseek-v4.1-flash | OpenRouter | gpt-5.4-mini (antes del 18-oct dejaba pasar sin revisar) |
| rag_respaldo | deepseek-v4.1-flash | OpenRouter | gpt-5.4-mini |
| escritor del RAG, redactor, aviso_final, plan | gpt-6-luna | OpenAI | el escritor del RAG cae a rag_respaldo (DeepSeek); el resto sin respaldo (cada uno sigue sin lo suyo) |
| embeddings | text-embedding-3-small | OpenAI | sin respaldo |

## Lo que se vio el 21-oct (ronda `2026-10-21-respaldo-luna`, 93 turnos)

- La clave dio **401** (no 402 ni 403) en todas las piezas de OpenRouter: extractor 92, extractor_paso6 92,
  senales_router 92, notas 63, pregunta_sola 55, revisor 49, reescritura 48, rag_respaldo 20 y resolutor 7.
  En total, 518 errores.
- Jev falló en los 93 turnos (`router` ≠ jev): todos los turnos los decidió el router LLM, que también falló y salió
  por OpenAI.
- Cada llamada fallida tarda ~0,25 s en volver con el error, y el respaldo (Luna) 1,4-2 s frente a 0,3-0,6 s de
  DeepSeek. Latencia del turno: p50 5,0 s y p90 10,6 s.
- El cliente no vio errores: 0 respuestas de fallo técnico, 9 pases y 36 turnos con RAG.

## Lo que NO fue: el G10 nº 3

En `2026-10-22-g10-arq3.metricas` (225 turnos) hay 0 errores de modelos, Jev contestó los 225 turnos (210 seguros y 15 con
dudas) y gpt-5.4-mini se llamó 4 veces. Que el redactor contestara la mitad no vino de OpenRouter.

## Riesgos que quedan

1. **Se repite el fallo en cada pieza de cada turno.** Con la clave caída, ~10 llamadas por turno van a OpenRouter
   sabiendo que fallarán: ~0,25 s cada etapa en serie y el doble de peticiones.
2. **Jev caído = sin intenciones.** Con `hechos_por_codigo` encendido, sin Jev no hay `_intenciones`: el redactor no
   contesta ningún turno y todo va al RAG (más lento y con las reglas de antes). Esto no lo arregla ningún respaldo:
   el router LLM no hace las preguntas de las intenciones.
3. **Nadie se entera.** El log solo da un WARNING por llamada. La alerta de saldo (mej-5, Álvaro) avisa antes de que se
   acabe el crédito, pero no de una clave revocada.

## El cambio mínimo (flag `openrouter_corte_segundos`, APAGADO = 0)

Con un **401/402/403** de OpenRouter (la clave o el crédito; un 5xx o un timeout no cuentan), se deja de llamar a
OpenRouter durante `openrouter_corte_segundos` (propuesta: 300 s):

- las piezas van directas a su respaldo de OpenAI, sin el intento que falla (`openrouter=cortado` en [TURN_METRICS]);
- Jev se salta y decide el router LLM, que también va por OpenAI;
- un solo `ERROR` en el log por corte: «[LLM][OPENROUTER] …: 401 (la clave o el crédito): se deja de llamar a
  OpenRouter 300 s…»;
- pasado el corte, se vuelve a intentar. Si la clave sigue mal, el primer intento lo vuelve a cortar.

No cambia ningún modelo ni el respaldo (gpt-5.4-mini). El riesgo 2 (sin Jev no hay redactor) sigue igual: es un cambio
mayor y no hace falta para que el turno no se rompa.

## Prueba con una clave falsa (23-oct, sin gasto de OpenRouter)

Banco de arq-1i (14 diálogos, 1 vuelta), `--codigo-local --env OPENROUTER_API_KEY=clave-falsa`; A sin corte, B con
`OPENROUTER_CORTE_SEGUNDOS=300` (`2026-10-23-mej7-A.jsonl` y `-B.jsonl`):

- **Jev:** A falla con 401 en cada turno (96-242 ms); B falla una vez y los otros 13 turnos se lo saltan («OpenRouter
  cortado»). El corte hace lo que tiene que hacer.
- **Latencia:** p50 8,5 s (A) frente a 9,8 s (B), p90 12,7 frente a 12,0. Con 14 turnos es ruido: el ahorro esperado
  (~0,25 s por etapa) es menor que la variación. Lo que pesa es que todo va por el respaldo de OpenAI.
- **Cliente:** 0 respuestas de error en los dos. Calidad 9/14 (A) y 8/14 (B, 2 invenciones), frente a 38/42 del mismo
  banco con la clave buena. Es el riesgo 2: sin Jev no hay redactor y todo va al RAG con las piezas de respaldo.

Conclusión: el corte no ahorra tiempo medible, pero quita el fallo repetido en cada pieza y lo avisa una vez.
Lo que de verdad cuesta calidad con la clave caída es perder Jev.
