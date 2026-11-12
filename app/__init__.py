import os
import secrets
from pathlib import Path
from .restaurants import bp as restaurants_bp


from flask import Flask, flash, redirect, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.exceptions import RequestEntityTooLarge

from .auth import bp as auth_bp
from .main import bp as main_bp
from .models import db
from .users import MAX_UPLOAD_MB
from .users import bp as users_bp

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

    return app
