# Slack AI WebSocket

Slack Bolt bot that runs in [Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/) with no public HTTP URL. It handles channel `@app` mentions and direct messages, then replies through Slack using Bolt's `say`. Channel mentions are answered in Slack threads, and recent conversation turns are stored in MongoDB Atlas so the AI can remember thread and DM context across restarts.

![Diagram Explainer — high-level bot overview](docs/Architecture%20&%20Diagrams/High%20Level%20-%20Overview/Diagram%20Explainer.png)

> All diagrams live under [`docs/`](docs/README.md). Mermaid sources for Video 2 are in [`docs/diagrams/video-2-real-ai/`](docs/diagrams/video-2-real-ai/).

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

## Architecture Diagrams

### High-level overview

| Diagram | What it shows |
| --- | --- |
| [Diagram Explainer](docs/Architecture%20&%20Diagrams/High%20Level%20-%20Overview/Diagram%20Explainer.png) | End-to-end map of Slack events, handlers, AI, and memory |
| [Event Handling Flow](docs/Architecture%20&%20Diagrams/High%20Level%20-%20Overview/Event%20Handling%20Flow.png) | How incoming events are routed inside the bot |
| [Full Event Handling Summary](docs/Architecture%20&%20Diagrams/High%20Level%20-%20Overview/Full%20Event%20Handling%20Summary.png) | Single-page summary of the full runtime path |
| [General Event Handling Flow](docs/Architecture%20&%20Diagrams/High%20Level%20-%20Overview/General%20Event%20Handling%20Flow%20.png) | General decision flow for supported vs ignored events |

![Full Event Handling Summary](docs/Architecture%20&%20Diagrams/High%20Level%20-%20Overview/Full%20Event%20Handling%20Summary.png)

### Video 2 — Real AI integration

OpenAI replies stay in `ai_handler.py`; Slack routing stays in `main.py`. See [`docs/diagrams/video-2-real-ai/README.md`](docs/diagrams/video-2-real-ai/README.md) for the walkthrough and talking points.

![Video 2 — Slack event to AI reply flowchart](docs/diagrams/video-2-real-ai/flowchart.svg)

### Channel `@app` mentions

| Diagram | Step |
| --- | --- |
| [App Mention](docs/Architecture%20&%20Diagrams/Channel/App%20Mention.png) | Overview of the channel mention path |
| [4A](docs/Architecture%20&%20Diagrams/Channel/4A.png) | Receive and clean mention text |
| [4B](docs/Architecture%20&%20Diagrams/Channel/4B.png) | Resolve thread target, load memory, reply in thread |

![Channel app mention flow](docs/Architecture%20&%20Diagrams/Channel/App%20Mention.png)

### Direct messages

| Diagram | Step |
| --- | --- |
| [Message DM](docs/Architecture%20&%20Diagrams/DM/Message%20DM.png) | Overview of the DM path |
| [4C](docs/Architecture%20&%20Diagrams/DM/4C.png) | Filter DMs and ignore bot/subtype events |
| [4D](docs/Architecture%20&%20Diagrams/DM/4D.png) | Load DM memory and generate the reply |
| [4E](docs/Architecture%20&%20Diagrams/DM/4E.png) | Post reply and save turns |

![Direct message flow](docs/Architecture%20&%20Diagrams/DM/Message%20DM.png)

### OpenAI + MongoDB sequence

![Sequence diagram — OpenAI and MongoDB Atlas](docs/Architecture%20&%20Diagrams/Sequence%20Diagarms/Sequence%20Diagram%20Openai%20-%20MongoDb.png)

### MongoDB Atlas memory

| Diagram | Topic |
| --- | --- |
| [1](docs/Architecture%20&%20Diagrams/MongoDb/1.png) | Memory overview |
| [2](docs/Architecture%20&%20Diagrams/MongoDb/2.png) | Conversation keys |
| [3](docs/Architecture%20&%20Diagrams/MongoDb/3.png) | Turn storage |
| [4](docs/Architecture%20&%20Diagrams/MongoDb/4.png) | Load before AI call |
| [5](docs/Architecture%20&%20Diagrams/MongoDb/5.png) | Save after Slack reply |
| [6](docs/Architecture%20&%20Diagrams/MongoDb/6.png) | End-to-end memory flow |

![MongoDB Atlas memory overview](docs/Architecture%20&%20Diagrams/MongoDb/1.png)

## Step 1 - Configure Slack

Use these Slack dashboard paths:

| Step | Dashboard path | Required action |
| --- | --- | --- |
| App-level token | Settings > Basic Information > App-Level Tokens | Generate `SLACK_APP_TOKEN` with `connections:write` |
| Socket Mode | Settings > Socket Mode | Turn Socket Mode on |
| Bot scopes | Features > OAuth & Permissions > Bot Token Scopes | Add `chat:write`, `app_mentions:read`, `im:history` |
| Bot events | Features > Event Subscriptions > Subscribe to bot events | Add `app_mention`, `message.im` |
| DMs | Features > App Home | Turn the Messages tab on |
| Install | Settings > Install App | Install or reinstall, then copy the `xoxb-` bot token |

Reinstall the app after any scope or event subscription change. Full walkthrough: [`setupslackwebsocket.md`](setupslackwebsocket.md).

## Step 2 - Understand Token Scopes

### Bot Token Scopes

Configured under **OAuth & Permissions > Scopes > Bot Token Scopes**:

| Scope | Required? | Why this bot needs it |
| --- | --- | --- |
| `chat:write` | Yes | Allows replies through `say(...)`, which posts Slack messages as the bot. |
| `app_mentions:read` | Yes | Sends `app_mention` events when the bot is @mentioned in a channel. |
| `im:history` | Yes | Sends/read direct-message content through `message.im` events. |
| `channels:history` | Optional | Required only if you subscribe to `message.channels` for ordinary channel messages. |

Do not add `connections:write` here. It belongs to the app-level token, not the bot token.

### App-Level Scope

Configured while generating `SLACK_APP_TOKEN` under **Basic Information > App-Level Tokens**:

| Scope | Token prefix | Purpose |
| --- | --- | --- |
| `connections:write` | `xapp-` | Lets Socket Mode call `apps.connections.open` and connect over WebSocket. |

## Step 3 - Subscribe To Events

Configured under **Event Subscriptions > Subscribe to bot events**:

| Bot event | Required scope | Current code path |
| --- | --- | --- |
| `app_mention` | `app_mentions:read` | `@app.event("app_mention")` → `handle_mentions` |
| `message.im` | `im:history` | `@app.event("message")` → `channel_type == "im"` → `handle_direct_messages` |
| `message.channels` | `channels:history` | Optional; current code ignores it because `channel_type != "im"` |

Use `app_mention` for channel mentions. Add `message.channels` only when you want every message from public channels the bot has joined and you have added handler logic for those events.

## Step 4 - Runtime Event Flow

The diagrams above map directly to the code paths below.

**Channel mention (`app_mention`)**

1. Clean mention text — remove bot markup.
2. Resolve thread target — use `event.thread_ts` or the message `ts` to create a thread.
3. Load memory — key: workspace + channel + thread timestamp.
4. Generate AI reply — `generate_ai_reply(text, history=...)`.
5. Post in thread — `say(text=reply, thread_ts=...)`.
6. Save user + assistant turns to MongoDB.

See: [Channel diagrams](#channel-app-mentions).

**Direct message (`message.im`)**

1. Filter — only `channel_type == "im"`, no bot echoes, no subtypes.
2. Resolve memory key — normal DM uses `default`; threaded DMs use `thread_ts`.
3. Load memory and generate AI reply.
4. Post reply — threaded DMs pass `thread_ts`; normal DMs stay top-level.
5. Save turns.

See: [DM diagrams](#direct-messages) and [MongoDB diagrams](#mongodb-atlas-memory).

**AI + memory sequence**

See: [OpenAI + MongoDB sequence diagram](#openai--mongodb-sequence).

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
docs/                    # Diagram PNGs, SVGs, and video walkthroughs (see docs/README.md)
setupslackwebsocket.md   # Detailed Slack dashboard setup guide
ARCHITECTURE.md          # Runtime architecture notes
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
