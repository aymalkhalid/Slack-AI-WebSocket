import importlib
import sys
import types
import unittest


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(output_text=" remembered reply ")


class FakeOpenAIClient:
    def __init__(self):
        self.responses = FakeResponses()


def import_ai_handler_with_fakes():
    sys.modules.pop("ai_handler", None)

    fake_openai = types.ModuleType("openai")
    fake_openai.APIError = RuntimeError
    fake_openai.OpenAI = lambda **kwargs: FakeOpenAIClient()
    sys.modules["openai"] = fake_openai

    return importlib.import_module("ai_handler")


class AiHandlerMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ai_handler = import_ai_handler_with_fakes()

    def test_build_response_input_uses_plain_prompt_without_history(self):
        self.assertEqual(
            self.ai_handler._build_response_input("hello", history=[]),
            "hello",
        )

    def test_build_response_input_appends_current_user_turn_to_history(self):
        self.assertEqual(
            self.ai_handler._build_response_input(
                "what is my name?",
                history=[
                    {"role": "user", "content": "My name is Ada."},
                    {"role": "assistant", "content": "Nice to meet you, Ada."},
                    {"role": "tool", "content": "ignored"},
                    {"role": "user", "content": "   "},
                ],
            ),
            [
                {"role": "user", "content": "My name is Ada."},
                {"role": "assistant", "content": "Nice to meet you, Ada."},
                {"role": "user", "content": "what is my name?"},
            ],
        )

    def test_generate_ai_reply_sends_history_to_openai(self):
        client = FakeOpenAIClient()
        self.ai_handler._openai_client = client

        reply = self.ai_handler.generate_ai_reply(
            "what is my name?",
            history=[
                {"role": "user", "content": "My name is Ada."},
                {"role": "assistant", "content": "Nice to meet you, Ada."},
            ],
        )

        self.assertEqual(reply, "remembered reply")
        self.assertEqual(
            client.responses.calls[0]["input"],
            [
                {"role": "user", "content": "My name is Ada."},
                {"role": "assistant", "content": "Nice to meet you, Ada."},
                {"role": "user", "content": "what is my name?"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
