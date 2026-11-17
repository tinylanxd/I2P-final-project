import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.models import db


class SchemaUpgradeTests(unittest.TestCase):
    """An app.db made before a nullable column existed keeps working."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "old.db"
        self.apps = []

    def tearDown(self):
        # Windows cannot delete the file while a connection is still open.
        self.close_connections()
        self.tmp.cleanup()

    def close_connections(self):
        for app in self.apps:
            with app.app_context():
                db.engine.dispose()

    def make_app(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.path}",
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.apps.append(app)
        return app

    def columns(self, table):
        with closing(sqlite3.connect(self.path)) as conn:
            return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]

    def test_adds_missing_nullable_column_and_keeps_data(self):
        app = self.make_app()
        client = app.test_client()
        client.post("/register", data={"username": "alice", "password": "pw"})
        client.post("/login", data={"username": "alice", "password": "pw"})
        client.post("/restaurants/new", data={"name": "老店"})
        self.close_connections()

        # Simulate a database created before price_level existed.
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("ALTER TABLE restaurant DROP COLUMN price_level")
            conn.commit()
        self.assertNotIn("price_level", self.columns("restaurant"))

        app = self.make_app()
        self.assertIn("price_level", self.columns("restaurant"))

        client = app.test_client()
        client.post("/login", data={"username": "alice", "password": "pw"})
        response = client.get("/restaurants/?scope=mine")
        self.assertEqual(response.status_code, 200)
        self.assertIn("老店", response.get_data(as_text=True))

    def test_running_twice_changes_nothing(self):
        self.make_app()
        before = self.columns("restaurant")
        self.make_app()
        self.assertEqual(self.columns("restaurant"), before)


if __name__ == "__main__":
    unittest.main()
