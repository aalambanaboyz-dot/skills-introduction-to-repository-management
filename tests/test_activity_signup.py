import unittest
from unittest.mock import patch

import mongomock
from fastapi import HTTPException

from src.backend.routers import activities


class SignupCapacityTests(unittest.TestCase):
    def setUp(self):
        self.db = mongomock.MongoClient().test
        self.db.teachers.insert_one({"_id": "teacher"})
        self.db.activities.insert_one({
            "_id": "Chess Club",
            "max_participants": 2,
            "participants": ["first@example.edu"],
        })
        for name in ("activities", "teachers"):
            patcher = patch.object(activities, f"{name}_collection", self.db[name])
            patcher.start()
            self.addCleanup(patcher.stop)

    def signup(self, email="new@example.edu"):
        return activities.signup_for_activity("Chess Club", email, "teacher")

    def participants(self):
        return self.db.activities.find_one({"_id": "Chess Club"})["participants"]

    def assert_full(self):
        with self.assertRaises(HTTPException) as caught:
            self.signup()
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail, "Activity is full")

    def test_full_activity_rejects_signup_without_changing_participants(self):
        self.db.activities.update_one({}, {"$set": {"max_participants": 1}})
        self.assert_full()
        self.assertEqual(self.participants(), ["first@example.edu"])

    def test_over_capacity_activity_rejects_signup(self):
        self.db.activities.update_one({}, {"$set": {
            "max_participants": 1,
            "participants": ["first@example.edu", "second@example.edu"],
        }})
        self.assert_full()
        self.assertEqual(len(self.participants()), 2)

    def test_zero_capacity_activity_rejects_signup(self):
        self.db.activities.update_one({}, {"$set": {
            "max_participants": 0, "participants": [],
        }})
        self.assert_full()
        self.assertEqual(self.participants(), [])

    def test_last_available_spot_can_be_filled(self):
        result = self.signup()
        self.assertEqual(result, {
            "message": "Signed up new@example.edu for Chess Club",
        })
        self.assertEqual(self.participants(), ["first@example.edu", "new@example.edu"])

    def test_signup_rechecks_capacity_when_another_request_fills_last_spot(self):
        update_one = self.db.activities.update_one

        def fill_last_spot_then_update(query, update):
            update_one({}, {"$push": {"participants": "other@example.edu"}})
            return update_one(query, update)

        with patch.object(self.db.activities, "update_one", side_effect=fill_last_spot_then_update):
            self.assert_full()
        self.assertEqual(self.participants(), ["first@example.edu", "other@example.edu"])

    def test_duplicate_signup_remains_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.signup("first@example.edu")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail, "Already signed up for this activity")
        self.assertEqual(self.participants(), ["first@example.edu"])


if __name__ == "__main__":
    unittest.main()
