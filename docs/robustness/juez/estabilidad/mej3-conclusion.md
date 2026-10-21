# mej-3 · Un juez más estable (21-oct, Gonzalo con Claude)

**Problema (Gadea):** la misma respuesta se aprueba en una ronda y se suspende en otra.

## Por qué pasa

El juez guarda una caché por transcripción exacta: si el diálogo es idéntico, el veredicto se repite. Pero las
respuestas del bot cambian de redacción de una ronda a otra, así que casi cada criterio se juzga de nuevo, y el juez
(gpt-5-mini, effort medium) no siempre decide lo mismo.

## Herramientas (scripts/, sin tocar el bot)

- `scripts/estabilidad_juez.py --run <ronda> --veces N [--votos V]`: juzga la MISMA ronda N veces sin caché y cuenta
  los criterios que cambian de veredicto y cuánto se mueven la nota y los diálogos sin fallos. Mide el ruido del
  juez, no el del bot.
- `judge_golden_set --votos 3`: si el PRIMER veredicto de un criterio es un suspenso (`no_cumple` o `revisar`), se
  pregunta dos veces más y manda la mayoría; sin mayoría, `revisar`. Los `cumple` no se repiten, así que el coste sube
  solo en los dudosos. Con 1 voto (por defecto) el juez y su caché quedan exactamente igual (dry-cache de gen5-A:
  190/190 con y sin el cambio).

## Medida (gen3b-A, 2 pasadas sin caché)

| Juez | Criterios que cambian | Nota | Diálogos sin fallos |
|---|---|---|---|
| Por defecto | 5/190 (2,6 %) | 97,0 / 97,4 % | 26 / 26 |
| `--votos 3` | 2/190 (1,1 %) | 97,8 / 98,3 % | 27 / 28 |

- Sin votos, entre los 5 que cambian estaban los DOS criterios que «empeoraron» en la A/B de gen-3b y una de sus
  «mejoras»: eran ruido del juez, no del bot.
- Los votos quitan más de la mitad del ruido, pero suben la nota (tumban suspensos falsos). Una nota con votos no se
  compara con una sin votos.

## Conclusión y propuesta

1. **En las A/B, juzgar A y B con el mismo juez** (con votos o sin ellos, pero igual en los dos lados). Con votos, el
   ruido baja de unos 5 a unos 2 criterios por ronda core.
2. **Una diferencia de 1-2 criterios entre A y B no decide nada**, con votos o sin ellos, salvo que esos criterios
   pasen por el cambio (atribución turno a turno, como en gen-3b y gen-8).
3. **G10:** Gadea decide si se juzga con votos. Si se juzga con votos, G9 de control también, para compararlos.
4. Muestra pequeña (1 ronda, 2 pasadas, unos 1,2 $). Si hace falta más certeza, `estabilidad_juez --veces 3` sobre otra
   ronda.

Ficheros: `docs/robustness/juez/estabilidad/2026-10-21-gen3b-A__veces2.json` y `…__veces2__votos3.json`.
