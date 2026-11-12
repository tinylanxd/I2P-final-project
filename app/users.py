import hashlib
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from PIL import Image, ImageOps
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from .auth import login_required, validate_password, validate_username
from .models import User, db

bp = Blueprint("users", __name__)

MAX_NICKNAME_LENGTH = 30
MAX_BIO_LENGTH = 200
MAX_UPLOAD_MB = 5
AVATAR_SIZE = 256
AVATAR_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


def make_avatar(stream):
    """Return the upload as square WebP bytes, or None if it is not a supported image.

    Re-encoding means only images this function made are ever served to others.
    """
    try:
        with Image.open(stream) as image:
            if image.format not in AVATAR_FORMATS:
                return None
            # Phones store rotation in EXIF; GIFs keep only their first frame.
            image = ImageOps.exif_transpose(image).convert("RGBA")
            image = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE))
            output = BytesIO()
            image.save(output, "WEBP", quality=85)
            return output.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def render_settings(**form):
    values = {
        "nickname": g.user.nickname,
        "bio": g.user.bio,
        "username": g.user.username,
    }
    values.update(form)
    return render_template("settings.html", form=values)


@bp.route("/users/<int:user_id>")
def profile(user_id):
    user = db.get_or_404(User, user_id)
    return render_template("profile.html", user=user)


@bp.route("/users/<int:user_id>/avatar")
def avatar(user_id):
    user = db.get_or_404(User, user_id)
    if not user.has_avatar:
        abort(404)

    response = make_response(user.avatar)
    response.mimetype = "image/webp"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Revalidate every time so a new avatar shows up right away.
    response.cache_control.no_cache = True
    response.set_etag(hashlib.sha256(user.avatar).hexdigest())
    return response.make_conditional(request)


@bp.get("/settings")
@login_required
def settings():
    return render_settings()


@bp.post("/settings/profile")
@login_required
def update_profile():
    nickname = request.form.get("nickname", "").strip()
    # Browsers send line breaks as \r\n but count them as one character.
    bio = request.form.get("bio", "").replace("\r\n", "\n").strip()
    upload = request.files.get("avatar")
    new_avatar = None
    error = None

    if len(nickname) > MAX_NICKNAME_LENGTH:
        error = f"暱稱不能超過 {MAX_NICKNAME_LENGTH} 個字元"
    elif len(bio) > MAX_BIO_LENGTH:
        error = f"自我介紹不能超過 {MAX_BIO_LENGTH} 個字元"
    elif upload and upload.filename:
        new_avatar = make_avatar(upload.stream)
        if new_avatar is None:
            error = "頭像請上傳 JPG、PNG、WebP 或 GIF 圖片"

    if error:
        flash(error, "error")
        return render_settings(nickname=nickname, bio=bio)

    g.user.nickname = nickname
    g.user.bio = bio
    if new_avatar:
        g.user.avatar = new_avatar
    elif request.form.get("remove_avatar"):
        g.user.avatar = None
    db.session.commit()
    flash("個人資料已更新", "success")
    return redirect(url_for("users.settings"))


@bp.post("/settings/username")
@login_required
def update_username():
    username = request.form.get("username", "").strip()
    error = validate_username(username)

    if error is None and username != g.user.username:
        g.user.username = username
        try:
            # The unique constraint also covers two people picking it at once.
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            error = "這個用戶名已被使用"

    if error:
        flash(error, "error")
        return render_settings(username=username)

    flash("用戶名已更新", "success")
    return redirect(url_for("users.settings"))


@bp.post("/settings/password")
@login_required
def update_password():
    password = request.form.get("password", "")
    error = validate_password(password)
    if error is None and password != request.form.get("confirm_password", ""):
        error = "兩次輸入的密碼不一樣"

    if error:
        flash(error, "error")
        return render_settings()

    g.user.password_hash = generate_password_hash(password)
    db.session.commit()
    flash("密碼已更新", "success")
    return redirect(url_for("users.settings"))
