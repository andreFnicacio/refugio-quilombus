import logging
from email.message import EmailMessage
from typing import List, Optional
import aiosmtplib
from config import settings

logger = logging.getLogger("refugio.email")


async def send_email_async(
    to_emails: List[str],
    subject: str,
    body_text: str,
    body_html: Optional[str] = None
) -> bool:
    """
    Envia e-mails de forma assíncrona usando aiosmtplib.
    Se as credenciais SMTP não estiverem configuradas, simula o envio no log.
    """
    if not to_emails:
        return False

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(
            f"[SMTP DEV MODE] E-mail não enviado para {to_emails}. Assunto: '{subject}' (SMTP_USER/SMTP_PASSWORD não configurados)."
        )
        return True

    msg = EmailMessage()
    msg["Subject"] = f"[{settings.APP_NAME}] {subject}"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_USER}>"
    msg["To"] = ", ".join(to_emails)
    msg.set_content(body_text)

    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
            timeout=10
        )
        logger.info(f"E-mail enviado com sucesso para {to_emails}: '{subject}'")
        return True
    except Exception as e:
        logger.error(f"Erro ao disparar e-mail para {to_emails}: {e}")
        return False


async def notify_new_comment_in_background(
    post_title: str,
    post_slug: str,
    comment_author: str,
    comment_content: str,
    recipient_emails: List[str]
):
    """Notifica inscritos sobre novo comentário no post."""
    if not recipient_emails:
        return

    post_url = f"{settings.BASE_URL}/post/{post_slug}"
    subject = f"Novo comentário em: {post_title}"
    body_text = f"""
Salve!

{comment_author} acabou de comentar no post: "{post_title}".

Comentário:
"{comment_content}"

Acesse o post para responder:
{post_url}

--
O Refúgio (Indie Blog & Community Hub)
"""
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: monospace; background: #0a0e17; color: #00ff66; padding: 20px; }}
        .card {{ border: 2px solid #00ff66; padding: 15px; background: #111625; box-shadow: 4px 4px 0 #00ff66; }}
        h2 {{ color: #ffb000; margin-top: 0; }}
        a {{ color: #00f0ff; text-decoration: none; font-weight: bold; }}
        blockquote {{ border-left: 3px solid #ffb000; margin: 10px 0; padding-left: 10px; color: #e0e0e0; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h2>[NOVA MENSAGEM NO REFÚGIO]</h2>
        <p><strong>{comment_author}</strong> deixou um comentário no post: <em>{post_title}</em></p>
        <blockquote>{comment_content}</blockquote>
        <p><a href="{post_url}">[CLIQUE AQUI PARA LER E RESPONDER NO SITE]</a></p>
        <hr style="border-color: #333;">
        <small style="color: #888;">Transmissão direta do terminal de O Refúgio.</small>
      </div>
    </body>
    </html>
    """
    await send_email_async(
        to_emails=recipient_emails,
        subject=subject,
        body_text=body_text,
        body_html=body_html
    )


async def notify_admin_new_submission_in_background(
    submission_title: str,
    author_name: str,
    github_link: str,
    category: str
):
    """Alerta o admin sobre uma nova submissão da comunidade para moderação."""
    admin_email = settings.ADMIN_EMAIL
    if not admin_email:
        return

    admin_url = f"{settings.BASE_URL}/admin"
    subject = f"[MODERAÇÃO PENDENTE] Nova submissão no Lab: {submission_title}"
    body_text = f"""
Salve, Admin!

Novo projeto submetido no Laboratório da Comunidade:
- Título: {submission_title}
- Autor: {author_name}
- Categoria: {category}
- GitHub: {github_link}

Acesse o painel para aprovar ou rejeitar:
{admin_url}
"""
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: monospace; background: #0a0e17; color: #ffb000; padding: 20px; }}
        .card {{ border: 2px solid #ffb000; padding: 15px; background: #111625; box-shadow: 4px 4px 0 #ffb000; }}
        a {{ color: #00ff66; font-weight: bold; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h2>[ALERTA DE MODERAÇÃO - LAB]</h2>
        <p>Um novo projeto foi submetido e aguarda sua aprovação:</p>
        <ul>
          <li><strong>Título:</strong> {submission_title}</li>
          <li><strong>Autor:</strong> {author_name}</li>
          <li><strong>Categoria:</strong> {category}</li>
          <li><strong>Repositório:</strong> <a href="{github_link}">{github_link}</a></li>
        </ul>
        <p><a href="{admin_url}">[ACESSAR PAINEL DE ADMINISTRAÇÃO]</a></p>
      </div>
    </body>
    </html>
    """
    await send_email_async(
        to_emails=[admin_email],
        subject=subject,
        body_text=body_text,
        body_html=body_html
    )
