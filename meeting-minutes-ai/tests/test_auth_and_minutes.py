import tempfile
import unittest
from pathlib import Path

from db import db_utils


class AuthAndMinutesTests(unittest.TestCase):
    def setUp(self):
        self.db_file = Path(tempfile.mkdtemp()) / "test_meetings.db"
        db_utils.DB_PATH = self.db_file
        db_utils.init_db()

    def test_user_scoped_meetings_and_auth(self):
        user_a = db_utils.create_user("Ada", "ada@example.com", "secret123")
        user_b = db_utils.create_user("Grace", "grace@example.com", "secret123")

        meeting_a1 = db_utils.create_meeting("Sprint review", "2026-09-26", user_a["user_id"])
        meeting_a2 = db_utils.create_meeting("Planning", "2026-09-27", user_a["user_id"])
        db_utils.create_meeting("Other team", "2026-09-28", user_b["user_id"])

        self.assertEqual(
            db_utils.authenticate_user("ada@example.com", "secret123")["user_id"],
            user_a["user_id"],
        )
        self.assertEqual(
            [m["title"] for m in db_utils.get_recent_meetings(limit=10, user_id=user_a["user_id"])],
            ["Planning", "Sprint review"],
        )
        self.assertEqual(len(db_utils.get_recent_meetings(limit=10, user_id=user_b["user_id"])), 1)
        self.assertEqual(meeting_a1[0], 1)
        self.assertEqual(meeting_a2[0], 2)

    def test_minutes_include_conversation_facts(self):
        conversation = "\n".join([
            "Maya: We agreed to launch on Friday.",
            "Leo: I will send the revised timeline by Thursday.",
            "Maya: Priya will prepare the customer brief.",
        ])

        minutes = db_utils.build_minutes_from_conversation(
            meeting_title="Launch review",
            date="2026-09-26",
            conversation=conversation,
            user_name="Ada",
        )

        self.assertIn("Launch review", minutes)
        self.assertIn("launch on friday", minutes.lower())
        self.assertIn("revised timeline", minutes.lower())
        self.assertIn("customer brief", minutes.lower())


if __name__ == "__main__":
    unittest.main()
