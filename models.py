"""
Database models for TING MEDIA CMS.
Using SQLAlchemy with SQLite.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Portfolio(db.Model):
    """Portfolio item - Video project."""
    __tablename__ = 'portfolios'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), nullable=False)  # Commercial, Social, Music, Interview, Corporate, Event
    video_url = db.Column(db.String(500), nullable=False)  # File path or YouTube URL
    thumbnail_url = db.Column(db.String(500))
    duration = db.Column(db.Integer)  # seconds
    order = db.Column(db.Integer, default=0)
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'video_url': self.video_url,
            'thumbnail_url': self.thumbnail_url,
            'duration': self.duration,
            'featured': self.featured,
            'order': self.order,
            'created_at': self.created_at.isoformat(),
        }


class CarouselItem(db.Model):
    """Carousel/Featured works."""
    __tablename__ = 'carousel_items'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    video_url = db.Column(db.String(500))
    order = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'image_url': self.image_url,
            'video_url': self.video_url,
            'order': self.order,
            'active': self.active,
        }


class ContentBlock(db.Model):
    """Content blocks for dynamic text sections."""
    __tablename__ = 'content_blocks'

    id = db.Column(db.Integer, primary_key=True)
    section_name = db.Column(db.String(100), nullable=False, unique=True)  # hero, about, services, etc.
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    subtitle = db.Column(db.String(300))
    button_text = db.Column(db.String(100))
    button_link = db.Column(db.String(200))
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'section_name': self.section_name,
            'title': self.title,
            'description': self.description,
            'subtitle': self.subtitle,
            'button_text': self.button_text,
            'button_link': self.button_link,
        }


class AdminUser(db.Model):
    """Admin users."""
    __tablename__ = 'admin_users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120))
    role = db.Column(db.String(20), default='editor')  # admin, editor, viewer
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'role': self.role,
        }
