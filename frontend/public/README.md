# Static assets

Everything in `frontend/public/` is copied verbatim into the build at
its root path.

## Custom domain for GitHub Pages

Copy `CNAME.example` to `CNAME` and replace the hostname with yours:

```bash
cp frontend/public/CNAME.example frontend/public/CNAME
# edit frontend/public/CNAME -> your-domain.example
```

When a `CNAME` file is present, the GitHub Pages workflow serves the
build at `/` instead of `/<repo>/`. See
[`docs/deployment.md`](../../docs/deployment.md) for DNS details.
