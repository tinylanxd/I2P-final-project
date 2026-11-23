import unittest
from io import BytesIO

from PIL import Image

from app import create_app
from app.models import User, db


def image_file(size=(300, 200), fmt="PNG"):
    """A red image with blue strips on the left and right edges."""
    image = Image.new("RGB", size, "red")
    strip = (size[0] - size[1]) // 2
    if strip > 0:
        image.paste("blue", (0, 0, strip, size[1]))
        image.paste("blue", (size[0] - strip, 0, size[0], size[1]))
    buffer = BytesIO()
    image.save(buffer, fmt)
    buffer.seek(0)
    return buffer


class UsersTestCase(unittest.TestCase):
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

    def register(self, username="alice", password="pw"):
        self.client.post("/register", data={"username": username, "password": password})

    def login(self, username="alice", password="pw"):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def logout(self):
        self.client.post("/logout")

    def signed_in(self, username="alice"):
        self.register(username)
        self.login(username)

    def post(self, path, **data):
        return self.client.post(path, data=data, follow_redirects=True)

    def upload(self, file, filename="avatar.png", **data):
        data["avatar"] = (file, filename)
        return self.client.post(
            "/settings/profile",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )

    def user(self, user_id=1):
        with self.app.app_context():
            user = db.session.get(User, user_id)
            return {
                "username": user.username,
                "nickname": user.nickname,
                "bio": user.bio,
                "avatar": user.avatar,
            }


class ProfilePageTests(UsersTestCase):
    def test_profile_is_public(self):
        self.register()

        response = self.client.get("/users/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("alice", response.get_data(as_text=True))

    def test_missing_user_is_404(self):
        self.assertEqual(self.client.get("/users/99").status_code, 404)
        self.assertEqual(self.client.get("/users/99/avatar").status_code, 404)

    def test_edit_link_only_for_owner(self):
        self.register("bob")
        self.signed_in("alice")

        self.assertNotIn("編輯個人資料", self.client.get("/users/1").get_data(as_text=True))
        self.assertIn("編輯個人資料", self.client.get("/users/2").get_data(as_text=True))

        self.logout()
        self.assertNotIn("編輯個人資料", self.client.get("/users/2").get_data(as_text=True))

    def test_nav_links_to_own_profile(self):
        self.signed_in()

        self.assertIn('href="/users/1"', self.client.get("/restaurants/").get_data(as_text=True))

    def test_settings_require_login(self):
        self.register()

        self.assertEqual(self.client.get("/settings", follow_redirects=True).request.path, "/login")
        for path in ["/settings/profile", "/settings/username", "/settings/password"]:
            with self.subTest(path=path):
                response = self.post(path, nickname="x", username="x", password="x")
                self.assertEqual(response.request.path, "/login")
        self.assertEqual(self.user()["nickname"], "")
        self.assertEqual(self.user()["username"], "alice")


class ProfileEditTests(UsersTestCase):
    def setUp(self):
        super().setUp()
        self.signed_in()

    def test_update_nickname_and_bio(self):
        response = self.post("/settings/profile", nickname=" 小艾 ", bio="愛吃拉麵\r\n住台北")

        self.assertIn("個人資料已更新", response.get_data(as_text=True))
        self.assertEqual(self.user()["nickname"], "小艾")
        self.assertEqual(self.user()["bio"], "愛吃拉麵\n住台北")
        page = self.client.get("/users/1").get_data(as_text=True)
        self.assertIn("小艾", page)
        self.assertIn("用戶名：alice", page)

    def test_empty_nickname_shows_username(self):
        page = self.client.get("/users/1").get_data(as_text=True)

        self.assertIn("<h1>alice</h1>", page)

    def test_length_limits(self):
        self.post("/settings/profile", nickname="a" * 30, bio="b" * 100 + "\r\n" + "b" * 99)
        self.assertEqual(len(self.user()["nickname"]), 30)
        self.assertEqual(len(self.user()["bio"]), 200)

        for data in [{"nickname": "a" * 31}, {"bio": "b" * 201}]:
            with self.subTest(data=data):
                response = self.post("/settings/profile", **data)
                self.assertIn("不能超過", response.get_data(as_text=True))
        self.assertEqual(len(self.user()["nickname"]), 30)

    def test_html_is_escaped(self):
        self.post("/settings/profile", nickname="<b>x</b>", bio="<script>bad()</script>")

        page = self.client.get("/users/1").get_data(as_text=True)
        self.assertNotIn("<b>x</b>", page)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", page)


class UsernameTests(UsersTestCase):
    def setUp(self):
        super().setUp()
        self.register("bob")
        self.signed_in("alice")

    def test_change_username(self):
        response = self.post("/settings/username", username="  alice2  ")

        self.assertIn("用戶名已更新", response.get_data(as_text=True))
        self.assertEqual(self.user(2)["username"], "alice2")
        self.assertEqual(self.client.get("/restaurants/").status_code, 200)

        self.logout()
        self.assertEqual(self.login("alice").request.path, "/login")
        self.assertEqual(self.login("alice2").request.path, "/home")

    def test_keeping_same_username_is_fine(self):
        response = self.post("/settings/username", username="alice")

        self.assertIn("用戶名已更新", response.get_data(as_text=True))

    def test_invalid_usernames_are_rejected(self):
        for username, message in [
            ("bob", "已被使用"),
            ("   ", "請輸入用戶名"),
            ("a" * 31, "不能超過"),
        ]:
            with self.subTest(username=username):
                response = self.post("/settings/username", username=username)
                self.assertIn(message, response.get_data(as_text=True))
                self.assertEqual(self.user(2)["username"], "alice")
                self.assertEqual(self.client.get("/restaurants/").status_code, 200)


class PasswordTests(UsersTestCase):
    def setUp(self):
        super().setUp()
        self.signed_in()

    def test_change_password(self):
        response = self.post("/settings/password", password="new", confirm_password="new")

        self.assertIn("密碼已更新", response.get_data(as_text=True))
        self.assertEqual(self.client.get("/restaurants/").status_code, 200)

        self.logout()
        self.assertEqual(self.login(password="pw").request.path, "/login")
        self.assertEqual(self.login(password="new").request.path, "/home")

    def test_invalid_passwords_are_rejected(self):
        for password, confirm, message in [
            ("new", "neW", "不一樣"),
            ("   ", "   ", "請輸入密碼"),
        ]:
            with self.subTest(password=password, confirm=confirm):
                response = self.post(
                    "/settings/password", password=password, confirm_password=confirm
                )
                self.assertIn(message, response.get_data(as_text=True))

        self.logout()
        self.assertEqual(self.login(password="pw").request.path, "/home")


class AvatarTests(UsersTestCase):
    def setUp(self):
        super().setUp()
        self.signed_in()

    def stored_avatar(self):
        return Image.open(BytesIO(self.user()["avatar"]))

    def test_upload_is_cropped_to_square_webp(self):
        response = self.upload(image_file((300, 200)))

        self.assertIn("個人資料已更新", response.get_data(as_text=True))
        avatar = self.stored_avatar()
        self.assertEqual(avatar.format, "WEBP")
        self.assertEqual(avatar.size, (256, 256))
        # The blue edge strips were cropped away from the centre.
        for corner in [(0, 0), (255, 255)]:
            red, green, blue, _ = avatar.convert("RGBA").getpixel(corner)
            self.assertGreater(red, 200)
            self.assertLess(blue, 50)

    def test_supported_formats(self):
        for fmt in ["JPEG", "PNG", "WEBP", "GIF"]:
            with self.subTest(fmt=fmt):
                self.post("/settings/profile", remove_avatar="on")
                self.upload(image_file(fmt=fmt), filename=f"a.{fmt.lower()}")
                self.assertEqual(self.stored_avatar().format, "WEBP")

    def test_non_images_are_rejected(self):
        for file, name in [
            (BytesIO(b"<html><script>bad()</script></html>"), "evil.png"),
            (image_file(fmt="BMP"), "a.bmp"),
        ]:
            with self.subTest(name=name):
                response = self.upload(file, filename=name, nickname="kept")
                page = response.get_data(as_text=True)
                self.assertIn("頭像請上傳", page)
                # The typed nickname stays in the form but is not saved.
                self.assertIn('value="kept"', page)
                self.assertIsNone(self.user()["avatar"])
                self.assertEqual(self.user()["nickname"], "")

    def test_oversized_pixel_count_is_rejected(self):
        original = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = 1000
        self.addCleanup(setattr, Image, "MAX_IMAGE_PIXELS", original)

        response = self.upload(image_file((300, 200)))

        self.assertIn("頭像請上傳", response.get_data(as_text=True))
        self.assertIsNone(self.user()["avatar"])

    def test_large_upload_is_rejected(self):
        big = BytesIO(b"0" * (5 * 1024 * 1024 + 1))

        response = self.upload(big)

        self.assertEqual(response.request.path, "/settings")
        self.assertIn("不能超過 5 MB", response.get_data(as_text=True))
        self.assertIsNone(self.user()["avatar"])

    def test_empty_file_field_keeps_avatar(self):
        self.upload(image_file())
        before = self.user()["avatar"]

        self.upload(BytesIO(b""), filename="", nickname="小艾")

        self.assertEqual(self.user()["avatar"], before)
        self.assertEqual(self.user()["nickname"], "小艾")

    def test_remove_avatar(self):
        self.upload(image_file())
        self.assertIn('src="/users/1/avatar"', self.client.get("/users/1").get_data(as_text=True))

        self.post("/settings/profile", remove_avatar="on")

        self.assertIsNone(self.user()["avatar"])
        self.assertNotIn('src="/users/1/avatar"', self.client.get("/users/1").get_data(as_text=True))
        self.assertEqual(self.client.get("/users/1/avatar").status_code, 404)

    def test_avatar_url_serves_webp_to_anyone(self):
        self.upload(image_file())
        self.logout()

        response = self.client.get("/users/1/avatar")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/webp")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-cache", response.headers["Cache-Control"])
        again = self.client.get(
            "/users/1/avatar", headers={"If-None-Match": response.headers["ETag"]}
        )
        self.assertEqual(again.status_code, 304)


if __name__ == "__main__":
    unittest.main()
