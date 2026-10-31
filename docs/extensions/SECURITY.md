# Current security boundaries

## Explicitly approved trusted-local mode

The operator selected trusted-local execution pending a separate protected Linux
runner. Each approval is tied to a source digest, separate storage grant and
enablement. New installs never approve/enable packages. CLI approval and all
execution refuse root; public mode refuses authoring and execution. Trust/grant
mutations are not exposed through the web API.

Core invokes a fixed stdlib bridge in a child process with no shell, a copied
approved source snapshot, a fresh temporary HOME and allowlisted environment.
Parameters/results are schema checked; nonzero exit is failure even if stdout
claims success. Time/output/concurrency and ordinary process-group cleanup are
enforced. Context file methods reject escaping paths and symlinks; logs exclude
input/result/exception values. All API routes require loopback or bearer auth,
and reject cross-site origins and loopback Host rebinding.

**These controls are NOT an OS sandbox.** Approved arbitrary Python runs under
your user account and can read user-accessible credentials or perform network/
subprocess/file operations outside the context. Sanitizing the environment does
not hide backing secret files. Detached descendants and hostile same-user code
are not contained. Never approve code you do not trust. Linux isolation and
negative access tests remain required for protected/marketed execution.

The checks below describe the original authoring boundary. Host execution,
production context, safe mode and views now exist only under the explicit policy
above; the old unavailable statements are superseded.

Authoring/discovery never imports or executes package code. YAML is safely parsed,
referenced files are confined to the package, unknown schema/UI fields fail,
remote schema references are rejected, and metadata writes are atomic under a
process lock. Packages are disabled by default and receive no grants.

The import API additionally requires a loopback client and loopback browser
origin, even for authenticated remote operators. It cannot approve or enable
packages. Git imports accept HTTPS without embedded credentials and use isolated
HOME/configuration, no credential helpers/hooks/submodules and a 60-second
timeout. Imports copy validated source snapshots, never overwrite existing
packages/data, and do not install dependencies or execute package code. These
checks are not an OS sandbox or a Git download disk/network quota.

These checks protect the **metadata workflow**. They are not an OS sandbox:

- No OS-contained extension runner exists yet.
- No filesystem/network permission enforcement is claimed.
- Enabled state alone does not authorize execution; matching approval/grants are required.
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
