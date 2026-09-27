import logging
from datetime import datetime
from database import engine, SessionLocal, Base
from models import User, Post, CommunitySubmission, Comment, SiteStat
from auth import hash_password
from config import settings

logger = logging.getLogger("refugio.init_db")


def init_database():
    """Cria tabelas e popula com dados iniciais (Seed Anti-Tela Pelada)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Usuário Administrador
        admin_user = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if not admin_user:
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                created_at=datetime.now()
            )
            db.add(admin_user)
            db.commit()
            logger.info(f"[SEED] Usuário admin '{settings.ADMIN_USERNAME}' criado com sucesso.")

        # 2. Contador de Visitas Digital
        visit_stat = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
        if not visit_stat:
            visit_stat = SiteStat(key="total_visits", value=1337)
            db.add(visit_stat)
            db.commit()
            logger.info("[SEED] Contador de visitas inicializado em 1337.")

        # 3. Posts Iniciais ("Anti-Tela Pelada")
        posts_count = db.query(Post).count()
        if posts_count == 0:
            posts_seed = [
                Post(
                    title="Manifesto do Refúgio: Construindo Trincheiras na Era dos Algoritmos",
                    slug="manifesto-do-refugio-trincheiras-era-dos-algoritmos",
                    category="Saga dos 28",
                    media_url="https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=1200&auto=format&fit=crop",
                    views_count=142,
                    content="""# O Refúgio: Nossa Trincheira Digital

A internet moderna virou um feed infinito de dopamina barata, métricas de vaidade e algoritmos desenhados para roubar a sua atenção antes mesmo de você terminar o seu primeiro café da manhã.

**O Refúgio nasce do cansaço desse modelo.**

Aqui não tem anúncio pulando na sua cara, não tem rastreador vendendo o seu histórico para corretores de dados, nem inteligência artificial gerando lixo em massa só para ranquear no Google. 

### Os Três Pilares Deste Espaço:

1. **Diário de Bordo & A Saga dos 28 Anos:** Crônicas sinceras sobre transição de carreira, o peso do amadurecimento, rotinas de saúde e os altos e baixos de viver de código.
2. **Cultura & Hobbies:** Reflexões profundas sobre mangás que moldaram caráter (de *Vagabond* a *Berserk*), cinema analógico e jogos que realmente respeitam o tempo do jogador.
3. **O Laboratório da Comunidade:** Um hub aberto e colaborativo para compartilhar ferramentas, scripts e protótipos que nasceram da curiosidade pura.

> *"Se você não constrói o seu próprio espaço na web, você é apenas um inquilino pagando aluguel com a sua atenção."*

Puxe uma cadeira, sirva um café forte e sinta-se em casa. O terminal está aberto.
""",
                    created_at=datetime.now()
                ),
                Post(
                    title="Vagabond, Berserk e a Busca pelo Silêncio Interior",
                    slug="vagabond-berserk-e-a-busca-pelo-silencio-interior",
                    category="Mangás & Cultura",
                    media_url="https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=1200&auto=format&fit=crop",
                    views_count=89,
                    content="""# Entre a Espada e a Serenidade

Ler *Vagabond* aos 20 anos é uma experiência sobre querer ser o mais forte do mundo. Ler aos 28 é sobre entender que **"infinito é apenas a sua própria mente"**.

Takehiko Inoue e Kentaro Miura nos deixaram mais do que histórias de batalhas sangrentas: deixaram manuais sobre resiliência humana. Guts nos ensina a resistir mesmo quando o destino conspira contra nós, enquanto Musashi Miyamoto nos conduz pela dolorosa jornada de desaprender a arrogância.

### Lições para o Mundo Dev e a Vida Real:
- **A espada não serve para cortar o outro, mas para cortar as próprias ilusões.**
- **O foco não é a ausência de distrações, é a clareza inabalável do próximo passo.**
- **A maestria leva tempo.** Não existe "Fullstack Sênior em 6 meses" no tatame da vida.

Numa época onde tudo é instantâneo e descartável, parar para contemplar o traço a nanquim de uma página dupla é um ato revolucionário de calma.
""",
                    created_at=datetime.now()
                ),
                Post(
                    title="Por que Monólitos em SQLite e FastAPI Ainda Dominam o Mundo Real",
                    slug="monolitos-sqlite-fastapi-dominam-o-mundo-real",
                    category="Dev & Tech",
                    media_url="https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?q=80&w=1200&auto=format&fit=crop",
                    views_count=215,
                    content="""# Menos Microserviços, Mais Código Entregue

Parece que a indústria de software sofre de uma febre coletiva: qualquer sistema que poderia rodar num Raspberry Pi de 2GB é fatiado em 14 microserviços, orquestrado por um cluster de Kubernetes que custa o salário anual de três estagiários.

Para projetos independentes, ferramentas internas e blogs autorais, a combinação **FastAPI + SQLite + Jinja2** é quase imbatível:

- **Zero Latência de Rede:** As queries do SQLite rodam no mesmo processo em disco local ou NVMe.
- **Backups Atômicos:** Quer fazer backup do banco de produção? `cp blog.db blog.db.bak`. Fim.
- **Tipagem Forte e DX:** FastAPI oferece serialização com Pydantic e async nativo sem mágica obscura.
- **FinOps Imbatível:** Roda em qualquer VPS de 4 dólares por mês sem suar.

Antes de adicionar mais uma fila no RabbitMQ, pergunte-se: *você precisa de escala planetária ou você só quer que seu sistema funcione sem te acordar às 3 da manhã?*
""",
                    created_at=datetime.now()
                )
            ]

            db.add_all(posts_seed)
            db.commit()

            # Adiciona comentários de exemplo no primeiro post
            first_post = db.query(Post).filter(Post.slug == "manifesto-do-refugio-trincheiras-era-dos-algoritmos").first()
            if first_post:
                comments_seed = [
                    Comment(
                        post_id=first_post.id,
                        author_name="Kenshin_01",
                        author_email="kenshin@retro.net",
                        content="Sensacional a iniciativa! A web dos anos 2000 faz muita falta. Já adicionei o feed no meu leitor RSS.",
                        notify_replies=True,
                        created_at=datetime.now()
                    ),
                    Comment(
                        post_id=first_post.id,
                        author_name="Luna Cyberpunk",
                        author_email="luna@matrix.io",
                        content="Essa estética Neo-Brutalista com verde terminal ficou absurda de linda. Parabéns pelo Refúgio!",
                        notify_replies=False,
                        created_at=datetime.now()
                    )
                ]
                db.add_all(comments_seed)
                db.commit()

            logger.info("[SEED] 3 posts inaugurais e comentários de exemplo injetados com sucesso.")

        # 4. Submissões Comunitárias no Lab
        lab_count = db.query(CommunitySubmission).count()
        if lab_count == 0:
            lab_seed = [
                CommunitySubmission(
                    author_name="RetroDev",
                    author_email="retro@pixel.games",
                    github_link="https://github.com/topics/roguelike-python",
                    title="Dungeon Crawler 16-bits",
                    category="Jogos 2D",
                    description="Mini roguelike procedural desenvolvido em Python com curses e suporte a paletas retrô do GameBoy.",
                    image_url="https://images.unsplash.com/photo-1551103782-8ab07afd45c1?q=80&w=800&auto=format&fit=crop",
                    status="approved",
                    clicks_count=67,
                    created_at=datetime.now()
                ),
                CommunitySubmission(
                    author_name="Kaizen",
                    author_email="kaizen@terminal.tools",
                    github_link="https://github.com/topics/cli-productivity",
                    title="Chrono-Tracker CLI",
                    category="Scripts Úteis",
                    description="Cronômetro Pomodoro embutido diretamente na barra de status do terminal, com estatísticas diárias exportadas em JSON.",
                    image_url="https://images.unsplash.com/photo-1517694712202-14dd9538aa97?q=80&w=800&auto=format&fit=crop",
                    status="approved",
                    clicks_count=42,
                    created_at=datetime.now()
                ),
                CommunitySubmission(
                    author_name="SamuraiSound",
                    author_email="beats@cyber.fm",
                    github_link="https://github.com/topics/lofi-radio",
                    title="Lo-Fi Beats Terminal Radio",
                    category="Ferramentas de IA",
                    description="Streamer de áudio leve via MPV integrado ao terminal, tocando playlists lo-fi 24/7 sem consumir sua RAM.",
                    image_url="https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?q=80&w=800&auto=format&fit=crop",
                    status="approved",
                    clicks_count=35,
                    created_at=datetime.now()
                ),
                CommunitySubmission(
                    author_name="CyberVoxel",
                    author_email="voxel@canvas.art",
                    github_link="https://github.com/topics/webgl-shaders",
                    title="Pixel-Shader Playground",
                    category="Ferramentas de IA",
                    description="Simulador interativo de shaders GLSL que converte imagens e vídeos para estilo pixel art dos consoles dos anos 90.",
                    image_url="https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=800&auto=format&fit=crop",
                    status="approved",
                    clicks_count=28,
                    created_at=datetime.now()
                ),
                CommunitySubmission(
                    author_name="Dixie",
                    author_email="dixie@refugio.local",
                    github_link="https://github.com/topics/rss-reader",
                    title="IndieWeb RSS Aggregator",
                    category="Scripts Úteis",
                    description="Leitor e agregador de feeds RSS ultrarrápido com cache SQLite local e exportação em Markdown puro.",
                    image_url="https://images.unsplash.com/photo-1504639725590-34d0984388bd?q=80&w=800&auto=format&fit=crop",
                    status="approved",
                    clicks_count=19,
                    created_at=datetime.now()
                )
            ]
            db.add_all(lab_seed)
            db.commit()
            logger.info("[SEED] 5 projetos aprovados da comunidade no Lab injetados com sucesso.")

    except Exception as e:
        db.rollback()
        logger.error(f"[SEED ERROR] Falha ao inicializar dados: {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_database()
    print("Banco de dados do Refúgio inicializado com sucesso!")
