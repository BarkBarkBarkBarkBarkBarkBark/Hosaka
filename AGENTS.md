# Hosaka agent entrypoint

- The Python TUI is canonical; preserve its thin React/Electron host and small
  Menu button. Flatpak apps, native RetroArch games and extensions are separate.
- For a new application, start with
  [the extension agent guide](docs/extensions/AGENT_GUIDE.md), the
  [implemented specification](docs/extensions/SPECIFICATION.md), and the
  [reference package](examples/extensions/reference-extension/). Ordinary
  extension work belongs outside this core checkout.
- Read [the extension roadmap](docs/extension_plan.md) for delivery status and
  [the market brief](docs/hosaka_market_preparation_brief.md) for appliance gates.
  Planned commands, UI and sandboxing are not implemented merely by documenting
  them. Request a tracked platform upgrade when the current API is insufficient.
- Execution is explicit, digest-approved trusted-local mode, not an OS sandbox.
  Never silently approve/enable packages or grant storage. Root/public execution
  is refused; do not weaken that boundary to work around service configuration.
- Reuse [native paths](hosaka/paths.py); preserve user packages, data, sessions,
  credentials and permissions. Do not migrate standalone PicoClaw implicitly.
- Follow [issue tracking](docs/issue-tracking.md) before nontrivial core changes.
  Run focused existing tests. No automatic commits, deployment or credential
  changes. Keep public/hosted execution restrictions intact.
- The [observability catalog](docs/hosaka.features.yaml) owns core feature
  metadata. Regenerate derived docs with `PY=.hosakavenv/bin/python bash
  scripts/gen_docs.sh`; do not hand-edit generated artifacts.
