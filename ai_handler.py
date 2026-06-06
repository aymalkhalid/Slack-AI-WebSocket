"""
AI replies for the Slack bot.

main.py calls generate_ai_reply(text, history=...). This file reads .env, calls
the OpenAI API, and returns plain text for Slack.
"""

import logging
import os

import openai
from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4.1-mini-2025-04-14"
MAX_OUTPUT_TOKENS = 600
SUPPORTED_HISTORY_ROLES = {"user", "assistant"}

SYSTEM_PROMPT = (
    "You are a helpful AI assistant replying inside Slack. "
    "Answer clearly and concisely. "
    "If the user asks for code, include the useful code and a short explanation. "
    "If you are unsure, say what is uncertain instead of inventing details."
)

# Created on the first AI request and reused after that.
_openai_client = None


def _env(name: str) -> str:
    """Read an environment variable; return "" if missing or blank."""
    return os.environ.get(name, "").strip()


def _get_openai_client() -> OpenAI:
    """Build the OpenAI client from OPENAI_API_KEY."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    _openai_client = OpenAI(
        api_key=api_key,
        max_retries=2,
        timeout=30.0,
    )
    return _openai_client


def _trim_for_slack(text: str) -> str:
    """Ensure the reply is non-empty and fits Slack character limits."""
    reply = (text or "").strip()
    if not reply:
        return "I could not generate a response. Please try again."
    if len(reply) > 3500:
        return reply[:3497].rstrip() + "..."
    return reply


def _build_response_input(user_text: str, history=None):
    """
    Build Responses API input from recent conversation history plus the user turn.

    ``history`` is expected to be a list of ``{"role": ..., "content": ...}``
    dicts from memory_store. If no valid history exists, return a plain string
    to preserve the original single-turn behavior.
    """
    prompt = user_text.strip()
    messages = []

    for turn in history or []:
        role = (turn.get("role") or "").strip()
        content = (turn.get("content") or "").strip()

        if role not in SUPPORTED_HISTORY_ROLES or not content:
            continue

        messages.append({"role": role, "content": content})

    if not messages:
        return prompt

    messages.append({"role": "user", "content": prompt})
    return messages


def generate_ai_reply(user_text: str, history=None) -> str:
    """
    Turn a Slack message into an AI reply.

    main.py passes cleaned user text and optional recent conversation history;
    we return text safe to post with say().
    """
    prompt = user_text.strip()
    if not prompt:
        return "Send me a question and I will help."

    try:
        client = _get_openai_client()
        model = _env("OPENAI_MODEL") or DEFAULT_MODEL

        response = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=_build_response_input(prompt, history=history),
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        return _trim_for_slack(response.output_text)
    except RuntimeError as exc:
        logger.warning("AI configuration error: %s", exc)
        return "AI is not configured yet. Add OPENAI_API_KEY and restart the bot."

    except openai.APIError:
        logger.warning("OpenAI API error", exc_info=True)
        return "I could not reach the AI service right now. Please try again in a moment."

    except Exception:
        logger.exception("Unexpected AI handler error")
        return "I could not generate a response right now. Please try again in a moment."
