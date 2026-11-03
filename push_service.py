import os
import json
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, Union

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
import pywebpush
from sqlalchemy.orm import Session

from config import settings
from models import PushSubscription, PushLog, Post, Comment, User, Notification
from database import SessionLocal

logger = logging.getLogger("refugio.push")

VAPID_PRIVATE_KEY_FILE = getattr(settings, "VAPID_PRIVATE_KEY_PATH", "vapid_private.pem")


def _get_raw_b64_public_key(vapid: Vapid) -> str:
    """Retorna a chave publica VAPID no formato bruto uncompressed URL-safe base64."""
    raw_bytes = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")


def ensure_vapid_keys() -> Tuple[str, Vapid]:
    """
    Garante que as chaves VAPID existem no disco e no ambiente.
    Se nao existirem, gera um novo par seguro e persiste.
    """
    vapid = Vapid()
    if os.path.exists(VAPID_PRIVATE_KEY_FILE):
        try:
            with open(VAPID_PRIVATE_KEY_FILE, "rb") as f:
                pem_data = f.read()
            vapid = Vapid.from_pem(pem_data)
            public_key = _get_raw_b64_public_key(vapid)
            return public_key, vapid
        except Exception as e:
            logger.warning(f"[PUSH] Erro ao carregar {VAPID_PRIVATE_KEY_FILE}: {e}. Gerando novas chaves.")

    # Gera novas chaves
    vapid.generate_keys()
    pem_bytes = vapid.private_pem()
    with open(VAPID_PRIVATE_KEY_FILE, "wb") as f:
        f.write(pem_bytes)
    try:
        os.chmod(VAPID_PRIVATE_KEY_FILE, 0o600)
    except Exception:
        pass

    public_key = _get_raw_b64_public_key(vapid)

    # Atualiza o arquivo .env se possivel
    env_path = ".env"
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()

            if "VAPID_PUBLIC_KEY=" in content:
                lines = content.splitlines()
                new_lines = []
                for line in lines:
                    if line.startswith("VAPID_PUBLIC_KEY="):
                        new_lines.append(f'VAPID_PUBLIC_KEY="{public_key}"')
                    else:
                        new_lines.append(line)
                new_content = "\n".join(new_lines) + "\n"
            else:
                new_content = content.rstrip() + f'\n\n# Web Push VAPID\nVAPID_PUBLIC_KEY="{public_key}"\nVAPID_PRIVATE_KEY_PATH="{VAPID_PRIVATE_KEY_FILE}"\nVAPID_CLAIM_EMAIL="{getattr(settings, "ADMIN_EMAIL", "admin@refugio.local")}"\n'

            with open(env_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            logger.warning(f"[PUSH] Nao foi possivel atualizar o .env: {e}")

    logger.info("[PUSH] Par de chaves VAPID configurado com sucesso.")
    return public_key, vapid


# Instancia e chave em cache de execucao
_CACHED_PUBLIC_KEY, _CACHED_VAPID = ensure_vapid_keys()


def get_vapid_public_key() -> str:
    """Retorna a chave publica VAPID configurada."""
    global _CACHED_PUBLIC_KEY, _CACHED_VAPID
    if not _CACHED_PUBLIC_KEY:
        _CACHED_PUBLIC_KEY, _CACHED_VAPID = ensure_vapid_keys()
    return _CACHED_PUBLIC_KEY


def get_vapid_instance() -> Vapid:
    """Retorna o objeto Vapid pronto para assinatura."""
    global _CACHED_PUBLIC_KEY, _CACHED_VAPID
    if not _CACHED_VAPID:
        _CACHED_PUBLIC_KEY, _CACHED_VAPID = ensure_vapid_keys()
    return _CACHED_VAPID


def register_subscription(
    db: Session,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: Optional[str] = None,
    user_id: Optional[int] = None
) -> PushSubscription:
    """Registra ou atualiza um endpoint de notificacao."""
    sub = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if sub:
        sub.p256dh = p256dh
        sub.auth = auth
        if user_agent:
            sub.user_agent = user_agent[:255]
        if user_id is not None:
            sub.user_id = user_id
    else:
        sub = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=user_agent[:255] if user_agent else None,
            created_at=datetime.now()
        )
        db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def unregister_subscription(db: Session, endpoint: str) -> bool:
    """Remove um endpoint de notificacao."""
    sub = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if sub:
        db.delete(sub)
        db.commit()
        return True
    return False


def get_subscribers_count(db: Session) -> int:
    """Retorna a contagem de assinaturas ativas."""
    return db.query(PushSubscription).count()


def send_single_push(
    sub: PushSubscription,
    payload: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Dispara notificacao push para uma assinatura especifica.
    Retorna (sucesso: bool, erro: Optional[str]).
    Se o status retornado pelo FCM/Mozilla for 404 ou 410, indica endpoint invalido.
    """
    vapid = get_vapid_instance()
    claim_email = getattr(settings, "VAPID_CLAIM_EMAIL", getattr(settings, "ADMIN_EMAIL", "admin@refugio.local"))
    vapid_claims = {"sub": f"mailto:{claim_email}"}

    sub_info = {
        "endpoint": sub.endpoint,
        "keys": {
            "p256dh": sub.p256dh,
            "auth": sub.auth
        }
    }

    try:
        pywebpush.webpush(
            subscription_info=sub_info,
            data=json.dumps(payload),
            vapid_private_key=vapid,
            vapid_claims=vapid_claims,
            ttl=86400  # 24 horas
        )
        return True, None
    except pywebpush.WebPushException as exc:
        status_code = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
        if status_code in (404, 410):
            return False, "unregistered"
        return False, f"WebPushException: {exc}"
    except Exception as exc:
        return False, f"Erro inesperado: {exc}"


def broadcast_notification(
    title: str,
    body: str,
    target_url: str,
    notification_type: str = "manual",
    target_user_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Dispara uma notificacao para assinaturas ativas no banco.
    Se target_user_ids for informado e houver inscritos vinculados, prioriza-os;
    caso contrario envia para as assinaturas ativas.
    Remove automaticamente endpoints obsoletos (404/410) e registra log.
    """
    db = SessionLocal()
    try:
        query = db.query(PushSubscription)
        if target_user_ids is not None:
            targeted = query.filter(PushSubscription.user_id.in_(target_user_ids)).all()
            subscriptions = targeted if targeted else query.all()
        else:
            subscriptions = query.all()

        total = len(subscriptions)
        now = datetime.now()
        if total == 0:
            logger.info(f"[PUSH] Nenhum inscrito ativo para envio de {notification_type}.")
            log_entry = PushLog(
                notification_type=notification_type,
                title=title,
                body=body,
                target_url=target_url,
                total_recipients=0,
                success_count=0,
                failure_count=0,
                sent_at=now
            )
            db.add(log_entry)
            db.commit()
            return {
                "total": 0,
                "success": 0,
                "failure": 0,
                "status": "sem_inscritos"
            }

        payload = {
            "title": title,
            "body": body,
            "url": target_url,
            "icon": "/static/favicon.ico",
            "badge": "/static/favicon.ico",
            "tag": f"refugio-{notification_type}-{int(now.timestamp())}",
            "timestamp": int(now.timestamp() * 1000)
        }

        success_count = 0
        failure_count = 0
        to_delete_endpoints = []

        for sub in subscriptions:
            success, err = send_single_push(sub, payload)
            if success:
                success_count += 1
                sub.last_notified_at = now
            else:
                failure_count += 1
                if err == "unregistered":
                    to_delete_endpoints.append(sub.endpoint)
                else:
                    logger.debug(f"[PUSH] Falha no endpoint {sub.id}: {err}")

        # Limpeza de endpoints obsoletos
        if to_delete_endpoints:
            db.query(PushSubscription).filter(
                PushSubscription.endpoint.in_(to_delete_endpoints)
            ).delete(synchronize_session=False)
            logger.info(f"[PUSH] Limpeza: {len(to_delete_endpoints)} assinaturas expiradas removidas.")

        # Log do disparo
        log_entry = PushLog(
            notification_type=notification_type,
            title=title,
            body=body,
            target_url=target_url,
            total_recipients=total,
            success_count=success_count,
            failure_count=failure_count,
            sent_at=now
        )
        db.add(log_entry)
        db.commit()

        logger.info(f"[PUSH] Broadcast '{title}' concluido: {success_count}/{total} entregues com sucesso.")
        return {
            "total": total,
            "success": success_count,
            "failure": failure_count,
            "removed_stale": len(to_delete_endpoints)
        }
    except Exception as e:
        logger.error(f"[PUSH] Falha no broadcast de notificacao: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


def send_post_push_notification(post: Union[Post, int]):
    """Dispara notificacao automatica para um novo post do blog."""
    db = SessionLocal()
    try:
        post_obj = db.query(Post).filter(Post.id == post).first() if isinstance(post, int) else post
        if not post_obj:
            return
        clean_title = f"Novo post: {post_obj.title}"
        body = (post_obj.content[:140] + "...") if len(post_obj.content) > 140 else post_obj.content
        target_url = f"/post/{post_obj.slug}"
    finally:
        db.close()

    broadcast_notification(
        title=clean_title,
        body=body,
        target_url=target_url,
        notification_type="post"
    )


def notify_new_comment(post_id: int, comment_id: int) -> Dict[str, Any]:
    """
    Cria notificacoes In-App (Central de Alertas) e dispara Web Push
    quando um post/forum recebe um novo comentario.
    Destinatarios:
      1. Autor do post e operadores (admins), exceto se forem o proprio autor do comentario.
      2. Usuarios que comentaram anteriormente no mesmo post com notify_replies=True.
    """
    db = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        if not post or not comment:
            return {"in_app_created": 0, "push": None}

        recipient_user_ids = set()

        # 1. Autor do post
        if post.author_id and post.author_id != comment.user_id:
            recipient_user_ids.add(post.author_id)

        # 2. Administradores / Operadores
        admins = db.query(User).filter(User.role == "admin").all()
        for adm in admins:
            if adm.id != comment.user_id and adm.username.lower() != comment.author_name.lower():
                recipient_user_ids.add(adm.id)

        # 3. Participantes da thread com notify_replies=True
        prev_comments = (
            db.query(Comment)
            .filter(
                Comment.post_id == post.id,
                Comment.id != comment.id,
                Comment.notify_replies == True
            )
            .all()
        )
        for prev in prev_comments:
            if prev.user_id and prev.user_id != comment.user_id:
                recipient_user_ids.add(prev.user_id)
            else:
                # Tenta localizar usuario pelo email ou username caso tenha comentado antes de logar
                matched_user = (
                    db.query(User)
                    .filter(
                        (User.email == prev.author_email) | (User.username == prev.author_name)
                    )
                    .first()
                )
                if matched_user and matched_user.id != comment.user_id and matched_user.username.lower() != comment.author_name.lower():
                    recipient_user_ids.add(matched_user.id)

        target_url = f"/post/{post.slug}#comment-{comment.id}"
        notif_title = f"Nova resposta em: {post.title[:80]}"
        snippet = (comment.content[:120] + "...") if len(comment.content) > 120 else comment.content
        notif_msg = f"@{comment.author_name} comentou: \"{snippet}\""

        created_count = 0
        now = datetime.now()
        for uid in recipient_user_ids:
            notif = Notification(
                user_id=uid,
                post_id=post.id,
                comment_id=comment.id,
                title=notif_title,
                message=notif_msg,
                target_url=target_url,
                is_read=False,
                created_at=now
            )
            db.add(notif)
            created_count += 1

        db.commit()
        target_ids_list = list(recipient_user_ids)
    except Exception as e:
        logger.error(f"[NOTIFY COMMENT] Erro ao gerar notificacoes de comentario: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()

    # Dispara Web Push para os inscritos
    push_res = broadcast_notification(
        title=notif_title,
        body=notif_msg,
        target_url=target_url,
        notification_type="comment",
        target_user_ids=target_ids_list if target_ids_list else None
    )
    return {"in_app_created": created_count, "push": push_res}


def check_and_send_daily_news_digest(force: bool = False) -> bool:
    """
    Verifica se o resumo diario do Radar de Noticias ja foi disparado nas ultimas 24h.
    Se force=True, ignora o throttle de 24h e dispara imediatamente.
    """
    from news_service import get_news_hub_data

    db = SessionLocal()
    try:
        # Verifica se ja houve envio de news_digest nas ultimas 24 horas (a menos que seja forcado)
        if not force:
            since = datetime.now() - timedelta(hours=24)
            last_digest = (
                db.query(PushLog)
                .filter(
                    PushLog.notification_type == "news_digest",
                    PushLog.sent_at >= since
                )
                .order_by(PushLog.sent_at.desc())
                .first()
            )
            if last_digest:
                return False

        news_hub = get_news_hub_data()
        if not news_hub:
            return False

        # Coleta os titulos das materias mais recentes
        headlines = []
        for category in ["tech", "nerd", "politics"]:
            items = news_hub.get(category, [])
            if items and len(items) > 0:
                first_title = items[0].get("title", "").strip()
                if first_title:
                    headlines.append(first_title)

        if not headlines:
            return False

        # Monta o resumo (sem emojis)
        title = "Radar de Noticias: Resumo diario"
        body = " | ".join(headlines[:2])
        if len(body) > 160:
            body = body[:157] + "..."

        target_url = "/radar"
        broadcast_notification(
            title=title,
            body=body,
            target_url=target_url,
            notification_type="news_digest"
        )
        return True
    except Exception as e:
        logger.error(f"[PUSH] Erro ao verificar resumo diario do Radar: {e}")
        return False
    finally:
        db.close()
