// hosaka install — Cloudflare Worker.
//
// Serves the one-line installer flow for install.hosaka.xyz by proxying
// a handful of static files out of the Hosaka repo on GitHub. No build
// step; edit in the repo, merge, and the worker picks up the new file
// on the next request (subject to CDN caching).
//
// Routes:
//   GET /            → install/install.sh
//   GET /windows     → install/install.ps1
//   GET /bin/<name>  → install/bin/<name>     (hosaka, hosaka.cmd, hosaka.ps1, …)
//   GET /version     → plain-text latest launcher version
//   GET /healthz     → "ok"
//
// Everything else is a 404 on purpose.

const TEXT_HEADERS = {
  "content-type": "text/plain; charset=utf-8",
  "cache-control": "public, max-age=300, s-maxage=300",
  "x-content-type-options": "nosniff",
  "strict-transport-security": "max-age=63072000; includeSubDomains; preload",
};

const ALLOWED_BIN = new Set([
  "hosaka",
  "hosaka.cmd",
  "hosaka.ps1",
]);

function ghRaw(env, relPath) {
  const base = `https://raw.githubusercontent.com/${env.REPO}/${env.REF}/${env.BASE_PATH}`;
  return `${base}/${relPath}`;
}

async function passthrough(env, relPath) {
  const upstream = await fetch(ghRaw(env, relPath), {
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!upstream.ok) {
    return new Response("not found", { status: 404, headers: TEXT_HEADERS });
  }
  return new Response(upstream.body, { status: 200, headers: TEXT_HEADERS });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);

    if (req.method !== "GET" && req.method !== "HEAD") {
      return new Response("method not allowed", { status: 405, headers: TEXT_HEADERS });
    }

    if (url.pathname === "/" || url.pathname === "/install.sh") {
      return passthrough(env, "install.sh");
    }
    if (url.pathname === "/windows" || url.pathname === "/install.ps1") {
      return passthrough(env, "install.ps1");
    }
    if (url.pathname.startsWith("/bin/")) {
      const name = url.pathname.slice("/bin/".length);
      if (!ALLOWED_BIN.has(name)) {
        return new Response("not found", { status: 404, headers: TEXT_HEADERS });
      }
      return passthrough(env, `bin/${name}`);
    }
    if (url.pathname === "/version") {
      // If you want per-launcher pinned versions later, serve a VERSION
      // file from the repo instead.
      return new Response(`${env.REF}\n`, { status: 200, headers: TEXT_HEADERS });
    }
    if (url.pathname === "/healthz") {
      return new Response("ok\n", { status: 200, headers: TEXT_HEADERS });
    }
    return new Response("not found", { status: 404, headers: TEXT_HEADERS });
  },
};
