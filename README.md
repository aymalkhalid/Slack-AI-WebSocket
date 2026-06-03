# Slack AI WebSocket

Slack Bolt bot that runs in [Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/) with no public HTTP URL. It handles channel `@app` mentions and direct messages, then replies through Slack using Bolt's `say`.

```mermaid
flowchart LR
    user["Slack user"]
    workspace["Slack workspace<br/>Events API"]
    websocket["Socket Mode WebSocket<br/>SLACK_APP_TOKEN<br/>connections:write"]
    app["Local Python process<br/>python main.py"]
    handlers["Bolt handlers<br/>app_mention + DM message"]
    reply["Slack Web API reply<br/>SLACK_BOT_TOKEN<br/>chat:write"]

    user --> workspace
    workspace <-->|event payloads| websocket
    websocket --> app
    app --> handlers
    handlers --> reply
    reply --> workspace
```

## Quick Start

Create `.env` in the project root:

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
LOG_LEVEL=INFO
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
    chat --> say["say(reply)<br/>chat.postMessage"]

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
    mention["app_mention"]
    message["message"]
    dmCheck{"channel_type == im?"}
    botCheck{"bot_id present?"}
    subtypeCheck{"subtype present?"}
    mentionReply["Log context<br/>build mention reply<br/>say(reply)"]
    dmReply["Log context<br/>build DM reply<br/>say(reply)"]
    ignore["Ignore event<br/>no reply"]

    incoming --> type
    type -->|app_mention| mention
    type -->|message| message
    mention --> mentionReply
    message --> dmCheck
    dmCheck -->|No| ignore
    dmCheck -->|Yes| botCheck
    botCheck -->|Yes| ignore
    botCheck -->|No| subtypeCheck
    subtypeCheck -->|Yes| ignore
    subtypeCheck -->|No| dmReply
```

## Step 5 - Verify

| Check | Pass criteria |
| --- | --- |
| App-level token | `SLACK_APP_TOKEN` starts with `xapp-` and has `connections:write` |
| Bot token | `SLACK_BOT_TOKEN` starts with `xoxb-` and app is installed |
| Bot scopes | `chat:write`, `app_mentions:read`, `im:history` are installed |
| Events | `app_mention` and `message.im` are subscribed |
| Socket Mode | Enabled; no public Request URL is needed |
| Channel mention | Bot is invited to the channel, then `@YourBot hello` logs `app_mention received` |
| Direct message | App Home messages are enabled, then a DM logs `dm received` |

## Configuration

| Variable | Description |
| --- | --- |
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`) used for Slack Web API calls such as replies. |
| `SLACK_APP_TOKEN` | App-level token (`xapp-...`) with `connections:write`, used only for Socket Mode. |
| `LOG_LEVEL` | Optional logging level; defaults to `INFO`. |

## Project Layout

```text
main.py                  # Entry point and event handlers
requirements.txt         # Python dependencies
setupslackwebsocket.md   # Detailed Slack dashboard setup guide
ARCHITECTURE.md          # Runtime architecture notes and diagrams
```

## References

- [Slack Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)
- [`connections:write` scope](https://docs.slack.dev/reference/scopes/connections.write/)
- [`chat:write` scope](https://docs.slack.dev/reference/scopes/chat.write/)
- [`app_mention` event](https://docs.slack.dev/reference/events/app_mention/)
- [`message.im` event](https://docs.slack.dev/reference/events/message.im/)
- [`message.channels` event](https://docs.slack.dev/reference/events/message.channels/)
- [`channels:history` scope](https://docs.slack.dev/reference/scopes/channels.history/)
