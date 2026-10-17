# Trabajo en paralelo: ramas, reparto y normas

Acordado por Gadea el 17-oct-2026 para cerrar la fase CAL más rápido, repartiendo el trabajo sin pisarnos. Es para
Álvaro, Gonzalo y Gadea (con Claude). Si algo de aquí choca con lo que estás haciendo, dilo en Plan Coral antes de
seguir.

Las normas no son teóricas: salen de cosas que ya nos han pasado en esta fase. Al lado de cada una está el porqué.

## 1. Antes de nada: poner tu rama al día

Cada uno trabaja en su rama `feature/pre_*`, y **PRE sirve la última rama que se sube**. Hoy:

| Rama | De quién | Estado el 17-oct |
|---|---|---|
| `feature/pre_gadea` | Gadea con Claude | **la referencia**: tiene todo lo promocionado (contacto a un asesor, consulta con lo sabido, contexto de Jev, pase por lo que la web no da), el banco reparado y los arreglos de las medidas |
| `feature/pre_alvaro` | Álvaro | **25 commits por detrás** (sigue en `041fc3d`, el relevo de CAL-C del 16-oct) |
| `feature/pre_pruebaGon` | Gonzalo | rama vieja (22-jul); está contenida en la de Gadea |

**Si subes tu rama sin ponerla al día, PRE vuelve a tu código y se deshacen sin avisar los cambios de los demás.**
Por eso, lo primero de todo:

```
git fetch origin
git checkout feature/pre_alvaro            # o la tuya
git merge --ff-only origin/feature/pre_gadea
```

Las dos ramas de Álvaro y Gonzalo están contenidas en la de Gadea, así que es un avance limpio, sin conflictos y sin
commits nuevos. Gonzalo, si prefieres, crea una rama nueva desde `origin/feature/pre_gadea`.

## 2. Reparto

| Quién | Tareas (id en Plan Coral) | Dónde toca el código |
|---|---|---|
| **Álvaro** | **CAL-C** (`cal-c`): los 17 casos de entender sin repreguntar ni suponer (C3 "no repreguntar lo sabido", el idioma y dos sueltos) | el extractor (`extractor_turno.py`) y el flujo de preguntas (`conversational_core.py`) |
| **Álvaro** | **Robustez de PRE** (`r6-1`, ya en curso): timeouts, respaldo y 429 | `llm_client.py`, `rag_agent.generar_con_respaldo` |
| **Gadea con Claude** | **CAL-A** (13 casos), **CAL-D** (el revisor del plan exacto), **CAL-F** (ronda del golden completo) y **CAL-G** (latencia) | la respuesta del RAG (`rag_agent.py`, `rag_plan.py`, `query_rewriter.py`) |
| **Libre (ideal Gonzalo)** | **Simulador de usuario** (`g-3`): adelanta el examen oculto sin esperar a Diving Planet | solo `scripts/` |
| **Libre** | **Puerta del golden y la latencia en CI** (`q5-1`) | solo CI |

**No se hace en paralelo:** la limpieza del camino antiguo (`ex-9`, `s4-1`, `s4-2`, `s4-25`). Parte los dos ficheros
grandes que tocamos todos. Va **después** de cerrar CAL.

Para Álvaro, al empezar CAL-C: el banco se reparó el 17-oct (12 casos tenían el mensaje del cliente cortado a 200
caracteres; 8 de ellos son de CAL-C: cal-22, cal-40, cal-41, cal-50 y cal-65 a cal-68). Y una pista para C3: el
extractor descarta "We will be staying at Bodegas de Santa Clara" porque la comprobación de la cita no lo reconoce como
un lugar, y es un hotel de Cartagena.

## 3. Normas

1. **Reclamar la tarea en Plan Coral antes de empezar** (dueño y "en curso"). *Por qué:* en esta fase hubo dos
   duplicaciones (ex-6, y la investigación de los 73 fallos con CAL-0 el mismo día).
2. **Antes de subir: integrar la rama del otro, `ruff check src` y la suite en verde.**
   `git merge origin/feature/pre_gadea` (o la del que haya subido último). *Por qué:* en PRE gana el último.
3. **No subir mientras alguien mide.** Subir despliega PRE y el despliegue **reinicia el contenedor**, que borra la copia
   del código de `--codigo-local` y mata la medida del otro. Quien vaya a medir más de unos minutos lo dice en el
   registro de Plan Coral con la hora de fin; quien vaya a subir mira ahí antes. *Por qué:* le pasó dos veces a Gadea
   la noche del 16 al 17.
4. **Tras un despliegue, no medir hasta que `check_deploy` dé verde.**
   `python -m scripts.check_deploy --branch feature/pre_<tu rama>`.
5. **Medir en paralelo ya se puede**: cada medida con `--codigo-local` sube a su propia carpeta
   (`/tmp/codigo-local-<usuario>-<pid>`). Lanza las medidas largas con `python -u` para ver por qué caso van.
6. **Todo cambio con su flag APAGADO por defecto.** Se promociona solo con el banco a 3 de 3 y una ronda del golden.
   Si la ronda da una diferencia pequeña (menos de unos 3 criterios), **no se decide por el número**: los diálogos que
   cambian se repiten 3 veces con y sin el cambio (`docs/robustness/protocolo-medicion.md`). *Por qué:* el juez
   re-juzga su ruido, pero no el del bot; cinco de seis "regresiones" del 17-oct no eran del cambio.
7. **Ficheros compartidos, avisar al tocarlos**: `src/agents/jev_router.py` (las señales), `src/config.py` y
   `docker-compose.vps.yml` (los flags: cada uno añade los suyos en su bloque, no en medio de los del otro),
   `docs/arquitectura/componentes.json` y `docs/HISTORY.md`. Son los que dan conflictos al integrar.
8. **Un cambio vale para los dos caminos, el grafo y la cascada.** PRE sirve el grafo (`AGENT_ARCH`); si arreglas algo
   en `supervisor.py`, mira si el nodo del grafo (`src/agents/*_agent.py`) llama a lo mismo. *Por qué:* el 17-oct el
   pase del contacto estaba solo en la cascada; lo cazó el test de equivalencia, no una medida.
9. **El crédito de OpenAI es compartido.** Antes de una medida larga, comprueba que hay saldo; si se acaba a mitad, el
   resultado no se escribe. *Por qué:* el 17-oct se agotó la clave de `.env.dev` a mitad de una medida del banco.
10. **Sin regex ni parches; nada caso a caso; no tocar el prompt del extractor por un caso.** Las normas de siempre.
11. **Un número que sale redondo de repente: mirar cuántos casos se midieron.** `banco_fallos medir` ya lista los
    casos sin medir y no los cuenta como buenos, pero conviene mirarlo. *Por qué:* una medida dijo "3/9 en 71 casos"
    con 62 casos sin medir.
12. **Al cerrar el día**: HISTORY, el relevo (`docs/project-history/session-handoff.md`) y Plan Coral al día.

## 4. Qué tiene que hacer cada uno

**Álvaro**
- [ ] Poner `feature/pre_alvaro` al día con el `merge --ff-only` de la sección 1, antes de tocar nada.
- [ ] Reclamar `cal-c` en Plan Coral (ya está a su nombre desde el 17-oct, 11:40).
- [ ] Re-medir la base de CAL-C con el banco reparado (`banco_fallos medir --tarea CAL-C --reps 3 --codigo-local`),
      porque 8 de sus casos se medían con el mensaje cortado.
- [ ] Seguir con C3, y medir C1 + C2 + C3 juntos al final con su mini-ronda A/B.
- [ ] En `r6-1`, valorar una **alerta de saldo** de OpenAI: PRE se quedó mudo dos veces esta semana por crédito.

**Gadea con Claude**
- [ ] Los 13 casos de CAL-A, empezando por re-medir el mecanismo de "sacar las preguntas del cliente y comprobar que
      la respuesta las cubre" con el banco reparado (se midió con mensajes cortados).
- [ ] El revisor del plan exacto contra la ficha (CAL-D).
- [ ] Cuando CAL-C esté cerrada: la ronda del golden visible completo (CAL-F) y CAL-G.

**Gonzalo (o quien lo coja)**
- [ ] Crear su rama desde `origin/feature/pre_gadea`.
- [ ] Reclamar `g-3` en Plan Coral y montar el simulador de usuario como modo de `run_synthetic_pre`.

**Gadea**
- [ ] Pedir a Diving Planet la tanda nueva de conversaciones para el examen oculto (o decidir los testers, `g-6`):
      tarda en llegar y es lo último que cierra CAL.
