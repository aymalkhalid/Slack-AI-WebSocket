"""
Slack AI chatbot entry point (Socket Mode).

Receives events from Slack over a WebSocket (no public HTTP URL), handles
@app mentions in channels and direct messages, and replies via Bolt's ``say``.

Required environment variables (``.env``):
    SLACK_BOT_TOKEN  — Bot User OAuth Token (xoxb-...)
    SLACK_APP_TOKEN  — App-level token with connections:write (xapp-...)
"""

import logging
import os
import sys

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

# Step 1: Load SLACK_BOT_TOKEN, SLACK_APP_TOKEN, LOG_LEVEL from .env into os.environ.
load_dotenv()

# Step 2: Configure process-wide logging (level from LOG_LEVEL, default INFO).
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _event_context(event: dict) -> str:
    """
    Build a short, stable string for log lines from a Slack event payload.

    Steps:
        1. Read ``user``, ``channel``, and ``ts`` from the event dict (may be None).
        2. Format them as ``user=... channel=... ts=...`` for grep-friendly logs.

    Args:
        event: Slack event object (e.g. ``body["event"]`` from Bolt).

    Returns:
        Single-line context string, never raises on missing keys.
    """
    return (
        f"user={event.get('user')} "
        f"channel={event.get('channel')} "
        f"ts={event.get('ts')}"
    )


# Step 3: Create the Bolt app; all API calls use SLACK_BOT_TOKEN from the environment.
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))


@app.event("app_mention")
def handle_mentions(body, say):
    """
    Reply when someone @-mentions the bot in a channel.

    Bolt injects:
        body — full request JSON (event lives under body["event"]).
        say  — posts to the same channel via chat.postMessage (no thread_ts here).

    Steps:
        1. Extract the Slack event and the message text (includes the mention markup).
        2. Log the incoming mention with user/channel/ts context.
        3. Run AI logic (placeholder: echo the user's text).
        4. Post the reply with say(reply) — top-level message in that channel.
        5. Log that the reply was sent.

    Args:
        body: Bolt request body containing ``event``.
        say: Callable that sends a message to ``event["channel"]``.
    """
    # Step 1: Unpack event and user-visible text from the Socket Mode payload.
    event = body["event"]
    user_text = event["text"]

    # Step 2: Record that we received an app_mention (text may include <@BOT_ID>).
    logger.info(
        "app_mention received | %s | text=%r",
        _event_context(event),
        user_text,
    )

    # Step 3: Generate a response (replace with your LLM / chain / RAG call).
    # Example: response = my_ai_chain.invoke({"input": user_text})
    reply = f"Hello! I received your mention. You said: {user_text}"

    # Step 4: Send reply to the channel where the bot was mentioned.
    say(reply)

    # Step 5: Confirm outbound message for observability.
    logger.info("app_mention replied | %s", _event_context(event))


@app.event("message")
def handle_direct_messages(body, say):
    """
    Reply to direct messages (DMs) only; ignore channel traffic and bot echoes.

    The ``message`` event fires for all messages. This handler filters so only
    human DMs are answered.

    Bolt injects:
        body — full request JSON (event under body["event"]).
        say  — posts to the DM channel (channel_type ``im``).

    Steps:
        1. Extract the event from the payload.
        2. Return early if not a DM (channel_type != "im").
        3. Return early if the sender is a bot (avoids reply loops).
        4. Return early if the message has a subtype (edits, file shares, etc.).
        5. Log the DM text.
        6. Run AI logic (placeholder: echo).
        7. Post the reply with say(reply).
        8. Log completion.

    Args:
        body: Bolt request body containing ``event``.
        say: Callable that sends a message to ``event["channel"]`` (the DM).
    """
    # Step 1: Unpack the message event.
    event = body["event"]

    # Step 2: Only DMs — channel messages and mentions are handled elsewhere / ignored.
    if event.get("channel_type") != "im":
        logger.debug(
            "message ignored (not a DM) | %s | channel_type=%s",
            _event_context(event),
            event.get("channel_type"),
        )
        return

    # Step 3: Skip bot-authored messages so we do not reply to ourselves.
    if event.get("bot_id"):
        logger.debug("message ignored (from bot) | %s", _event_context(event))
        return

    # Step 4: Skip system subtypes (message_changed, channel_join, etc.).
    if event.get("subtype"):
        logger.debug(
            "message ignored (subtype) | %s | subtype=%s",
            _event_context(event),
            event.get("subtype"),
        )
        return

    # Step 5: Log the human DM text.
    user_text = event["text"]
    logger.info(
        "dm received | %s | text=%r",
        _event_context(event),
        user_text,
    )

    # Step 6: Generate a response (replace with your AI pipeline).
    reply = f"Hello! I received your DM. You said: {user_text}"

    # Step 7: Send reply into the same DM conversation.
    say(reply)

    # Step 8: Confirm outbound message.
    logger.info("dm replied | %s", _event_context(event))


def main() -> None:
    """
    Boot the bot when this file is run directly (``python main.py``).

    Steps:
        1. Read SLACK_APP_TOKEN (required for Socket Mode WebSocket).
        2. Exit with a clear error if the token is missing.
        3. Log startup and open the Socket Mode connection (blocks until exit).
    """
    # Step 1: App-level token (xapp-...) — separate from the bot token on ``app``.
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        raise SystemExit("SLACK_APP_TOKEN is not set. Check your .env file.")

    # Step 2: Connect Bolt to Slack over WebSocket; dispatches events to handlers above.
    logger.info("AI chatbot starting (socket mode)")
    SocketModeHandler(app, app_token).start()


if __name__ == "__main__":
    main()
