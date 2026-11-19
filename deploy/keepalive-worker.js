export default {
  async scheduled(event, env, ctx) {
    const url = env.RENDER_URL || "https://momenz.onrender.com/health";
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
