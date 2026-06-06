"""
MongoDB Atlas-backed conversation memory for the Slack AI bot.

Each Slack thread or DM maps to one conversation. Turns are stored with roles so
the AI layer can rebuild recent chat history before generating the next reply.
"""

import os
from datetime import datetime, timezone
from typing import Optional

DEFAULT_MONGODB_DATABASE = "slack_ai_chatbot"
DEFAULT_CONVERSATIONS_COLLECTION = "conversations"
DEFAULT_TURNS_COLLECTION = "conversation_turns"
DEFAULT_MEMORY_MAX_TURNS = 12
VALID_ROLES = {"user", "assistant", "system", "tool"}


def _env(name: str) -> str:
    """Read an environment variable; return "" if missing or blank."""
    return os.environ.get(name, "").strip()


def mongodb_uri() -> str:
    """Return the MongoDB Atlas connection string from the environment."""
    return _env("MONGODB_URI")


def mongodb_database_name() -> str:
    """Return the MongoDB database name used for persistent memory."""
    return _env("MONGODB_DATABASE") or DEFAULT_MONGODB_DATABASE


def memory_max_turns() -> int:
    """Return how many recent role turns should be sent back to the model."""
    raw_value = _env("MEMORY_MAX_TURNS")
    if not raw_value:
        return DEFAULT_MEMORY_MAX_TURNS

    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MEMORY_MAX_TURNS

    return max(0, value)


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for MongoDB documents."""
    return datetime.now(timezone.utc)


class ConversationMemoryStore:
    """MongoDB-backed store for conversation state and role-based history."""

    def __init__(
        self,
        uri: Optional[str] = None,
        *,
        database_name: Optional[str] = None,
        client=None,
    ):
        self.uri = uri or mongodb_uri()
        self.database_name = database_name or mongodb_database_name()
        self._client = client

        if self._client is None and not self.uri:
            raise RuntimeError("MONGODB_URI is not set.")

        self._database = None
        self._conversations = None
        self._turns = None

    @classmethod
    def from_env(cls):
        """Create a store using environment-backed MongoDB configuration."""
        return cls(mongodb_uri(), database_name=mongodb_database_name())

    def close(self) -> None:
        """Close the underlying MongoDB client when the store owns one."""
        if self._client is not None:
            self._client.close()

    @property
    def conversations(self):
        """MongoDB collection containing one document per conversation."""
        self._ensure_collections()
        return self._conversations

    @property
    def turns(self):
        """MongoDB collection containing ordered role/content turns."""
        self._ensure_collections()
        return self._turns

    def _ensure_collections(self) -> None:
        if self._conversations is not None and self._turns is not None:
            return

        if self._client is None:
            from pymongo import MongoClient
            from pymongo.server_api import ServerApi

            self._client = MongoClient(
                self.uri,
                server_api=ServerApi("1"),
                serverSelectionTimeoutMS=5000,
            )

        self._database = self._client[self.database_name]
        self._conversations = self._database[
            _env("MONGODB_CONVERSATIONS_COLLECTION")
            or DEFAULT_CONVERSATIONS_COLLECTION
        ]
        self._turns = self._database[
            _env("MONGODB_TURNS_COLLECTION") or DEFAULT_TURNS_COLLECTION
        ]

        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self._conversations.create_index("conversation_id", unique=True)
        self._conversations.create_index("updated_at")
        self._turns.create_index([("conversation_id", 1), ("created_at", -1)])

    def ping(self) -> bool:
        """Ping MongoDB Atlas to verify the configured deployment is reachable."""
        self._ensure_collections()
        self._client.admin.command("ping")
        return True

    def ensure_conversation(
        self,
        conversation_id: str,
        *,
        channel_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> bool:
        """
        Create or refresh a conversation document without changing its state.

        Returns:
            True when this call created a new conversation document, otherwise False.
        """
        now = _utc_now()
        set_on_insert = {
            "conversation_id": conversation_id,
            "state": {},
            "created_at": now,
        }
        update = {
            "$set": {
                "updated_at": now,
            },
            "$setOnInsert": set_on_insert,
        }

        optional_fields = {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "channel_type": channel_type,
        }
        update["$set"].update(
            {
                field_name: field_value
                for field_name, field_value in optional_fields.items()
                if field_value is not None
            }
        )

        result = self.conversations.update_one(
            {"conversation_id": conversation_id},
            update,
            upsert=True,
        )
        return result.upserted_id is not None

    def append_turn(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        user_id: Optional[str] = None,
        slack_ts: Optional[str] = None,
    ):
        """Append one role turn to a conversation and return the inserted id."""
        normalized_role = (role or "").strip()
        normalized_content = (content or "").strip()

        if normalized_role not in VALID_ROLES:
            raise ValueError(f"Unsupported memory role: {role!r}")
        if not normalized_content:
            return None

        now = _utc_now()
        result = self.turns.insert_one(
            {
                "conversation_id": conversation_id,
                "role": normalized_role,
                "content": normalized_content,
                "user_id": user_id,
                "slack_ts": slack_ts,
                "created_at": now,
            }
        )
        self.conversations.update_one(
            {"conversation_id": conversation_id},
            {"$set": {"updated_at": now}},
        )
        return result.inserted_id

    def get_recent_turns(self, conversation_id: str, limit: Optional[int] = None):
        """Return recent turns in chronological order as role/content dicts."""
        max_turns = memory_max_turns() if limit is None else max(0, int(limit))
        if max_turns == 0:
            return []

        cursor = (
            self.turns.find(
                {"conversation_id": conversation_id},
                {"_id": 0, "role": 1, "content": 1, "created_at": 1},
            )
            .sort("created_at", -1)
            .limit(max_turns)
        )
        rows = list(cursor)

        return [
            {"role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]

    def get_state(self, conversation_id: str) -> dict:
        """Return state for a conversation, or an empty state dict."""
        document = self.conversations.find_one(
            {"conversation_id": conversation_id},
            {"_id": 0, "state": 1},
        )
        if not document:
            return {}

        state = document.get("state")
        return state if isinstance(state, dict) else {}

    def set_state(self, conversation_id: str, state: dict) -> None:
        """Replace state for a conversation document."""
        self.conversations.update_one(
            {"conversation_id": conversation_id},
            {
                "$set": {
                    "state": state or {},
                    "updated_at": _utc_now(),
                }
            },
            upsert=True,
        )

    def update_state(self, conversation_id: str, **changes) -> dict:
        """Merge state changes into a conversation and return the new state."""
        state = self.get_state(conversation_id)
        state.update(changes)
        self.set_state(conversation_id, state)
        return state
