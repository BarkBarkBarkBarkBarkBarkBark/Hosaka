# Reference package context

Read the installed platform's `docs/extensions/AGENT_GUIDE.md` and specification.
This is standalone extension source, not a core customization workspace.

- Keep the extension ID, action schemas, callable and declarative view consistent.
- Persist user data only through the caller-provided context, never inside source.
- Run the local unittest suite explicitly after inspecting/trusting the source.
- Do not edit core, provider configurations, other extensions or shared runtime
  state to make this package work.
- The host now renders the declarative UI and runs explicitly approved code in
  a bounded trusted-local worker. Owner approval/grants and enablement are
  separate. Do not self-approve on the owner's behalf.
- Trusted-local is not OS isolation. Environment sanitation and context path
  checks do not prevent arbitrary approved Python from accessing user files,
  sockets or subprocesses. Root/public execution is refused.
