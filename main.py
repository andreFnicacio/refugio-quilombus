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
from database import get_db, SessionLocal, engine
from models import User, Post, CommunitySubmission, Comment, SiteStat
from auth import (
    require_admin,
    get_current_user_optional,
    verify_password,
    hash_password,
    create_session_token,
    validate_image_file,
    generate_safe_filename
)
from init_db import init_database
from news_service import get_news_hub_data


# Rate Limiter em memória (FinOps: zero overhead de Redis para instâncias locais/leves)
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialização automática do banco e seed anti-tela pelada
    init_database()
    yield
    # Checkpoint de saída para consolidar WAL no arquivo blog.db antes de reiniciar container
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
    author_name: str = Form(...),
    author_email: str = Form(...),
    content: str = Form(...),
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

    author_name = clean_plain_text(author_name)
    author_email = author_email.strip()
    # Sanitiza conteúdo do comentário para evitar injeção de HTML
    content = clean_plain_text(content)

    if not author_name or not author_email or not content:
        return RedirectResponse(
            url=f"/post/{slug}?msg=Campos+obrigatorios+nao+preenchidos#comment-box",
            status_code=status.HTTP_303_SEE_OTHER
        )

    comment = Comment(
        post_id=post.id,
        author_name=author_name,
        author_email=author_email,
        content=content,
        notify_replies=False,
        created_at=datetime.now()
    )
    db.add(comment)
    db.commit()

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

    # Cria sessão com cookie assinado efêmero (Session Cookie puro)
    token = create_session_token(user.username)
    target = next if (next and next.startswith("/")) else "/admin"
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


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return response


# --- ÁREA ADMINISTRATIVA PROTEGIDA ---

DEFAULT_POST_CATEGORIES = [
    "Saga dos 28",
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
    operators = db.query(User).order_by(User.created_at.asc()).all()

    # Categorias consolidadas para o dropdown de criação de posts
    available_categories = get_available_post_categories(db)

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
            "categories": available_categories,
            "pending_submissions": pending_submissions,
            "approved_submissions": approved_submissions,
            "rejected_submissions": rejected_submissions,
            "comments": recent_comments,
            "operators": operators,
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

    total_operators = db.query(User).count()
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

