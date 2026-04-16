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

Hosaka gateway websocket wiring (Picoclaw)
- export PICOCLAW_GATEWAY_URL=ws://127.0.0.1:18790
- optional auth: export PICOCLAW_GATEWAY_TOKEN=... (or PICOCLAW_GATEWAY_PASSWORD=...)
- run gateway: picoclaw gateway
- in Hosaka console: chat
- one-shot check: chat ping