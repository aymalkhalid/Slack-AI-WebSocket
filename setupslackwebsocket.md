# Slack Socket Mode setup

Configure the **AI Chatbot** Slack app and run `main.py` over [Socket Mode](https://api.slack.com/apis/connections/socket) — no public HTTP endpoint.

**What this bot does**


| Trigger               | Slack event              | Handler                          |
| --------------------- | ------------------------ | -------------------------------- |
| @mention in a channel | `app_mention`            | `handle_mentions`                |
| Direct message        | `message.im` → `message` | `handle_direct_messages`         |
| Reply style           | Threaded channel replies | `say(text=reply, thread_ts=...)` |
| Memory style          | MongoDB Atlas turns       | `thread_ts` / DM channel key     |


---

## Prerequisites

- Slack workspace with permission to [create apps](https://api.slack.com/apps)
- Python 3.10+
- Packages installed from `requirements.txt` (`slack-bolt`, `python-dotenv`, `openai`, `pymongo`, `dnspython`)
- MongoDB Atlas connection string for persistent memory

---

## Quick reference: two tokens


|                 | App-level token                                     | Bot token                               |
| --------------- | --------------------------------------------------- | --------------------------------------- |
| **Prefix**      | `xapp-`                                             | `xoxb-`                                 |
| **Env var**     | `SLACK_APP_TOKEN`                                   | `SLACK_BOT_TOKEN`                       |
| **Dashboard**   | Settings → **Basic Information** → App-Level Tokens | Settings → **Install App**              |
| **Scope / use** | `connections:write` — WebSocket only                | Bot scopes — read events, send messages |


> **Do not** add `connections:write` under **OAuth & Permissions → Bot Token Scopes**. It only belongs on an **app-level token**.

---

## Bot token scopes and event subscriptions

**Dashboard paths**

- Scopes: **Features → OAuth & Permissions → Bot Token Scopes**
- Events: **Features → Event Subscriptions → Subscribe to bot events**

Turn **Enable Events** ON. With Socket Mode, leave **Request URL** empty.

After any scope or event change, **Reinstall to Workspace**.

---

### Required bot token scopes

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages as the bot |
| `app_mentions:read` | Receive `app_mention` when someone @mentions the bot |
| `im:history` | Receive DM content via `message.im` events |

---

### Required event subscriptions (bot events)

| Event | Purpose |
|-------|---------|
| `app_mention` | User @mentions the bot in a channel |
| `message.im` | User sends a direct message to the bot |

---

### Event → scope mapping

Each bot event requires its matching scope:

| Bot event | Required bot token scope |
|-----------|--------------------------|
| `app_mention` | `app_mentions:read` |
| `message.im` | `im:history` |

`chat:write` is not tied to a specific event; it is required for the bot to reply.

---

### Optional (not needed for current `main.py`)

| Bot event | Required bot token scope | Notes |
|-----------|--------------------------|-------|
| `message.channels` | `channels:history` | Every message in public channels the bot is in |

`main.py` ignores non-DM `message` events (`channel_type != "im"`). Subscribing to `message.channels` only adds traffic and DEBUG logs unless you add handler logic.

---

### Also required (non-OAuth)

- Socket Mode ON (Settings → Socket Mode)
- App-level token with `connections:write` → `SLACK_APP_TOKEN` (not a bot scope)
- Messages tab ON (Features → App Home)
- App installed; Slack, OpenAI, and MongoDB values in `.env`

---

## Setup steps

### Step 1 — Create the app

1. [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Name the app (e.g. **AI Chatbot**) and select a workspace
3. Use **granular bot scopes** (default for newer apps; required for Socket Mode)

---

### Step 2 — App-level token

**Path:** Settings → **Basic Information** → **App-Level Tokens**

1. **Generate Token and Scopes**
2. Name: e.g. `socket-mode`
3. Scope: **`connections:write`**
4. Copy the token (`xapp-…`) → `SLACK_APP_TOKEN` in `.env`

Expected in the dashboard:


| Token name                 | Scope               |
| -------------------------- | ------------------- |
| `socket-mode` (or similar) | `connections:write` |


---

### Step 3 — Enable Socket Mode

**Path:** Settings → **Socket Mode**

1. **Enable Socket Mode** → ON
2. Confirm under **Features affected**:
  - **Event Subscriptions:** Yes
  - **Interactivity & Shortcuts:** Yes (optional until you add UI)
  - **Slash Commands:** No (not used by `main.py`)

Under **Event Subscriptions**, Slack shows: *Socket Mode is enabled. You won't need to specify a Request URL.*

`main.py` uses `SocketModeHandler`; Bolt opens the WebSocket via `apps.connections.open`.

---

### Step 4 — App Home (bot user + DMs)

**Path:** Features → **App Home**

1. Ensure a **Bot User** exists
2. **Show Tabs:**
  - **Messages Tab:** ON
  - Check **Allow users to send Slash commands and messages from the messages tab**
  - **Home Tab:** ON (optional)

If the Messages tab is off, users see: *Sending messages to this app has been turned off.*

---

### Step 5 — Bot token scopes

**Path:** Features → **OAuth & Permissions** → **Bot Token Scopes**

Add the [required bot token scopes](#required-bot-token-scopes). Optionally add `channels:history` if using `message.channels`.

**Reinstall to Workspace** after any scope change (button on this page or Settings → Install App).

---

### Step 6 — Event subscriptions

**Path:** Features → **Event Subscriptions**

1. **Enable Events:** ON
2. **Request URL:** leave empty (Socket Mode)
3. **Subscribe to bot events:** add the [required event subscriptions](#required-event-subscriptions-bot-events)
4. **Save Changes**

---

### Step 7 — Install app and copy bot token

**Path:** Settings → **Install App**

1. **Install to Workspace** (or **Reinstall** after Steps 5–6)
2. Copy **Bot User OAuth Token** (`xoxb-…`) → `SLACK_BOT_TOKEN` in `.env`

---

### Step 8 — Local environment and run

Create `.env` in the project root (do not commit):

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
LOG_LEVEL=INFO
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-5-mini
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/?appName=SlackMemoryCluster
MONGODB_DATABASE=slack_ai_chatbot
MEMORY_MAX_TURNS=12
```

Install and start:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Expected output:

```text
INFO | __main__ | AI chatbot starting (socket mode)
INFO | slack_bolt.App | ⚡️ Bolt app is running!
```

---

### Step 9 — Channel access (@mentions)

In Slack:

1. Open the channel
2. `/invite @YourBotName` or add via **Integrations**

`app_mention` only fires in channels the bot has joined.

---

### Step 10 — Threaded replies

- Slack threads when `thread_ts` is set on `chat.postMessage`
- For a message already in a thread, Slack sends `event["thread_ts"]`
- For a new top-level mention, use the message's own `event["ts"]` to create the thread
- Current code uses `thread_ts = event.get("thread_ts") or event.get("ts")` for channel mentions
- DMs stay top-level unless the incoming DM is already inside a thread

---

### Step 11 — Persistent memory

- `memory_store.py` stores conversations and role turns in MongoDB Atlas
- Channel conversations use workspace + channel + Slack `thread_ts`
- Normal DMs use workspace + DM channel + `default`
- The bot loads the most recent `MEMORY_MAX_TURNS` turns before each OpenAI call
- The bot saves the current `user` and `assistant` turns after Slack accepts the reply call
- Set `MONGODB_URI` in `.env` to your Atlas connection string
- Optionally set `MONGODB_DATABASE`; it defaults to `slack_ai_chatbot`

---

## Verification checklist


| #   | Check           | Pass criteria                                   |
| --- | --------------- | ----------------------------------------------- |
| 1   | App-level token | `connections:write` under Basic Information     |
| 2   | Socket Mode     | Enabled; Event Subscriptions = Yes              |
| 3   | Messages tab    | ON + “allow messages from messages tab” checked |
| 4   | Bot scopes      | `chat:write`, `app_mentions:read`, `im:history` |
| 5   | Bot events      | `app_mention`, `message.im`                     |
| 6   | Install         | Workspace installed; `xoxb-` token in `.env`    |
| 7   | MongoDB Atlas   | `MONGODB_URI` is present and Atlas allows access |
| 8   | Process         | `python main.py` → `Bolt app is running!`       |
| 9   | @mention test   | Log: `app_mention received`                     |
| 10  | DM test         | Apps → your bot → message → log: `dm received`  |


Use `LOG_LEVEL=DEBUG` to see ignored `message.channels` payloads if that event is still subscribed.

---

## Code mapping (`main.py`)


| Slack                | Implementation                                   |
| -------------------- | ------------------------------------------------ |
| `SLACK_BOT_TOKEN`    | `App(token=...)`                                 |
| `SLACK_APP_TOKEN`    | `SocketModeHandler(app, app_token).start()`      |
| `app_mention`        | `@app.event("app_mention")`                      |
| `message.im`         | `@app.event("message")` + `channel_type == "im"` |
| Threaded replies     | `thread_ts = event.get("thread_ts") or event.get("ts")` |
| Persistent memory    | `memory_store.py` + `ConversationMemoryStore`     |
| AI replies           | `ai_handler.py` + `generate_ai_reply(..., history=...)` |
| Bot / subtype filter | Skip `bot_id` and `subtype` on DMs               |
| Logging              | `LOG_LEVEL` env; events logged at INFO           |


---

## Troubleshooting


| Symptom                                | Likely cause                              | Fix                                                         |
| -------------------------------------- | ----------------------------------------- | ----------------------------------------------------------- |
| `SLACK_BOT_TOKEN` / BoltError on start | `.env` missing or `load_dotenv()` not run | Add `.env`; confirm `load_dotenv()` in `main.py`            |
| `SLACK_APP_TOKEN is not set`           | No app-level token in `.env`              | Step 2; use `xapp-` token                                   |
| DMs disabled in Slack                  | Messages tab off                          | Step 4                                                      |
| No `app_mention` events                | Bot not in channel                        | Step 9                                                      |
| No DM events                           | Missing `message.im` or `im:history`      | Steps 5–6; reinstall                                        |
| Bot does not reply in a channel thread | Missing `thread_ts` in `say(...)`         | Confirm `main.py` passes `thread_ts` for `app_mention`      |
| Bot forgets after restart              | MongoDB URI missing or unreachable        | Check `MONGODB_URI`, network access, and Atlas IP allowlist |
| Extra DEBUG noise                      | `message.channels` subscribed             | Remove event or set `LOG_LEVEL=INFO`                        |
| Changes not applied                    | Scopes/events updated                     | **Reinstall to Workspace**                                  |


---

## Dashboard navigation


| Task                | Sidebar path                   |
| ------------------- | ------------------------------ |
| App-level token     | Settings → Basic Information   |
| Socket Mode         | Settings → Socket Mode         |
| Install / bot token | Settings → Install App         |
| Scopes              | Features → OAuth & Permissions |
| Events              | Features → Event Subscriptions |
| DM tab              | Features → App Home            |


---

## References

- [Using Socket Mode](https://api.slack.com/apis/connections/socket)
- [App-level tokens](https://api.slack.com/authentication/tokens#app)
- [Bolt for Python](https://slack.dev/tools/bolt-python/)
- [`app_mention` event](https://api.slack.com/events/app_mention)
- [`message` events](https://api.slack.com/events/message)
