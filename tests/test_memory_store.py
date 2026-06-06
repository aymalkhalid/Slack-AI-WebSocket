import os
import unittest

from memory_store import ConversationMemoryStore, memory_max_turns


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeUpdateResult:
    def __init__(self, upserted_id=None):
        self.upserted_id = upserted_id


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field_name, direction):
        self.documents.sort(
            key=lambda document: document[field_name],
            reverse=direction < 0,
        )
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    def __init__(self):
        self.documents = []
        self.indexes = []

    def create_index(self, index_spec, unique=False):
        self.indexes.append((index_spec, unique))

    def update_one(self, filter_doc, update_doc, upsert=False):
        document = self._find_matching_document(filter_doc)
        is_insert = document is None

        if is_insert:
            if not upsert:
                return FakeUpdateResult()
            document = dict(filter_doc)
            self.documents.append(document)

        if is_insert:
            document.update(update_doc.get("$setOnInsert", {}))
        document.update(update_doc.get("$set", {}))
        return FakeUpdateResult(document.get("_id") if is_insert else None)

    def insert_one(self, document):
        stored_document = dict(document)
        stored_document["_id"] = len(self.documents) + 1
        self.documents.append(stored_document)
        return FakeInsertResult(stored_document["_id"])

    def find(self, filter_doc, projection=None):
        return FakeCursor(
            [
                self._project(document, projection)
                for document in self.documents
                if self._matches(document, filter_doc)
            ]
        )

    def find_one(self, filter_doc, projection=None):
        document = self._find_matching_document(filter_doc)
        if document is None:
            return None
        return self._project(document, projection)

    def _find_matching_document(self, filter_doc):
        for document in self.documents:
            if self._matches(document, filter_doc):
                return document
        return None

    def _matches(self, document, filter_doc):
        return all(document.get(key) == value for key, value in filter_doc.items())

    def _project(self, document, projection):
        if projection is None:
            return dict(document)

        include_fields = {
            key
            for key, value in projection.items()
            if value and key != "_id"
        }
        projected = {
            key: document[key]
            for key in include_fields
            if key in document
        }

        if projection.get("_id", 1) and "_id" in document:
            projected["_id"] = document["_id"]

        return projected


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, collection_name):
        return self.collections.setdefault(collection_name, FakeCollection())


class FakeAdmin:
    def __init__(self):
        self.commands = []

    def command(self, command_name):
        self.commands.append(command_name)
        return {"ok": 1}


class FakeMongoClient:
    def __init__(self):
        self.databases = {}
        self.admin = FakeAdmin()
        self.closed = False

    def __getitem__(self, database_name):
        return self.databases.setdefault(database_name, FakeDatabase())

    def close(self):
        self.closed = True


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeMongoClient()
        self.store = ConversationMemoryStore(
            "mongodb+srv://example.invalid",
            database_name="test_memory",
            client=self.client,
        )

    def tearDown(self):
        self.store.close()

    def test_turns_load_in_chronological_order(self):
        conversation_id = "workspace:channel:C123:1710000000.000100"
        self.store.ensure_conversation(
            conversation_id,
            channel_id="C123",
            thread_ts="1710000000.000100",
            channel_type="channel",
        )
        self.store.append_turn(
            conversation_id,
            "user",
            "My name is Ada.",
            user_id="U123",
            slack_ts="1710000000.000100",
        )
        self.store.append_turn(
            conversation_id,
            "assistant",
            "Nice to meet you, Ada.",
        )

        self.assertEqual(
            self.store.get_recent_turns(conversation_id, limit=10),
            [
                {"role": "user", "content": "My name is Ada."},
                {"role": "assistant", "content": "Nice to meet you, Ada."},
            ],
        )

    def test_recent_turn_limit_keeps_latest_turns_in_order(self):
        conversation_id = "workspace:dm:D123:default"
        self.store.ensure_conversation(
            conversation_id,
            channel_id="D123",
            channel_type="im",
        )

        for index in range(5):
            self.store.append_turn(conversation_id, "user", f"user turn {index}")

        self.assertEqual(
            self.store.get_recent_turns(conversation_id, limit=3),
            [
                {"role": "user", "content": "user turn 2"},
                {"role": "user", "content": "user turn 3"},
                {"role": "user", "content": "user turn 4"},
            ],
        )

    def test_state_is_stored_in_conversation_document(self):
        conversation_id = "workspace:channel:C123:1710000000.000100"
        self.store.ensure_conversation(conversation_id)
        self.store.update_state(
            conversation_id,
            last_user_id="U123",
            active_role="support",
        )

        self.assertEqual(
            self.store.get_state(conversation_id),
            {"active_role": "support", "last_user_id": "U123"},
        )

    def test_invalid_role_is_rejected(self):
        conversation_id = "workspace:dm:D123:default"
        self.store.ensure_conversation(conversation_id)

        with self.assertRaises(ValueError):
            self.store.append_turn(conversation_id, "invalid", "content")

    def test_ping_uses_mongo_admin_command(self):
        self.assertTrue(self.store.ping())
        self.assertEqual(self.client.admin.commands, ["ping"])

    def test_missing_mongodb_uri_is_rejected_without_injected_client(self):
        original_value = os.environ.get("MONGODB_URI")
        os.environ.pop("MONGODB_URI", None)

        try:
            with self.assertRaises(RuntimeError):
                ConversationMemoryStore()
        finally:
            if original_value is not None:
                os.environ["MONGODB_URI"] = original_value

    def test_memory_max_turns_env_falls_back_on_invalid_value(self):
        original_value = os.environ.get("MEMORY_MAX_TURNS")
        os.environ["MEMORY_MAX_TURNS"] = "not-a-number"

        try:
            self.assertEqual(memory_max_turns(), 12)
        finally:
            if original_value is None:
                os.environ.pop("MEMORY_MAX_TURNS", None)
            else:
                os.environ["MEMORY_MAX_TURNS"] = original_value


if __name__ == "__main__":
    unittest.main()
