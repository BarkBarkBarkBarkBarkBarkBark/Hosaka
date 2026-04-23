# install.hosaka.xyz — Cloudflare Worker

Serves the one-line installer for the Hosaka client. It's a thin
pass-through: every request is proxied to the `install/` directory of
the `Hosaka` repo on GitHub, with a short CDN cache.

## Deploy

```bash
cd Hosaka/install/worker
npm install
npx wrangler login                     # first time only
npx wrangler deploy
```

On first deploy you'll also need to bind the custom domain:

1. Add `hosaka.xyz` to Cloudflare (Dashboard → Add Site → free plan).
2. Switch the registrar's nameservers (e.g. GoDaddy → Cloudflare's two
   assigned NS records). Propagation takes ~1 h.
3. In the Worker's dashboard: **Settings → Domains & Routes → Add
   Custom Domain → `install.hosaka.xyz`**. Cloudflare creates the
   `AAAA`/`A` records and provisions TLS automatically.

Subsequent deploys are just `npm run deploy`.

## Smoke test

```bash
curl -fsSL https://install.hosaka.xyz/healthz
curl -fsSL https://install.hosaka.xyz/version
curl -fsSL https://install.hosaka.xyz            | head
curl -fsSL https://install.hosaka.xyz/bin/hosaka | head
curl -fsSL https://install.hosaka.xyz/windows    | head
```

## Cutting a staging channel

Keep a second worker on `install-next.hosaka.xyz` that points at a
different branch:

```bash
npx wrangler deploy --name hosaka-install-next \
  --var REF:next \
  --route "install-next.hosaka.xyz/*"
```

That way you can dog-food installer changes on a branch without
blasting every fresh customer with WIP shell scripts.
