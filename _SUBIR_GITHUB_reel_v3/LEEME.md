# Deploy motor de reels v3 — noailimites/nal-reel-engine

## Qué cambia
v3 agrega lo que hacía falta para reels de convocatoria (fechas, precios, cupos):
- `sub` por lámina — segunda línea chica en DM Sans, color acento.
- `cta_title` / `cta_handle` / `cta_sub` — el CTA ya NO está hardcodeado en "Sígueme." + @noailimites.ia.
- `bg`, `anim`, `beats` por lámina + `cover_beats` / `cover_sub` / `cta_beats`.
- Saltos de línea explícitos con `\n` en cualquier título.
- Fix de layout del CTA (antes se solapaban dominio y título con offsets fijos).

Compatible hacia atrás: un JSON viejo (sin campos nuevos) renderiza igual que antes.

## Pasos
1. Respaldar el actual: en GitHub, renombrar `reel_engine.py` a `reel_engine_v2_backup.py`.
2. Subir el `reel_engine.py` de esta carpeta a la RAÍZ del repo.
   (`service.py` hace `from reel_engine import build_reel` — el nombre del archivo debe quedar `reel_engine.py`.)
3. Commit → Render redeploya solo.
4. Smoke test:
   curl -s -X POST https://nal-reel-engine.onrender.com/render \
     -H "x-api-key: $NAL_REEL_KEY" -H "content-type: application/json" \
     -d @reel_T2_promo.json
   Debe devolver {"url": "..."} — abrir esa URL y verificar que se ve el reel de Temporada 2.

## OJO antes de sembrar la fila en Notion
El JSON del reel T2 usa campos v3. Si se siembra la fila en el Calendario ANTES de este deploy,
Workflow D la renderiza con el motor viejo: ignora `sub` y `cta_*`, y el reel sale sin fechas
y cerrando con "Sígueme." en vez de noailimites.com. Deploy primero, siembra después.

## Estado del servicio (verificado 15-sep-2026)
El servicio **ESTÁ VIVO**: Render dashboard muestra `nal-reel-engine` en estado **Live**,
Docker/Free, commit `b8a7b1e`, Service ID `srv-d9dr29ernols73d1ihr0`.
Es instancia Free: **se duerme por inactividad y la primera request puede tardar 50s o más**
(cold start). Eso NO es una falla — el WF D tiene timeout de 300s, le da de sobra.
Al hacer el smoke test, si la primera llamada tarda, esperar; no asumir que el servicio murió.
Nota: desde los shells de Claude el egress bloquea `onrender.com`, así que el smoke test
se hace desde el navegador o desde la máquina de Choco.
