import json
import re
import unittest

from app import create_app
from app.location import Location, get_user_location

TEST_CONFIG = {
    "TESTING": True,
    "SECRET_KEY": "test",
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
}

TAIPEI = {"latitude": 25.0339, "longitude": 121.5645, "accuracy": 12}


class LocationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app({**TEST_CONFIG, "WTF_CSRF_ENABLED": False})
        self.client = self.app.test_client()

    def store(self, data):
        return self.client.post("/location", json=data)

    def stored_location(self):
        with self.client:
            self.client.get("/login")
            return get_user_location()

    def test_no_location_by_default(self):
        self.assertIsNone(self.stored_location())

    def test_store_valid_location(self):
        response = self.store(TAIPEI)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.get_data(), b"")
        location = self.stored_location()
        self.assertEqual(location, Location(25.0339, 121.5645, 12.0))
        self.assertTrue(all(isinstance(value, float) for value in location))

    def test_extra_keys_are_ignored(self):
        response = self.store({**TAIPEI, "altitude": 10})

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.stored_location(), Location(25.0339, 121.5645, 12.0))

    def test_invalid_location_is_rejected_and_old_one_kept(self):
        self.store(TAIPEI)
        missing_key = {k: v for k, v in TAIPEI.items() if k != "accuracy"}
        json_bodies = [
            {**TAIPEI, "latitude": 91},
            {**TAIPEI, "latitude": -91},
            {**TAIPEI, "longitude": 181},
            {**TAIPEI, "longitude": -181},
            {**TAIPEI, "accuracy": -1},
            {**TAIPEI, "latitude": "25"},
            {**TAIPEI, "latitude": True},
            missing_key,
            [25.0, 121.5, 10.0],
        ]
        for body in json_bodies:
            with self.subTest(body=body):
                response = self.store(body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json(), {"error": "invalid location"})

        raw_bodies = [
            '{"latitude": NaN, "longitude": 121.5, "accuracy": 10}',
            '{"latitude": 25.0, "longitude": Infinity, "accuracy": 10}',
            '{"latitude": 25.0, "longitude": 121.5, "accuracy": -Infinity}',
            "not json",
        ]
        for body in raw_bodies:
            with self.subTest(body=body):
                response = self.client.post(
                    "/location", data=body, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)

        self.assertEqual(self.stored_location(), Location(25.0339, 121.5645, 12.0))

    def test_delete_location(self):
        self.store(TAIPEI)

        response = self.client.delete("/location")

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.stored_location())

    def test_delete_without_location(self):
        self.assertEqual(self.client.delete("/location").status_code, 204)

    def test_logout_forgets_location(self):
        credentials = {"username": "alice", "password": "pw"}
        self.client.post("/register", data=credentials)
        self.client.post("/login", data=credentials)
        self.store(TAIPEI)
        self.assertIsNotNone(self.stored_location())

        self.client.post("/logout")

        self.assertIsNone(self.stored_location())

    def test_login_forgets_location(self):
        credentials = {"username": "alice", "password": "pw"}
        self.client.post("/register", data=credentials)
        self.store(TAIPEI)

        self.client.post("/login", data=credentials)

        self.assertIsNone(self.stored_location())

    def test_corrupt_session_value_is_ignored(self):
        for stored in ["text", [1.0, 2.0], [1.0, 2.0, "x"], [100.0, 0.0, 1.0], None]:
            with self.subTest(stored=stored):
                with self.client.session_transaction() as sess:
                    sess["location"] = stored
                self.assertIsNone(self.stored_location())

    def test_pages_load_the_helper(self):
        html = self.client.get("/login").get_data(as_text=True)

        self.assertIn('<meta name="csrf-token" content="', html)
        self.assertRegex(html, r'<script src="/static/location\.js[^"]*" defer>')
        response = self.client.get("/static/location.js")
        self.assertEqual(response.status_code, 200)
        response.close()


class LocationCsrfTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TEST_CONFIG)
        self.client = self.app.test_client()

    def stored_location(self):
        with self.client:
            self.client.get("/login")
            return get_user_location()

    def csrf_token(self):
        html = self.client.get("/login").get_data(as_text=True)
        return re.search(r'<meta name="csrf-token" content="([^"]+)"', html).group(1)

    def test_post_without_token_stores_nothing(self):
        response = self.client.post("/location", json=TAIPEI)

        self.assertNotEqual(response.status_code, 204)
        self.assertIsNone(self.stored_location())

    def test_post_and_delete_with_token(self):
        headers = {"X-CSRFToken": self.csrf_token()}

        response = self.client.post(
            "/location", data=json.dumps(TAIPEI),
            content_type="application/json", headers=headers,
        )
        self.assertEqual(response.status_code, 204)
        self.assertIsNotNone(self.stored_location())

        response = self.client.delete("/location", headers=headers)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.stored_location())


if __name__ == "__main__":
    unittest.main()
