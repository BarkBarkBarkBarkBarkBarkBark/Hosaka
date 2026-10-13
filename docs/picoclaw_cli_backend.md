Command	Description
picoclaw onboard	Initialize config & workspace
picoclaw auth weixin	Connect WeChat account via QR
picoclaw agent -m "..."	Chat with the agent
picoclaw agent	Interactive chat mode
picoclaw gateway	Start the gateway
picoclaw status	Show status
picoclaw version	Show version info
picoclaw model	View or switch the default model
picoclaw cron list	List all scheduled jobs
picoclaw cron add ...	Add a scheduled job
picoclaw cron disable	Disable a scheduled job
picoclaw cron remove	Remove a scheduled job
picoclaw skills list	List installed skills
picoclaw skills install	Install a skill
picoclaw migrate	Migrate data from older versions
picoclaw auth login	Authenticate with providers

Hosaka console `/llm`
- `/llm`, `/llm <message>`, `/ask`, and `/chat` use `picoclaw agent`, not direct completions.
- PicoClaw owns native tools, workspace instructions, and the persistent `hosaka:tui` session.
  Hosaka maps the session alias to an explicit opaque PicoClaw key so it does
  not share the agent's default/social session. `/clear` inside `/chat` starts
  a fresh native session without deleting existing history.
- Each request includes Hosaka identity, actual host OS, hostname, and operator working directory.
- `/select llm` selects the model/provider used *inside* PicoClaw. An explicit
  `PICOCLAW_MODEL` instead selects an existing PicoClaw model alias.
- Hosaka creates a private temporary config overlay for the selected model,
  retaining PicoClaw's workspace and tool permissions, but disabling native
  web search (`tools.web.prefer_native=false`). Native `web_search_preview`
  is incompatible with the Chat Completions transport; normal web tools
  remain available. The original config is
  unchanged; temporary credentials are removed when the request finishes.
- PicoClaw must be installed and onboarded. Agent/config/provider failures are
  reported at the console; there is no direct OpenAI or offline fallback.
- The gateway is not required for console chat. Streaming is word-by-word
  presentation after the CLI response, not live model-token streaming.

Install and update defaults
- Fresh installs use OpenAI `gpt-4.1`; enter the API key once with hidden input.
- `HOSAKA_LOCAL_FIRST=1` opts fresh configurations into Ollama. Existing
  explicitly selected model aliases are preserved across runtime refreshes.
- `hosaka chat [-s session]` and `hosaka message [-s session] <text>` use the
  same saved provider and request overlay as console chat, rather than
  bypassing Hosaka configuration with a raw PicoClaw invocation.
- Appliance installs and deployments prepare both root and operator agent
  runtimes, preserving the shared private LLM configuration's operator ownership.

Hosaka gateway websocket wiring (Picoclaw)
- export PICOCLAW_GATEWAY_URL=ws://127.0.0.1:18790
- optional auth: export PICOCLAW_GATEWAY_TOKEN=... (or PICOCLAW_GATEWAY_PASSWORD=...)
- run gateway: picoclaw gateway
- in Hosaka console: chat
- one-shot check: chat ping