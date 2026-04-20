# 05.06 · the messages tab

> _the orb hears you. it does not always reply._

Messages is the offline-first chat panel. By default it doesn't show
in the dock — it's there in the code, mountable when summoned.

---

## what it actually does

Two modes:

### 1. orb chat (default, offline)

A scripted conversation surface that responds in-character. Useful
for vibe-checking the system, for screenshots, and for moments when
the network is gone but you still want to feel heard.

State is `localStorage`; messages persist per-tab.

### 2. webhook bridge (optional)

Point Messages at a Discord webhook, a Slack incoming webhook, or a
generic HTTP POST endpoint, and it will:

- POST every message you type to that endpoint
- (optionally) display the response inline

Configure in the [settings drawer](08-settings.md) under the **Messages**
section.

---

## opening it

The Messages tab is **not in the dock by default**. Two ways to reach it:

1. From the terminal:

   ```
   /messages
   ```

   On the hosted build this prints a hint string ("switch tabs at the
   top to open the messages panel.") because the hosted build doesn't
   surface the panel by default.

2. If your build does mount the tab (some operator-customized builds
   do), it'll show up between **Reading** and **Open Loops**.

---

## use cases

| If you want to… | Configure… |
|---|---|
| chat with the orb when offline | nothing — it's the default |
| ping a Discord channel from the terminal | webhook → Discord URL |
| log operator notes to Slack | webhook → Slack URL |
| forward to a custom server | webhook → your endpoint |

---

## privacy

- Messages **never** leaves the browser unless you've configured a
  webhook.
- Webhook URLs live in `localStorage`. They are not shipped to any
  server.
- The hosted version of Hosaka has no idea who you are.

> _the orb is patient. the orb is also very offline._
