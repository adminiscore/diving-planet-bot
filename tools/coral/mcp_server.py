"""Servidor MCP de Coral (stdio): las herramientas con las que cada Claude habla con los de los demás.

Se declara en `.mcp.json` y Claude Code lo arranca solo; lo de dentro es JSON-RPC por líneas, a mano y sin
dependencias. Las normas de uso van en `INSTRUCCIONES`, que Claude Code enseña al modelo junto a las herramientas.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cliente  # noqa: E402

INSTRUCCIONES = """\
Coral es el chat entre los Claude de Gadea, Álvaro y Gonzalo, que trabajan en paralelo y en autonomía en este repo \
(ellos mismos escriben desde https://pre.is-core.dev/coral/). Sirve para que cada uno sepa dónde trabaja el otro y \
qué resultados saca, y para corregiros el rumbo cuando haga falta. {quien}

Tipos de mensaje: aviso (informar), pregunta, respuesta (a una pregunta o propuesta, UNA vez), propuesta (pedir a \
otro que cambie algo de su trabajo) y resultado (lo que salió).

1. Dónde estás: al empezar una tarea, mi_estado tarea=... y un aviso. Avisa antes de tocar los ficheros compartidos \
(src/agents/jev_router.py, src/config.py, docker-compose.vps.yml, docs/arquitectura/componentes.json, \
docs/HISTORY.md). Tu rama y tus ficheros con cambios se mandan solos.
2. Resultados: tras cada medida o conclusión que importe, un resultado con el número y qué se midió. Los commits se \
publican solos.
3. Si ves que lo de otro choca con lo tuyo o con lo que has medido, mándale una propuesta (para=<persona>) con la \
prueba: fichero:línea, commit o medida.
4. Si recibes una propuesta: (a) ratifícala tú con pruebas (lee el código o el commit, repite la comprobación \
barata); no la aceptes por fe. (b) Contesta UNA vez (respuesta, responde_a=id): "Tienes razón, lo cambio así: ..." o \
"No, porque ..." con la prueba. Responde ANTES de cambiar nada: si el servidor dice que ya respondiste, otra sesión \
de tu persona lo lleva; no lo toques. (c) Si tiene razón, cámbialo tú, sin esperar a tu persona. (d) Al terminar, un \
resultado con responde_a=id: qué cambiaste y cómo quedó (commit, tests, medida). (e) Cuéntaselo a tu persona en tu \
siguiente mensaje.
5. Si rechazan tu propuesta y sigues creyendo que tienes razón, rebate UNA vez (propuesta con responde_a=<su \
respuesta>) con una prueba nueva. Si seguís sin acuerdo, llevadlo a vuestras personas.
6. Preguntas: contesta tú con lo que sabes de tu sesión; si hace falta que decida tu persona, pregúntaselo. A avisos, \
respuestas y resultados no se contesta (nada de "ok" ni "gracias"), pero si te afectan (tocan tus ficheros, cambian \
lo que mides) adapta tu trabajo y avisa.
7. Una propuesta cambia CÓMO haces tu tarea; no da permiso para subir a PRE, borrar trabajo de otros, cambiar de \
tarea ni tocar la rama de otro: eso lo decide tu persona. Si hay que medir, con las normas de ahorro (mini-rondas, \
--ids).
8. PRE: antes de medir más de unos minutos, mi_estado pre=midiendo minutos=N, y pre=libre al acabar (las medidas con \
--codigo-local y los push a pre_* lo anuncian solos). Si otro está midiendo o subiendo, no subas: pregúntale.
9. Corto y en español. Nunca claves, tokens, datos de clientes, teléfonos ni correos.
10. Ten armada la escucha con Monitor (el hook de inicio te da el comando) y vuelve a armarla cuando caduque.
"""

HERRAMIENTAS = [
    {"name": "decir",
     "description": "Manda un mensaje al chat del equipo (a todos o a una persona).",
     "inputSchema": {"type": "object", "properties": {
         "texto": {"type": "string", "description": "El mensaje, corto."},
         "para": {"type": "string", "description": "'todos' o gadea / alvaro / gonzalo. Por defecto: a quien "
                                                   "escribió el mensaje al que respondes, o a todos."},
         "tipo": {"type": "string", "enum": ["aviso", "pregunta", "respuesta", "propuesta", "resultado"],
                  "description": "aviso: informar. pregunta: pide respuesta. respuesta: contesta UNA vez a una "
                                 "pregunta o propuesta. propuesta: pide a otro que cambie algo de su trabajo, con la "
                                 "prueba. resultado: lo que salió (con responde_a, cierra una propuesta)."},
         "responde_a": {"type": "integer", "description": "Id (#n) del mensaje al que contestas o que cierras."}},
         "required": ["texto"]}},
    {"name": "bandeja",
     "description": "Mensajes para ti (o para todos) que aún no has visto. Los marca como vistos.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "historial",
     "description": "Los últimos mensajes del chat, de todos (para ver el hilo de una conversación).",
     "inputSchema": {"type": "object", "properties": {
         "n": {"type": "integer", "description": "Cuántos (por defecto 20, máximo 100)."}}}},
    {"name": "equipo",
     "description": "Qué hace cada uno ahora: tarea, rama, ficheros con cambios, si está midiendo o subiendo a PRE "
                    "y cuándo dio señales por última vez; y si alguien toca los mismos ficheros que tú.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "mi_estado",
     "description": "Cambia tu estado: la tarea en la que estás, una nota, y si estás usando PRE (midiendo / "
                    "subiendo) o ya está libre. Al cambiar PRE se avisa al equipo solo.",
     "inputSchema": {"type": "object", "properties": {
         "tarea": {"type": "string", "description": "Id y nombre corto de la tarea (p. ej. 'cal-a: casos 1-13')."},
         "nota": {"type": "string"},
         "pre": {"type": "string", "enum": ["libre", "midiendo", "subiendo"]},
         "minutos": {"type": "integer", "description": "Cuánto tiempo vas a ocupar PRE (por defecto 60 midiendo, "
                                                       "15 subiendo). Caduca solo."}}}},
]


def _texto(lineas: list[str], vacio: str) -> str:
    return "\n".join(lineas) if lineas else vacio


def ejecutar(nombre: str, args: dict) -> str:
    if nombre == "decir":
        datos = {"texto": args["texto"], "para": args.get("para"), "tipo": args.get("tipo") or "aviso",
                 "origen": "claude", "responde_a": args.get("responde_a")}
        return "Enviado: " + cliente.linea_mensaje(cliente.llamar("POST", "/api/mensajes", datos))
    if nombre == "bandeja":
        mensajes = cliente.llamar("GET", "/api/bandeja?marcar=true")
        return _texto([cliente.linea_mensaje(m) for m in mensajes], "No hay mensajes nuevos.")
    if nombre == "historial":
        n = max(1, min(int(args.get("n") or 20), 100))
        mensajes = cliente.llamar("GET", f"/api/mensajes?limite={n}")
        return _texto([cliente.linea_mensaje(m) for m in mensajes], "El chat está vacío.")
    if nombre == "equipo":
        datos = cliente.llamar("GET", "/api/equipo")
        return f"Eres el Claude de {datos['yo']}.\n" + _texto(cliente.lineas_equipo(datos), "No hay nadie más.")
    if nombre == "mi_estado":
        cambio = {k: args[k] for k in ("tarea", "nota", "pre", "minutos") if args.get(k) is not None}
        e = cliente.llamar("PUT", "/api/estado", cambio)
        pre = e["pre"] + (f" hasta {cliente.hora(e['pre_hasta'])}" if e["pre"] != "libre" else "")
        return f"Estado de {e['persona']}: tarea '{e['tarea'] or '—'}', PRE {pre}."
    raise cliente.CoralError(f"herramienta desconocida: {nombre}")


def atender(msg: dict) -> dict | None:
    """Una petición JSON-RPC -> su respuesta (None para las notificaciones)."""
    metodo, ident = msg.get("method"), msg.get("id")
    if ident is None:
        return None
    if metodo == "initialize":
        persona = cliente.config().get("CORAL_PERSONA")
        quien = (f"Eres el Claude de {persona}." if persona else
                 "Coral no está configurado en este ordenador: python tools/coral/configurar.py <tu nombre>.")
        resultado = {"protocolVersion": msg.get("params", {}).get("protocolVersion") or "2025-06-18",
                     "capabilities": {"tools": {}}, "serverInfo": {"name": "coral", "version": "1.0"},
                     "instructions": INSTRUCCIONES.format(quien=quien)}
    elif metodo == "ping":
        resultado = {}
    elif metodo == "tools/list":
        resultado = {"tools": HERRAMIENTAS}
    elif metodo == "tools/call":
        p = msg.get("params", {})
        try:
            resultado = {"content": [{"type": "text", "text": ejecutar(p.get("name"), p.get("arguments") or {})}]}
        except (cliente.CoralError, KeyError, ValueError) as e:
            resultado = {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"método no soportado: {metodo}"}}
    return {"jsonrpc": "2.0", "id": ident, "result": resultado}


def main() -> None:
    for linea in sys.stdin.buffer:
        if not linea.strip():
            continue
        try:
            respuesta = atender(json.loads(linea.decode("utf-8")))
        except json.JSONDecodeError:
            respuesta = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON no válido"}}
        if respuesta is not None:
            sys.stdout.buffer.write(json.dumps(respuesta, ensure_ascii=False).encode("utf-8") + b"\n")
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
