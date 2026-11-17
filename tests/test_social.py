import unittest

from app import create_app
from app.models import Follow, db


class SocialTestCase(unittest.TestCase):
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
        # alice = 1, bob = 2, carol = 3
        for name in ("alice", "bob", "carol"):
            self.client.post("/register", data={"username": name, "password": "pw"})
        self.login("alice")

    def login(self, username):
        self.client.post("/logout")
        self.client.post(
            "/login", data={"username": username, "password": "pw"}
        )

    def post(self, path, **data):
        return self.client.post(path, data=data, follow_redirects=True)

    def text(self, path):
        return self.client.get(path).get_data(as_text=True)

    def follows(self):
        with self.app.app_context():
            return {
                (f.follower_id, f.followed_id)
                for f in db.session.scalars(db.select(Follow))
            }


class FollowTests(SocialTestCase):
    def test_follow_and_unfollow(self):
        response = self.post("/users/2/follow")
        self.assertIn("已追蹤 bob", response.get_data(as_text=True))
        self.assertEqual(self.follows(), {(1, 2)})

        response = self.post("/users/2/unfollow")
        self.assertIn("已取消追蹤 bob", response.get_data(as_text=True))
        self.assertEqual(self.follows(), set())

    def test_follow_twice_keeps_one_row(self):
        self.post("/users/2/follow")
        self.post("/users/2/follow")
        self.assertEqual(self.follows(), {(1, 2)})

    def test_unfollow_when_not_following_is_harmless(self):
        response = self.post("/users/2/unfollow")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.follows(), set())

    def test_cannot_follow_self(self):
        response = self.post("/users/1/follow")
        self.assertIn("不能追蹤自己", response.get_data(as_text=True))
        self.assertEqual(self.follows(), set())

    def test_unknown_user_is_404(self):
        self.assertEqual(self.client.post("/users/99/follow").status_code, 404)
        self.assertEqual(self.client.post("/users/99/unfollow").status_code, 404)

    def test_follow_requires_login(self):
        self.client.post("/logout")
        response = self.client.post("/users/2/follow")
        self.assertIn("/login", response.headers["Location"])
        self.assertEqual(self.follows(), set())

    def test_follow_only_by_post(self):
        self.assertEqual(self.client.get("/users/2/follow").status_code, 405)

    def test_following_back_makes_friends(self):
        self.post("/users/2/follow")
        self.login("bob")
        response = self.post("/users/1/follow")
        self.assertIn("你和 alice 已成為好友", response.get_data(as_text=True))

    def test_redirects_to_next(self):
        response = self.client.post("/users/2/follow", data={"next": "/friends?q=b"})
        self.assertEqual(response.headers["Location"], "/friends?q=b")

    def test_ignores_offsite_next(self):
        for target in ("https://evil.example/", "//evil.example/", "/\\evil.example"):
            response = self.client.post("/users/2/follow", data={"next": target})
            self.assertEqual(response.headers["Location"], "/users/2")


class ProfileTests(SocialTestCase):
    def test_profile_shows_counts(self):
        self.post("/users/2/follow")
        self.login("carol")
        self.post("/users/2/follow")

        page = self.text("/users/2")
        self.assertIn("<strong>2</strong> 粉絲", page)
        self.assertIn("<strong>0</strong> 追蹤中", page)

    def test_follow_button_states(self):
        self.assertIn("＋ 追蹤", self.text("/users/2"))
        self.post("/users/2/follow")
        self.assertIn("已追蹤 ✓", self.text("/users/2"))

    def test_shows_follows_you_and_friend_badges(self):
        self.login("bob")
        self.post("/users/1/follow")
        self.login("alice")
        self.assertIn("追蹤了你", self.text("/users/2"))

        self.post("/users/2/follow")
        page = self.text("/users/2")
        self.assertIn('<span class="badge">好友</span>', page)
        self.assertNotIn("追蹤了你", page)

    def test_no_follow_button_on_own_profile(self):
        page = self.text("/users/1")
        self.assertNotIn("＋ 追蹤", page)
        self.assertNotIn("已追蹤 ✓", page)

    def test_no_follow_button_when_logged_out(self):
        self.client.post("/logout")
        page = self.text("/users/2")
        self.assertIn("粉絲", page)
        self.assertNotIn("＋ 追蹤", page)


class ListTests(SocialTestCase):
    def test_followers_and_following_lists(self):
        self.post("/users/2/follow")

        followers = self.text("/users/2/followers")
        self.assertIn("alice", followers)
        self.assertNotIn(">carol<", followers)

        following = self.text("/users/1/following")
        self.assertIn("bob", following)

    def test_lists_are_public(self):
        self.post("/users/2/follow")
        self.client.post("/logout")
        self.assertIn("alice", self.text("/users/2/followers"))

    def test_empty_lists(self):
        self.assertIn("還沒有粉絲", self.text("/users/3/followers"))
        self.assertIn("還沒有追蹤任何人", self.text("/users/3/following"))

    def test_unknown_user_lists_are_404(self):
        self.assertEqual(self.client.get("/users/99/followers").status_code, 404)
        self.assertEqual(self.client.get("/users/99/following").status_code, 404)


class FriendsPageTests(SocialTestCase):
    def test_friends_are_mutual_follows_only(self):
        self.post("/users/2/follow")  # alice -> bob
        self.post("/users/3/follow")  # alice -> carol
        self.login("bob")
        self.post("/users/1/follow")  # bob -> alice: friends
        self.login("alice")

        page = self.text("/friends")
        friends = page.split("好友（互相追蹤）")[1]
        self.assertIn("bob", friends)
        self.assertNotIn("carol", friends)

    def test_no_friends_message(self):
        self.assertIn("還沒有好友", self.text("/friends"))

    def test_search_by_username_and_nickname(self):
        self.login("carol")
        self.post("/settings/profile", nickname="小卡")
        self.login("alice")

        self.assertIn("bob", self.text("/friends?q=BO"))
        page = self.text("/friends?q=小卡")
        self.assertIn("小卡", page)
        self.assertIn("@carol", page)

    def test_search_excludes_self(self):
        page = self.text("/friends?q=alice")
        self.assertIn("找不到符合「alice」的使用者", page)

    def test_search_treats_wildcards_literally(self):
        self.assertIn("找不到符合", self.text("/friends?q=%25"))
        self.assertIn("找不到符合", self.text("/friends?q=_"))

    def test_friends_requires_login(self):
        self.client.post("/logout")
        response = self.client.get("/friends")
        self.assertIn("/login", response.headers["Location"])

    def test_home_links_to_friends(self):
        self.assertIn('href="/friends"', self.text("/home"))


class DatabaseTests(SocialTestCase):
    def test_constraints(self):
        from sqlalchemy.exc import IntegrityError

        with self.app.app_context():
            db.session.add(Follow(follower_id=1, followed_id=1))
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

            db.session.add(Follow(follower_id=1, followed_id=2))
            db.session.commit()
            db.session.add(Follow(follower_id=1, followed_id=2))
            with self.assertRaises(IntegrityError):
                db.session.commit()


if __name__ == "__main__":
    unittest.main()
