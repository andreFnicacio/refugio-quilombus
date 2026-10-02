import os
import re
import uuid
import bcrypt
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models import User
from config import settings

serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="refugio-session-salt")

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def hash_password(plain_password: str) -> str:
    pwd_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_session_token(username: str) -> str:
    return serializer.dumps({"sub": username})


def verify_session_token(token: str, max_age: int = 60 * 60 * 2) -> Optional[str]:
    """Valida token assinado com tempo máximo de inatividade (padrão 2 horas)."""
    try:
        data = serializer.loads(token, max_age=max_age)
        return data.get("sub")
    except (BadSignature, SignatureExpired, Exception):
        return None


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        return None

    username = verify_session_token(token)
    if not username:
        return None

    user = db.query(User).filter(User.username == username).first()
    return user


def require_admin(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    user = get_current_user_optional(request, db)
    if not user:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": f"/login?next={request.url.path}"}
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária"
        )
    return user


def check_image_magic_bytes(header: bytes, ext: str) -> bool:
    """Verifica assinatura binária do cabeçalho da imagem para evitar falsificação de extensão."""
    if ext == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    elif ext in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    elif ext == ".gif":
        return header.startswith(b"GIF87a") or header.startswith(b"GIF89a")
    elif ext == ".webp":
        return len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    return False


def validate_image_file(filename: str, file_bytes: bytes) -> tuple[bool, str]:
    """Valida extensão, tamanho e cabeçalho binário (magic bytes) do arquivo."""
    base_name = os.path.basename(filename)
    ext = os.path.splitext(base_name)[1].lower()

    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False, f"Extensão '{ext}' inválida. Use PNG, JPG, JPEG, WEBP ou GIF."

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        return False, f"Arquivo excede o limite de {settings.MAX_UPLOAD_SIZE_MB}MB."

    if len(file_bytes) < 12:
        return False, "Arquivo corrompido ou vazio."

    if not check_image_magic_bytes(file_bytes[:32], ext):
        return False, f"Conteúdo do arquivo não corresponde a uma imagem válida do tipo {ext}."

    return True, ""


def generate_safe_filename(original_filename: str) -> str:
    """Gera nome único e sanitizado, protegendo contra Path Traversal."""
    clean_base = os.path.basename(original_filename)
    ext = os.path.splitext(clean_base)[1].lower()
    raw_name = os.path.splitext(clean_base)[0]
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "", raw_name)[:30] or "upload"
    return f"{safe_name}_{uuid.uuid4().hex[:8]}{ext}"
