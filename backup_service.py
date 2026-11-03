import os
import json
import base64
import hashlib
import logging
import subprocess
from datetime import datetime
from typing import Optional, Dict, Any, Union

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import (
    User,
    Post,
    Comment,
    CommunitySubmission,
    SiteStat,
    RadioTrack
)

logger = logging.getLogger("refugio.backup")

DEFAULT_BACKUP_JSON_PATH = os.path.join("backups", "refugio_snapshot.json")


def _get_fernet() -> Fernet:
    """Deriva chave Fernet deterministica de 32 bytes a partir da SECRET_KEY."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _encrypt_sensitive(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if value.startswith("enc:"):
        return value
    token = _get_fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"enc:{token}"


def _decrypt_sensitive(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if not value.startswith("enc:"):
        return value
    raw_token = value[4:]
    try:
        return _get_fernet().decrypt(raw_token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.warning("[BACKUP] Nao foi possivel decifrar campo sensivel (SECRET_KEY diferente?).")
        return value


def _parse_dt(val: Optional[str]) -> datetime:
    if not val:
        return datetime.now()
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return datetime.now()


def build_backup_payload(db: Session) -> Dict[str, Any]:
    """Serializa todas as tabelas essenciais do banco SQLite para um dicionario estruturado."""
    users = db.query(User).order_by(User.id.asc()).all()
    posts = db.query(Post).order_by(Post.id.asc()).all()
    comments = db.query(Comment).order_by(Comment.id.asc()).all()
    submissions = db.query(CommunitySubmission).order_by(CommunitySubmission.id.asc()).all()
    stats = db.query(SiteStat).order_by(SiteStat.id.asc()).all()
    tracks = db.query(RadioTrack).order_by(RadioTrack.id.asc()).all()

    data = {
        "site_stats": [
            {"id": s.id, "key": s.key, "value": s.value}
            for s in stats
        ],
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": _encrypt_sensitive(u.email),
                "password_hash": _encrypt_sensitive(u.password_hash),
                "role": getattr(u, "role", "admin"),
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ],
        "posts": [
            {
                "id": p.id,
                "title": p.title,
                "slug": p.slug,
                "content": p.content,
                "category": p.category,
                "media_url": p.media_url,
                "author_id": p.author_id,
                "views_count": p.views_count,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None
            }
            for p in posts
        ],
        "comments": [
            {
                "id": c.id,
                "post_id": c.post_id,
                "post_slug": c.post.slug if c.post else None,
                "user_id": c.user_id,
                "author_name": c.author_name,
                "author_email": _encrypt_sensitive(c.author_email),
                "content": c.content,
                "notify_replies": bool(c.notify_replies),
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None
            }
            for c in comments
        ],
        "community_submissions": [
            {
                "id": sub.id,
                "author_name": sub.author_name,
                "author_email": _encrypt_sensitive(sub.author_email),
                "github_link": sub.github_link,
                "title": sub.title,
                "category": sub.category,
                "description": sub.description,
                "image_url": sub.image_url,
                "status": sub.status,
                "clicks_count": sub.clicks_count,
                "created_at": sub.created_at.isoformat() if sub.created_at else None
            }
            for sub in submissions
        ],
        "radio_tracks": [
            {
                "id": t.id,
                "title": t.title,
                "artist": t.artist,
                "country": t.country,
                "genre": t.genre,
                "youtube_id": t.youtube_id,
                "youtube_url": t.youtube_url,
                "description": t.description,
                "is_active": bool(t.is_active),
                "created_at": t.created_at.isoformat() if t.created_at else None
            }
            for t in tracks
        ]
    }

    canonical_bytes = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    checksum = hashlib.sha256(canonical_bytes).hexdigest()

    return {
        "metadata": {
            "app": settings.APP_NAME,
            "version": "1.3.0",
            "exported_at": datetime.now().isoformat(),
            "sha256_checksum": checksum,
            "counts": {
                "users": len(users),
                "posts": len(posts),
                "comments": len(comments),
                "community_submissions": len(submissions),
                "radio_tracks": len(tracks),
                "site_stats": len(stats)
            }
        },
        "data": data
    }


def export_backup_to_json(
    db: Optional[Session] = None,
    output_path: str = DEFAULT_BACKUP_JSON_PATH
) -> Dict[str, Any]:
    """Exporta os dados do banco para o arquivo JSON de snapshot."""
    owns_session = False
    if db is None:
        db = SessionLocal()
        owns_session = True

    try:
        os.makedirs(os.path.dirname(output_path) or "backups", exist_ok=True)
        payload = build_backup_payload(db)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(f"[BACKUP] Snapshot JSON gravado com sucesso em {output_path}.")
        return payload
    finally:
        if owns_session:
            db.close()


def import_backup_from_json(
    source: Union[str, Dict[str, Any]],
    db: Optional[Session] = None
) -> Dict[str, int]:
    """Restaura/mescla registros a partir de um arquivo ou dicionario JSON de backup."""
    owns_session = False
    if db is None:
        db = SessionLocal()
        owns_session = True

    try:
        if isinstance(source, str):
            with open(source, "r", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            payload = source

        data = payload.get("data", payload)
        restored_counts = {
            "users": 0,
            "posts": 0,
            "comments": 0,
            "community_submissions": 0,
            "radio_tracks": 0,
            "site_stats": 0
        }

        # 1. Site Stats
        for s_item in data.get("site_stats", []):
            stat = db.query(SiteStat).filter(SiteStat.key == s_item["key"]).first()
            if stat:
                stat.value = max(stat.value, int(s_item.get("value", 0)))
            else:
                db.add(SiteStat(key=s_item["key"], value=int(s_item.get("value", 0))))
            restored_counts["site_stats"] += 1

        # 2. Users
        for u_item in data.get("users", []):
            existing = db.query(User).filter(User.username == u_item["username"]).first()
            dec_email = _decrypt_sensitive(u_item.get("email"))
            dec_pwd = _decrypt_sensitive(u_item.get("password_hash")) or ""
            if not existing:
                db.add(User(
                    username=u_item["username"],
                    email=dec_email,
                    password_hash=dec_pwd,
                    role=u_item.get("role", "user"),
                    created_at=_parse_dt(u_item.get("created_at"))
                ))
                restored_counts["users"] += 1

        db.flush()

        # 3. Posts
        snapshot_post_id_to_slug = {}
        for p_item in data.get("posts", []):
            if p_item.get("id") and p_item.get("slug"):
                snapshot_post_id_to_slug[p_item["id"]] = p_item["slug"]
            existing_post = db.query(Post).filter(Post.slug == p_item["slug"]).first()
            if existing_post:
                existing_post.title = p_item["title"]
                existing_post.content = p_item["content"]
                existing_post.category = p_item.get("category", "Geral")
                existing_post.media_url = p_item.get("media_url")
                existing_post.views_count = max(existing_post.views_count, int(p_item.get("views_count", 0)))
            else:
                db.add(Post(
                    title=p_item["title"],
                    slug=p_item["slug"],
                    content=p_item["content"],
                    category=p_item.get("category", "Geral"),
                    media_url=p_item.get("media_url"),
                    author_id=p_item.get("author_id"),
                    views_count=int(p_item.get("views_count", 0)),
                    created_at=_parse_dt(p_item.get("created_at")),
                    updated_at=_parse_dt(p_item.get("updated_at"))
                ))
            restored_counts["posts"] += 1

        db.flush()

        # 4. Comments
        for c_item in data.get("comments", []):
            target_slug = c_item.get("post_slug") or snapshot_post_id_to_slug.get(c_item.get("post_id"))
            target_post = None
            if target_slug:
                target_post = db.query(Post).filter(Post.slug == target_slug).first()
            if not target_post and c_item.get("post_id"):
                target_post = db.query(Post).filter(Post.id == c_item.get("post_id")).first()
            if not target_post:
                continue

            existing_comment = None
            if c_item.get("id"):
                existing_comment = db.query(Comment).filter(Comment.id == c_item.get("id")).first()

            dec_c_email = _decrypt_sensitive(c_item.get("author_email")) or "anon@refugio.local"
            parsed_updated = _parse_dt(c_item.get("updated_at")) if c_item.get("updated_at") else None

            if existing_comment:
                existing_comment.content = c_item["content"]
                existing_comment.notify_replies = bool(c_item.get("notify_replies", False))
                if parsed_updated:
                    existing_comment.updated_at = parsed_updated
            else:
                db.add(Comment(
                    post_id=target_post.id,
                    user_id=c_item.get("user_id"),
                    author_name=c_item["author_name"],
                    author_email=dec_c_email,
                    content=c_item["content"],
                    notify_replies=bool(c_item.get("notify_replies", False)),
                    created_at=_parse_dt(c_item.get("created_at")),
                    updated_at=parsed_updated
                ))
                restored_counts["comments"] += 1

        # 5. Community Submissions
        for sub_item in data.get("community_submissions", []):
            existing_sub = db.query(CommunitySubmission).filter(
                CommunitySubmission.title == sub_item["title"],
                CommunitySubmission.github_link == sub_item["github_link"]
            ).first()
            dec_sub_email = _decrypt_sensitive(sub_item.get("author_email")) or "dev@refugio.local"
            if not existing_sub:
                db.add(CommunitySubmission(
                    author_name=sub_item["author_name"],
                    author_email=dec_sub_email,
                    github_link=sub_item["github_link"],
                    title=sub_item["title"],
                    category=sub_item.get("category", "Scripts Úteis"),
                    description=sub_item["description"],
                    image_url=sub_item.get("image_url"),
                    status=sub_item.get("status", "pending"),
                    clicks_count=int(sub_item.get("clicks_count", 0)),
                    created_at=_parse_dt(sub_item.get("created_at"))
                ))
                restored_counts["community_submissions"] += 1

        # 6. Radio Tracks
        for t_item in data.get("radio_tracks", []):
            existing_track = db.query(RadioTrack).filter(RadioTrack.youtube_id == t_item["youtube_id"]).first()
            if not existing_track:
                db.add(RadioTrack(
                    title=t_item["title"],
                    artist=t_item["artist"],
                    country=t_item.get("country", "América Latina"),
                    genre=t_item.get("genre", "Protesto"),
                    youtube_id=t_item["youtube_id"],
                    youtube_url=t_item["youtube_url"],
                    description=t_item.get("description"),
                    is_active=bool(t_item.get("is_active", True)),
                    created_at=_parse_dt(t_item.get("created_at"))
                ))
                restored_counts["radio_tracks"] += 1

        db.commit()
        return restored_counts
    except Exception as e:
        db.rollback()
        logger.error(f"[BACKUP RESTORE] Erro ao restaurar JSON: {e}")
        raise e
    finally:
        if owns_session:
            db.close()


def git_commit_and_push_backup(
    backup_path: str = DEFAULT_BACKUP_JSON_PATH,
    push_remote: bool = True
) -> Dict[str, Any]:
    """
    Exporta o JSON de backup atual e executa git add + git commit + git push local
    para salvar o snapshot no repositorio Git/GitHub.
    """
    export_backup_to_json(output_path=backup_path)

    try:
        # 1. git add -f backups/refugio_snapshot.json
        subprocess.run(
            ["git", "add", "-f", backup_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=10
        )

        # 2. Verifica se houve alteracao em relacao ao HEAD
        diff_res = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", backup_path],
            capture_output=True,
            text=True,
            timeout=10
        )

        commit_hash = None
        if diff_res.returncode != 0:
            timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"chore(backup): snapshot de dados O Refugio [{timestamp_str}]"
            subprocess.run(
                ["git", "commit", "-m", commit_msg, "--", backup_path],
                check=True,
                capture_output=True,
                text=True,
                timeout=15
            )

        rev_res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if rev_res.returncode == 0:
            commit_hash = rev_res.stdout.strip()

        if not push_remote:
            return {
                "status": "committed_local",
                "pushed": False,
                "commit_hash": commit_hash,
                "message": f"Backup JSON salvo e commitado localmente ({commit_hash})."
            }

        # 3. git push para o remoto configurado
        push_res = subprocess.run(
            ["git", "push"],
            capture_output=True,
            text=True,
            timeout=25
        )
        if push_res.returncode == 0:
            return {
                "status": "ok",
                "pushed": True,
                "commit_hash": commit_hash,
                "message": f"Backup JSON sincronizado no GitHub com sucesso (commit {commit_hash})."
            }
        else:
            stderr_msg = (push_res.stderr or push_res.stdout or "").strip()[:200]
            return {
                "status": "committed_local",
                "pushed": False,
                "commit_hash": commit_hash,
                "message": f"Snapshot commitado localmente ({commit_hash}), mas git push retornou aviso: {stderr_msg}"
            }
    except Exception as e:
        logger.error(f"[BACKUP GIT] Falha no git commit/push do backup: {e}")
        return {
            "status": "error",
            "pushed": False,
            "commit_hash": None,
            "message": f"Snapshot JSON gerado em {backup_path}, mas erro no Git: {e}"
        }
