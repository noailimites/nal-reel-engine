// NAL Fábrica IG — Workflow D (Publicar REELS)
// Lee Notion (Estado=Programado, Canal=Instagram, Formato=Reel) -> render en el
// servicio de reels -> Meta Graph media_type=REELS -> media_publish -> Notion=Publicado.
// Paralelo a Workflow B (carruseles). 1 paso Node.js. Conexión: notion.
//
// Env vars del proyecto Pipedream:
//   NAL_REEL_SERVICE_URL   (ej. https://nal-reel-engine.onrender.com)
//   NAL_RENDER_KEY         (x-api-key del servicio)
//   META_TOKEN             (System User token nunca-expira — el mismo de WF B)
//   IG_USER_ID             (17841448926883700)
//   NOTION_DS              (data source id: 85fd2f55-54aa-4e4f-8217-fb6cd0455033)
//   GRAPH_VER              (v25.0)  PUBLISH_LIMIT (1)

import { Client } from "@notionhq/client";

export default defineComponent({
  props: { notion: { type: "app", app: "notion" } },
  async run({ steps, $ }) {
    const notion = new Client({ auth: this.notion.$auth.oauth_access_token });
    const DS = process.env.NOTION_DS;
    const G = process.env.GRAPH_VER || "v25.0";
    const IG = process.env.IG_USER_ID;
    const TOKEN = process.env.META_TOKEN;
    const SVC = process.env.NAL_REEL_SERVICE_URL.replace(/\/$/, "");
    const LIMIT = parseInt(process.env.PUBLISH_LIMIT || "1", 10);
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    // 1) siguiente reel aprobado (más viejo primero)
    const q = await notion.dataSources.query({
      data_source_id: DS,
      page_size: LIMIT,
      sorts: [{ timestamp: "created_time", direction: "ascending" }],
      filter: {
        and: [
          { property: "Estado", status: { equals: "Programado" } },
          { property: "Canal", select: { equals: "Instagram" } },
          { property: "Formato", select: { equals: "Reel" } },
        ],
      },
    });
    if (!q.results.length) return $.export("info", "No hay reels Programados");

    const results = [];
    for (const page of q.results) {
      const P = page.properties;
      const jsonTxt = (P.JSON?.rich_text || []).map((t) => t.plain_text).join("");
      const caption = (P.Caption?.rich_text || []).map((t) => t.plain_text).join("");
      if (!jsonTxt) { results.push({ id: page.id, skip: "sin JSON" }); continue; }
      const carousel = JSON.parse(jsonTxt);

      // 2) render del reel
      const rr = await fetch(`${SVC}/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": process.env.NAL_RENDER_KEY },
        body: JSON.stringify({ carousel }),
      });
      if (!rr.ok) throw new Error(`render ${rr.status}: ${await rr.text()}`);
      const { url: videoUrl } = await rr.json();

      // 3) crear container REELS
      const cr = await fetch(`https://graph.facebook.com/${G}/${IG}/media`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          media_type: "REELS",
          video_url: videoUrl,
          caption,
          share_to_feed: true,
          access_token: TOKEN,
        }),
      });
      const cj = await cr.json();
      if (!cj.id) throw new Error(`container: ${JSON.stringify(cj)}`);

      // 4) poll status hasta FINISHED (reels tardan en procesar)
      let ready = false;
      for (let i = 0; i < 30; i++) {
        await sleep(4000);
        const st = await fetch(`https://graph.facebook.com/${G}/${cj.id}?fields=status_code&access_token=${TOKEN}`).then((r) => r.json());
        if (st.status_code === "FINISHED") { ready = true; break; }
        if (st.status_code === "ERROR") throw new Error(`ingest ERROR ${JSON.stringify(st)}`);
      }
      if (!ready) throw new Error("timeout esperando FINISHED");

      // 5) publicar
      const pub = await fetch(`https://graph.facebook.com/${G}/${IG}/media_publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ creation_id: cj.id, access_token: TOKEN }),
      }).then((r) => r.json());
      if (!pub.id) throw new Error(`publish: ${JSON.stringify(pub)}`);

      // 6) permalink + Notion=Publicado
      const perm = await fetch(`https://graph.facebook.com/${G}/${pub.id}?fields=permalink&access_token=${TOKEN}`).then((r) => r.json());
      await notion.pages.update({
        page_id: page.id,
        properties: {
          Estado: { status: { name: "Publicado" } },
          Permalink: { url: perm.permalink || null },
          "IG Media ID": { rich_text: [{ text: { content: pub.id } }] },
        },
      });
      results.push({ id: page.id, media_id: pub.id, permalink: perm.permalink });
    }
    return $.export("published", results);
  },
});
