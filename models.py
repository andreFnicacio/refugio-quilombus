from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user", nullable=False, index=True)  # "admin" ou "user"
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(220), unique=True, index=True, nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(100), default="Geral", nullable=False, index=True)
    media_url = Column(String(500), nullable=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    views_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    author = relationship("User")
    comments = relationship(
        "Comment",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="desc(Comment.created_at)"
    )

    def __repr__(self):
        return f"<Post {self.slug}>"


class CommunitySubmission(Base):
    __tablename__ = "community_submissions"

    id = Column(Integer, primary_key=True, index=True)
    author_name = Column(String(100), nullable=False)
    author_email = Column(String(150), nullable=False)
    github_link = Column(String(300), nullable=False)
    title = Column(String(150), nullable=False)
    category = Column(String(100), default="Scripts Úteis", nullable=False, index=True)
    description = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending, approved, rejected
    clicks_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<CommunitySubmission {self.title} ({self.status})>"


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    author_name = Column(String(100), nullable=False)
    author_email = Column(String(150), nullable=False)
    content = Column(Text, nullable=False)
    notify_replies = Column(Boolean, default=False, nullable=False)
    edit_token = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, nullable=True)

    post = relationship("Post", back_populates="comments")
    user = relationship("User")

    def __repr__(self):
        return f"<Comment by {self.author_name} on Post {self.post_id}>"


class Notification(Base):
    __tablename__ = "user_notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True, index=True)
    comment_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    target_url = Column(String(500), nullable=False)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    user = relationship("User")

    def __repr__(self):
        return f"<Notification user={self.user_id} title={self.title} read={self.is_read}>"


class RadioTrack(Base):
    __tablename__ = "radio_tracks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    artist = Column(String(150), nullable=False)
    country = Column(String(80), default="América Latina", nullable=False)
    genre = Column(String(80), default="Protesto", nullable=False)
    youtube_id = Column(String(30), nullable=False, index=True)
    youtube_url = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<RadioTrack {self.artist} - {self.title} ({self.youtube_id})>"


class SiteStat(Base):
    __tablename__ = "site_stats"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, index=True, nullable=False)
    value = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<SiteStat {self.key}={self.value}>"


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    endpoint = Column(Text, unique=True, nullable=False, index=True)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    last_notified_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<PushSubscription {self.id} ({self.endpoint[:30]}...)>"


class PushLog(Base):
    __tablename__ = "push_logs"

    id = Column(Integer, primary_key=True, index=True)
    notification_type = Column(String(50), nullable=False)  # post, news_digest, comment, manual
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    target_url = Column(String(500), nullable=False)
    total_recipients = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    failure_count = Column(Integer, default=0, nullable=False)
    sent_at = Column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<PushLog {self.notification_type}: {self.title}>"
