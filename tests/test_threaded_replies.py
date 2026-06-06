import importlib
import sys
import types
import unittest


class FakeApp:
    def __init__(self, token=None):
        self.token = token

    def event(self, _event_name):
        def decorator(handler):
            return handler

        return decorator


class FakeSocketModeHandler:
    def __init__(self, app, app_token):
        self.app = app
        self.app_token = app_token

    def start(self):
        return None


class FakeMemoryStore:
    def __init__(self, history=None):
        self.history = history or []
        self.conversations = []
        self.turns = []
        self.states = []

    def ensure_conversation(self, conversation_id, **metadata):
        self.conversations.append((conversation_id, metadata))

    def get_recent_turns(self, conversation_id, limit=None):
        return list(self.history)

    def append_turn(self, conversation_id, role, content, **metadata):
        self.turns.append((conversation_id, role, content, metadata))
        return len(self.turns)

    def update_state(self, conversation_id, **changes):
        self.states.append((conversation_id, changes))
        return changes


def import_main_with_fakes():
    sys.modules.pop("main", None)

    fake_ai_handler = types.ModuleType("ai_handler")
    fake_ai_handler.calls = []

    def generate_ai_reply(text, history=None):
        fake_ai_handler.calls.append((text, history or []))
        return f"AI: {text}"

    fake_ai_handler.generate_ai_reply = generate_ai_reply

    fake_slack_bolt = types.ModuleType("slack_bolt")
    fake_slack_bolt.App = FakeApp

    fake_socket_mode = types.ModuleType("slack_bolt.adapter.socket_mode")
    fake_socket_mode.SocketModeHandler = FakeSocketModeHandler

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda: None

    sys.modules["ai_handler"] = fake_ai_handler
    sys.modules["slack_bolt"] = fake_slack_bolt
    sys.modules["slack_bolt.adapter.socket_mode"] = fake_socket_mode
    sys.modules["dotenv"] = fake_dotenv

    return importlib.import_module("main")


class ThreadedReplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = import_main_with_fakes()

    def setUp(self):
        self.memory_store = FakeMemoryStore()
        self.main._memory_store = self.memory_store
        sys.modules["ai_handler"].calls.clear()

    def test_thread_ts_for_top_level_message_uses_message_ts(self):
        event = {"ts": "1710000000.000100"}

        self.assertEqual(
            self.main._thread_ts_for_reply(event),
            "1710000000.000100",
        )

    def test_thread_ts_for_threaded_message_uses_parent_thread_ts(self):
        event = {
            "ts": "1710000001.000200",
            "thread_ts": "1710000000.000100",
        }

        self.assertEqual(
            self.main._thread_ts_for_reply(event),
            "1710000000.000100",
        )

    def test_app_mention_replies_in_new_thread_for_top_level_mention(self):
        calls = []
        body = {
            "authorizations": [{"user_id": "UBOT"}],
            "event": {
                "user": "U123",
                "channel": "C123",
                "ts": "1710000000.000100",
                "text": "<@UBOT> hello",
            },
        }

        self.main.handle_mentions(
            body,
            lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        self.assertEqual(
            calls,
            [((), {"text": "AI: hello", "thread_ts": "1710000000.000100"})],
        )
        self.assertEqual(
            self.memory_store.turns,
            [
                (
                    "workspace:channel:C123:1710000000.000100",
                    "user",
                    "hello",
                    {"user_id": "U123", "slack_ts": "1710000000.000100"},
                ),
                (
                    "workspace:channel:C123:1710000000.000100",
                    "assistant",
                    "AI: hello",
                    {"slack_ts": "1710000000.000100"},
                ),
            ],
        )

    def test_app_mention_replies_in_existing_thread(self):
        calls = []
        body = {
            "authorizations": [{"user_id": "UBOT"}],
            "event": {
                "user": "U123",
                "channel": "C123",
                "ts": "1710000001.000200",
                "thread_ts": "1710000000.000100",
                "text": "<@UBOT> follow up",
            },
        }

        self.main.handle_mentions(
            body,
            lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        self.assertEqual(
            calls,
            [((), {"text": "AI: follow up", "thread_ts": "1710000000.000100"})],
        )
        self.assertEqual(
            self.memory_store.conversations[0][0],
            "workspace:channel:C123:1710000000.000100",
        )

    def test_top_level_dm_stays_top_level(self):
        calls = []
        body = {
            "event": {
                "user": "U123",
                "channel": "D123",
                "channel_type": "im",
                "ts": "1710000000.000100",
                "text": "hello",
            },
        }

        self.main.handle_direct_messages(
            body,
            lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        self.assertEqual(calls, [(("AI: hello",), {})])
        self.assertEqual(
            self.memory_store.turns[0][0],
            "workspace:dm:D123:default",
        )

    def test_threaded_dm_stays_in_thread(self):
        calls = []
        body = {
            "event": {
                "user": "U123",
                "channel": "D123",
                "channel_type": "im",
                "ts": "1710000001.000200",
                "thread_ts": "1710000000.000100",
                "text": "follow up",
            },
        }

        self.main.handle_direct_messages(
            body,
            lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        self.assertEqual(
            calls,
            [((), {"text": "AI: follow up", "thread_ts": "1710000000.000100"})],
        )
        self.assertEqual(
            self.memory_store.turns[0][0],
            "workspace:dm:D123:1710000000.000100",
        )

    def test_existing_memory_history_is_sent_to_ai_handler(self):
        self.memory_store.history = [
            {"role": "user", "content": "My name is Ada."},
            {"role": "assistant", "content": "Nice to meet you, Ada."},
        ]
        body = {
            "team_id": "T123",
            "authorizations": [{"user_id": "UBOT"}],
            "event": {
                "user": "U123",
                "channel": "C123",
                "ts": "1710000001.000200",
                "thread_ts": "1710000000.000100",
                "text": "<@UBOT> what is my name?",
            },
        }

        self.main.handle_mentions(body, lambda *args, **kwargs: None)

        self.assertEqual(
            sys.modules["ai_handler"].calls,
            [
                (
                    "what is my name?",
                    [
                        {"role": "user", "content": "My name is Ada."},
                        {"role": "assistant", "content": "Nice to meet you, Ada."},
                    ],
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
