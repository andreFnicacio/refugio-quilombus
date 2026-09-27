from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, HttpUrl, EmailStr, Field


# --- USER SCHEMAS ---
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserOut(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- COMMENT SCHEMAS ---
class CommentBase(BaseModel):
    author_name: str = Field(..., min_length=2, max_length=100)
    author_email: EmailStr
    content: str = Field(..., min_length=2, max_length=2000)
    notify_replies: bool = False


class CommentCreate(CommentBase):
    pass


class CommentOut(CommentBase):
    id: int
    post_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- POST SCHEMAS ---
class PostBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    content: str = Field(..., min_length=10)
    category: str = Field(default="Geral", max_length=100)
    media_url: Optional[str] = None


class PostCreate(PostBase):
    pass


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    content: Optional[str] = Field(None, min_length=10)
    category: Optional[str] = Field(None, max_length=100)
    media_url: Optional[str] = None


class PostOut(PostBase):
    id: int
    slug: str
    views_count: int
    created_at: datetime
    updated_at: datetime
    comments: List[CommentOut] = []

    class Config:
        from_attributes = True


# --- COMMUNITY SUBMISSION SCHEMAS ---
class CommunitySubmissionBase(BaseModel):
    author_name: str = Field(..., min_length=2, max_length=100)
    author_email: EmailStr
    github_link: str = Field(..., max_length=300)
    title: str = Field(..., min_length=3, max_length=150)
    category: str = Field(default="Scripts Úteis", max_length=100)
    description: str = Field(..., min_length=10, max_length=3000)
    image_url: Optional[str] = None


class CommunitySubmissionCreate(CommunitySubmissionBase):
    pass


class CommunitySubmissionOut(CommunitySubmissionBase):
    id: int
    status: str
    clicks_count: int
    created_at: datetime

    class Config:
        from_attributes = True
