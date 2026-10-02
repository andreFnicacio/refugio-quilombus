import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "O Refúgio"
    APP_ENV: str = "development"
    BASE_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "refugio-secret-key-indieweb-2026-matrix-reloaded-super-secure"

    DATABASE_URL: str = "sqlite:///./blog.db"

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "refugio2026!"

    SESSION_COOKIE_NAME: str = "refugio_session"
    MAX_UPLOAD_SIZE_MB: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
