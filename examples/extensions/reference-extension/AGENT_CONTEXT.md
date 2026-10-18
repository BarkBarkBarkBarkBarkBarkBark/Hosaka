# Reference package context

Read the installed platform's `docs/extensions/AGENT_GUIDE.md` and specification.
This is standalone extension source, not a core customization workspace.

- Keep the extension ID, action schemas, callable and declarative view consistent.
- Persist user data only through the caller-provided context, never inside source.
- Run the local unittest suite explicitly after inspecting/trusting the source.
- Do not edit core, provider configurations, other extensions or shared runtime
  state to make this package work.
- Current authoring phase validates the UI but does not render or execute it
  through Hosaka. Do not claim permission enforcement or a working host runner.
