import re
import unittest

from app import create_app

NAV = 'class="site-nav"'
# Everything the shared button bar links to. The pick link may carry ?scope=...
NAV_LINKS = [
    'href="/restaurants/?scope=mine"',
    'href="/restaurants/?scope=public"',
    'href="/restaurants/?scope=favorites"',
    'href="/restaurants/new"',
    'href="/restaurants/pick',
    'href="/users/1"',
    'action="/logout"',
]
LOGGED_IN_PAGES = [
    "/restaurants/",
    "/restaurants/?scope=public",
    "/restaurants/?scope=favorites",
    "/restaurants/new",
    "/restaurants/1",
    "/restaurants/1/edit",
    "/restaurants/pick",
    "/users/1",
    "/users/2",
    "/settings",
]


class NavTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.alice = self.logged_in_client("alice")  # user 1
        self.logged_in_client("bob")  # user 2, for viewing someone else's profile
        self.alice.post("/restaurants/new", data={"name": "拉麵店"})  # restaurant 1

    def logged_in_client(self, username):
        client = self.app.test_client()
        data = {"username": username, "password": "pw"}
        client.post("/register", data=data)
        client.post("/login", data=data)
        return client

    def html(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(as_text=True)

    def current(self, html):
        """Labels of the bar buttons marked as the current page."""
        return re.findall(r'aria-current="page">([^<]+)</a>', html)

    def test_home_redirects_to_my_restaurants(self):
        response = self.alice.get("/home")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/restaurants/"))

    def test_bar_is_on_every_logged_in_page(self):
        for path in LOGGED_IN_PAGES:
            with self.subTest(path=path):
                html = self.html(self.alice, path)
                self.assertEqual(html.count(NAV), 1)
                for link in NAV_LINKS:
                    self.assertIn(link, html)

    def test_bar_comes_before_flash_messages(self):
        response = self.alice.post(
            "/restaurants/new", data={"name": "咖啡店"}, follow_redirects=True
        )
        html = response.get_data(as_text=True)

        self.assertLess(html.index(NAV), html.index("已新增餐廳"))

    def test_bar_is_hidden_when_logged_out(self):
        anonymous = self.app.test_client()

        for path in ["/login", "/register", "/users/1"]:
            with self.subTest(path=path):
                self.assertNotIn(NAV, self.html(anonymous, path))

    def test_bar_is_hidden_on_login_and_register_when_logged_in(self):
        for path in ["/login", "/register"]:
            with self.subTest(path=path):
                self.assertNotIn(NAV, self.html(self.alice, path))

    def test_current_page_is_marked(self):
        for path, expected in [
            ("/restaurants/", ["我的餐廳"]),
            ("/restaurants/?scope=public", ["公用餐廳"]),
            ("/restaurants/?scope=favorites", ["♥ 我的收藏"]),
            ("/restaurants/?scope=unknown", ["我的餐廳"]),
            ("/restaurants/new", ["＋ 新增餐廳"]),
            ("/restaurants/pick", ["🎲 隨機抽一間"]),
            ("/restaurants/pick?scope=public", ["🎲 隨機抽一間"]),
            ("/restaurants/1", []),
            ("/restaurants/1/edit", []),
            ("/users/1", []),
            ("/settings", []),
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.current(self.html(self.alice, path)), expected)

    def test_pick_button_keeps_the_list_scope(self):
        self.assertIn(
            'href="/restaurants/pick?scope=public"',
            self.html(self.alice, "/restaurants/?scope=public"),
        )
        self.assertIn('href="/restaurants/pick"', self.html(self.alice, "/restaurants/1"))


if __name__ == "__main__":
    unittest.main()
