import os
import re
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
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import markdown
import bleach
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from database import get_db, SessionLocal
from models import User, Post, CommunitySubmission, Comment, SiteStat
from auth import (
    require_admin,
    get_current_user_optional,
    verify_password,
    create_session_token,
    validate_image_file,
    generate_safe_filename
)
from init_db import init_database
from email_service import (
    notify_new_comment_in_background,
    notify_admin_new_submission_in_background
)


# Rate Limiter em memória (FinOps: zero overhead de Redis para instâncias locais/leves)
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialização automática do banco e seed anti-tela pelada
    init_database()
    yield


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


# Configuração rígida de tags e atributos permitidos para sanitização contra XSS
ALLOWED_TAGS = [
    "a", "abbr", "acronym", "b", "blockquote", "code", "em", "i", "li", "ol",
    "strong", "ul", "p", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "table",
    "thead", "tbody", "tr", "th", "td", "img", "hr", "br", "span", "div"
]
ALLOWED_ATTRIBUTES = {
    "*": ["class", "id"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "loading", "width", "height"],
    "code": ["class"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def render_markdown(text: str) -> str:
    """Renderiza Markdown e sanitiza com Bleach para imunizar a aplicação contra XSS."""
    if not text:
        return ""
    # Expurga qualquer bloco <script> e seu conteúdo antes do processamento
    sanitized_input = re.sub(r"<script\b[^>]*>([\s\S]*?)<\/script>", "", text, flags=re.IGNORECASE)
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


def format_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ""
    return value.strftime("%d/%m/%Y às %H:%M")


def format_odometer(value: int) -> list[str]:
    """Retorna os dígitos para o odômetro retrô no rodapé (6 dígitos fixos)."""
    s = f"{value:06d}"
    return list(s)


templates.env.filters["markdown"] = render_markdown
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_odometer"] = format_odometer
templates.env.globals["app_name"] = settings.APP_NAME
templates.env.globals["base_url"] = settings.BASE_URL


def get_site_visits(db: Session) -> int:
    stat = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
    if not stat:
        stat = SiteStat(key="total_visits", value=1337)
        db.add(stat)
        db.commit()
    return stat.value


def increment_site_visits(db: Session) -> int:
    stat = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
    if not stat:
        stat = SiteStat(key="total_visits", value=1337)
        db.add(stat)
    else:
        stat.value += 1
    db.commit()
    return stat.value


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
            "current_user": current_user
        }
    )


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

    return templates.TemplateResponse(
        request=request,
        name="post.html",
        context={
            "post": post,
            "total_visits": visits,
            "current_user": current_user,
            "flash_message": request.query_params.get("msg")
        }
    )


@app.post("/post/{slug}/comment")
@limiter.limit("10/minute")
def create_comment(
    request: Request,
    slug: str,
    background_tasks: BackgroundTasks,
    author_name: str = Form(...),
    author_email: str = Form(...),
    content: str = Form(...),
    notify_replies: bool = Form(False),
    website_hp: Optional[str] = Form(None),  # Honeypot anti-spam
    db: Session = Depends(get_db)
):
    # Proteção Anti-Spam: Se honeypot foi preenchido por robô, descarta silenciosamente
    if website_hp:
        return RedirectResponse(url=f"/post/{slug}#comments", status_code=status.HTTP_303_SEE_OTHER)

    post = db.query(Post).filter(Post.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")

    author_name = clean_plain_text(author_name)
    author_email = author_email.strip()
    # Sanitiza conteúdo do comentário para evitar injeção de HTML
    content = clean_plain_text(content)

    if not author_name or not author_email or not content:
        return RedirectResponse(
            url=f"/post/{slug}?msg=Campos+obrigatorios+nao+preenchidos#comment-box",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Identifica emails de pessoas que solicitaram notificação para este post
    subscriber_emails = [
        c.author_email for c in post.comments
        if c.notify_replies and c.author_email and c.author_email != author_email
    ]
    # Inclui o e-mail do admin para notificação se configurado e não for o autor do comentário
    if settings.ADMIN_EMAIL and settings.ADMIN_EMAIL != author_email:
        subscriber_emails.append(settings.ADMIN_EMAIL)

    # Remove duplicados
    subscriber_emails = list(set(subscriber_emails))

    comment = Comment(
        post_id=post.id,
        author_name=author_name,
        author_email=author_email,
        content=content,
        notify_replies=notify_replies,
        created_at=datetime.now()
    )
    db.add(comment)
    db.commit()

    # Dispara e-mail em background se houver inscritos
    if subscriber_emails:
        background_tasks.add_task(
            notify_new_comment_in_background,
            post_title=post.title,
            post_slug=post.slug,
            comment_author=author_name,
            comment_content=content,
            recipient_emails=subscriber_emails
        )

    return RedirectResponse(
        url=f"/post/{slug}?msg=Comentario+publicado+com+sucesso#comments",
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
    background_tasks: BackgroundTasks,
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

    # Dispara e-mail de alerta para o admin avaliar
    background_tasks.add_task(
        notify_admin_new_submission_in_background,
        submission_title=sub.title,
        author_name=sub.author_name,
        github_link=sub.github_link,
        category=sub.category
    )

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


# --- RSS FEED (INDIEWEB COMPLIANT) ---

@app.get("/feed.xml")
@app.get("/rss")
def rss_feed(db: Session = Depends(get_db)):
    posts = db.query(Post).order_by(Post.created_at.desc()).limit(20).all()
    items_xml = []
    for p in posts:
        pub_date = p.created_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
        post_url = f"{settings.BASE_URL}/post/{p.slug}"
        items_xml.append(f"""
        <item>
            <title><![CDATA[{p.title}]]></title>
            <link>{post_url}</link>
            <guid>{post_url}</guid>
            <pubDate>{pub_date}</pubDate>
            <category><![CDATA[{p.category}]]></category>
            <description><![CDATA[{p.content[:300]}...]]></description>
        </item>
        """)

    feed = f"""<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>{settings.APP_NAME}</title>
        <link>{settings.BASE_URL}</link>
        <description>Indie Blog &amp; Community Hub na estética Neo-Brutalist</description>
        <language>pt-br</language>
        <atom:link href="{settings.BASE_URL}/feed.xml" rel="self" type="application/rss+xml" />
        {''.join(items_xml)}
    </channel>
    </rss>
    """
    return Response(content=feed, media_type="application/xml")


# --- AUTENTICAÇÃO ---

@app.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next: Optional[str] = "/admin",
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    current_user = get_current_user_optional(request, db)
    if current_user:
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

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

    # Cria sessão com cookie assinado
    token = create_session_token(user.username)
    target = next if (next and next.startswith("/")) else "/admin"
    response = RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,  # 7 dias
        samesite="lax",
        secure=False  # True em prod com HTTPS
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return response


# --- ÁREA ADMINISTRATIVA PROTEGIDA ---

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

    # Métricas gerais
    stats = {
        "total_posts": len(posts),
        "total_views": db.query(func.coalesce(func.sum(Post.views_count), 0)).scalar(),
        "pending_submissions": len(pending_submissions),
        "approved_submissions": len(approved_submissions),
        "total_comments": db.query(Comment).count(),
        "total_visits": visits
    }

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "admin_user": admin_user,
            "current_user": admin_user,
            "posts": posts,
            "pending_submissions": pending_submissions,
            "approved_submissions": approved_submissions,
            "rejected_submissions": rejected_submissions,
            "comments": recent_comments,
            "stats": stats,
            "active_tab": tab,
            "total_visits": visits,
            "flash_message": request.query_params.get("msg")
        }
    )


@app.post("/admin/posts/new")
async def admin_create_post(
    title: str = Form(...),
    content: str = Form(...),
    category: str = Form("Geral"),
    media_url: Optional[str] = Form(None),
    media_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    title = clean_plain_text(title)
    content = content.strip()
    category = clean_plain_text(category)

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
        created_at=datetime.now()
    )
    db.add(post)
    db.commit()

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

    return templates.TemplateResponse(
        request=request,
        name="admin_edit.html",
        context={
            "admin_user": admin_user,
            "current_user": admin_user,
            "post": post,
            "total_visits": get_site_visits(db)
        }
    )


@app.post("/admin/posts/{post_id}/edit")
async def admin_edit_post(
    post_id: int,
    title: str = Form(...),
    content: str = Form(...),
    category: str = Form("Geral"),
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
    post.category = clean_plain_text(category)

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
