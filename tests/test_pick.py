import unittest
from types import SimpleNamespace

from app import create_app
from app.models import Restaurant, db
from app.picker import choose, distance_m, format_distance, within_distance

# A fixed "user location" and points at known straight-line distances from it.
HOME = {"latitude": 25.0, "longitude": 121.5, "accuracy": 10}
METRES_PER_DEGREE_LAT = 111195  # 2 * pi * 6371000 / 360
NEAR = (25.0 + 300 / METRES_PER_DEGREE_LAT, 121.5)  # about 300 m north
FAR = (25.0 + 2000 / METRES_PER_DEGREE_LAT, 121.5)  # about 2 km north

NO_RESULT = "這次抽到"


class PickerTestCase(unittest.TestCase):
    def test_distance_of_one_degree_latitude(self):
        self.assertAlmostEqual(distance_m(25, 121, 26, 121), 111195, delta=1)

    def test_distance_to_itself_is_zero(self):
        self.assertEqual(distance_m(25.03, 121.56, 25.03, 121.56), 0)

    def test_format_distance(self):
        self.assertEqual(format_distance(850), "約 850 公尺")
        self.assertEqual(format_distance(999.4), "約 999 公尺")
        self.assertEqual(format_distance(1234), "約 1.2 公里")

    def test_within_distance_keeps_restaurants_without_coordinates(self):
        near = SimpleNamespace(id=1, latitude=NEAR[0], longitude=NEAR[1])
        far = SimpleNamespace(id=2, latitude=FAR[0], longitude=FAR[1])
        unknown = SimpleNamespace(id=3, latitude=None, longitude=None)

        result = within_distance([near, far, unknown], (25.0, 121.5), 500)

        self.assertEqual([r.id for r, _ in result], [1, 3])
        self.assertAlmostEqual(result[0][1], 300, delta=1)
        self.assertIsNone(result[1][1])

    def test_choose(self):
        a, b = SimpleNamespace(id=1), SimpleNamespace(id=2)
        self.assertIsNone(choose([]))
        self.assertIsNone(choose([], last_id=1))
        # The previous pick is skipped when there is something else.
        for _ in range(10):
            self.assertIs(choose([(a, None), (b, None)], last_id=1)[0], b)
        # ...but a single candidate is still returned.
        self.assertIs(choose([(a, None)], last_id=1)[0], a)


class PickPageTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.alice = self.logged_in_client("alice")
        self.bob = self.logged_in_client("bob")

    def logged_in_client(self, username):
        client = self.app.test_client()
        data = {"username": username, "password": "pw"}
        client.post("/register", data=data)
        client.post("/login", data=data)
        return client

    def add(self, client, name, coords=None, **extra):
        data = {"name": name, **extra}
        if coords:
            data["latitude"], data["longitude"] = coords
        return client.post("/restaurants/new", data=data, follow_redirects=True)

    def restaurant(self, name):
        with self.app.app_context():
            return db.session.scalar(db.select(Restaurant).filter_by(name=name))

    def html(self, client, path):
        return client.get(path).get_data(as_text=True)

    def pick(self, client, **params):
        params.setdefault("draw", "1")
        response = client.get("/restaurants/pick", query_string=params)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def picked_names(self, client, candidates, times=20, **params):
        """Draw several times and return the set of names that came up."""
        seen = set()
        for _ in range(times):
            html = self.pick(client, **params)
            seen.update(name for name in candidates if f">{name}</a></h2>" in html)
        return seen

    # ---- price level in the restaurant form ----

    def test_price_level_is_saved(self):
        for value, expected in [("1", 1), ("2", 2), ("3", 3), ("", None)]:
            with self.subTest(value=value):
                name = f"店{value or 'none'}"
                response = self.add(self.alice, name, price_level=value)
                self.assertIn("已新增餐廳", response.get_data(as_text=True))
                self.assertEqual(self.restaurant(name).price_level, expected)

    def test_invalid_price_level_is_rejected(self):
        for value in ["4", "0", "x"]:
            with self.subTest(value=value):
                response = self.add(self.alice, f"店{value}", price_level=value)
                self.assertIn("價位等級不正確", response.get_data(as_text=True))
                self.assertIsNone(self.restaurant(f"店{value}"))

    def test_edit_changes_price_level(self):
        self.add(self.alice, "拉麵店", price_level="1")
        rid = self.restaurant("拉麵店").id

        form = self.html(self.alice, f"/restaurants/{rid}/edit")
        self.assertIn('<option value="1" selected>', form)

        self.alice.post(f"/restaurants/{rid}/edit", data={"name": "拉麵店", "price_level": "3"})
        self.assertEqual(self.restaurant("拉麵店").price_level, 3)

        self.alice.post(f"/restaurants/{rid}/edit", data={"name": "拉麵店", "price_level": ""})
        self.assertIsNone(self.restaurant("拉麵店").price_level)

    def test_save_copy_keeps_price_level(self):
        self.add(self.bob, "公開店", price_level="2", is_public="on")
        source = self.restaurant("公開店")

        self.alice.post(f"/restaurants/{source.id}/save")

        with self.app.app_context():
            copy = db.session.scalar(db.select(Restaurant).filter_by(source_id=source.id))
            self.assertEqual(copy.price_level, 2)

    def test_list_and_detail_show_price_level(self):
        self.add(self.alice, "拉麵店", price_level="2")
        rid = self.restaurant("拉麵店").id
        tag = '<span class="tag" title="每人 150–300 元">$$</span>'

        self.assertIn(tag, self.html(self.alice, "/restaurants/"))
        self.assertIn(tag, self.html(self.alice, f"/restaurants/{rid}"))

    # ---- pick page ----

    def test_pick_requires_login(self):
        response = self.app.test_client().get("/restaurants/pick", follow_redirects=True)
        self.assertEqual(response.request.path, "/login")

    def test_form_only_without_draw(self):
        self.add(self.alice, "拉麵店")

        html = self.pick(self.alice, draw="")

        self.assertIn("🎲 抽一間", html)
        self.assertNotIn(NO_RESULT, html)
        self.assertNotIn("沒有符合條件的餐廳", html)

    def test_entry_points(self):
        self.assertIn('href="/restaurants/pick"', self.html(self.alice, "/restaurants/new"))
        self.assertIn('href="/restaurants/pick?scope=mine"', self.html(self.alice, "/restaurants/"))

    def test_no_filters_picks_own_restaurants_only(self):
        self.add(self.alice, "A店")
        self.add(self.alice, "B店")
        self.add(self.bob, "Bob私房店")

        seen = self.picked_names(self.alice, ["A店", "B店", "Bob私房店"])

        self.assertEqual(seen, {"A店", "B店"})
        self.assertIn("符合條件的餐廳共 2 間", self.pick(self.alice))
        self.assertIn("🎲 再抽一次", self.pick(self.alice))

    def test_public_scope(self):
        self.add(self.bob, "Bob公開店", is_public="on")
        self.add(self.bob, "Bob私房店")
        self.add(self.alice, "Alice私房店")

        seen = self.picked_names(
            self.alice, ["Bob公開店", "Bob私房店", "Alice私房店"], scope="public"
        )

        self.assertEqual(seen, {"Bob公開店"})

    def test_favorites_scope(self):
        self.add(self.bob, "收藏店", is_public="on")
        self.add(self.bob, "沒收藏店", is_public="on")
        self.add(self.alice, "我的店")
        self.alice.post(f"/restaurants/{self.restaurant('收藏店').id}/favorite")

        seen = self.picked_names(
            self.alice, ["收藏店", "沒收藏店", "我的店"], scope="favorites"
        )

        self.assertEqual(seen, {"收藏店"})

    def test_price_filter_keeps_unknown_level(self):
        self.add(self.alice, "便宜店", price_level="1")
        self.add(self.alice, "中價店", price_level="2")
        self.add(self.alice, "高價店", price_level="3")
        self.add(self.alice, "未知店")
        names = ["便宜店", "中價店", "高價店", "未知店"]

        seen = self.picked_names(self.alice, names, times=40, price=["1", "3"])

        self.assertEqual(seen, {"便宜店", "高價店", "未知店"})
        self.assertIn("符合條件的餐廳共 3 間", self.pick(self.alice, price=["1", "3"]))

    def test_unknown_price_is_noted(self):
        self.add(self.alice, "未知店")

        self.assertIn("未設定價位", self.pick(self.alice, price="2"))
        # Without a price filter there is nothing to warn about.
        self.assertNotIn("未設定價位", self.pick(self.alice))

    def test_distance_filter(self):
        self.alice.post("/location", json=HOME)
        self.add(self.alice, "近店", coords=NEAR)
        self.add(self.alice, "遠店", coords=FAR)
        self.add(self.alice, "無座標店")

        seen = self.picked_names(
            self.alice, ["近店", "遠店", "無座標店"], distance="500"
        )

        self.assertEqual(seen, {"近店", "無座標店"})
        self.assertIn("符合條件的餐廳共 2 間", self.pick(self.alice, distance="500"))
        # With 3 km both restaurants with coordinates are close enough.
        self.assertIn("符合條件的餐廳共 3 間", self.pick(self.alice, distance="3000"))

    def test_distance_is_shown(self):
        self.alice.post("/location", json=HOME)
        self.add(self.alice, "近店", coords=NEAR)

        self.assertIn("距離約 300 公尺", self.pick(self.alice, distance="500"))

    def test_missing_coordinates_is_noted(self):
        self.alice.post("/location", json=HOME)
        self.add(self.alice, "無座標店")

        html = self.pick(self.alice, distance="1000")

        self.assertIn(">無座標店</a></h2>", html)
        self.assertIn("沒有座標，無法確認距離", html)

    def test_distance_without_location_shows_error(self):
        self.add(self.alice, "近店", coords=NEAR)

        html = self.pick(self.alice, distance="500")

        self.assertIn("無法取得你的位置", html)
        self.assertNotIn(NO_RESULT, html)

    def test_invalid_filters_show_errors(self):
        self.add(self.alice, "拉麵店")
        cases = [
            ({"distance": "123"}, "距離選項不正確"),
            ({"distance": "abc"}, "距離選項不正確"),
            ({"price": "4"}, "價位選項不正確"),
            ({"price": ["1", "x"]}, "價位選項不正確"),
        ]
        for params, message in cases:
            with self.subTest(params=params):
                html = self.pick(self.alice, **params)
                self.assertIn(message, html)
                self.assertNotIn(NO_RESULT, html)

    def test_invalid_scope_and_last_fall_back(self):
        self.add(self.alice, "拉麵店")

        html = self.pick(self.alice, scope="nope", last="abc")

        self.assertIn(">拉麵店</a></h2>", html)

    def test_no_match(self):
        self.assertIn("沒有符合條件的餐廳", self.pick(self.alice))

        self.alice.post("/location", json=HOME)
        self.add(self.alice, "遠店", coords=FAR, price_level="3")
        self.assertIn("沒有符合條件的餐廳", self.pick(self.alice, distance="500"))
        self.assertIn("沒有符合條件的餐廳", self.pick(self.alice, price="1"))

    def test_draw_again_avoids_last_pick(self):
        self.add(self.alice, "A店")
        self.add(self.alice, "B店")
        a_id = self.restaurant("A店").id

        for _ in range(10):
            html = self.pick(self.alice, last=str(a_id))
            self.assertIn(">B店</a></h2>", html)
        # The form carries the new pick as the next "last".
        b_id = self.restaurant("B店").id
        self.assertIn(f'name="last" value="{b_id}"', html)

    def test_single_candidate_is_picked_again(self):
        self.add(self.alice, "A店")
        a_id = self.restaurant("A店").id

        self.assertIn(">A店</a></h2>", self.pick(self.alice, last=str(a_id)))

    def test_filters_are_kept_after_drawing(self):
        self.alice.post("/location", json=HOME)
        self.add(self.alice, "近店", coords=NEAR, price_level="2")

        html = self.pick(self.alice, scope="mine", distance="1000", price=["2", "3"])

        self.assertIn('<option value="1000" selected>', html)
        self.assertIn('value="2" checked', html)
        self.assertIn('value="3" checked', html)
        self.assertNotIn('value="1" checked', html)


if __name__ == "__main__":
    unittest.main()
