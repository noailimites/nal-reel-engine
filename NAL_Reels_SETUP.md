# NAL Fábrica IG — Track A: Reels automáticos (SETUP)

Motor de reels **funk / kinetic-typography** que convierte cualquier fila de Notion
(el mismo JSON de los carruseles) en un reel 9:16 con marca Café Editorial, cortes
secos al beat y groove funk sintetizado. **0 créditos** (no usa Opus). Corre como
servicio HTTP y se publica desde Pipedream, igual que los carruseles.

## Arquitectura (paralela a A/B/C)

```
Notion 📅 (Estado=Programado, Formato=Reel)
   └─ Workflow D (Pipedream) ─ POST /render ─→ NAL Reel Engine (Render, Docker+ffmpeg)
                                                   └─ devuelve URL del .mp4
   └─ Meta Graph media_type=REELS (video_url) → poll FINISHED → media_publish
   └─ Notion = Publicado (Permalink + IG Media ID)
```

## Archivos (este folder)
- `reel_engine.py` — motor (JSON carrusel → MP4). Auto-ajusta texto (nada se corta).
- `service.py` — servicio HTTP (POST /render, GET /vid/<id>.mp4, GET / health).
- `Dockerfile`, `requirements.txt` — deploy con ffmpeg.
- `fonts/` — Fraunces + DM Sans.
- `pipedream_WFD_reel.js` — Workflow D.

## 1) Deploy del servicio (Render.com, Docker)
1. Repo GitHub nuevo (ej. `noailimites/nal-reel-engine`) con TODO este folder.
2. Render → New → **Web Service** → el repo → Runtime **Docker** → plan Free.
3. Env vars: `NAL_RENDER_KEY` (botón Generate; guárdalo en Bitwarden). `PUBLIC_BASE_URL`
   se resuelve solo vía `RENDER_EXTERNAL_URL`.
4. Verificar: `GET /` → `{ok:true}`. `POST /render` con `{carousel:{...}}` → `{url,...}`.
   (Free se duerme ~50s en frío; irrelevante porque el reel está gateado.)

## 2) Notion — discriminador de formato (IMPORTANTE)
- Agregar propiedad **Formato** (select): `Carrusel` / `Reel`.
- **Guardia crítica en Workflow B (carruseles):** añadir al filtro `Formato != Reel`
  (o `= Carrusel`). Si no, B intentaría publicar un reel como carrusel y rompe.
- Confirmar que existan `Permalink` (url) e `IG Media ID` (text) — ya se usan en B.

## 3) Origen de las filas de reel (v1)
Una fila de reel = fila del Calendario con **Formato=Reel** + columna **JSON** (mismo
esquema de carrusel: `pilar`, `hook`, `laminas[].titulo`). Para el ritmo de 1/semana:
marca 1 carrusel aprobado como `Reel` (o duplícalo y cámbiale Formato). *(Fase 2: que
Workflow C/A siembren la fila de reel automáticamente cada semana.)*

## 4) Workflow D (Pipedream)
1. Nuevo workflow, trigger **Schedule** (ej. viernes 9:00 AM America/Caracas — así no
   choca con B los L/M/V; o el día que definas).
2. 1 paso **Node.js**, pega `pipedream_WFD_reel.js`, conecta la cuenta **notion**.
3. Env vars del proyecto: `NAL_REEL_SERVICE_URL`, `NAL_RENDER_KEY`, `META_TOKEN`
   (el mismo nunca-expira de B), `IG_USER_ID` = 17841448926883700,
   `NOTION_DS` = 85fd2f55-54aa-4e4f-8217-fb6cd0455033, `GRAPH_VER` = v25.0,
   `PUBLISH_LIMIT` = 1.
4. Deploy + Generate Test Event (con 0 reels Programados = publica cero, seguro).

## Notas
- Publicación de reels usa `media_type=REELS` + `video_url` público (el servicio lo aloja
  20 min, suficiente para que Meta lo ingiera) + poll a `status_code=FINISHED` (los reels
  tardan más que las imágenes) + `media_publish`.
- El MP4 sale H.264/AAC yuv420p + `faststart` (requisito de Meta).
- Créditos Opus = 0. Opus queda solo para el reel mensual "premium" (voz clonada), aparte.
