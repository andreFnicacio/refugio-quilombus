import pytest
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
from models import Post, CommunitySubmission, Comment, SiteStat
from config import settings


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "O Refúgio"


def test_homepage_and_odometer(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "O REFÚGIO" in response.text
    assert "DIÁRIO" in response.text
    assert "VISITAS" in response.text
    assert "Manifesto do Refúgio" in response.text


def test_post_detail_and_views_increment(client):
    db = SessionLocal()
    post = db.query(Post).filter(Post.slug == "manifesto-do-refugio-trincheiras-era-dos-algoritmos").first()
    initial_views = post.views_count
    db.close()

    response = client.get("/post/manifesto-do-refugio-trincheiras-era-dos-algoritmos")
    assert response.status_code == 200
    assert "Construindo Trincheiras na Era dos Algoritmos" in response.text

    # Verifica se incrementou views
    db = SessionLocal()
    post_updated = db.query(Post).filter(Post.slug == "manifesto-do-refugio-trincheiras-era-dos-algoritmos").first()
    assert post_updated.views_count == initial_views + 1
    db.close()


def test_comment_honeypot_blocking(client):
    db = SessionLocal()
    post = db.query(Post).first()
    initial_comments_count = len(post.comments)
    db.close()

    # Robô preenchendo campo honeypot
    bot_payload = {
        "author_name": "SpamBot 3000",
        "author_email": "bot@spam.com",
        "content": "Compre seguidores baratos agora mesmo!",
        "website_hp": "http://spam-link.ru"  # Honeypot ativado!
    }
    response = client.post(f"/post/{post.slug}/comment", data=bot_payload, follow_redirects=False)
    assert response.status_code == 303

    # Garante que NÃO foi salvo no banco
    db = SessionLocal()
    post_check = db.query(Post).filter(Post.id == post.id).first()
    assert len(post_check.comments) == initial_comments_count
    db.close()


def test_comment_legitimate_creation(client):
    db = SessionLocal()
    post = db.query(Post).first()
    db.close()

    user_payload = {
        "author_name": "DevGuerreiro",
        "author_email": "guerreiro@retro.io",
        "content": "Excelente reflexão sobre a cultura IndieWeb. Vida longa ao Refúgio!",
        "notify_replies": "true",
        "website_hp": ""  # Honeypot vazio
    }
    response = client.post(f"/post/{post.slug}/comment", data=user_payload, follow_redirects=True)
    assert response.status_code == 200
    assert "DevGuerreiro" in response.text


def test_community_lab_and_top5(client):
    response = client.get("/lab")
    assert response.status_code == 200
    assert "O LABORATÓRIO" in response.text
    assert "TOP 5 PROJETOS MAIS ACESSADOS" in response.text
    assert "Dungeon Crawler 16-bits" in response.text


def test_lab_submission_and_honeypot(client):
    import uuid
    unique_suffix = uuid.uuid4().hex[:6]
    test_title = f"NeoVim Cyberpunk Config {unique_suffix}"

    # 1. Envio com honeypot (Bot)
    bot_submission = {
        "author_name": "BotMalicioso",
        "author_email": "bot@bad.com",
        "github_link": "http://crypto-phishing.com",
        "title": f"Crypto Miner {unique_suffix}",
        "category": "Scripts Úteis",
        "description": "Minerador oculto...",
        "website_hp": "http://bot-site.com"
    }
    resp = client.post("/lab/submit", data=bot_submission, follow_redirects=False)
    assert resp.status_code == 303

    db = SessionLocal()
    bot_sub = db.query(CommunitySubmission).filter(CommunitySubmission.title == f"Crypto Miner {unique_suffix}").first()
    assert bot_sub is None
    db.close()

    # 2. Envio legítimo (Humano)
    human_submission = {
        "author_name": "CyberSamurai",
        "author_email": "samurai@cyber.io",
        "github_link": "https://github.com/cybersamurai/dotfiles",
        "title": test_title,
        "category": "Hacking & Terminal",
        "description": "Configuração minimalista em Lua com tema neon e navegação por teclado.",
        "website_hp": ""
    }
    resp = client.post("/lab/submit", data=human_submission, follow_redirects=False)
    assert resp.status_code == 303

    db = SessionLocal()
    human_sub = db.query(CommunitySubmission).filter(CommunitySubmission.title == test_title).first()
    assert human_sub is not None
    assert human_sub.status == "pending"
    db.close()


def test_lab_click_redirect(client):
    db = SessionLocal()
    sub = db.query(CommunitySubmission).filter(CommunitySubmission.status == "approved").first()
    initial_clicks = sub.clicks_count
    sub_id = sub.id
    target_link = sub.github_link
    db.close()

    resp = client.get(f"/lab/redirect/{sub_id}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == target_link

    db = SessionLocal()
    sub_after = db.query(CommunitySubmission).filter(CommunitySubmission.id == sub_id).first()
    assert sub_after.clicks_count == initial_clicks + 1
    db.close()


def test_rss_feed_removed_and_clean_footer(client):
    # Garante que as rotas de RSS foram desativadas e retornam 404
    resp_rss = client.get("/rss")
    assert resp_rss.status_code == 404

    resp_feed = client.get("/feed.xml")
    assert resp_feed.status_code == 404

    # Garante que o rodapé não contém mais o botão [FEED RSS] nem tag de link no head
    resp_home = client.get("/")
    assert "[FEED RSS]" not in resp_home.text
    assert 'href="/rss"' not in resp_home.text



def test_about_page(client):
    resp = client.get("/about")
    assert resp.status_code == 200
    assert "O REFÚGIO: TRINCHEIRAS NA ERA DOS ALGORITMOS" in resp.text
    assert "A Saga dos 28 Anos" in resp.text


def test_admin_authentication_and_dashboard(client):
    # Acesso desautenticado a /admin redireciona para login
    resp_unauth = client.get("/admin", follow_redirects=False, headers={"accept": "text/html"})
    assert resp_unauth.status_code == 303
    assert "/login" in resp_unauth.headers["location"]

    # Tentativa de login inválida
    resp_bad_login = client.post("/login", data={"username": "admin", "password": "wrongpassword"})
    assert resp_bad_login.status_code == 401
    assert "Acesso negado" in resp_bad_login.text

    # Login correto
    resp_login = client.post(
        "/login",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
        follow_redirects=False
    )
    assert resp_login.status_code == 303
    assert settings.SESSION_COOKIE_NAME in resp_login.cookies

    # Acesso autenticado ao dashboard
    cookies = {settings.SESSION_COOKIE_NAME: resp_login.cookies[settings.SESSION_COOKIE_NAME]}
    resp_admin = client.get("/admin", cookies=cookies)
    assert resp_admin.status_code == 200
    assert "PAINEL DE CONTROLE" in resp_admin.text
    assert "Posts Publicados" in resp_admin.text


def test_admin_create_post_and_moderate(client):
    # Login para obter cookie
    resp_login = client.post(
        "/login",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
        follow_redirects=False
    )
    cookies = {settings.SESSION_COOKIE_NAME: resp_login.cookies[settings.SESSION_COOKIE_NAME]}

    # Criar novo post
    post_data = {
        "title": "Post Criado no Teste Automatizado",
        "category": "Dev & Tech",
        "content": "Conteúdo de teste com **Markdown em negrito** e uma lista:\n- Item 1\n- Item 2"
    }
    resp_post = client.post("/admin/posts/new", data=post_data, cookies=cookies, follow_redirects=False)
    assert resp_post.status_code == 303

    db = SessionLocal()
    new_post = db.query(Post).filter(Post.title == "Post Criado no Teste Automatizado").first()
    assert new_post is not None
    assert new_post.slug == "post-criado-no-teste-automatizado"

    # Aprovar uma submissão pendente
    sub_pending = db.query(CommunitySubmission).filter(CommunitySubmission.status == "pending").first()
    if sub_pending:
        resp_approve = client.post(
            f"/admin/submissions/{sub_pending.id}/status",
            data={"status_value": "approved"},
            cookies=cookies,
            follow_redirects=False
        )
        assert resp_approve.status_code == 303

        db.refresh(sub_pending)
        assert sub_pending.status == "approved"

    db.close()


def test_sqlite_wal_mode_active():
    from database import engine
    with engine.connect() as conn:
        journal_mode = conn.exec_driver_sql("PRAGMA journal_mode;").scalar()
        busy_timeout = conn.exec_driver_sql("PRAGMA busy_timeout;").scalar()
        assert journal_mode.lower() == "wal"
        assert busy_timeout >= 5000


def test_xss_sanitization_in_markdown():
    from main import render_markdown
    malicious_md = """# Título Seguro
<script>alert('XSS Attack');</script>
<img src="x" onerror="alert('hack')">
[Link Legítimo](https://indieweb.org)
<a href="javascript:alert(1)">Clique aqui</a>
"""
    clean_html = render_markdown(malicious_md)
    # Garante que scripts e atributos perigosos foram exterminados
    assert "<script>" not in clean_html
    assert "alert(" not in clean_html
    assert "onerror" not in clean_html
    assert "javascript:" not in clean_html
    assert "href=\"https://indieweb.org\"" in clean_html
    assert "Título Seguro" in clean_html


def test_magic_bytes_image_validation():
    from auth import validate_image_file
    # 1. Arquivo texto renomeado como .png (Ataque)
    fake_png_bytes = b"<?php echo 'malware'; ?>"
    is_valid, err = validate_image_file("hacked.png", fake_png_bytes)
    assert not is_valid
    assert "não corresponde a uma imagem válida" in err

    # 2. PNG legítimo com cabeçalho magic bytes correto
    valid_png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    is_valid, err = validate_image_file("foto.png", valid_png_bytes)
    assert is_valid
    assert err == ""


def test_rate_limiting_protection(client):
    # Faz requisições consecutivas no login para estourar o limite de 5/minuto
    exceeded = False
    for _ in range(8):
        resp = client.post("/login", data={"username": "fake", "password": "wrong"})
        if resp.status_code == 429:
            exceeded = True
            break
    assert exceeded


def test_category_filter_with_ampersand(client):
    # Categoria com '&' (Dev & Tech)
    resp = client.get("/?category=Dev%20%26%20Tech")
    assert resp.status_code == 200
    assert "Por que Monólitos em SQLite e FastAPI Ainda Dominam o Mundo Real" in resp.text
    assert "[TERMINAL SILENCIOSO]" not in resp.text

    # Categoria Mangás & Cultura
    resp_mangas = client.get("/?category=Mang%C3%A1s%20%26%20Cultura")
    assert resp_mangas.status_code == 200
    assert "Vagabond, Berserk" in resp_mangas.text
    assert "[TERMINAL SILENCIOSO]" not in resp_mangas.text


def test_github_link_stored_xss_protection(client):
    # Submissão com javascript: deve ser sumariamente rejeitada
    malicious_sub = {
        "author_name": "HackerX",
        "author_email": "hack@xss.io",
        "github_link": "javascript:alert(document.cookie)",
        "title": "Exploit Payload",
        "category": "Scripts Úteis",
        "description": "Tentativa de stored XSS no admin",
        "website_hp": ""
    }
    resp = client.post("/lab/submit", data=malicious_sub, follow_redirects=False)
    assert resp.status_code == 303
    assert "submitted=false" in resp.headers["location"]

    db = SessionLocal()
    sub = db.query(CommunitySubmission).filter(CommunitySubmission.title == "Exploit Payload").first()
    assert sub is None
    db.close()


def test_slugify_emoji_and_symbol_fallback():
    from main import slugify
    slug_emoji = slugify("✨🔥🚀")
    assert slug_emoji.startswith("post-")
    assert len(slug_emoji) > 5

    slug_symbols = slugify("??? !!!")
    assert slug_symbols.startswith("post-")


def test_custom_404_retro_page(client):
    resp = client.get("/post/post-totalmente-inexistente-xyz", headers={"accept": "text/html"})
    assert resp.status_code == 404
    assert "[SYS: COORDENADA INEXISTENTE]" in resp.text
    assert "RETORNAR AO DIÁRIO" in resp.text


def test_admin_edit_post_workflow(client):
    from auth import create_session_token
    token = create_session_token(settings.ADMIN_USERNAME)
    cookies = {settings.SESSION_COOKIE_NAME: token}

    db = SessionLocal()
    post = db.query(Post).first()
    post_id = post.id
    orig_title = post.title
    orig_category = post.category
    orig_content = post.content
    db.close()

    try:
        # 1. Carrega tela de edição GET
        resp_edit_page = client.get(f"/admin/posts/{post_id}/edit", cookies=cookies)
        assert resp_edit_page.status_code == 200
        assert f"MODIFICAR ENTRADA #{post_id}" in resp_edit_page.text

        # 2. Salva modificação POST
        new_title = f"Título Modificado no Patch Test {post_id}"
        update_data = {
            "title": new_title,
            "category": "Dev & Tech",
            "content": "Conteúdo modificado com sucesso e validado pelo teste automatizado."
        }
        resp_update = client.post(f"/admin/posts/{post_id}/edit", data=update_data, cookies=cookies, follow_redirects=False)
        assert resp_update.status_code == 303

        db = SessionLocal()
        updated_post = db.query(Post).filter(Post.id == post_id).first()
        assert updated_post.title == new_title
        db.close()
    finally:
        # Restaura o estado original para manter o teste idempotente
        db = SessionLocal()
        p = db.query(Post).filter(Post.id == post_id).first()
        if p:
            p.title = orig_title
            p.category = orig_category
            p.content = orig_content
            db.commit()
        db.close()


def test_admin_category_dropdown_and_custom_creation(client):
    import uuid
    from auth import create_session_token
    token = create_session_token(settings.ADMIN_USERNAME)
    cookies = {settings.SESSION_COOKIE_NAME: token}

    # 1. Verifica se o painel administrativo carrega o <select> com categorias
    resp_admin = client.get("/admin?tab=new_post", cookies=cookies)
    assert resp_admin.status_code == 200
    assert 'id="category_select"' in resp_admin.text
    assert '<option value="Saga dos 28">Saga dos 28</option>' in resp_admin.text
    assert '<option value="__custom__">+ [CRIAR NOVA CATEGORIA...]</option>' in resp_admin.text

    # 2. Cria post com categoria customizada via dropdown "__custom__"
    custom_post_title = f"Post com Categoria Nova {uuid.uuid4().hex[:6]}"
    custom_category_name = "Automação & Cyberpunk"
    post_payload = {
        "title": custom_post_title,
        "category": "__custom__",
        "category_custom": custom_category_name,
        "content": "Testando seleção customizada no dropdown do admin."
    }
    resp_create = client.post("/admin/posts/new", data=post_payload, cookies=cookies, follow_redirects=False)
    assert resp_create.status_code == 303

    db = SessionLocal()
    created_post = db.query(Post).filter(Post.title == custom_post_title).first()
    assert created_post is not None
    assert created_post.category == custom_category_name
    created_post_id = created_post.id
    db.close()

    # 3. Verifica se a tela de edição preseleciona a categoria correta
    resp_edit = client.get(f"/admin/posts/{created_post_id}/edit", cookies=cookies)
    assert resp_edit.status_code == 200
    assert "Automação" in resp_edit.text
    assert "Cyberpunk" in resp_edit.text
    assert "selected" in resp_edit.text

    # Limpeza
    db = SessionLocal()
    p = db.query(Post).filter(Post.id == created_post_id).first()
    if p:
        db.delete(p)
        db.commit()
    db.close()



