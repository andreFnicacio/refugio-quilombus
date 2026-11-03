import os
import re
import json
import uuid
import math
import html
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import (
    FastAPI,
    Request,
    Depends,
    Form,
    UploadFile,
    File,
    HTTPException,
    status,
    BackgroundTasks
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import asyncio
import logging
import markdown
import bleach
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from database import get_db, SessionLocal, engine
from models import (
    User,
    Post,
    CommunitySubmission,
    Comment,
    SiteStat,
    PushSubscription,
    PushLog,
    Notification,
    RadioTrack
)
from schemas import PushSubscriptionCreate, PushUnsubscribeRequest, PushBroadcastRequest
from push_service import (
    ensure_vapid_keys,
    get_vapid_public_key,
    register_subscription,
    unregister_subscription,
    broadcast_notification,
    send_post_push_notification,
    notify_new_comment,
    check_and_send_daily_news_digest
)
from auth import (
    require_admin,
    require_login,
    get_current_user_optional,
    verify_password,
    hash_password,
    create_session_token,
    validate_image_file,
    generate_safe_filename
)
from init_db import init_database
from news_service import get_news_hub_data
from media_utils import (
    extract_youtube_id,
    render_youtube_card,
    render_link_preview,
    process_media_links
)
from backup_service import (
    DEFAULT_BACKUP_JSON_PATH,
    export_backup_to_json,
    import_backup_from_json,
    git_commit_and_push_backup
)


# Rate Limiter em memória (FinOps: zero overhead de Redis para instâncias locais/leves)
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

COMMENT_TOKENS_COOKIE = "refugio_comment_tokens"

logger = logging.getLogger("refugio.main")


async def run_daily_digest_scheduler():
    """Rotina em segundo plano que verifica e envia o resumo diario de noticias do Radar."""
    while True:
        try:
            await asyncio.sleep(3600)
            await asyncio.to_thread(check_and_send_daily_news_digest)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[PUSH SCHEDULER] Erro no agendador de resumo diario: {e}")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializacao automatica do banco e seed anti-tela pelada
    init_database()
    ensure_vapid_keys()

    # Inicia tarefa em segundo plano para o resumo diario do Radar
    digest_task = asyncio.create_task(run_daily_digest_scheduler())

    yield

    digest_task.cancel()
    try:
        await digest_task
    except asyncio.CancelledError:
        pass

    # Checkpoint de saida para consolidar WAL no arquivo blog.db antes de reiniciar container
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE);")
    except Exception:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    description="Indie Blog & Community Hub com estética Neo-Brutalist e Retrô 16-bits",
    lifespan=lifespan
)
app.state.limiter = limiter


# Handler customizado para RateLimitExceeded com visual Neo-Brutalist
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        html_content = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
          <meta charset="UTF-8">
          <title>429 - Limite Excedido // O Refúgio</title>
          <link rel="stylesheet" href="/static/css/style.css">
        </head>
        <body style="display:flex; justify-content:center; align-items:center; min-height:100vh;">
          <div class="card-brutalist" style="border-color:var(--border-pink); box-shadow:6px 6px 0 var(--border-pink); max-width:520px; text-align:center;">
            <h1 style="font-family:var(--font-pixel); color:var(--border-pink); font-size:1.4rem; margin-bottom:15px;">
              [429: TAXA EXCEDIDA]
            </h1>
            <p style="font-family:var(--font-mono); color:#ffffff; margin-bottom:15px;">
              Calma lá, cowboy! Muitas requisições originadas do seu IP em um curto intervalo de tempo.
            </p>
            <p style="font-family:var(--font-mono); font-size:0.85rem; color:var(--text-dim); margin-bottom:20px;">
              // PROTOCOLO DE SEGURANÇA ATIVADO CONTRA FLOOD E BRUTE-FORCE
            </p>
            <a href="/" class="btn btn-amber">RETORNAR AO DIÁRIO &gt;&gt;</a>
          </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Limite de requisições excedido. Tente novamente em instantes."}
    )


# Handler customizado para 404 mantendo a imersão Retrô & Neo-Brutalist
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        db = SessionLocal()
        try:
            visits = get_site_visits(db)
            current_user = get_current_user_optional(request, db)
        finally:
            db.close()
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            context={
                "total_visits": visits,
                "current_user": current_user
            },
            status_code=404
        )
    return JSONResponse(
        status_code=404,
        content={"detail": "Recurso não encontrado"}
    )


# Static and Uploads directory
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# --- HELPER FUNCTIONS, JINJA FILTERS & XSS SANITIZATION ---

def slugify(value: str) -> str:
    """Gera slugs amigáveis em português com fallback determinístico anti-colisão."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    clean_slug = re.sub(r"[-\s]+", "-", value)
    return clean_slug if clean_slug else f"post-{uuid.uuid4().hex[:8]}"


def clean_plain_text(text: str) -> str:
    """Sanitiza texto puro removendo tags HTML e mantendo caracteres como & e acentos sem entity-escaping desnecessário."""
    if not text:
        return ""
    sanitized = re.sub(r"<script\b[^>]*>([\s\S]*?)<\/script>", "", text, flags=re.IGNORECASE)
    cleaned = bleach.clean(sanitized.strip(), tags=[], strip=True)
    return html.unescape(cleaned)


def render_comment_content(text: str) -> str:
    """
    Renderiza o conteudo de comentarios com suporte seguro a hiperlinks:
      - Converte links Markdown [Texto](https://...) em <a href="...">
      - Converte URLs diretas (https://... ou http://...) em hiperlinks clicaveis
      - Bloqueia rigorosamente XSS e protocolos maliciosos (javascript:, data:, vbscript:)
    """
    if not text:
        return ""

    # 1. Escapa todo o texto contra HTML/XSS
    escaped = html.escape(text.strip())

    placeholders: dict[str, str] = {}

    def _store_anchor(href: str, label: str) -> str:
        key = f"__LINK_PLACEHOLDER_{len(placeholders)}__"
        placeholders[key] = (
            f'<a href="{href}" target="_blank" rel="noopener noreferrer nofollow" '
            f'class="comment-link">{label}</a>'
        )
        return key

    # 2. Links no formato Markdown: [Texto](https://exemplo.com)
    md_link_pattern = re.compile(r'\[([^\[\]\n]{1,120})\]\((https?:\/\/[^\s\)\"\'\<\>]+)\)', re.IGNORECASE)

    def _replace_md_link(match: re.Match) -> str:
        label = match.group(1)
        url = match.group(2)
        return _store_anchor(url, label)

    processed = md_link_pattern.sub(_replace_md_link, escaped)

    # 3. URLs diretas soltas no texto: https://... ou http://...
    bare_url_pattern = re.compile(r'(https?:\/\/[^\s\"\'\<\>]+)', re.IGNORECASE)

    def _replace_bare_url(match: re.Match) -> str:
        raw_url = match.group(1)
        trailing = ""
        while raw_url and raw_url[-1] in ".,;:!?)":
            trailing = raw_url[-1] + trailing
            raw_url = raw_url[:-1]
        if not raw_url or raw_url in ("http://", "https://"):
            return match.group(0)
        return _store_anchor(raw_url, raw_url) + trailing

    processed = bare_url_pattern.sub(_replace_bare_url, processed)

    for key, anchor_html in placeholders.items():
        processed = processed.replace(key, anchor_html)

    return processed


# Configuração rígida de tags e atributos permitidos para sanitização contra XSS
ALLOWED_TAGS = [
    "a", "abbr", "acronym", "b", "blockquote", "code", "em", "i", "li", "ol",
    "strong", "ul", "p", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "table",
    "thead", "tbody", "tr", "th", "td", "img", "hr", "br", "span", "div", "iframe"
]
ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "data-video-id"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "loading", "width", "height"],
    "code": ["class"],
    "iframe": ["src", "width", "height", "frameborder", "allow", "allowfullscreen", "title", "loading"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def render_markdown(text: str) -> str:
    """Renderiza Markdown e sanitiza com Bleach para imunizar a aplicação contra XSS."""
    if not text:
        return ""
    # Processa links de vídeo do YouTube e hiperlinks formatados antes do parser
    processed_text = process_media_links(text)
    # Expurga qualquer bloco <script> e seu conteúdo antes do processamento
    sanitized_input = re.sub(r"<script\b[^>]*>([\s\S]*?)<\/script>", "", processed_text, flags=re.IGNORECASE)
    raw_html = markdown.markdown(
        sanitized_input,
        extensions=["extra", "fenced_code", "tables", "nl2br", "sane_lists"]
    )
    cleaned_html = bleach.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True
    )
    return cleaned_html


def render_post_media(media_url: Optional[str], title: str = "", slug: str = "") -> str:
    """Renderiza capa da publicação: card de YouTube se for vídeo ou tag <img> se for imagem."""
    if not media_url:
        return ""
    yt_id = extract_youtube_id(media_url)
    if yt_id:
        return render_youtube_card(yt_id, media_url)
    safe_src = html.escape(media_url)
    safe_title = html.escape(title)
    if slug:
        return f'<a href="/post/{html.escape(slug)}"><img src="{safe_src}" alt="{safe_title}" class="post-media-cover" loading="lazy"></a>'
    return f'<img src="{safe_src}" alt="{safe_title}" class="post-media-cover" loading="lazy">'


def get_first_youtube_id(content: Optional[str]) -> Optional[str]:
    """Extrai o primeiro ID de vídeo do YouTube presente no conteúdo, caso exista."""
    if not content:
        return None
    return extract_youtube_id(content)


def format_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ""
    return value.strftime("%d/%m/%Y às %H:%M")


def format_odometer(value: int) -> list[str]:
    """Retorna os dígitos para o odômetro retrô no rodapé (6 dígitos fixos)."""
    s = f"{value:06d}"
    return list(s)


templates.env.filters["markdown"] = render_markdown
templates.env.filters["render_comment"] = render_comment_content
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_odometer"] = format_odometer
templates.env.filters["render_media"] = render_post_media
templates.env.filters["render_youtube_card"] = render_youtube_card
templates.env.filters["extract_youtube_id"] = extract_youtube_id
templates.env.filters["get_first_youtube_id"] = get_first_youtube_id
templates.env.globals["app_name"] = settings.APP_NAME
templates.env.globals["base_url"] = settings.BASE_URL


def get_site_visits(db: Session) -> int:
    stat = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
    if not stat:
        stat = SiteStat(key="total_visits", value=0)
        db.add(stat)
        db.commit()
    return stat.value


def increment_site_visits(db: Session) -> int:
    stat = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
    if not stat:
        stat = SiteStat(key="total_visits", value=0)
        db.add(stat)
    else:
        stat.value += 1
    db.commit()
    return stat.value


def _safe_redirect_path(path: Optional[str], default: str = "/diario") -> str:
    """Garante redirecionamento apenas para rotas internas, bloqueando Open Redirect (ex: //evil.com)."""
    if not path:
        return default
    cleaned = path.strip()
    if not cleaned.startswith("/") or cleaned.startswith("//") or cleaned.startswith("/\\"):
        return default
    return cleaned


def _get_comment_tokens_map(request: Request) -> dict[str, str]:
    raw = request.cookies.get(COMMENT_TOKENS_COOKIE)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def can_user_edit_comment(
    comment: Comment,
    current_user: Optional[User],
    token_map: dict[str, str],
    explicit_token: Optional[str] = None
) -> bool:
    """Verifica se o usuario logado ou visitante atual tem permissao para editar o comentario."""
    if current_user:
        if getattr(current_user, "role", "user") == "admin":
            return True
        if comment.user_id is not None and comment.user_id == current_user.id:
            return True

    if comment.edit_token:
        if explicit_token and explicit_token == comment.edit_token:
            return True
        cookie_tok = token_map.get(str(comment.id))
        if cookie_tok and cookie_tok == comment.edit_token:
            return True

    return False


# --- ROTAS PÚBLICAS ---

@app.get("/health")
def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    page: int = 1,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    current_user = get_current_user_optional(request, db)
    visits = increment_site_visits(db)

    per_page = 6
    offset = (page - 1) * per_page

    query = db.query(Post)
    if category:
        query = query.filter(Post.category == category)

    total_posts = query.count()
    total_pages = max(1, math.ceil(total_posts / per_page))
    posts = query.order_by(Post.created_at.desc()).offset(offset).limit(per_page).all()

    # Categorias distintas existentes
    categories_raw = db.query(Post.category).distinct().all()
    categories = [c[0] for c in categories_raw if c[0]]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "posts": posts,
            "page": page,
            "total_pages": total_pages,
            "current_category": category,
            "categories": categories,
            "total_visits": visits,
            "current_user": current_user,
            "flash_message": request.query_params.get("msg")
        }
    )


@app.get("/diario", response_class=HTMLResponse)
def diario_feed(
    request: Request,
    page: int = 1,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Alias direto para a rota do Diário de Bordo (/diario)."""
    return index(request=request, page=page, category=category, db=db)


@app.get("/post/{slug}", response_class=HTMLResponse)
def post_detail(
    request: Request,
    slug: str,
    db: Session = Depends(get_db)
):
    current_user = get_current_user_optional(request, db)
    visits = get_site_visits(db)

    post = db.query(Post).filter(Post.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")

    # Incrementa views
    post.views_count += 1
    db.commit()

    token_map = _get_comment_tokens_map(request)
    editable_comment_ids = {
        c.id for c in post.comments
        if can_user_edit_comment(c, current_user, token_map)
    }

    return templates.TemplateResponse(
        request=request,
        name="post.html",
        context={
            "post": post,
            "total_visits": visits,
            "current_user": current_user,
            "editable_comment_ids": editable_comment_ids,
            "flash_message": request.query_params.get("msg")
        }
    )


@app.post("/post/{slug}/comment")
@limiter.limit("10/minute")
def create_comment(
    request: Request,
    slug: str,
    background_tasks: BackgroundTasks,
    author_name: Optional[str] = Form(None),
    author_email: Optional[str] = Form(None),
    content: str = Form(""),
    notify_replies: Optional[bool] = Form(False),
    website_hp: Optional[str] = Form(None),  # Honeypot anti-spam
    db: Session = Depends(get_db)
):
    # Proteção Anti-Spam: Se honeypot foi preenchido por robô, descarta silenciosamente
    if website_hp:
        return RedirectResponse(url=f"/post/{slug}#comments", status_code=status.HTTP_303_SEE_OTHER)

    post = db.query(Post).filter(Post.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")

    current_user = get_current_user_optional(request, db)

    if current_user:
        resolved_name = clean_plain_text(author_name) if author_name and author_name.strip() else current_user.username
        resolved_email = (
            author_email.strip()
            if author_email and author_email.strip()
            else (current_user.email or f"{current_user.username}@refugio.local")
        )
    else:
        resolved_name = clean_plain_text(author_name or "")
        resolved_email = (author_email or "").strip()

    # Sanitiza conteúdo do comentário para evitar injeção de HTML bruto e limita tamanho
    cleaned_content = clean_plain_text(content)[:3000]
    resolved_name = resolved_name[:100]
    resolved_email = resolved_email[:150]

    if not resolved_name or not resolved_email or not cleaned_content:
        return RedirectResponse(
            url=f"/post/{slug}?msg=Campos+obrigatorios+nao+preenchidos#comment-box",
            status_code=status.HTTP_303_SEE_OTHER
        )

    edit_token = uuid.uuid4().hex
    comment = Comment(
        post_id=post.id,
        user_id=current_user.id if current_user else None,
        author_name=resolved_name,
        author_email=resolved_email,
        content=cleaned_content,
        notify_replies=bool(notify_replies),
        edit_token=edit_token,
        created_at=datetime.now()
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    # Dispara notificacoes In-App e Web Push em background
    background_tasks.add_task(notify_new_comment, post.id, comment.id)

    response = RedirectResponse(
        url=f"/post/{slug}?msg=Comentario+publicado+com+sucesso#comment-{comment.id}",
        status_code=status.HTTP_303_SEE_OTHER
    )
    token_map = _get_comment_tokens_map(request)
    token_map[str(comment.id)] = edit_token
    # Mantem apenas os ultimos 25 tokens no cookie para ser super leve
    if len(token_map) > 25:
        keys = list(token_map.keys())[-25:]
        token_map = {k: token_map[k] for k in keys}
    response.set_cookie(
        key=COMMENT_TOKENS_COOKIE,
        value=json.dumps(token_map),
        httponly=True,
        samesite="lax"
    )
    return response


@app.post("/post/{slug}/comment/{comment_id}/edit")
@limiter.limit("15/minute")
def edit_comment(
    request: Request,
    slug: str,
    comment_id: int,
    content: str = Form(...),
    edit_token: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    post = db.query(Post).filter(Post.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")

    comment = db.query(Comment).filter(Comment.id == comment_id, Comment.post_id == post.id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentário não encontrado")

    current_user = get_current_user_optional(request, db)
    token_map = _get_comment_tokens_map(request)

    if not can_user_edit_comment(comment, current_user, token_map, explicit_token=edit_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não possui permissão para editar este comentário."
        )

    cleaned_content = clean_plain_text(content)[:3000]
    if not cleaned_content or len(cleaned_content) < 2:
        return RedirectResponse(
            url=f"/post/{slug}?msg=Conteudo+do+comentario+invalido#comment-{comment.id}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    comment.content = cleaned_content
    comment.updated_at = datetime.now()
    db.commit()

    return RedirectResponse(
        url=f"/post/{slug}?msg=Comentario+atualizado+com+sucesso#comment-{comment.id}",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/lab", response_class=HTMLResponse)
def community_lab(
    request: Request,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    current_user = get_current_user_optional(request, db)
    visits = get_site_visits(db)

    # Top 5 mais clicados
    top_5 = (
        db.query(CommunitySubmission)
        .filter(CommunitySubmission.status == "approved")
        .order_by(CommunitySubmission.clicks_count.desc())
        .limit(5)
        .all()
    )

    # Todos os projetos aprovados
    query = db.query(CommunitySubmission).filter(CommunitySubmission.status == "approved")
    if category:
        query = query.filter(CommunitySubmission.category == category)

    submissions = query.order_by(CommunitySubmission.created_at.desc()).all()

    categories_raw = (
        db.query(CommunitySubmission.category)
        .filter(CommunitySubmission.status == "approved")
        .distinct()
        .all()
    )
    categories = [c[0] for c in categories_raw if c[0]]

    return templates.TemplateResponse(
        request=request,
        name="lab.html",
        context={
            "top_5": top_5,
            "submissions": submissions,
            "categories": categories,
            "current_category": category,
            "total_visits": visits,
            "current_user": current_user,
            "submitted": request.query_params.get("submitted") == "true"
        }
    )


@app.post("/lab/submit")
@limiter.limit("5/minute")
def submit_lab_project(
    request: Request,
    author_name: str = Form(...),
    author_email: str = Form(...),
    github_link: str = Form(...),
    title: str = Form(...),
    category: str = Form("Scripts Úteis"),
    description: str = Form(...),
    image_url: Optional[str] = Form(None),
    website_hp: Optional[str] = Form(None),  # Honeypot
    db: Session = Depends(get_db)
):
    if website_hp:
        return RedirectResponse(url="/lab?submitted=true", status_code=status.HTTP_303_SEE_OTHER)

    clean_github = github_link.strip()
    # Validação estrita de URL para impedir XSS com javascript: ou esquemas inseguros
    url_pattern = re.compile(r"^https?:\/\/[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(\/[^\s]*)?$", re.IGNORECASE)
    if not url_pattern.match(clean_github):
        return RedirectResponse(
            url="/lab?submitted=false&msg=Link+do+repositorio+invalido.+Deve+iniciar+com+https://",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Sanitização de entradas da comunidade
    author_name = clean_plain_text(author_name)
    title = clean_plain_text(title)
    category = clean_plain_text(category)
    description = clean_plain_text(description)

    sub = CommunitySubmission(
        author_name=author_name,
        author_email=author_email.strip(),
        github_link=clean_github,
        title=title,
        category=category,
        description=description,
        image_url=image_url.strip() if image_url else None,
        status="pending",
        clicks_count=0,
        created_at=datetime.now()
    )
    db.add(sub)
    db.commit()

    return RedirectResponse(url="/lab?submitted=true", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/lab/redirect/{submission_id}")
@limiter.limit("30/minute")
def redirect_lab_submission(
    request: Request,
    submission_id: int,
    db: Session = Depends(get_db)
):
    """Incrementa contagem de cliques e redireciona para o link do repositório."""
    sub = db.query(CommunitySubmission).filter(CommunitySubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    sub.clicks_count += 1
    db.commit()

    target_url = sub.github_link
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = f"https://{target_url}"

    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/about", response_class=HTMLResponse)
def about(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    visits = get_site_visits(db)

    return templates.TemplateResponse(
        request=request,
        name="about.html",
        context={
            "total_visits": visits,
            "current_user": current_user
        }
    )


# --- RÁDIO PIRATA BY YOUTUBE (MÚSICAS DE PROTESTO) ---

@app.get("/radio", response_class=HTMLResponse)
def pirate_radio_page(
    request: Request,
    db: Session = Depends(get_db)
):
    current_user = get_current_user_optional(request, db)
    visits = increment_site_visits(db)
    tracks = (
        db.query(RadioTrack)
        .filter(RadioTrack.is_active == True)
        .order_by(RadioTrack.id.asc())
        .all()
    )
    tracks_json = [
        {
            "id": t.id,
            "title": t.title,
            "artist": t.artist,
            "country": t.country,
            "genre": t.genre,
            "youtube_id": t.youtube_id,
            "youtube_url": t.youtube_url,
            "description": t.description or ""
        }
        for t in tracks
    ]

    return templates.TemplateResponse(
        request=request,
        name="radio.html",
        context={
            "tracks": tracks,
            "tracks_json": json.dumps(tracks_json, ensure_ascii=False),
            "total_visits": visits,
            "current_user": current_user
        }
    )


@app.get("/api/radio/playlist")
def api_radio_playlist(db: Session = Depends(get_db)):
    tracks = (
        db.query(RadioTrack)
        .filter(RadioTrack.is_active == True)
        .order_by(RadioTrack.id.asc())
        .all()
    )
    return {
        "station": "Rádio Pirata // O Refúgio (Vozes de Protesto)",
        "total": len(tracks),
        "tracks": [
            {
                "id": t.id,
                "title": t.title,
                "artist": t.artist,
                "country": t.country,
                "genre": t.genre,
                "youtube_id": t.youtube_id,
                "youtube_url": t.youtube_url,
                "description": t.description or ""
            }
            for t in tracks
        ]
    }


# --- AUTENTICAÇÃO E CADASTRO DE USUÁRIOS ---

@app.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next: Optional[str] = "/admin",
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    current_user = get_current_user_optional(request, db)
    if current_user:
        dest = "/admin" if current_user.is_admin else "/diario"
        return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)

    visits = get_site_visits(db)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "next": next,
            "error": error,
            "total_visits": visits,
            "current_user": None
        }
    )


@app.post("/login")
@limiter.limit("5/minute")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form("/admin"),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "next": next,
                "error": "Credenciais incorretas. Acesso negado.",
                "total_visits": get_site_visits(db),
                "current_user": None
            },
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    # Cria sessão com cookie assinado efêmero (Session Cookie puro)
    token = create_session_token(user.username)
    default_dest = "/admin" if user.is_admin else "/diario"
    target = _safe_redirect_path(next, default=default_dest)
    if not user.is_admin and target.startswith("/admin"):
        target = "/diario"

    response = RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=None,  # Session cookie puro: morre ao fechar o navegador/aba
        expires=None,
        samesite="lax",
        secure=False  # True em prod com HTTPS
    )
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page(
    request: Request,
    next: Optional[str] = "/diario",
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    current_user = get_current_user_optional(request, db)
    if current_user:
        return RedirectResponse(url="/diario", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "next": next,
            "error": error,
            "total_visits": get_site_visits(db),
            "current_user": None
        }
    )


@app.post("/register")
@limiter.limit("5/minute")
def register_post(
    request: Request,
    username: str = Form(...),
    email: Optional[str] = Form(None),
    password: str = Form(...),
    confirm_password: str = Form(...),
    next: Optional[str] = Form("/diario"),
    website_hp: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    if website_hp:
        return RedirectResponse(url="/diario", status_code=status.HTTP_303_SEE_OTHER)

    clean_username = clean_plain_text(username).strip()
    clean_email = email.strip().lower() if email and email.strip() else None
    visits = get_site_visits(db)

    if not clean_username or len(clean_username) < 3 or len(clean_username) > 30:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "next": next,
                "error": "Nome de usuário inválido (deve ter entre 3 e 30 caracteres).",
                "total_visits": visits,
                "current_user": None
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if not re.match(r"^[a-zA-Z0-9_-]+$", clean_username):
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "next": next,
                "error": "Use apenas letras, números, hífen (-) ou underline (_).",
                "total_visits": visits,
                "current_user": None
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if len(password) < 6:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "next": next,
                "error": "A senha deve possuir no mínimo 6 caracteres.",
                "total_visits": visits,
                "current_user": None
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "next": next,
                "error": "As senhas informadas não conferem.",
                "total_visits": visits,
                "current_user": None
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    existing = db.query(User).filter(User.username == clean_username).first()
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "next": next,
                "error": f"O identificador '{clean_username}' já está em uso.",
                "total_visits": visits,
                "current_user": None
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if clean_email:
        existing_email = db.query(User).filter(User.email == clean_email).first()
        if existing_email:
            return templates.TemplateResponse(
                request=request,
                name="register.html",
                context={
                    "next": next,
                    "error": "Este endereço de e-mail já está vinculado a outra conta.",
                    "total_visits": visits,
                    "current_user": None
                },
                status_code=status.HTTP_400_BAD_REQUEST
            )

    new_user = User(
        username=clean_username,
        email=clean_email,
        password_hash=hash_password(password),
        role="user",
        created_at=datetime.now()
    )
    db.add(new_user)
    db.commit()

    token = create_session_token(new_user.username)
    safe_next = _safe_redirect_path(next, default="/diario")
    target = safe_next if not safe_next.startswith("/admin") else "/diario"
    response = RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=None,
        expires=None,
        samesite="lax",
        secure=False
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return response


# --- CENTRAL DE ALERTAS IN-APP (NOTIFICAÇÕES DE USUÁRIOS & FÓRUNS) ---

@app.get("/notifications", response_class=HTMLResponse)
def user_notifications_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_login)
):
    visits = get_site_visits(db)
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    unread_count = sum(1 for n in notifications if not n.is_read)

    return templates.TemplateResponse(
        request=request,
        name="notifications.html",
        context={
            "notifications": notifications,
            "unread_count": unread_count,
            "total_visits": visits,
            "current_user": current_user,
            "flash_message": request.query_params.get("msg")
        }
    )


@app.post("/notifications/{notif_id}/read")
def mark_notification_read(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_login)
):
    notif = (
        db.query(Notification)
        .filter(Notification.id == notif_id, Notification.user_id == current_user.id)
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")

    notif.is_read = True
    db.commit()

    target = _safe_redirect_path(notif.target_url, default="/notifications")
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_login)
):
    (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)
        .update({"is_read": True}, synchronize_session=False)
    )
    db.commit()
    return RedirectResponse(
        url="/notifications?msg=Todos+os+alertas+foram+marcados+como+lidos.",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/api/notifications/unread")
def api_unread_notifications(
    request: Request,
    db: Session = Depends(get_db)
):
    current_user = get_current_user_optional(request, db)
    if not current_user:
        return {"authenticated": False, "unread_count": 0, "items": []}

    unread_items = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )
    return {
        "authenticated": True,
        "unread_count": getattr(current_user, "unread_notifications_count", len(unread_items)),
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "target_url": n.target_url,
                "created_at": format_datetime(n.created_at)
            }
            for n in unread_items
        ]
    }


# --- ÁREA ADMINISTRATIVA PROTEGIDA ---

DEFAULT_POST_CATEGORIES = [
    "Diário de Bordo",
    "Dev & Tech",
    "Mangás & Cultura",
    "IndieWeb & Minimalismo",
    "Hacking & Terminal",
    "Reflexões & Carreira",
    "Geral"
]


def get_available_post_categories(db: Session) -> list[str]:
    """Retorna lista ordenada e consolidada de categorias disponíveis para posts."""
    db_cats = [c[0].strip() for c in db.query(Post.category).distinct().all() if c[0] and c[0].strip()]
    merged = list(dict.fromkeys(DEFAULT_POST_CATEGORIES + db_cats))
    return sorted(merged)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    tab: str = "posts",
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    visits = get_site_visits(db)
    posts = db.query(Post).order_by(Post.created_at.desc()).all()
    pending_submissions = (
        db.query(CommunitySubmission)
        .filter(CommunitySubmission.status == "pending")
        .order_by(CommunitySubmission.created_at.desc())
        .all()
    )
    approved_submissions = (
        db.query(CommunitySubmission)
        .filter(CommunitySubmission.status == "approved")
        .order_by(CommunitySubmission.created_at.desc())
        .all()
    )
    rejected_submissions = (
        db.query(CommunitySubmission)
        .filter(CommunitySubmission.status == "rejected")
        .order_by(CommunitySubmission.created_at.desc())
        .all()
    )
    recent_comments = db.query(Comment).order_by(Comment.created_at.desc()).limit(30).all()
    operators = db.query(User).filter(User.role == "admin").order_by(User.created_at.asc()).all()
    community_users = db.query(User).filter(User.role == "user").order_by(User.created_at.desc()).all()
    radio_tracks = db.query(RadioTrack).order_by(RadioTrack.id.asc()).all()

    push_subscribers_count = db.query(PushSubscription).count()
    push_logs = db.query(PushLog).order_by(PushLog.sent_at.desc()).limit(15).all()

    # Categorias consolidadas para o dropdown de criação de posts
    available_categories = get_available_post_categories(db)

    # Informações do snapshot de backup JSON
    backup_exists = os.path.exists(DEFAULT_BACKUP_JSON_PATH)
    backup_meta = None
    if backup_exists:
        try:
            with open(DEFAULT_BACKUP_JSON_PATH, "r", encoding="utf-8") as bf:
                b_data = json.load(bf)
                backup_meta = b_data.get("metadata", {})
        except Exception:
            backup_meta = None

    # Métricas gerais
    stats = {
        "total_posts": len(posts),
        "total_views": db.query(func.coalesce(func.sum(Post.views_count), 0)).scalar(),
        "pending_submissions": len(pending_submissions),
        "approved_submissions": len(approved_submissions),
        "total_comments": db.query(Comment).count(),
        "total_visits": visits,
        "push_subscribers": push_subscribers_count,
        "radio_tracks": len(radio_tracks)
    }

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "admin_user": admin_user,
            "current_user": admin_user,
            "posts": posts,
            "categories": available_categories,
            "pending_submissions": pending_submissions,
            "approved_submissions": approved_submissions,
            "rejected_submissions": rejected_submissions,
            "comments": recent_comments,
            "operators": operators,
            "community_users": community_users,
            "radio_tracks": radio_tracks,
            "backup_exists": backup_exists,
            "backup_meta": backup_meta,
            "stats": stats,
            "active_tab": tab,
            "total_visits": visits,
            "flash_message": request.query_params.get("msg"),
            "push_logs": push_logs,
            "vapid_public_key": get_vapid_public_key()
        }
    )


@app.post("/admin/posts/new")
async def admin_create_post(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    content: str = Form(...),
    category: str = Form("Geral"),
    category_custom: Optional[str] = Form(None),
    media_url: Optional[str] = Form(None),
    media_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    title = clean_plain_text(title)
    content = content.strip()

    # Suporte a dropdown com opção de criar nova categoria customizada
    if category == "__custom__" and category_custom:
        category = clean_plain_text(category_custom)
    else:
        category = clean_plain_text(category)

    if not category or category == "__custom__":
        category = "Geral"

    final_media_url = media_url.strip() if media_url else None

    # Processamento de arquivo local seguro com validação de magic bytes
    if media_file and media_file.filename:
        file_bytes = await media_file.read()
        is_valid, err_msg = validate_image_file(media_file.filename, file_bytes)
        if not is_valid:
            return RedirectResponse(
                url=f"/admin?tab=new_post&msg={err_msg}",
                status_code=status.HTTP_303_SEE_OTHER
            )
        safe_name = generate_safe_filename(media_file.filename)
        save_path = os.path.join("static", "uploads", safe_name)
        with open(save_path, "wb") as f:
            f.write(file_bytes)
        final_media_url = f"/static/uploads/{safe_name}"

    # Gera slug único
    base_slug = slugify(title)
    slug = base_slug
    counter = 1
    while db.query(Post).filter(Post.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    post = Post(
        title=title,
        slug=slug,
        content=content,
        category=category,
        media_url=final_media_url,
        views_count=0,
        author_id=admin_user.id,
        created_at=datetime.now()
    )
    db.add(post)
    db.commit()

    # Disparo assincrono em segundo plano para inscritos no Web Push
    background_tasks.add_task(send_post_push_notification, post.id)

    return RedirectResponse(
        url="/admin?tab=posts&msg=Post+publicado+com+sucesso",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/admin/posts/{post_id}/edit", response_class=HTMLResponse)
def admin_edit_post_page(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")

    available_categories = get_available_post_categories(db)

    return templates.TemplateResponse(
        request=request,
        name="admin_edit.html",
        context={
            "admin_user": admin_user,
            "current_user": admin_user,
            "post": post,
            "categories": available_categories,
            "total_visits": get_site_visits(db)
        }
    )


@app.post("/admin/posts/{post_id}/edit")
async def admin_edit_post(
    post_id: int,
    title: str = Form(...),
    content: str = Form(...),
    category: str = Form("Geral"),
    category_custom: Optional[str] = Form(None),
    media_url: Optional[str] = Form(None),
    media_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")

    post.title = clean_plain_text(title)
    post.content = content.strip()

    if category == "__custom__" and category_custom:
        post.category = clean_plain_text(category_custom)
    else:
        post.category = clean_plain_text(category)

    if not post.category or post.category == "__custom__":
        post.category = "Geral"

    if media_url:
        post.media_url = media_url.strip()

    if media_file and media_file.filename:
        file_bytes = await media_file.read()
        is_valid, err_msg = validate_image_file(media_file.filename, file_bytes)
        if is_valid:
            safe_name = generate_safe_filename(media_file.filename)
            save_path = os.path.join("static", "uploads", safe_name)
            with open(save_path, "wb") as f:
                f.write(file_bytes)
            post.media_url = f"/static/uploads/{safe_name}"

    post.updated_at = datetime.now()
    db.commit()

    return RedirectResponse(
        url="/admin?tab=posts&msg=Post+atualizado+com+sucesso",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/posts/{post_id}/delete")
def admin_delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if post:
        db.delete(post)
        db.commit()
    return RedirectResponse(
        url="/admin?tab=posts&msg=Post+removido",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/submissions/{submission_id}/status")
def admin_update_submission_status(
    submission_id: int,
    status_value: str = Form(...),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    sub = db.query(CommunitySubmission).filter(CommunitySubmission.id == submission_id).first()
    if sub and status_value in ["approved", "rejected", "pending"]:
        sub.status = status_value
        db.commit()
    return RedirectResponse(
        url=f"/admin?tab=submissions&msg=Status+do+projeto+atualizado+para+{status_value}",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/submissions/{submission_id}/delete")
def admin_delete_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    sub = db.query(CommunitySubmission).filter(CommunitySubmission.id == submission_id).first()
    if sub:
        db.delete(sub)
        db.commit()
    return RedirectResponse(
        url="/admin?tab=submissions&msg=Projeto+removido",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/comments/{comment_id}/delete")
def admin_delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment:
        db.delete(comment)
        db.commit()
    return RedirectResponse(
        url="/admin?tab=comments&msg=Comentario+removido",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/operators/new")
def admin_create_operator(
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    clean_username = clean_plain_text(username).strip()
    if not clean_username or len(clean_username) < 3 or len(clean_username) > 30:
        return RedirectResponse(
            url="/admin?tab=operators&msg=Nome+de+usuario+invalido.+Deve+ter+entre+3+e+30+caracteres.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    if not re.match(r"^[a-zA-Z0-9_-]+$", clean_username):
        return RedirectResponse(
            url="/admin?tab=operators&msg=Nome+de+usuario+deve+conter+apenas+letras,+numeros,+hifen+ou+underline.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    if len(password) < 6:
        return RedirectResponse(
            url="/admin?tab=operators&msg=A+senha+deve+possuir+no+minimo+6+caracteres.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    if password != confirm_password:
        return RedirectResponse(
            url="/admin?tab=operators&msg=As+senhas+informadas+nao+conferem.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    existing = db.query(User).filter(User.username == clean_username).first()
    if existing:
        return RedirectResponse(
            url=f"/admin?tab=operators&msg=O+identificador+'{clean_username}'+ja+esta+em+uso+no+sistema.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    new_operator = User(
        username=clean_username,
        password_hash=hash_password(password),
        role="admin",
        created_at=datetime.now()
    )
    db.add(new_operator)
    db.commit()

    return RedirectResponse(
        url=f"/admin?tab=operators&msg=Novo+operador+'{clean_username}'+forjado+com+sucesso!",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/operators/{user_id}/delete")
def admin_delete_operator(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    if admin_user.id == user_id:
        return RedirectResponse(
            url="/admin?tab=operators&msg=Acao+bloqueada:+voce+nao+pode+revogar+o+proprio+acesso.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    total_operators = db.query(User).filter(User.role == "admin").count()
    if total_operators <= 1:
        return RedirectResponse(
            url="/admin?tab=operators&msg=Acao+bloqueada:+o+sistema+precisa+manter+ao+menos+um+operador+ativo.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    op_to_delete = db.query(User).filter(User.id == user_id).first()
    if op_to_delete:
        target_name = op_to_delete.username
        db.delete(op_to_delete)
        db.commit()
        return RedirectResponse(
            url=f"/admin?tab=operators&msg=Acesso+do+operador+'{target_name}'+revogado+com+sucesso.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    return RedirectResponse(
        url="/admin?tab=operators&msg=Operador+nao+encontrado.",
        status_code=status.HTTP_303_SEE_OTHER
    )


# --- ROTAS ADMIN: RÁDIO PIRATA ---

@app.post("/admin/radio/new")
def admin_add_radio_track(
    title: str = Form(...),
    artist: str = Form(...),
    country: str = Form("América Latina"),
    genre: str = Form("Protesto"),
    youtube_url: str = Form(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    clean_title = clean_plain_text(title)
    clean_artist = clean_plain_text(artist)
    clean_country = clean_plain_text(country) or "América Latina"
    clean_genre = clean_plain_text(genre) or "Protesto"
    clean_desc = clean_plain_text(description or "")

    yt_id = extract_youtube_id(youtube_url)
    if not yt_id and re.match(r"^[a-zA-Z0-9_-]{11}$", youtube_url.strip()):
        yt_id = youtube_url.strip()

    if not yt_id:
        return RedirectResponse(
            url="/admin?tab=radio&msg=Link+do+YouTube+invalido.+Informe+uma+URL+valida+do+YouTube.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    track = RadioTrack(
        title=clean_title,
        artist=clean_artist,
        country=clean_country,
        genre=clean_genre,
        youtube_id=yt_id,
        youtube_url=f"https://www.youtube.com/watch?v={yt_id}",
        description=clean_desc,
        is_active=True,
        created_at=datetime.now()
    )
    db.add(track)
    db.commit()

    return RedirectResponse(
        url="/admin?tab=radio&msg=Faixa+adicionada+na+Radio+Pirata+com+sucesso!",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/radio/{track_id}/toggle")
def admin_toggle_radio_track(
    track_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    track = db.query(RadioTrack).filter(RadioTrack.id == track_id).first()
    if track:
        track.is_active = not track.is_active
        db.commit()
    return RedirectResponse(
        url="/admin?tab=radio&msg=Status+da+faixa+atualizado.",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/radio/{track_id}/delete")
def admin_delete_radio_track(
    track_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    track = db.query(RadioTrack).filter(RadioTrack.id == track_id).first()
    if track:
        db.delete(track)
        db.commit()
    return RedirectResponse(
        url="/admin?tab=radio&msg=Faixa+removida+da+Radio+Pirata.",
        status_code=status.HTTP_303_SEE_OTHER
    )


# --- ROTAS ADMIN: BACKUP JSON & GIT PUSH ---

@app.post("/admin/backup/export")
def admin_backup_export(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    payload = export_backup_to_json(db=db)
    counts = payload["metadata"]["counts"]
    return RedirectResponse(
        url=f"/admin?tab=backup&msg=Snapshot+JSON+gerado+com+sucesso+({counts['posts']}+posts,+{counts['comments']}+comentarios).",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/admin/backup/download")
def admin_backup_download(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    export_backup_to_json(db=db, output_path=DEFAULT_BACKUP_JSON_PATH)
    return FileResponse(
        DEFAULT_BACKUP_JSON_PATH,
        media_type="application/json",
        filename="refugio_snapshot.json"
    )


@app.post("/admin/backup/git-push")
def admin_backup_git_push(
    admin_user: User = Depends(require_admin)
):
    res = git_commit_and_push_backup()
    msg = res.get("message", "Operacao concluida.").replace(" ", "+")
    return RedirectResponse(
        url=f"/admin?tab=backup&msg={msg}",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/backup/restore")
async def admin_backup_restore(
    backup_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    try:
        if backup_file and backup_file.filename:
            raw_bytes = await backup_file.read()
            payload = json.loads(raw_bytes.decode("utf-8"))
            restored = import_backup_from_json(payload, db=db)
        elif os.path.exists(DEFAULT_BACKUP_JSON_PATH):
            restored = import_backup_from_json(DEFAULT_BACKUP_JSON_PATH, db=db)
        else:
            return RedirectResponse(
                url="/admin?tab=backup&msg=Nenhum+arquivo+de+backup+encontrado+para+restaurar.",
                status_code=status.HTTP_303_SEE_OTHER
            )
        return RedirectResponse(
            url=f"/admin?tab=backup&msg=Backup+restaurado+com+sucesso!+({restored['posts']}+posts+verificados).",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin?tab=backup&msg=Erro+ao+restaurar+backup:+{str(e)[:80]}",
            status_code=status.HTTP_303_SEE_OTHER
        )


# --- HUB DINÂMICO DE NOTÍCIAS (RADAR) ---

@app.get("/radar", response_class=HTMLResponse)
def news_radar(
    request: Request,
    db: Session = Depends(get_db)
):
    current_user = get_current_user_optional(request, db)
    visits = increment_site_visits(db)
    news_data = get_news_hub_data()

    return templates.TemplateResponse(
        request=request,
        name="radar.html",
        context={
            "news": news_data,
            "total_visits": visits,
            "current_user": current_user
        }
    )


# --- ROTAS DE WEB PUSH NOTIFICATIONS ---

@app.get("/favicon.ico")
def get_favicon():
    """Entrega o favicon do blog."""
    return FileResponse("static/favicon.ico", media_type="image/x-icon")


@app.get("/sw.js")
def get_service_worker():
    """Entrega o Service Worker com escopo raiz para o Web Push."""
    sw_path = os.path.join("static", "sw.js")
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )


@app.get("/manifest.json")
def get_manifest():
    """Entrega o Web App Manifest para PWA standalone no celular."""
    manifest_path = os.path.join("static", "manifest.json")
    return FileResponse(
        manifest_path,
        media_type="application/manifest+json"
    )


@app.get("/api/push/vapid-public-key")
def get_push_vapid_key():
    """Retorna a chave publica VAPID para os navegadores realizarem a inscricao."""
    return {"public_key": get_vapid_public_key()}


@app.post("/api/push/subscribe")
def api_push_subscribe(
    request: Request,
    payload: PushSubscriptionCreate,
    db: Session = Depends(get_db)
):
    """Registra ou atualiza a assinatura de notificacoes do leitor."""
    current_user = get_current_user_optional(request, db)
    sub = register_subscription(
        db=db,
        endpoint=payload.endpoint,
        p256dh=payload.p256dh,
        auth=payload.auth,
        user_agent=payload.user_agent,
        user_id=current_user.id if current_user else None
    )
    return {"status": "ok", "id": sub.id}


@app.post("/api/push/unsubscribe")
def api_push_unsubscribe(
    payload: PushUnsubscribeRequest,
    db: Session = Depends(get_db)
):
    """Remove a assinatura de notificacoes do leitor."""
    removed = unregister_subscription(db=db, endpoint=payload.endpoint)
    return {"status": "ok", "removed": removed}


@app.post("/admin/push/broadcast")
async def admin_push_broadcast(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    body: str = Form(...),
    target_url: str = Form("/"),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Dispara um comunicado ou teste manual para todos os navegadores inscritos."""
    clean_title = clean_plain_text(title)
    clean_body = clean_plain_text(body)
    clean_url = _safe_redirect_path(target_url, default="/")

    background_tasks.add_task(
        broadcast_notification,
        clean_title,
        clean_body,
        clean_url,
        "manual"
    )

    return RedirectResponse(
        url="/admin?tab=push&msg=Disparo+de+notificacao+iniciado+em+segundo+plano.",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/push/digest-now")
async def admin_push_digest_now(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Dispara imediatamente o resumo do Radar para todos os assinantes ignorando o limite de 24h."""
    background_tasks.add_task(check_and_send_daily_news_digest, force=True)

    return RedirectResponse(
        url="/admin?tab=push&msg=Resumo+do+Radar+disparado+com+sucesso+para+os+inscritos.",
        status_code=status.HTTP_303_SEE_OTHER
    )
