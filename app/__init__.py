import os
import secrets
from pathlib import Path


import sqlalchemy as sa
from flask import Flask, flash, redirect, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.exceptions import RequestEntityTooLarge

from .auth import bp as auth_bp
from .location import bp as location_bp
from .main import bp as main_bp
from .models import db
from .users import MAX_UPLOAD_MB
from .users import bp as users_bp
from .restaurants import bp as restaurants_bp

csrf = CSRFProtect()


def load_secret_key(instance_path):
    key = os.environ.get("SECRET_KEY")
    if key:
        return key

    # Keep local sessions valid across restarts without committing a key.
    key_file = Path(instance_path) / "secret_key"
    if key_file.exists():
        return key_file.read_text().strip()

    key = secrets.token_hex(32)
    key_file.write_text(key)
    return key


def add_missing_columns():
    """Add columns that were added to the models after the database was created.

    create_all() only creates missing tables, so an older app.db would otherwise
    fail with "no such column". Only nullable columns can be added this way.
    """
    inspector = sa.inspect(db.engine)
    with db.engine.begin() as conn:
        for table in db.metadata.sorted_tables:
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable:
                    raise RuntimeError(
                        f"資料庫的 {table.name} 表缺少必填欄位 {column.name}，"
                        "請刪除 instance/app.db 後重新啟動"
                    )
                column_type = column.type.compile(dialect=db.engine.dialect)
                conn.execute(
                    sa.text(
                        f'ALTER TABLE "{table.name}" '
                        f'ADD COLUMN "{column.name}" {column_type}'
                    )
                )


def create_app(test_config=None):
    app = Flask(__name__)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.update(
        SESSION_COOKIE_SAMESITE="Lax",
        # Set DATABASE_URL to switch to a cloud database.
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///app.db"),
        MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,
    )
    app.config.update(test_config or {})
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = load_secret_key(app.instance_path)

    db.init_app(app)
    csrf.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(location_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(restaurants_bp)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        flash("頁面已過期，請再試一次", "error")
        return redirect(url_for("main.index"))

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(error):
        # Only the avatar form uploads files, so send the user back there.
        flash(f"圖片不能超過 {MAX_UPLOAD_MB} MB", "error")
        return redirect(url_for("users.settings"))

    with app.app_context():
        db.create_all()
        add_missing_columns()

    return app
