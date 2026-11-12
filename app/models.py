from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import deferred

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nickname = db.Column(db.String(30), nullable=False, default="")
    bio = db.Column(db.String(200), nullable=False, default="")
    # WebP bytes made by users.make_avatar; only loaded when a page needs it.
    avatar = deferred(db.Column(db.LargeBinary))

    @property
    def display_name(self):
        return self.nickname or self.username

    @property
    def has_avatar(self):
        return self.avatar is not None
