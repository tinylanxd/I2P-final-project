import unittest

from app import create_app
from app.models import Favorite, MenuItem, Restaurant, Review, User, db


class DetailsTestCase(unittest.TestCase):
    """Menu items, location, star ratings, favorites and the detail page."""

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

    # ---- helpers ----

    def logged_in_client(self, username):
        client = self.app.test_client()
        data = {"username": username, "password": "pw"}
        client.post("/register", data=data)
        client.post("/login", data=data)
        return client

    def user_id(self, username):
        with self.app.app_context():
            return db.session.scalar(db.select(User.id).filter_by(username=username))

    def query(self, model, **filters):
        with self.app.app_context():
            return db.session.scalars(
                db.select(model).filter_by(**filters).order_by(model.id)
            ).all()

    def restaurant(self, restaurant_id=None):
        rows = self.query(Restaurant)
        return rows[0] if restaurant_id is None else next(
            r for r in rows if r.id == restaurant_id
        )

    def menu(self, restaurant_id):
        return [
            (item.name, item.price)
            for item in self.query(MenuItem, restaurant_id=restaurant_id)
        ]

    def reviews(self, restaurant_id):
        return [
            (review.user_id, review.stars, review.comment)
            for review in self.query(Review, restaurant_id=restaurant_id)
        ]

    def add(self, client, name="拉麵店", **extra):
        return client.post(
            "/restaurants/new", data={"name": name, **extra}, follow_redirects=True
        )

    def text(self, response):
        return response.get_data(as_text=True)

    def page(self, client, scope="mine", **params):
        return self.text(
            client.get("/restaurants/", query_string={"scope": scope, **params})
        )

    def detail(self, client, restaurant_id):
        return client.get(f"/restaurants/{restaurant_id}")

    def post(self, client, restaurant_id, action, **data):
        return client.post(f"/restaurants/{restaurant_id}/{action}", data=data)

    # ---- menu items ----

    def test_menu_items_are_saved_in_order(self):
        self.add(
            self.alice,
            item_name=["豚骨拉麵", "", "煎餃", "時價海鮮"],
            item_price=["180", "", "60", ""],
        )

        self.assertEqual(
            self.menu(self.restaurant().id),
            [("豚骨拉麵", 180), ("煎餃", 60), ("時價海鮮", None)],
        )

    def test_restaurant_without_menu_is_allowed(self):
        self.add(self.alice, item_name=[""], item_price=[""])

        self.assertEqual(self.menu(self.restaurant().id), [])

    def test_invalid_menu_input_is_rejected(self):
        cases = [
            (["拉麵"], ["-5"], "價格必須是"),
            (["拉麵"], ["12.5"], "價格必須是"),
            (["拉麵"], ["abc"], "價格必須是"),
            (["拉麵"], ["100000"], "價格必須是"),
            ([""], ["50"], "請輸入餐點名稱"),
            (["a" * 51], ["50"], "餐點名稱不能超過"),
            (["x"] * 31, ["1"] * 31, "最多只能新增"),
        ]
        for names, prices, message in cases:
            with self.subTest(names=names[:2], prices=prices[:2]):
                response = self.add(self.alice, item_name=names, item_price=prices)
                self.assertIn(message, self.text(response))
        self.assertEqual(self.query(Restaurant), [])
        self.assertEqual(self.query(MenuItem), [])

    def test_invalid_form_keeps_entered_menu(self):
        response = self.add(
            self.alice, name="", item_name=["豚骨拉麵"], item_price=["180"]
        )

        self.assertIn("豚骨拉麵", self.text(response))
        self.assertIn('value="180"', self.text(response))

    def test_menu_is_shown_on_detail_and_list_pages(self):
        self.add(self.alice, item_name=["豚骨拉麵", "時價海鮮"], item_price=["180", ""])
        restaurant_id = self.restaurant().id

        detail = self.text(self.detail(self.alice, restaurant_id))
        self.assertIn("豚骨拉麵", detail)
        self.assertIn("NT$ 180", detail)
        self.assertIn("時價海鮮", detail)
        self.assertNotIn("NT$ None", detail)
        self.assertIn("NT$ 180", self.page(self.alice))

    def test_edit_replaces_menu_and_removes_old_rows(self):
        self.add(self.alice, item_name=["A", "B"], item_price=["1", "2"])
        restaurant_id = self.restaurant().id

        self.alice.post(
            f"/restaurants/{restaurant_id}/edit",
            data={"name": "拉麵店", "item_name": ["C"], "item_price": ["3"]},
        )

        self.assertEqual(self.menu(restaurant_id), [("C", 3)])
        self.assertEqual(len(self.query(MenuItem)), 1)

    def test_edit_page_prefills_menu(self):
        self.add(self.alice, item_name=["豚骨拉麵"], item_price=["180"])

        html = self.text(
            self.alice.get(f"/restaurants/{self.restaurant().id}/edit")
        )

        self.assertIn('value="豚骨拉麵"', html)
        self.assertIn('value="180"', html)

    def test_search_matches_menu_items(self):
        self.add(self.alice, name="甲店", item_name=["牛肉麵"], item_price=["150"])
        self.add(self.alice, name="乙店", item_name=["咖哩飯"], item_price=["120"])

        html = self.page(self.alice, q="牛肉")

        self.assertIn("甲店", html)
        self.assertNotIn("乙店", html)

    # ---- location ----

    def test_location_is_saved(self):
        self.add(self.alice, latitude="25.033964", longitude="121.564468")

        restaurant = self.restaurant()
        self.assertAlmostEqual(restaurant.latitude, 25.033964)
        self.assertAlmostEqual(restaurant.longitude, 121.564468)

    def test_location_is_optional(self):
        self.add(self.alice)

        self.assertIsNone(self.restaurant().latitude)
        self.assertIsNone(self.restaurant().longitude)

    def test_invalid_location_is_rejected(self):
        cases = [
            ("25.0", "", "座標格式不正確"),
            ("", "121.5", "座標格式不正確"),
            ("abc", "121.5", "座標格式不正確"),
            ("nan", "121.5", "座標超出範圍"),
            ("91", "0", "座標超出範圍"),
            ("0", "181", "座標超出範圍"),
        ]
        for latitude, longitude, message in cases:
            with self.subTest(latitude=latitude, longitude=longitude):
                response = self.add(self.alice, latitude=latitude, longitude=longitude)
                self.assertIn(message, self.text(response))
        self.assertEqual(self.query(Restaurant), [])

    def test_clearing_location_in_edit(self):
        self.add(self.alice, latitude="25.0", longitude="121.5")
        restaurant_id = self.restaurant().id

        self.alice.post(f"/restaurants/{restaurant_id}/edit", data={"name": "拉麵店"})

        self.assertIsNone(self.restaurant().latitude)
        self.assertIsNone(self.restaurant().longitude)

    def test_edit_page_prefills_location(self):
        self.add(self.alice, latitude="25.033964", longitude="121.564468")

        html = self.text(self.alice.get(f"/restaurants/{self.restaurant().id}/edit"))

        self.assertIn('value="25.033964"', html)
        self.assertIn('value="121.564468"', html)

    def test_map_link_uses_coordinates_or_address(self):
        self.add(self.alice, name="有座標", latitude="25.033964", longitude="121.564468")
        self.add(self.alice, name="只有地址", address="信義路")
        self.add(self.alice, name="什麼都沒有")
        by_name = {r.name: r.id for r in self.query(Restaurant)}

        with_coordinates = self.text(self.detail(self.alice, by_name["有座標"]))
        self.assertIn("maps?q=25.033964,121.564468", with_coordinates)
        address_only = self.text(self.detail(self.alice, by_name["只有地址"]))
        self.assertIn("query=%E4%BF%A1%E7%BE%A9%E8%B7%AF", address_only)
        nothing = self.text(self.detail(self.alice, by_name["什麼都沒有"]))
        self.assertNotIn("在地圖開啟", nothing)

    # ---- star ratings ----

    def test_rating_from_the_form_creates_a_review(self):
        self.add(self.alice, stars="5", review_comment="很好吃")

        self.assertEqual(
            self.reviews(self.restaurant().id),
            [(self.user_id("alice"), 5, "很好吃")],
        )

    def test_rating_is_optional(self):
        self.add(self.alice)

        self.assertEqual(self.query(Review), [])
        self.assertIn("尚無評價", self.page(self.alice))

    def test_invalid_rating_is_rejected(self):
        cases = [
            ("0", "", "評分必須是 1 到 5 顆星"),
            ("6", "", "評分必須是 1 到 5 顆星"),
            ("abc", "", "評分必須是 1 到 5 顆星"),
            ("", "沒給星數", "請選擇評分星數才能留下評價內容"),
        ]
        for stars, comment, message in cases:
            with self.subTest(stars=stars, comment=comment):
                response = self.add(self.alice, stars=stars, review_comment=comment)
                self.assertIn(message, self.text(response))
        self.assertEqual(self.query(Restaurant), [])

    def test_editing_updates_and_removes_own_rating(self):
        self.add(self.alice, stars="5", review_comment="很好吃")
        restaurant_id = self.restaurant().id

        self.alice.post(
            f"/restaurants/{restaurant_id}/edit",
            data={"name": "拉麵店", "stars": "3", "review_comment": "普通"},
        )
        self.assertEqual(
            self.reviews(restaurant_id), [(self.user_id("alice"), 3, "普通")]
        )

        self.alice.post(f"/restaurants/{restaurant_id}/edit", data={"name": "拉麵店"})
        self.assertEqual(self.reviews(restaurant_id), [])

    def test_other_users_can_rate_public_restaurants(self):
        self.add(self.alice, stars="5", is_public="on")
        restaurant_id = self.restaurant().id

        response = self.bob.post(
            f"/restaurants/{restaurant_id}/review",
            data={"stars": "3", "review_comment": "還可以"},
            follow_redirects=True,
        )

        self.assertIn("已送出評價", self.text(response))
        self.assertEqual(len(self.reviews(restaurant_id)), 2)
        self.assertIn("4.0（2 則評價）", self.text(self.detail(self.bob, restaurant_id)))
        self.assertIn("4.0（2 則評價）", self.page(self.bob, "public"))
        self.assertIn("還可以", self.text(self.detail(self.alice, restaurant_id)))

    def test_rating_again_updates_instead_of_adding(self):
        self.add(self.alice, is_public="on")
        restaurant_id = self.restaurant().id

        self.post(self.bob, restaurant_id, "review", stars="2", review_comment="一般")
        self.post(self.bob, restaurant_id, "review", stars="4", review_comment="進步了")

        self.assertEqual(
            self.reviews(restaurant_id), [(self.user_id("bob"), 4, "進步了")]
        )

    def test_review_endpoint_validates_input(self):
        self.add(self.alice, is_public="on")
        restaurant_id = self.restaurant().id

        cases = [
            ({}, "請選擇評分星數"),
            ({"stars": "9"}, "評分必須是 1 到 5 顆星"),
            ({"stars": "x"}, "評分必須是 1 到 5 顆星"),
            ({"review_comment": "只有文字"}, "請選擇評分星數才能留下評價內容"),
        ]
        for data, message in cases:
            with self.subTest(data=data):
                response = self.bob.post(
                    f"/restaurants/{restaurant_id}/review",
                    data=data,
                    follow_redirects=True,
                )
                self.assertIn(message, self.text(response))
        self.assertEqual(self.reviews(restaurant_id), [])

    def test_cannot_review_someone_elses_private_restaurant(self):
        self.add(self.alice)
        restaurant_id = self.restaurant().id

        response = self.post(self.bob, restaurant_id, "review", stars="1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.reviews(restaurant_id), [])

    def test_delete_own_review_only(self):
        self.add(self.alice, stars="5", is_public="on")
        restaurant_id = self.restaurant().id
        self.post(self.bob, restaurant_id, "review", stars="1")

        self.post(self.bob, restaurant_id, "review/delete")

        self.assertEqual(
            [stars for _, stars, _ in self.reviews(restaurant_id)], [5]
        )

    def test_review_text_is_escaped(self):
        self.add(self.alice, stars="5", review_comment="<b>hi</b>")

        html = self.text(self.detail(self.alice, self.restaurant().id))

        self.assertIn("&lt;b&gt;hi&lt;/b&gt;", html)
        self.assertNotIn("<b>hi</b>", html)

    # ---- detail page ----

    def test_detail_page_access_rules(self):
        self.add(self.alice, name="私藏小店")
        self.add(self.alice, name="公開名店", is_public="on")
        private_id, public_id = [r.id for r in self.query(Restaurant)]

        self.assertEqual(self.detail(self.alice, private_id).status_code, 200)
        self.assertEqual(self.detail(self.bob, private_id).status_code, 404)
        self.assertEqual(self.detail(self.bob, public_id).status_code, 200)
        self.assertEqual(self.detail(self.bob, 999).status_code, 404)

        response = self.app.test_client().get(
            f"/restaurants/{public_id}", follow_redirects=True
        )
        self.assertEqual(response.request.path, "/login")

    def test_detail_page_forms_carry_csrf_token(self):
        self.add(self.alice, stars="4")

        html = self.text(self.detail(self.alice, self.restaurant().id))

        self.assertGreaterEqual(html.count('name="csrf_token"'), 5)

    # ---- favorites ----

    def favorite_rows(self, username):
        return self.query(Favorite, user_id=self.user_id(username))

    def test_favorite_own_and_public_restaurants(self):
        self.add(self.alice, name="阿麗的店")
        self.add(self.alice, name="公開名店", is_public="on")
        own_id, public_id = [r.id for r in self.query(Restaurant)]

        self.post(self.alice, own_id, "favorite")
        self.post(self.bob, public_id, "favorite")

        self.assertEqual(len(self.favorite_rows("alice")), 1)
        self.assertEqual(len(self.favorite_rows("bob")), 1)
        self.assertIn("阿麗的店", self.page(self.alice, "favorites"))
        self.assertNotIn("公開名店", self.page(self.alice, "favorites"))
        self.assertIn("公開名店", self.page(self.bob, "favorites"))

    def test_favorites_are_per_user(self):
        self.add(self.alice, name="阿麗的店", is_public="on")
        self.post(self.alice, self.restaurant().id, "favorite")

        self.assertNotIn("阿麗的店", self.page(self.bob, "favorites"))

    def test_favoriting_twice_keeps_one_row(self):
        self.add(self.alice)
        restaurant_id = self.restaurant().id

        self.post(self.alice, restaurant_id, "favorite")
        self.post(self.alice, restaurant_id, "favorite")

        self.assertEqual(len(self.favorite_rows("alice")), 1)

    def test_cannot_favorite_someone_elses_private_restaurant(self):
        self.add(self.alice)

        response = self.post(self.bob, self.restaurant().id, "favorite")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.favorite_rows("bob"), [])

    def test_unfavorite(self):
        self.add(self.alice)
        restaurant_id = self.restaurant().id
        self.post(self.alice, restaurant_id, "favorite")

        self.post(self.alice, restaurant_id, "unfavorite")
        self.post(self.alice, restaurant_id, "unfavorite")  # harmless when repeated

        self.assertEqual(self.favorite_rows("alice"), [])
        self.assertNotIn("拉麵店", self.page(self.alice, "favorites"))

    def test_favorite_state_is_shown_on_buttons(self):
        self.add(self.alice)
        restaurant_id = self.restaurant().id
        self.assertIn("♡ 收藏", self.page(self.alice))

        self.post(self.alice, restaurant_id, "favorite")

        self.assertIn("♥ 已收藏", self.page(self.alice))
        self.assertIn("♥ 已收藏", self.text(self.detail(self.alice, restaurant_id)))

    def test_favorite_disappears_while_owner_keeps_it_private(self):
        self.add(self.alice, name="公開名店", is_public="on")
        restaurant_id = self.restaurant().id
        self.post(self.bob, restaurant_id, "favorite")

        self.post(self.alice, restaurant_id, "share")  # back to private
        self.assertNotIn("公開名店", self.page(self.bob, "favorites"))
        self.assertEqual(len(self.favorite_rows("bob")), 1)

        self.post(self.alice, restaurant_id, "share")  # public again
        self.assertIn("公開名店", self.page(self.bob, "favorites"))

    def test_empty_favorites_message(self):
        self.assertIn("還沒有收藏", self.page(self.alice, "favorites"))

    def test_actions_return_to_where_they_started(self):
        self.add(self.alice, is_public="on")
        restaurant_id = self.restaurant().id

        from_detail = self.post(
            self.bob, restaurant_id, "favorite", return_to="detail"
        )
        self.assertTrue(
            from_detail.headers["Location"].endswith(f"/restaurants/{restaurant_id}")
        )

        from_tab = self.post(self.alice, restaurant_id, "share", scope="favorites")
        self.assertIn("scope=favorites", from_tab.headers["Location"])

    # ---- copies and deletion ----

    def test_saved_copy_has_menu_and_location_but_no_reviews_or_favorites(self):
        self.add(
            self.alice,
            name="公開名店",
            item_name=["豚骨拉麵", "煎餃"],
            item_price=["180", "60"],
            latitude="25.033964",
            longitude="121.564468",
            stars="5",
            is_public="on",
        )
        source_id = self.restaurant().id
        self.post(self.alice, source_id, "favorite")

        self.post(self.bob, source_id, "save")

        copy = self.query(Restaurant, user_id=self.user_id("bob"))[0]
        self.assertEqual(self.menu(copy.id), [("豚骨拉麵", 180), ("煎餃", 60)])
        self.assertAlmostEqual(copy.latitude, 25.033964)
        self.assertEqual(self.reviews(copy.id), [])
        self.assertEqual(self.query(Favorite, restaurant_id=copy.id), [])
        # The copy owns its own menu rows.
        self.assertEqual(len(self.query(MenuItem)), 4)

    def test_deleting_a_restaurant_removes_its_menu_reviews_and_favorites(self):
        self.add(
            self.alice,
            item_name=["豚骨拉麵"],
            item_price=["180"],
            stars="5",
            is_public="on",
        )
        restaurant_id = self.restaurant().id
        self.post(self.bob, restaurant_id, "review", stars="3")
        self.post(self.bob, restaurant_id, "favorite")

        self.post(self.alice, restaurant_id, "delete")

        self.assertEqual(self.query(Restaurant), [])
        self.assertEqual(self.query(MenuItem), [])
        self.assertEqual(self.query(Review), [])
        self.assertEqual(self.query(Favorite), [])

    # ---- navigation ----

    def test_home_links_to_favorites(self):
        html = self.text(self.alice.get("/home"))

        self.assertIn("scope=favorites", html)


if __name__ == "__main__":
    unittest.main()
