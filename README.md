# Slack AI WebSocket

Slack Bolt bot using [Socket Mode](https://api.slack.com/apis/connections/socket) — no public HTTP URL. Handles `@app` mentions in channels and direct messages.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Slack tokens
python main.py
```

## Configuration

| Variable | Description |
| --- | --- |
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | App-level token with `connections:write` (`xapp-...`) |
| `LOG_LEVEL` | Optional; default `INFO` |

## Documentation

- [setupslackwebsocket.md](setupslackwebsocket.md) — Slack app setup, scopes, events, verification
- [ARCHITECTURE.md](ARCHITECTURE.md) — Runtime flow and file map

## Project layout

```
main.py                  # Entry point and event handlers
setupslackwebsocket.md   # Slack dashboard setup guide
ARCHITECTURE.md          # Architecture notes
```
