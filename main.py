"""
Slack AI chatbot entry point (Socket Mode).

Receives events from Slack over a WebSocket (no public HTTP URL), handles
@app mentions in channels and direct messages, and replies via Bolt's ``say``.

Required environment variables (``.env``):
    SLACK_BOT_TOKEN  — Bot User OAuth Token (xoxb-...)
    SLACK_APP_TOKEN  — App-level token with connections:write (xapp-...)
    OPENAI_API_KEY   - OpenAI API key for generated replies
    OPENAI_MODEL     - Optional model name (default set in ai_handler.py)
    MONGODB_URI      - MongoDB Atlas connection string for persistent memory
    MONGODB_DATABASE - Optional MongoDB database name for memory
    MEMORY_MAX_TURNS - Optional recent turn count sent to the model
"""

import logging
import os
import re
import sys

from ai_handler import generate_ai_reply
from memory_store import ConversationMemoryStore, memory_max_turns
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

# Step 1: Load Slack, logging, OpenAI, and memory settings from .env into os.environ.
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

SLACK_MENTION_PATTERN = re.compile(r"<@[A-Z0-9]+>\s*")
_memory_store = None


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


def _thread_ts_for_reply(event: dict):
    """
    Return the Slack thread timestamp that should receive a threaded reply.

    Slack includes ``thread_ts`` when the incoming message is already inside a
    thread. For a new top-level message, its own ``ts`` becomes the parent
    timestamp for the new thread.

    Args:
        event: Slack message-like event containing ``ts`` and maybe ``thread_ts``.

    Returns:
        Existing parent thread timestamp, the message timestamp, or ``None`` if
        Slack sent neither value.
    """
    return event.get("thread_ts") or event.get("ts")


def _say_reply(say, reply: str, thread_ts=None) -> None:
    """
    Send a Slack reply, optionally inside a thread.

    Passing ``thread_ts`` makes Bolt call ``chat.postMessage`` with Slack's
    thread parent timestamp. Without it, the reply stays top-level.
    """
    if thread_ts:
        say(text=reply, thread_ts=thread_ts)
    else:
        say(reply)


def _preview_text(text: str, limit: int = 220) -> str:
    """Return a single-line, bounded preview for human-friendly logs."""
    normalized = (text or "").replace("\n", "\\n").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _log_flow_step(flow_label: str, step_number: int, title: str, **fields) -> None:
    """Print one structured lifecycle step for easier scanning in production logs."""
    field_parts = [f"{key}={value!r}" for key, value in fields.items()]
    suffix = f" | {' | '.join(field_parts)}" if field_parts else ""
    logger.info("%s | step=%02d | %s%s", flow_label, step_number, title, suffix)


def _get_memory_store() -> ConversationMemoryStore:
    """Create the persistent memory store lazily so imports stay side-effect light."""
    global _memory_store
    if _memory_store is None:
        _memory_store = ConversationMemoryStore.from_env()
    return _memory_store


def _conversation_id_for_event(event: dict, thread_ts=None, team_id=None) -> str:
    """
    Build a stable memory key for a Slack conversation.

    Channel messages use the Slack thread timestamp, so each thread has its own
    memory. Normal DMs use the DM channel as one ongoing conversation; threaded
    DMs use their thread timestamp as a separate memory.
    """
    workspace_id = team_id or event.get("team") or "workspace"
    channel_id = event.get("channel") or "unknown-channel"

    if event.get("channel_type") == "im":
        dm_thread_key = thread_ts or "default"
        return f"{workspace_id}:dm:{channel_id}:{dm_thread_key}"

    thread_key = (
        thread_ts
        or event.get("thread_ts")
        or event.get("ts")
        or "unknown-thread"
    )
    return f"{workspace_id}:channel:{channel_id}:{thread_key}"


def _load_memory_history(conversation_id: str, event: dict, thread_ts=None):
    """
    Ensure a memory conversation exists and return recent turns for the model.

    Memory failures are logged and treated as empty history so the bot can still
    answer the user.
    """
    try:
        store = _get_memory_store()
        created_new = store.ensure_conversation(
            conversation_id,
            channel_id=event.get("channel"),
            thread_ts=thread_ts,
            channel_type=event.get("channel_type"),
        )
        history = store.get_recent_turns(
            conversation_id,
            limit=memory_max_turns(),
        )
        return store, history, created_new
    except Exception:
        logger.exception("memory load failed | conversation_id=%s", conversation_id)
        return None, [], False


def _save_memory_turns(
    store,
    conversation_id: str,
    event: dict,
    user_text: str,
    reply: str,
    *,
    thread_ts=None,
) -> None:
    """
    Save the current user/assistant turn pair and lightweight conversation state.
    """
    if store is None or not user_text.strip():
        return

    try:
        store.append_turn(
            conversation_id,
            "user",
            user_text,
            user_id=event.get("user"),
            slack_ts=event.get("ts"),
        )
        store.append_turn(
            conversation_id,
            "assistant",
            reply,
            slack_ts=thread_ts,
        )
        store.update_state(
            conversation_id,
            last_user_id=event.get("user"),
            last_event_ts=event.get("ts"),
            last_thread_ts=thread_ts,
            last_channel_id=event.get("channel"),
        )
        turn_count = len(
            store.get_recent_turns(
                conversation_id,
                limit=memory_max_turns(),
            )
        )
        logger.info(
            "ConversationMemoryStore updated | conversation_id=%s | recent_turns=%d",
            conversation_id,
            turn_count,
        )
    except Exception:
        logger.exception("memory save failed | conversation_id=%s", conversation_id)


def _bot_user_id(body: dict):
    """
    Read the bot user ID from Slack authorization metadata when available.

    Slack mention text uses markup like ``<@U123ABC>``. Knowing the bot user ID
    lets us remove the bot mention without touching other user mentions.

    Examples:
        Incoming ``body`` may include::

            {"authorizations": [{"user_id": "U0ABCDEF12"}], "event": {...}}

        Return value::

            "U0ABCDEF12"

        That ID is passed to ``_clean_app_mention_text`` so only the bot
        mention is stripped. In a message like::

            <@U0ABCDEF12> <@U0ALICE99> summarize this thread

        we remove ``<@U0ABCDEF12>`` and keep ``<@U0ALICE99>`` in the text
        (or strip Alice separately later). Without the bot ID, a generic
        "remove first mention" rule could delete Alice's mention by mistake.

    Returns:
        Bot user ID string, or ``None`` when authorizations are missing.
    """
    authorizations = body.get("authorizations") or []
    if not authorizations:
        return None

    return authorizations[0].get("user_id")


def _clean_app_mention_text(text: str, bot_user_id=None) -> str:
    """
    Remove Slack bot mention markup before sending user text to the model.

    If Slack provided the bot user ID, remove that exact mention. Otherwise,
    remove the first Slack mention token as a practical fallback for Video 2.

    Examples (preferred path, ``bot_user_id="U0BOT"``):

        ``"<@U0BOT> what is Python?"``  →  ``"what is Python?"``
        ``"<@U0BOT>   hello"``          →  ``"hello"``

    Examples (fallback when ``bot_user_id`` is ``None``):

        ``"<@U0BOT> what is Python?"``  →  ``"what is Python?"``
        (only the first ``<@...>`` token is removed)

    Args:
        text: Raw ``event["text"]`` from an ``app_mention`` (includes markup).
        bot_user_id: From ``_bot_user_id(body)``; ``None`` uses the fallback rule.

    Returns:
        Stripped text safe to pass to ``generate_ai_reply``.
    """
    clean_text = text.strip()

    if bot_user_id:
        clean_text = re.sub(rf"<@{re.escape(bot_user_id)}>\s*", "", clean_text)
    else:
        clean_text = SLACK_MENTION_PATTERN.sub("", clean_text, count=1)

    return clean_text.strip()


# Step 3: Create the Bolt app; all API calls use SLACK_BOT_TOKEN from the environment.
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))


@app.event("app_mention")
def handle_mentions(body, say):
    """
    Reply when someone @-mentions the bot in a channel.

    Bolt injects:
        body — full request JSON (event lives under body["event"]).
        say  — posts to the same channel via chat.postMessage.

    Steps:
        1. Extract the Slack event and the message text (includes the mention markup).
        2. Log the incoming mention with user/channel/ts context.
        3. Remove the bot mention markup from the text.
        4. Load recent conversation memory for this Slack thread.
        5. Generate a response through ``ai_handler.generate_ai_reply``.
        6. Post the reply in the source Slack thread using ``thread_ts``.
        7. Save the user/assistant turns to memory.
        8. Log that the reply was sent.

    Args:
        body: Bolt request body containing ``event``.
        say: Callable that sends a message to ``event["channel"]``.
    """
    # Step 1: Unpack event and user-visible text from the Socket Mode payload.
    event = body["event"]
    user_text = event.get("text", "")

    # Step 2: Record that we received an app_mention (text may include <@BOT_ID>).
    flow_label = "Incoming channel mention"
    _log_flow_step(
        flow_label,
        1,
        "event received",
        context=_event_context(event),
        incoming_text=_preview_text(user_text),
    )
    # Step 3: Remove Slack bot mention markup before sending text to the model.
    clean_text = _clean_app_mention_text(user_text, _bot_user_id(body))

    # Step 4: Load recent memory for this Slack thread before generating.
    thread_ts = _thread_ts_for_reply(event)
    conversation_id = _conversation_id_for_event(
        event,
        thread_ts=thread_ts,
        team_id=body.get("team_id"),
    )
    store, history, created_new = _load_memory_history(
        conversation_id,
        event,
        thread_ts=thread_ts,
    )
    _log_flow_step(
        flow_label,
        2,
        "memory loaded",
        conversation_id=conversation_id,
        collection_state="new" if created_new else "existing",
        loaded_turns=len(history),
    )

    # Step 5: Generate a response through the AI model layer.
    reply = generate_ai_reply(clean_text, history=history)
    _log_flow_step(
        flow_label,
        3,
        "AI generated response",
        ai_response=_preview_text(reply),
    )

    # Step 6: Post the reply in the source thread, creating one for top-level mentions.
    _say_reply(say, reply, thread_ts=thread_ts)

    # Step 7: Save the conversation turn after Slack accepts the reply call.
    _save_memory_turns(
        store,
        conversation_id,
        event,
        clean_text,
        reply,
        thread_ts=thread_ts,
    )
    _log_flow_step(
        flow_label,
        4,
        "ConversationMemoryStore state updated",
        conversation_id=conversation_id,
    )

    # Step 8: Confirm outbound message for observability.
    _log_flow_step(
        flow_label,
        5,
        "reply posted to Slack",
        context=_event_context(event),
        thread_ts=thread_ts,
        conversation_id=conversation_id,
    )


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
        6. Load recent DM memory.
        7. Generate a response through ``ai_handler.generate_ai_reply``.
        8. Post the reply. Existing DM threads are preserved.
        9. Save the user/assistant turns to memory.
        10. Log completion.

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
    user_text = event.get("text", "").strip()
    flow_label = "Incoming dm"
    _log_flow_step(
        flow_label,
        1,
        "event received",
        context=_event_context(event),
        incoming_text=_preview_text(user_text),
    )

    # Step 6: Load recent memory for this DM or DM thread before generating.
    thread_ts = event.get("thread_ts")
    conversation_id = _conversation_id_for_event(
        event,
        thread_ts=thread_ts,
        team_id=body.get("team_id"),
    )
    store, history, created_new = _load_memory_history(
        conversation_id,
        event,
        thread_ts=thread_ts,
    )
    _log_flow_step(
        flow_label,
        2,
        "memory loaded",
        conversation_id=conversation_id,
        collection_state="new" if created_new else "existing",
        loaded_turns=len(history),
    )

    # Step 7: Generate a response through the AI model layer.
    reply = generate_ai_reply(user_text, history=history)
    _log_flow_step(
        flow_label,
        3,
        "AI generated response",
        ai_response=_preview_text(reply),
    )

    # Step 8: Keep normal DMs top-level, but preserve an existing DM thread.
    _say_reply(say, reply, thread_ts=thread_ts)

    # Step 9: Save the conversation turn after Slack accepts the reply call.
    _save_memory_turns(
        store,
        conversation_id,
        event,
        user_text,
        reply,
        thread_ts=thread_ts,
    )
    _log_flow_step(
        flow_label,
        4,
        "ConversationMemoryStore state updated",
        conversation_id=conversation_id,
    )

    # Step 10: Confirm outbound message.
    _log_flow_step(
        flow_label,
        5,
        "reply posted to Slack",
        context=_event_context(event),
        thread_ts=thread_ts,
        conversation_id=conversation_id,
    )


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
