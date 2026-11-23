import unittest
from collections import Counter

from app import create_app
from app.demo import DEMO_PASSWORD, RESTAURANTS, USERS
from app.models import MenuItem, Restaurant, Review, User, db
from app.restaurants import MAX_COMMENT, validate


class SeedDemoTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.runner = self.app.test_cli_runner()

    def seed(self):
        result = self.runner.invoke(args=["seed-demo"])
        self.assertEqual(result.exit_code, 0, result.output)
        return result.output

    def counts(self):
        with self.app.app_context():
            return {
                model.__name__: db.session.scalar(
                    db.select(db.func.count()).select_from(model)
                )
                for model in (User, Restaurant, MenuItem, Review)
            }

    def test_creates_accounts_restaurants_menus_and_reviews(self):
        output = self.seed()

        self.assertIn("已加入範例資料", output)
        self.assertEqual(
            self.counts(),
            {
                "User": 2,
                "Restaurant": 12,
                "MenuItem": sum(len(data["menu"]) for data in RESTAURANTS),
                "Review": sum(len(data["reviews"]) for data in RESTAURANTS),
            },
        )
        with self.app.app_context():
            rows = db.session.execute(
                db.select(User.username, Restaurant.is_public).join(Restaurant.owner)
            ).all()
        self.assertEqual(
            Counter(rows),
            {("demo", True): 2, ("demo", False): 4, ("foodie", True): 6},
        )

    def test_demo_account_sees_both_sources_on_home(self):
        self.seed()
        client = self.app.test_client()

        response = client.post(
            "/login",
            data={"username": "demo", "password": DEMO_PASSWORD},
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertEqual(response.request.path, "/home")
        self.assertEqual(html.count('<span class="meta">我的餐廳</span>'), 3)
        self.assertEqual(html.count('<span class="meta">公用餐廳</span>'), 3)

    def test_running_twice_changes_nothing(self):
        self.seed()
        before = self.counts()

        output = self.seed()

        self.assertIn("範例資料已經存在，沒有變更", output)
        self.assertEqual(self.counts(), before)

    def test_existing_demo_username_blocks_seeding(self):
        self.app.test_client().post(
            "/register", data={"username": "foodie", "password": "mine"}
        )

        output = self.seed()

        self.assertIn("範例資料已經存在，沒有變更", output)
        self.assertEqual(self.counts()["User"], 1)
        self.assertEqual(self.counts()["Restaurant"], 0)

    def test_sample_restaurants_pass_the_form_validation(self):
        for data in RESTAURANTS:
            with self.subTest(name=data["name"]):
                form = {
                    "name": data["name"],
                    "address": data["address"],
                    "category": data["category"],
                    "note": data["note"],
                    "price_level": str(data["price_level"]),
                    "latitude": str(data["latitude"]),
                    "longitude": str(data["longitude"]),
                    "items": [
                        {"name": name, "price": str(price)} for name, price in data["menu"]
                    ],
                    "stars": "",
                    "review_comment": "",
                }
                self.assertIsNone(validate(form, {}))

    def test_sample_reviews_are_allowed(self):
        usernames = {user["username"] for user in USERS}
        for data in RESTAURANTS:
            with self.subTest(name=data["name"]):
                reviewers = [username for username, _, _ in data["reviews"]]
                # One review per user, and only on their own or a public restaurant.
                self.assertEqual(len(reviewers), len(set(reviewers)))
                for username, stars, comment in data["reviews"]:
                    self.assertIn(username, usernames)
                    self.assertTrue(data["is_public"] or username == data["owner"])
                    self.assertIn(stars, range(1, 6))
                    self.assertLessEqual(len(comment), MAX_COMMENT)


if __name__ == "__main__":
    unittest.main()
