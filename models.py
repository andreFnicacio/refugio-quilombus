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
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<User {self.username}>"


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(220), unique=True, index=True, nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(100), default="Geral", nullable=False, index=True)
    media_url = Column(String(500), nullable=True)
    views_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

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
    author_name = Column(String(100), nullable=False)
    author_email = Column(String(150), nullable=False)
    content = Column(Text, nullable=False)
    notify_replies = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    post = relationship("Post", back_populates="comments")

    def __repr__(self):
        return f"<Comment by {self.author_name} on Post {self.post_id}>"


class SiteStat(Base):
    __tablename__ = "site_stats"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, index=True, nullable=False)
    value = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<SiteStat {self.key}={self.value}>"
