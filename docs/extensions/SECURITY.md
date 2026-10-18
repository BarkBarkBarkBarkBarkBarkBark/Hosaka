# Current security boundaries

Authoring/discovery never imports or executes package code. YAML is safely parsed,
referenced files are confined to the package, unknown schema/UI fields fail,
remote schema references are rejected, and metadata writes are atomic under a
process lock. Packages are disabled by default and receive no grants.

These checks protect the **metadata workflow**. They are not an OS sandbox:

- No Hosaka extension runner or production context exists yet.
- No filesystem/network permission enforcement is claimed.
- Enabled state does not imply authorization or make a package runnable.
- Standalone tests execute trusted code with the caller's full user privileges.
- Scaffolding or linking a directory does not confine an authoring agent's shell.
- Registry digests detect local changes; they are not signatures or source
  authenticity proofs. User-writeable metadata is not a trust anchor against
  malicious same-user processes. File checks do not eliminate TOCTOU attacks.

For later Linux appliance execution, preserve the market brief's requirement for
OS-enforced isolation, secret-free environments/mounts, denied network by default,
narrow data capabilities, bounded output/time/processes and negative access tests.
If unavailable, fail explicitly; do not launch unrestricted code silently.
macOS/Windows trusted-only execution requires explicit owner choice and an honest
platform label, not a claim of Linux-equivalent containment.

Public/hosted extension management and execution are not added by this slice.
The CLI/TUI entrypoint rejects authoring in `HOSAKA_PUBLIC_MODE`; public Docker
core boot skips package bootstrap rather than failing core startup.
Do not widen native PTY or API authorization to expose packages. No provider or
upstream PicoClaw migration occurs during authoring or bootstrap.
