import unittest

from app import create_app
from app.models import Restaurant, User, db


class RestaurantTestCase(unittest.TestCase):
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

    def user_id(self, username):
        with self.app.app_context():
            return db.session.scalar(db.select(User.id).filter_by(username=username))

    def rows(self, **filters):
        with self.app.app_context():
            return db.session.scalars(
                db.select(Restaurant).filter_by(**filters)
            ).all()

    def add(self, client, name="拉麵店", **extra):
        return client.post(
            "/restaurants/new", data={"name": name, **extra}, follow_redirects=True
        )

    def page(self, client, scope="mine", **params):
        response = client.get("/restaurants/", query_string={"scope": scope, **params})
        return response.get_data(as_text=True)

    def post(self, client, restaurant_id, action, **data):
        return client.post(f"/restaurants/{restaurant_id}/{action}", data=data)

    # ---- access ----

    def test_pages_require_login(self):
        anonymous = self.app.test_client()
        for path in ["/restaurants/", "/restaurants/new"]:
            with self.subTest(path=path):
                response = anonymous.get(path, follow_redirects=True)
                self.assertEqual(response.request.path, "/login")

    def test_forms_carry_csrf_token(self):
        self.add(self.alice)

        self.assertIn('name="csrf_token"', self.page(self.alice))
        self.assertIn(
            'name="csrf_token"', self.alice.get("/restaurants/new").get_data(as_text=True)
        )

    # ---- create ----

    def test_add_restaurant_is_private_by_default(self):
        response = self.add(self.alice, address="台北市", category="拉麵", note="濃厚")

        self.assertIn("已新增餐廳", response.get_data(as_text=True))
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].user_id, self.user_id("alice"))
        self.assertFalse(rows[0].is_public)
        self.assertEqual(
            (rows[0].address, rows[0].category, rows[0].note),
            ("台北市", "拉麵", "濃厚"),
        )

    def test_add_public_restaurant(self):
        self.add(self.alice, is_public="on")

        self.assertTrue(self.rows()[0].is_public)

    def test_fields_are_stripped(self):
        self.add(self.alice, name="  拉麵店  ", category="  拉麵 ")

        self.assertEqual(self.rows()[0].name, "拉麵店")
        self.assertEqual(self.rows()[0].category, "拉麵")

    def test_blank_name_is_rejected(self):
        response = self.add(self.alice, name="   ")

        self.assertIn("請輸入餐廳名稱", response.get_data(as_text=True))
        self.assertEqual(self.rows(), [])

    def test_field_length_limits(self):
        self.add(self.alice, name="a" * 50)
        self.assertEqual(len(self.rows()), 1)

        for field, limit in [("name", 50), ("address", 200), ("category", 30), ("note", 200)]:
            with self.subTest(field=field):
                data = {"name": "店", field: "a" * (limit + 1)}
                response = self.alice.post("/restaurants/new", data=data)
                self.assertIn("不能超過", response.get_data(as_text=True))
        self.assertEqual(len(self.rows()), 1)

    def test_invalid_form_keeps_entered_values(self):
        response = self.add(self.alice, name="", address="台北市")

        self.assertIn("台北市", response.get_data(as_text=True))

    def test_user_text_is_escaped(self):
        self.add(self.alice, name="<script>alert(1)</script>")

        html = self.page(self.alice)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    # ---- personal vs public lists ----

    def test_personal_list_shows_only_own_restaurants(self):
        self.add(self.alice, name="阿麗的店")
        self.add(self.bob, name="阿寶的店", is_public="on")

        html = self.page(self.alice, "mine")
        self.assertIn("阿麗的店", html)
        self.assertNotIn("阿寶的店", html)

    def test_private_restaurant_is_hidden_from_public_list(self):
        self.add(self.alice, name="私藏小店")

        self.assertNotIn("私藏小店", self.page(self.bob, "public"))
        self.assertNotIn("私藏小店", self.page(self.alice, "public"))

    def test_public_restaurant_is_visible_to_everyone(self):
        self.add(self.alice, name="公開名店", is_public="on")

        html = self.page(self.bob, "public")
        self.assertIn("公開名店", html)
        self.assertIn("分享者：alice", html)
        self.assertNotIn("公開名店", self.page(self.bob, "mine"))

    def test_unknown_scope_falls_back_to_personal_list(self):
        self.add(self.alice, name="阿麗的店")
        self.add(self.bob, name="阿寶的店", is_public="on")

        html = self.page(self.alice, "everything")
        self.assertIn("阿麗的店", html)
        self.assertNotIn("阿寶的店", html)

    def test_search_filters_by_name_category_and_address(self):
        self.add(self.alice, name="拉麵店", category="日式", address="信義路")
        self.add(self.alice, name="咖哩屋", category="印度", address="中山路")

        for keyword, shown, hidden in [
            ("拉麵", "拉麵店", "咖哩屋"),
            ("印度", "咖哩屋", "拉麵店"),
            ("信義", "拉麵店", "咖哩屋"),
        ]:
            with self.subTest(keyword=keyword):
                html = self.page(self.alice, q=keyword)
                self.assertIn(shown, html)
                self.assertNotIn(hidden, html)

    def test_search_without_match_shows_message(self):
        self.add(self.alice)

        self.assertIn("找不到符合的餐廳", self.page(self.alice, q="不存在"))

    # ---- edit ----

    def test_owner_can_edit(self):
        self.add(self.alice, name="舊名字", is_public="on")
        restaurant_id = self.rows()[0].id

        response = self.alice.post(
            f"/restaurants/{restaurant_id}/edit",
            data={"name": "新名字", "category": "拉麵"},
            follow_redirects=True,
        )

        self.assertIn("已更新餐廳", response.get_data(as_text=True))
        restaurant = self.rows()[0]
        self.assertEqual((restaurant.name, restaurant.category), ("新名字", "拉麵"))
        # The checkbox was left unticked, so the restaurant is private again.
        self.assertFalse(restaurant.is_public)

    def test_edit_validates_input(self):
        self.add(self.alice, name="店")
        restaurant_id = self.rows()[0].id

        response = self.alice.post(
            f"/restaurants/{restaurant_id}/edit", data={"name": " "}
        )

        self.assertIn("請輸入餐廳名稱", response.get_data(as_text=True))
        self.assertEqual(self.rows()[0].name, "店")

    def test_edit_page_prefills_values(self):
        self.add(self.alice, name="拉麵店", address="信義路")
        restaurant_id = self.rows()[0].id

        html = self.alice.get(f"/restaurants/{restaurant_id}/edit").get_data(as_text=True)

        self.assertIn("拉麵店", html)
        self.assertIn("信義路", html)

    def test_non_owner_cannot_edit(self):
        self.add(self.alice, name="店", is_public="on")
        restaurant_id = self.rows()[0].id

        self.assertEqual(
            self.bob.get(f"/restaurants/{restaurant_id}/edit").status_code, 403
        )
        response = self.bob.post(
            f"/restaurants/{restaurant_id}/edit", data={"name": "被改了"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.rows()[0].name, "店")

    def test_missing_restaurant_is_404(self):
        self.assertEqual(self.alice.get("/restaurants/999/edit").status_code, 404)

    # ---- share / unshare ----

    def test_owner_can_publish_and_unpublish(self):
        self.add(self.alice, name="店")
        restaurant_id = self.rows()[0].id

        self.post(self.alice, restaurant_id, "share")
        self.assertTrue(self.rows()[0].is_public)
        self.assertIn("店", self.page(self.bob, "public"))

        self.post(self.alice, restaurant_id, "share")
        self.assertFalse(self.rows()[0].is_public)
        self.assertNotIn("店", self.page(self.bob, "public"))

    def test_non_owner_cannot_change_sharing(self):
        self.add(self.alice, name="店", is_public="on")
        restaurant_id = self.rows()[0].id

        response = self.post(self.bob, restaurant_id, "share")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.rows()[0].is_public)

    # ---- save a copy ----

    def test_save_public_restaurant_creates_private_copy(self):
        self.add(self.alice, name="公開名店", address="台北", is_public="on")
        source = self.rows()[0]

        response = self.post(self.bob, source.id, "save", scope="public")

        self.assertEqual(response.status_code, 302)
        copies = self.rows(user_id=self.user_id("bob"))
        self.assertEqual(len(copies), 1)
        self.assertEqual((copies[0].name, copies[0].address), ("公開名店", "台北"))
        self.assertFalse(copies[0].is_public)
        self.assertEqual(copies[0].source_id, source.id)
        self.assertIn("公開名店", self.page(self.bob, "mine"))

    def test_saving_twice_is_rejected(self):
        self.add(self.alice, is_public="on")
        source_id = self.rows()[0].id

        self.post(self.bob, source_id, "save")
        response = self.bob.post(
            f"/restaurants/{source_id}/save", follow_redirects=True
        )

        self.assertIn("已在你的清單中", response.get_data(as_text=True))
        self.assertEqual(len(self.rows(user_id=self.user_id("bob"))), 1)

    def test_saved_restaurant_is_marked_in_public_list(self):
        self.add(self.alice, name="公開名店", is_public="on")
        self.post(self.bob, self.rows()[0].id, "save")

        self.assertIn("已存入我的清單", self.page(self.bob, "public"))

    def test_cannot_save_private_restaurant(self):
        self.add(self.alice, name="私藏小店")

        response = self.post(self.bob, self.rows()[0].id, "save")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.rows(user_id=self.user_id("bob")), [])

    def test_cannot_save_own_restaurant(self):
        self.add(self.alice, is_public="on")

        response = self.post(self.alice, self.rows()[0].id, "save")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.rows()), 1)

    def test_copy_is_independent_of_source(self):
        self.add(self.alice, name="原名", is_public="on")
        source_id = self.rows()[0].id
        self.post(self.bob, source_id, "save")

        self.alice.post(f"/restaurants/{source_id}/edit", data={"name": "改名了"})

        self.assertEqual(self.rows(user_id=self.user_id("bob"))[0].name, "原名")

    # ---- delete ----

    def test_owner_can_delete(self):
        self.add(self.alice)
        restaurant_id = self.rows()[0].id

        response = self.alice.post(
            f"/restaurants/{restaurant_id}/delete", follow_redirects=True
        )

        self.assertIn("已刪除餐廳", response.get_data(as_text=True))
        self.assertEqual(self.rows(), [])

    def test_non_owner_cannot_delete(self):
        self.add(self.alice, is_public="on")

        response = self.post(self.bob, self.rows()[0].id, "delete")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.rows()), 1)

    def test_delete_requires_post(self):
        self.add(self.alice)

        response = self.alice.get(f"/restaurants/{self.rows()[0].id}/delete")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(len(self.rows()), 1)

    def test_deleting_source_keeps_saved_copies(self):
        self.add(self.alice, name="公開名店", is_public="on")
        source_id = self.rows()[0].id
        self.post(self.bob, source_id, "save")

        self.post(self.alice, source_id, "delete")

        copies = self.rows(user_id=self.user_id("bob"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].name, "公開名店")
        self.assertIsNone(copies[0].source_id)

    def test_unpublishing_keeps_saved_copies(self):
        self.add(self.alice, is_public="on")
        source_id = self.rows()[0].id
        self.post(self.bob, source_id, "save")

        self.post(self.alice, source_id, "share")

        self.assertEqual(len(self.rows(user_id=self.user_id("bob"))), 1)

    # ---- navigation ----

    def test_home_links_to_restaurants(self):
        html = self.alice.get("/home").get_data(as_text=True)

        self.assertIn("/restaurants/", html)

    def test_actions_return_to_the_same_tab(self):
        self.add(self.alice, is_public="on")
        restaurant_id = self.rows()[0].id

        response = self.post(self.alice, restaurant_id, "share", scope="public")

        self.assertIn("scope=public", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
