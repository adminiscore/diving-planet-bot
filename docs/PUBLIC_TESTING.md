# Cómo exponer el chat públicamente para pruebas

Esta guía explica cómo levantar el bot + Chatwoot localmente y exponerlos con una URL
pública (sin desplegar a un VPS) para que cualquier persona, desde cualquier
dispositivo, pueda probar el chat.

> **Para Claude:** si te han pasado este documento, ejecuta cada bloque de comandos
> en orden, en una terminal **bash** (Git Bash en Windows), desde la raíz del repo.
> Al final debes obtener y comunicar al usuario un link `https://...trycloudflare.com/chat`.
> No necesitas pedir confirmación para los pasos de este documento salvo que algo falle.

## Qué vamos a montar

| Pieza | Puerto | Qué es |
|---|---|---|
| Postgres + Redis | 5432 / 6379 | Dependencias del bot (docker-compose.yml) |
| Chatwoot (Rails + worker) | 3300 | UI de chat (docker-compose.yml, perfil `chatwoot`) |
| Bot público | 8001 | Igual que el bot normal, pero con la ruta extra `/chat` que sirve el widget embebido. Vive en `docker-compose.public.yml` y **no toca** el contenedor de desarrollo (`dp-dev-bot`, puerto 8000) |
| Cloudflare Tunnel ×2 | — | Hace público el puerto 3300 (Chatwoot) y el puerto 8001 (bot) sin abrir el router ni configurar nada en casa |

No usamos ngrok ni serveo: ambos, en su plan gratis, muestran una pantalla de aviso
("¿seguro que quieres visitar este sitio?") a cualquier navegador real, y esa pantalla
también bloquea el iframe del widget de Chatwoot — el botón de chat nunca llega a
aparecer. Cloudflare Tunnel (modo "quick tunnel", sin cuenta) no tiene ese problema.

## 1. Requisitos (una sola vez por máquina)

```bash
# Docker Desktop debe estar abierto y corriendo
docker ps   # si esto falla, abre Docker Desktop y espera a que arranque

# cloudflared (cliente de Cloudflare Tunnel)
winget install --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
```

Tras instalar, busca el ejecutable (winget no siempre actualiza el PATH en la sesión
actual):

```bash
find "/c/Users/$USER/AppData/Local/Microsoft/WinGet/Packages/" -iname "cloudflared.exe"
```

Guarda esa ruta en una variable para los siguientes comandos:

```bash
CF="<ruta-completa-a-cloudflared.exe>"
```

## 2. Levantar Postgres, Redis y Chatwoot

```bash
cd /ruta/al/repo/diving-planet-bot
docker compose up -d                       # Postgres + Redis
docker compose --profile chatwoot up -d    # + Chatwoot
```

Comprueba que responde:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3300   # debe dar 200
```

## 3. Levantar el bot público (puerto 8001)

Este compose es independiente del bot de desarrollo — se puede tener los dos a la vez.

```bash
docker compose -f docker-compose.public.yml up -d --build
curl -s http://localhost:8001/health   # {"status":"ok",...}
```

## 4. Abrir los túneles de Cloudflare

Se necesitan **dos** túneles: uno para Chatwoot (3300) y otro para el bot (8001).

```bash
"$CF" tunnel --url http://localhost:3300 > /tmp/cf_chatwoot.log 2>&1 &
"$CF" tunnel --url http://localhost:8001 > /tmp/cf_bot.log 2>&1 &
sleep 8
grep -o "https://[a-z0-9-]*\.trycloudflare\.com" /tmp/cf_chatwoot.log | head -1   # URL de Chatwoot
grep -o "https://[a-z0-9-]*\.trycloudflare\.com" /tmp/cf_bot.log | head -1       # URL del bot
```

Guarda las dos URLs que salgan. Son aleatorias y cambian cada vez que se relanza el túnel.

## 5. Conectar la URL de Chatwoot al bot

El bot necesita saber la URL pública de Chatwoot para poder incrustar el widget
correctamente en `/chat`. Se configura en `.env`:

```bash
# Edita la línea CHATWOOT_BASE_URL en .env con la URL de Chatwoot del paso 4, ej.:
# CHATWOOT_BASE_URL=https://essential-highly-inch-affair.trycloudflare.com
```

Tras editar `.env`, reconstruye el contenedor del bot público para que recoja el cambio:

```bash
docker compose -f docker-compose.public.yml up -d
sleep 5
curl -s http://localhost:8001/chat | grep -o "chatwootSDK"   # debe aparecer
```

## 6. Apuntar el webhook de Chatwoot al bot

1. Abre **http://localhost:3300** → Settings → Integrations → Webhooks
2. Pon como URL: `<URL-del-bot-del-paso-4>/webhooks/chatwoot`
   - Ejemplo: `https://summary-climb-married-britain.trycloudflare.com/webhooks/chatwoot`
3. Guarda

## 7. Verificación final

```bash
URL_BOT="<URL-del-bot-del-paso-4>"
curl -s -o /dev/null -w "%{http_code}\n" "$URL_BOT/chat" -H "User-Agent: Mozilla/5.0" -H "Sec-Fetch-Mode: navigate"   # 200
curl -s -X POST "$URL_BOT/webhooks/chatwoot" -H "Content-Type: application/json" -d '{"event":"test"}'              # {"status":"ok"}
```

El link para compartir es:

```
<URL-del-bot-del-paso-4>/chat
```

## ⚠️ Importante: la URL cambia

Estos túneles de Cloudflare son del tipo "quick tunnel" (sin cuenta, gratis). Cloudflare
genera una URL aleatoria nueva **cada vez que se lanza el proceso `cloudflared`**. Si:

- se cierra la terminal,
- se reinicia el PC,
- o el túnel se cae por cualquier motivo,

al volver a lanzar `cloudflared tunnel --url ...` obtendrás una URL distinta. Cuando eso
pase hay que repetir, en este orden:

1. Relanzar los dos túneles (paso 4) → apunta las nuevas URLs.
2. Si cambió la de **Chatwoot**: actualizar `CHATWOOT_BASE_URL` en `.env` y repetir el
   paso 5 (reconstruir el contenedor del bot público).
3. Si cambió la de **bot**: actualizar el webhook en Chatwoot (paso 6).
4. El link que compartes con la gente es siempre `<URL-del-bot-actual>/chat`.

**Por qué no se puede tener una URL fija gratis sin más:** para fijar la URL para
siempre habría que crear una cuenta gratuita en Cloudflare y asociar un dominio
gestionado por Cloudflare a un túnel "nombrado" (`cloudflared tunnel create ...` en vez
de `--url`). El dominio de producción `divingplanet.org` está en HostGator, no en
Cloudflare, y mover sus nameservers para conseguir esto metería en riesgo el sitio en
producción solo por un entorno de pruebas. La alternativa segura sería comprar un
dominio nuevo y barato solo para esto y meterlo en Cloudflare — si en algún momento se
quiere eso, dilo y se monta así.

## Si algo no funciona

- **No sale el botón de chat / la página está vacía:** revisa que Docker esté
  corriendo (`docker ps`) y que los 5 contenedores (`postgres`, `redis`,
  `dp-dev-chatwoot`, `dp-dev-chatwoot-worker`, `dp-public-bot`) estén `Up`.
- **`/chat` da 404:** el contenedor `dp-public-bot` no tiene el código actualizado;
  reconstruye con `docker compose -f docker-compose.public.yml up -d --build`.
- **El webhook no responde:** confirma que la URL en Chatwoot termina en
  `/webhooks/chatwoot` y que el túnel del bot sigue vivo (revisa `/tmp/cf_bot.log`).
