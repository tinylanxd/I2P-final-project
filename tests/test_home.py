import random
import re
import unittest
from collections import Counter

from app import create_app
from app.main import recommend
from app.picker import weighted_sample

RELOAD = '<a class="button secondary" href="/home">🔄 換一批</a>'
EMPTY = "還沒有可以推薦的餐廳"
CARD_TITLE = re.compile(r'<h2><a href="(/restaurants/\d+)">([^<]+)</a></h2>')
LABEL = re.compile(r'<span class="meta">(我的餐廳|公用餐廳)</span>')


def keep_random_state(test):
    """Seed the random module for one test and restore it afterwards."""
    test.addCleanup(random.setstate, random.getstate())
    random.seed(0)


class HomeTestCase(unittest.TestCase):
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
        self.bob = self.logged_in_client("bob")  # user 2

    def logged_in_client(self, username):
        client = self.app.test_client()
        data = {"username": username, "password": "pw"}
        client.post("/register", data=data)
        client.post("/login", data=data)
        return client

    def add(self, client, name, public=False, stars=""):
        data = {"name": name, "stars": stars}
        if public:
            data["is_public"] = "on"
        client.post("/restaurants/new", data=data)

    def add_many(self, client, prefix, count, public=False):
        for n in range(count):
            self.add(client, f"{prefix}{n}", public=public)

    def html(self, client=None):
        response = (client or self.alice).get("/home")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def cards(self, html):
        """(restaurant link, name, source label) for every recommended card."""
        cards = []
        for chunk in html.split('<article class="item">')[1:]:
            link, name = CARD_TITLE.search(chunk).groups()
            label = LABEL.search(chunk)
            cards.append((link, name, label and label.group(1)))
        return cards

    def labels(self, html):
        return Counter(label for _, _, label in self.cards(html))

    # ------------------------------------------------------------- the page

    def test_title_heading_and_current_button(self):
        html = self.html()

        self.assertIn("<title>首頁 - 美食地圖</title>", html)
        self.assertIn("<h1>今天吃什麼？</h1>", html)
        self.assertIn('href="/home" aria-current="page">首頁</a>', html)

    def test_empty_state(self):
        html = self.html()

        self.assertIn(EMPTY, html)
        self.assertEqual(self.cards(html), [])
        self.assertNotIn(RELOAD, html)

    def test_reload_button_links_to_home(self):
        self.add(self.alice, "拉麵店")

        html = self.html()

        self.assertIn(RELOAD, html)
        self.assertNotIn(EMPTY, html)

    def test_cards_have_no_action_buttons(self):
        self.add(self.alice, "拉麵店", public=True)
        self.add(self.bob, "牛肉麵", public=True)

        html = self.html()

        self.assertEqual(len(self.cards(html)), 2)
        for action in ["/edit", "/share", "/delete", "/favorite", "/save"]:
            with self.subTest(action=action):
                self.assertNotIn(action, html)

    def test_card_shows_restaurant_details(self):
        self.bob.post(
            "/restaurants/new",
            data={
                "name": "牛肉麵",
                "category": "麵食",
                "address": "新竹市東區東門街",
                "price_level": "2",
                "is_public": "on",
                "item_name": "紅燒牛肉麵",
                "item_price": "200",
                "stars": "4",
            },
        )

        html = self.html()

        for text in ["牛肉麵", "麵食", "$$", "新竹市東區東門街", "紅燒牛肉麵", "NT$ 200",
                     "4.0（1 則評價）", "分享者：bob", "公用餐廳"]:
            with self.subTest(text=text):
                self.assertIn(text, html)

    # -------------------------------------------------- which restaurants

    def test_three_from_each_side_when_both_have_enough(self):
        self.add_many(self.alice, "我的", 5)
        self.add_many(self.bob, "公用", 5, public=True)

        for _ in range(5):
            self.assertEqual(self.labels(self.html()), {"我的餐廳": 3, "公用餐廳": 3})

    def test_public_fills_up_when_few_of_mine(self):
        self.add_many(self.alice, "我的", 2)
        self.add_many(self.bob, "公用", 10, public=True)

        for _ in range(5):
            self.assertEqual(self.labels(self.html()), {"我的餐廳": 2, "公用餐廳": 4})

    def test_mine_fills_up_when_nothing_public(self):
        self.add_many(self.alice, "我的", 10)
        self.add_many(self.bob, "秘密", 3)  # bob's private restaurants

        for _ in range(5):
            self.assertEqual(self.labels(self.html()), {"我的餐廳": 6})

    def test_no_restaurant_appears_twice(self):
        self.add_many(self.alice, "我的", 4, public=True)
        self.add_many(self.bob, "公用", 4, public=True)

        for _ in range(5):
            links = [link for link, _, _ in self.cards(self.html())]
            self.assertEqual(len(links), 6)
            self.assertEqual(len(set(links)), 6)

    def test_never_shows_private_restaurants_of_others(self):
        self.add(self.alice, "拉麵店")
        self.add_many(self.bob, "秘密", 3)

        html = self.html()

        self.assertEqual([name for _, name, _ in self.cards(html)], ["拉麵店"])
        self.assertNotIn("秘密", html)

    def test_own_public_restaurant_is_labelled_mine(self):
        self.add(self.alice, "拉麵店", public=True)

        self.assertEqual(
            self.cards(self.html(self.alice)), [("/restaurants/1", "拉麵店", "我的餐廳")]
        )
        self.assertEqual(
            self.cards(self.html(self.bob)), [("/restaurants/1", "拉麵店", "公用餐廳")]
        )

    def test_saved_copy_replaces_its_source(self):
        self.add(self.bob, "牛肉麵", public=True)  # restaurant 1
        self.alice.post("/restaurants/1/save")  # alice's copy is restaurant 2

        self.assertEqual(
            self.cards(self.html()), [("/restaurants/2", "牛肉麵", "我的餐廳")]
        )

    def test_higher_rated_restaurants_are_recommended_more_often(self):
        keep_random_state(self)
        # 20 restaurants and nothing public, so 6 of the 20 are shown each time.
        self.add(self.alice, "五星", stars="5")
        self.add(self.alice, "沒評價")
        for n in range(18):
            self.add(self.alice, f"一星{n}", stars="1")

        shown = Counter()
        with self.app.app_context():
            for _ in range(300):
                picks, _ = recommend(1)
                shown.update(r.name for r in picks)

        self.assertGreater(shown["五星"], shown["沒評價"])
        self.assertGreater(shown["沒評價"], shown["一星0"])


class WeightedSampleTestCase(unittest.TestCase):
    def test_picks_k_distinct_items(self):
        picked = weighted_sample(range(10), lambda item: 1, 4)

        self.assertEqual(len(picked), 4)
        self.assertEqual(len(set(picked)), 4)
        self.assertTrue(set(picked) <= set(range(10)))

    def test_returns_everything_when_k_is_large(self):
        for k in [3, 10]:
            with self.subTest(k=k):
                self.assertEqual(sorted(weighted_sample("abc", lambda item: 1, k)), ["a", "b", "c"])

    def test_empty_pool(self):
        self.assertEqual(weighted_sample([], lambda item: 1, 6), [])

    def test_higher_weight_is_picked_more_often(self):
        keep_random_state(self)
        weights = {"high": 25, "low": 1}

        counts = Counter(
            weighted_sample(weights, weights.get, 1)[0] for _ in range(2000)
        )

        self.assertGreater(counts["high"], 10 * counts["low"])
        self.assertGreater(counts["low"], 0)


if __name__ == "__main__":
    unittest.main()
