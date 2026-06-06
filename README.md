# Slack AI WebSocket

Slack Bolt bot that runs in [Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/) with no public HTTP URL. It handles channel `@app` mentions and direct messages, then replies through Slack using Bolt's `say`. Channel mentions are answered in Slack threads, and recent conversation turns are stored in MongoDB Atlas so the AI can remember thread and DM context across restarts.

```mermaid
flowchart LR
    user["Slack user"]
    workspace["Slack workspace<br/>Events API"]
    websocket["Socket Mode WebSocket<br/>SLACK_APP_TOKEN<br/>connections:write"]
    app["Local Python process<br/>python main.py"]
    handlers["Bolt handlers<br/>app_mention + DM message"]
    threadTarget["Thread target<br/>channel: thread_ts or ts<br/>DM: existing thread_ts only"]
    memory["MongoDB Atlas memory<br/>turns by thread or DM key"]
    reply["Slack Web API reply<br/>say(text=reply, thread_ts?)"]

    user --> workspace
    workspace <-->|event payloads| websocket
    websocket --> app
    app --> handlers
    handlers --> threadTarget
    threadTarget --> memory
    memory --> handlers
    handlers --> reply
    threadTarget --> reply
    reply --> workspace
```

## Quick Start

Create `.env` in the project root:

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

Run the bot:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Expected startup:

```text
AI chatbot starting (socket mode)
Bolt app is running!
```

## Step 1 - Configure Slack

```mermaid
flowchart TD
    create["Create Slack app"]
    socket["Enable Socket Mode"]
    appToken["Generate app-level token<br/>connections:write"]
    botScopes["Add bot token scopes<br/>chat:write<br/>app_mentions:read<br/>im:history"]
    events["Subscribe to bot events<br/>app_mention<br/>message.im"]
    home["Enable App Home messages tab<br/>for DMs"]
    install["Install or reinstall app"]
    env["Add xoxb and xapp tokens to .env"]
    run["Run python main.py"]

    create --> socket
    socket --> appToken
    appToken --> botScopes
    botScopes --> events
    events --> home
    home --> install
    install --> env
    env --> run
```

Use these Slack dashboard paths:

| Step | Dashboard path | Required action |
| --- | --- | --- |
| App-level token | Settings > Basic Information > App-Level Tokens | Generate `SLACK_APP_TOKEN` with `connections:write` |
| Socket Mode | Settings > Socket Mode | Turn Socket Mode on |
| Bot scopes | Features > OAuth & Permissions > Bot Token Scopes | Add `chat:write`, `app_mentions:read`, `im:history` |
| Bot events | Features > Event Subscriptions > Subscribe to bot events | Add `app_mention`, `message.im` |
| DMs | Features > App Home | Turn the Messages tab on |
| Install | Settings > Install App | Install or reinstall, then copy the `xoxb-` bot token |

Reinstall the app after any scope or event subscription change.

## Step 2 - Understand Token Scopes

```mermaid
flowchart LR
    subgraph appLevel["App-level token: xapp"]
        connections["connections:write"]
    end

    subgraph botToken["Bot token: xoxb"]
        chat["chat:write"]
        mentionScope["app_mentions:read"]
        dmScope["im:history"]
        channelScope["channels:history<br/>optional"]
    end

    connections --> socketMode["SocketModeHandler opens WebSocket"]
    mentionScope --> mentionEvent["app_mention event"]
    dmScope --> dmEvent["message.im event"]
    channelScope -.-> channelEvent["message.channels event"]
    chat --> say["say(text=reply, thread_ts=...)<br/>chat.postMessage"]

    mentionEvent --> mentionHandler["handle_mentions"]
    dmEvent --> dmHandler["handle_direct_messages"]
    channelEvent -.-> ignored["Ignored by current main.py<br/>unless channel logic is added"]
    mentionHandler --> say
    dmHandler --> say
```

### Bot Token Scopes

These are configured under **OAuth & Permissions > Scopes > Bot Token Scopes**:

| Scope | Required? | Why this bot needs it |
| --- | --- | --- |
| `chat:write` | Yes | Allows replies and notifications through `say(...)`, which posts Slack messages as the bot. |
| `app_mentions:read` | Yes | Allows Slack to send `app_mention` events when the bot is directly mentioned in a channel the app is in. |
| `im:history` | Yes | Allows Slack to send/read direct-message content through `message.im` events. |
| `channels:history` | Optional | Required only if you subscribe to `message.channels` to receive ordinary public-channel messages. |

Do not add `connections:write` here. It belongs to the app-level token, not the bot token.

### App-Level Scope

This is configured while generating `SLACK_APP_TOKEN` under **Basic Information > App-Level Tokens**:

| Scope | Token prefix | Purpose |
| --- | --- | --- |
| `connections:write` | `xapp-` | Lets Socket Mode call `apps.connections.open` and connect to Slack over WebSocket. |

## Step 3 - Subscribe To Events

These are configured under **Event Subscriptions > Subscribe to bot events**:

| Bot event | Required scope | Current code path |
| --- | --- | --- |
| `app_mention` | `app_mentions:read` | `@app.event("app_mention")` -> `handle_mentions` |
| `message.im` | `im:history` | `@app.event("message")` -> `channel_type == "im"` -> `handle_direct_messages` |
| `message.channels` | `channels:history` | Optional; current code ignores it because `channel_type != "im"` |

Use `app_mention` for channel mentions. Add `message.channels` only when you want every message from public channels the bot has joined and you have added handler logic for those events.

## Step 4 - Runtime Event Flow

```mermaid
flowchart TD
    incoming["Incoming Slack event over Socket Mode"]
    type{"Event type"}
    mentionStart["Channel mention<br/>app_mention"]
    message["Message event"]
    dmCheck{"channel_type == im?"}
    botCheck{"bot_id present?"}
    subtypeCheck{"subtype present?"}
    ignore["Ignore event<br/>no reply"]

    mentionClean["1. Clean mention text<br/>remove bot markup"]
    mentionThread{"2. thread_ts present?"}
    mentionExisting["Use existing parent thread_ts"]
    mentionNew["Use message ts<br/>to create a thread"]
    mentionMemory["3. Load memory<br/>workspace + channel + thread_ts"]
    mentionAI["4. Generate AI reply<br/>clean text + history"]
    mentionSay["5. say(text=reply, thread_ts)<br/>post in source thread"]
    mentionSave["6. Save user + assistant turns"]

    dmText["1. Read DM text"]
    dmThread{"2. thread_ts present?"}
    dmThreadKey["Threaded DM key<br/>workspace + DM + thread_ts"]
    dmDefaultKey["Normal DM key<br/>workspace + DM + default"]
    dmMemory["3. Load DM memory"]
    dmAI["4. Generate AI reply<br/>DM text + history"]
    dmSayChoice{"5. thread_ts present?"}
    dmSayThread["say(text=reply, thread_ts)<br/>preserve DM thread"]
    dmSayTop["say(reply)<br/>normal DM response"]
    dmSave["6. Save user + assistant turns"]

    incoming --> type
    type -->|app_mention| mentionStart
    type -->|message| message

    mentionStart --> mentionClean --> mentionThread
    mentionThread -->|Yes| mentionExisting --> mentionMemory
    mentionThread -->|No| mentionNew --> mentionMemory
    mentionMemory --> mentionAI --> mentionSay --> mentionSave

    message --> dmCheck
    dmCheck -->|No| ignore
    dmCheck -->|Yes| botCheck
    botCheck -->|Yes| ignore
    botCheck -->|No| subtypeCheck
    subtypeCheck -->|Yes| ignore
    subtypeCheck -->|No| dmText --> dmThread
    dmThread -->|Yes| dmThreadKey --> dmMemory
    dmThread -->|No| dmDefaultKey --> dmMemory
    dmMemory --> dmAI --> dmSayChoice
    dmSayChoice -->|Yes| dmSayThread --> dmSave
    dmSayChoice -->|No| dmSayTop --> dmSave
```

## Step 5 - Verify

| Check | Pass criteria |
| --- | --- |
| App-level token | `SLACK_APP_TOKEN` starts with `xapp-` and has `connections:write` |
| Bot token | `SLACK_BOT_TOKEN` starts with `xoxb-` and app is installed |
| Bot scopes | `chat:write`, `app_mentions:read`, `im:history` are installed |
| Events | `app_mention` and `message.im` are subscribed |
| Socket Mode | Enabled; no public Request URL is needed |
| Channel mention | Bot is invited to the channel, then `@YourBot hello` logs `app_mention received` and replies in that message's thread |
| Follow-up in same thread | Ask a follow-up in the same Slack thread; the bot uses recent saved turns as context |
| Direct message | App Home messages are enabled, then a DM logs `dm received` and remembers prior DM turns |

## Conversation Memory

Memory is stored in MongoDB Atlas through `memory_store.py`.

| Conversation type | Memory key |
| --- | --- |
| Channel mention | Workspace + channel + Slack `thread_ts` |
| New top-level channel mention | Workspace + channel + the message's own `ts`, which creates the thread |
| Normal DM | Workspace + DM channel + `default` |
| Threaded DM | Workspace + DM channel + Slack `thread_ts` |

The bot loads the most recent `MEMORY_MAX_TURNS` role turns before calling OpenAI, then saves the current `user` and `assistant` turns after Slack accepts the reply call. MongoDB access stays inside `memory_store.py`; `main.py` only calls the store API.

## Configuration

| Variable | Description |
| --- | --- |
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`) used for Slack Web API calls such as replies. |
| `SLACK_APP_TOKEN` | App-level token (`xapp-...`) with `connections:write`, used only for Socket Mode. |
| `LOG_LEVEL` | Optional logging level; defaults to `INFO`. |
| `OPENAI_API_KEY` | OpenAI API key used by `ai_handler.py` to generate replies. |
| `OPENAI_MODEL` | Optional OpenAI model name; defaults in `ai_handler.py`. |
| `MONGODB_URI` | MongoDB Atlas connection string for persistent memory. |
| `MONGODB_DATABASE` | Optional MongoDB database name; defaults to `slack_ai_chatbot`. |
| `MEMORY_MAX_TURNS` | Optional count of recent role turns sent to the AI; defaults to `12`. |

## Project Layout

```text
main.py                  # Entry point and event handlers
ai_handler.py            # OpenAI Responses API wrapper
memory_store.py          # MongoDB Atlas conversation state and role-turn storage
requirements.txt         # Python dependencies
docs/                    # Video diagrams and flow walkthroughs (see docs/README.md)
setupslackwebsocket.md   # Detailed Slack dashboard setup guide
ARCHITECTURE.md          # Runtime architecture notes and diagrams
PLAYLIST.md              # YouTube series roadmap
tests/                   # Focused unit tests for threading, memory, and AI input
```

## References

- [Slack Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)
- [`connections:write` scope](https://docs.slack.dev/reference/scopes/connections.write/)
- [`chat:write` scope](https://docs.slack.dev/reference/scopes/chat.write/)
- [`app_mention` event](https://docs.slack.dev/reference/events/app_mention/)
- [`message.im` event](https://docs.slack.dev/reference/events/message.im/)
- [`message.channels` event](https://docs.slack.dev/reference/events/message.channels/)
- [`channels:history` scope](https://docs.slack.dev/reference/scopes/channels.history/)

## Security

- **Never commit `.env`.** It holds live Slack, OpenAI, and MongoDB credentials. Copy `.env.example` locally and keep `.env` out of version control (listed in `.gitignore`).
- **Rotate tokens** if they were ever committed, shared, or pasted into issues or chat. Regenerate Slack app/bot tokens and OpenAI keys in their dashboards, then update your local `.env`.
- **Before making this repo public**, confirm no secrets in Git history:
  ```bash
  git log --all --full-history -- .env          # should be empty
  git grep -E 'xox[bpsa]-[0-9]|xapp-[0-9]|sk-' # should match nothing except placeholders
  ```
- **Do not commit** `.venv/`, logs, or screenshots that show tokens from Slack or cloud dashboards.
