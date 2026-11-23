import unittest

from app import create_app
from app.models import User, db


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.client = self.app.test_client()

    def post(self, path, username="alice", password="pw"):
        return self.client.post(
            path,
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def users(self):
        with self.app.app_context():
            return db.session.scalars(db.select(User)).all()

    def test_register_stores_hashed_password(self):
        response = self.post("/register", password="secret")

        self.assertIn("註冊成功", response.get_data(as_text=True))
        self.assertEqual(response.request.path, "/login")
        users = self.users()
        self.assertEqual(len(users), 1)
        self.assertNotIn("secret", users[0].password_hash)

    def test_register_does_not_log_in(self):
        self.post("/register")

        self.assertEqual(self.client.get("/restaurants/").status_code, 302)

    def test_duplicate_username_is_rejected(self):
        self.post("/register")
        response = self.post("/register", password="other")

        self.assertIn("已被使用", response.get_data(as_text=True))
        self.assertEqual(len(self.users()), 1)

    def test_username_is_case_sensitive(self):
        self.post("/register", username="Alice")
        self.post("/register", username="alice")

        self.assertEqual(len(self.users()), 2)

    def test_username_surrounding_spaces_are_removed(self):
        self.post("/register", username="  alice  ")

        self.assertEqual(self.users()[0].username, "alice")

    def test_username_length_limit(self):
        self.post("/register", username="a" * 30)
        response = self.post("/register", username="a" * 31)

        self.assertIn("不能超過", response.get_data(as_text=True))
        self.assertEqual(len(self.users()), 1)

    def test_blank_fields_are_rejected(self):
        for username, password in [("   ", "pw"), ("alice", "   "), ("alice", "")]:
            with self.subTest(username=username, password=password):
                self.post("/register", username=username, password=password)
                self.assertEqual(self.users(), [])

    def test_any_nonblank_password_is_accepted(self):
        self.post("/register", password="1")

        self.assertEqual(self.post("/login", password="1").request.path, "/home")

    def test_login_leads_to_home(self):
        self.post("/register")
        response = self.post("/login")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request.path, "/home")

    def test_login_failures_show_the_same_error(self):
        self.post("/register")

        for username, password in [("alice", "wrong"), ("nobody", "pw"), ("ALICE", "pw")]:
            with self.subTest(username=username):
                response = self.post("/login", username=username, password=password)
                self.assertEqual(response.request.path, "/login")
                self.assertIn("用戶名或密碼錯誤", response.get_data(as_text=True))

    def test_home_requires_login(self):
        response = self.client.get("/home", follow_redirects=True)

        self.assertEqual(response.request.path, "/login")

    def test_session_ends_with_browser(self):
        self.post("/register")
        response = self.client.post(
            "/login", data={"username": "alice", "password": "pw"}
        )

        cookie = response.headers["Set-Cookie"].lower()
        self.assertNotIn("expires", cookie)
        self.assertNotIn("max-age", cookie)

    def test_session_for_missing_user_is_rejected(self):
        self.post("/register")
        self.post("/login")
        with self.app.app_context():
            db.session.execute(db.delete(User))
            db.session.commit()

        response = self.client.get("/home", follow_redirects=True)

        self.assertEqual(response.request.path, "/login")

    def test_logout_ends_session(self):
        self.post("/register")
        self.post("/login")

        response = self.client.post("/logout", follow_redirects=True)

        self.assertEqual(response.request.path, "/login")
        self.assertEqual(self.client.get("/restaurants/").status_code, 302)

    def test_index_redirects_by_login_state(self):
        self.assertEqual(
            self.client.get("/", follow_redirects=True).request.path, "/login"
        )

        self.post("/register")
        self.post("/login")

        self.assertEqual(
            self.client.get("/", follow_redirects=True).request.path, "/home"
        )


class CsrfTestCase(unittest.TestCase):
    def test_post_without_token_is_rejected(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            }
        )

        response = app.test_client().post(
            "/register",
            data={"username": "alice", "password": "pw"},
            follow_redirects=True,
        )

        self.assertIn("頁面已過期", response.get_data(as_text=True))
        with app.app_context():
            self.assertEqual(db.session.scalars(db.select(User)).all(), [])


if __name__ == "__main__":
    unittest.main()
