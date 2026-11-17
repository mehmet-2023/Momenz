/**
 * Render free servisini uyandırır / açık tutar.
 *
 * Render free 15 dk hareketsizlikte uyur, 30 gün hareketsizlikte silinir.
 * Cloudflare Worker Cron (günlük 100k istek ücretsiz) her 10 dakikada
 * /health'e ping atar → uyanma süresi ve silinme riski kalkar.
 *
 * Kurulum:
 *   wrangler secret put RENDER_URL
 *   wrangler deploy
 */
export default {
  async scheduled(event, env, ctx) {
    const url = env.RENDER_URL || "https://momenz.onrender.app/health";
    ctx.waitUntil(
      fetch(url, {
        headers: { "User-Agent": "Momenz-Keepalive/1.0" },
      }).then((r) => {
        console.log(`keepalive ${new Date().toISOString()} -> ${r.status}`);
      }).catch((e) => {
        console.error(`keepalive failed: ${e}`);
      })
    );
  },
};
