import logging
from datetime import datetime
from sqlalchemy import inspect, text
from database import engine, SessionLocal, Base
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
from auth import hash_password
from config import settings

logger = logging.getLogger("refugio.init_db")


DEFAULT_PROTEST_TRACKS = [
    # --- CLÁSSICOS HISTÓRICOS DA AMÉRICA LATINA & MUNDO ---
    {
        "title": "Apesar de Você",
        "artist": "Chico Buarque",
        "country": "Brasil",
        "genre": "Clássico 1970 // MPB de Protesto",
        "youtube_id": "tj_sU3uGFXk",
        "youtube_url": "https://www.youtube.com/watch?v=tj_sU3uGFXk",
        "description": "Composta em 1970, driblou a censura e se tornou o maior símbolo musical da luta pela redemocratização no Brasil."
    },
    {
        "title": "Pra Não Dizer Que Não Falei das Flores",
        "artist": "Geraldo Vandré",
        "country": "Brasil",
        "genre": "Clássico 1968 // Canção de Protesto",
        "youtube_id": "1KskJDDW93k",
        "youtube_url": "https://www.youtube.com/watch?v=1KskJDDW93k",
        "description": "Hino histórico de 1968 que convocou a resistência civil ('Quem sabe faz a hora, não espera acontecer')."
    },
    {
        "title": "Como Nossos Pais",
        "artist": "Elis Regina & Belchior",
        "country": "Brasil",
        "genre": "Clássico 1976 // MPB",
        "youtube_id": "LfCDkut_j9M",
        "youtube_url": "https://www.youtube.com/watch?v=LfCDkut_j9M",
        "description": "Reflexão geracional sobre resistência política, inconformismo e a urgência de manter a transformação viva."
    },
    {
        "title": "El Derecho de Vivir en Paz",
        "artist": "Víctor Jara",
        "country": "Chile",
        "genre": "Clássico 1971 // Nueva Canción Chilena",
        "youtube_id": "XkXise2bHE0",
        "youtube_url": "https://www.youtube.com/watch?v=XkXise2bHE0",
        "description": "Obra imortal de Víctor Jara que ecoou nas ruas do Chile e de toda a América Latina pelo direito à paz e soberania."
    },
    {
        "title": "El Pueblo Unido Jamás Será Vencido",
        "artist": "Inti-Illimani & Quilapayún",
        "country": "Chile",
        "genre": "Clássico 1973 // Canto Popular Latino",
        "youtube_id": "K3AcdMdwL70",
        "youtube_url": "https://www.youtube.com/watch?v=K3AcdMdwL70",
        "description": "O cântico de união popular mais traduzido da história latino-americana."
    },
    {
        "title": "Todo Cambia",
        "artist": "Mercedes Sosa",
        "country": "Argentina",
        "genre": "Clássico 1984 // Folclore Sul-Americano",
        "youtube_id": "0khKL3tTOTs",
        "youtube_url": "https://www.youtube.com/watch?v=0khKL3tTOTs",
        "description": "Na voz de 'La Negra' Mercedes Sosa, um manifesto poético sobre exílio, mudança e amor inabalável à América Latina."
    },
    {
        "title": "Ojalá",
        "artist": "Silvio Rodríguez",
        "country": "Cuba",
        "genre": "Clássico 1978 // Nueva Trova",
        "youtube_id": "u3quFCVY6Ug",
        "youtube_url": "https://www.youtube.com/watch?v=u3quFCVY6Ug",
        "description": "Clássico da Nueva Trova Latino-Americana sobre memória, libertação e superação de tempos sombrios."
    },
    {
        "title": "El Baile de los que Sobran",
        "artist": "Los Prisioneros",
        "country": "Chile",
        "genre": "Clássico 1986 // Rock Latino",
        "youtube_id": "uPJrZFBiy-A",
        "youtube_url": "https://www.youtube.com/watch?v=uPJrZFBiy-A",
        "description": "Crítica contundente à desigualdade educacional e social imposta à juventude trabalhadora latino-americana."
    },
    {
        "title": "Diário de um Detento",
        "artist": "Racionais MC's",
        "country": "Brasil",
        "genre": "Clássico 1997 // Rap Nacional",
        "youtube_id": "dGFxdmuDA4A",
        "youtube_url": "https://www.youtube.com/watch?v=dGFxdmuDA4A",
        "description": "Relato visceral sobre o massacre do Carandiru e a realidade das periferias e do sistema carcerário brasileiro."
    },
    {
        "title": "Gimme Tha Power",
        "artist": "Molotov",
        "country": "México",
        "genre": "Clássico 1997 // Rap Rock",
        "youtube_id": "9YI4aqaVSg0",
        "youtube_url": "https://www.youtube.com/watch?v=9YI4aqaVSg0",
        "description": "Denúncia explosiva contra a corrupção política, o abuso de poder e a desigualdade na América Latina."
    },
    {
        "title": "Um Bom Lugar",
        "artist": "Sabotage",
        "country": "Brasil",
        "genre": "Clássico 2000 // Rap Nacional",
        "youtube_id": "GA7LcSX8tYE",
        "youtube_url": "https://www.youtube.com/watch?v=GA7LcSX8tYE",
        "description": "Hino imortal do Maestro do Canão sobre sobrevivência, dignidade e resistência na periferia."
    },
    {
        "title": "Latinoamérica",
        "artist": "Calle 13 (part. Totó la Momposina, Susana Baca & Maria Rita)",
        "country": "Porto Rico / América Latina",
        "genre": "Clássico 2010 // Rap & Folclore Latino",
        "youtube_id": "DkFJE8ZdeG8",
        "youtube_url": "https://www.youtube.com/watch?v=DkFJE8ZdeG8",
        "description": "Celebração épica da resistência, memória histórica e soberania dos povos latino-americanos."
    },

    # --- CENA CONTEMPORÂNEA & PROTESTO 2026 (AMÉRICA LATINA & MUNDO) ---
    {
        "title": "This Is Not America (feat. Ibeyi)",
        "artist": "Residente",
        "country": "Porto Rico / América Latina",
        "genre": "Cena 2026 // Rap & Percussão Afro-Latina",
        "youtube_id": "GK87AKIPyZY",
        "youtube_url": "https://www.youtube.com/watch?v=GK87AKIPyZY",
        "description": "Manifesto audiovisual contemporâneo reivindicando a identidade continental da América Latina contra o imperialismo."
    },
    {
        "title": "Tierra Zanta",
        "artist": "Trueno & Victor Heredia",
        "country": "Argentina",
        "genre": "Cena 2026 // Rap Sul-Americano & Folclore",
        "youtube_id": "POAdMW-4yfw",
        "youtube_url": "https://www.youtube.com/watch?v=POAdMW-4yfw",
        "description": "Encontro da nova geração do rap argentino com a lenda da canção de protesto Victor Heredia em defesa da América do Sul."
    },
    {
        "title": "Antipatriarca",
        "artist": "Ana Tijoux",
        "country": "Chile",
        "genre": "Cena 2026 // Rap de Protesto Latino",
        "youtube_id": "RoKoj8bFg2E",
        "youtube_url": "https://www.youtube.com/watch?v=RoKoj8bFg2E",
        "description": "Voz potente do hip-hop chileno contemporâneo contra a opressão, o autoritarismo e a violência estrutural."
    },
    {
        "title": "Primavera (part. Rael & Giovani Cidreira)",
        "artist": "Don L",
        "country": "Brasil",
        "genre": "Cena 2026 // Rap Político Brasileiro",
        "youtube_id": "bs5B5VLhqlk",
        "youtube_url": "https://www.youtube.com/watch?v=bs5B5VLhqlk",
        "description": "Lirismo revolucionário da cena contemporânea brasileira conectando a luta histórica do Sul Global ao futuro."
    },
    {
        "title": "Olho de Tigre (Fogo nos Racistas)",
        "artist": "Djonga",
        "country": "Brasil",
        "genre": "Cena 2026 // Rap Nacional",
        "youtube_id": "s5pPKgPS50w",
        "youtube_url": "https://www.youtube.com/watch?v=s5pPKgPS50w",
        "description": "Um dos maiores hinos de protesto antirracista da música brasileira contemporânea."
    },
    {
        "title": "Lucro (Descomprimindo)",
        "artist": "BaianaSystem",
        "country": "Brasil",
        "genre": "Cena 2026 // Afro-Rock & SoundSystem",
        "youtube_id": "y7NJN0MFnTw",
        "youtube_url": "https://www.youtube.com/watch?v=y7NJN0MFnTw",
        "description": "Crítica feroz à especulação imobiliária e à máquina de lucro urbano ('Tire as construções da minha praia')."
    },
    {
        "title": "AmarElo (Sample: Belchior)",
        "artist": "Emicida (part. Majur & Pabllo Vittar)",
        "country": "Brasil",
        "genre": "Cena 2026 // Rap Consciente & MPB",
        "youtube_id": "PTDgP3BDPIU",
        "youtube_url": "https://www.youtube.com/watch?v=PTDgP3BDPIU",
        "description": "Ponte entre o clássico de Belchior e a luta contemporânea por saúde mental, dignidade e resistência coletiva."
    },
    {
        "title": "Não Existe Amor em SP",
        "artist": "Criolo",
        "country": "Brasil",
        "genre": "Cena 2026 // Rap & MPB Contemporânea",
        "youtube_id": "0PfevkndCPU",
        "youtube_url": "https://www.youtube.com/watch?v=0PfevkndCPU",
        "description": "Retrato poético e contundente sobre a frieza urbana, desigualdade e busca por humanidade nas metrópoles."
    }
]


def _ensure_schema_migrations():
    """Adds missing columns to existing SQLite tables (create_all won't ALTER)."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "posts" in table_names:
            post_columns = {col["name"] for col in inspector.get_columns("posts")}
            if "author_id" not in post_columns:
                conn.execute(text("ALTER TABLE posts ADD COLUMN author_id INTEGER REFERENCES users(id)"))
                logger.info("[MIGRATE] Column posts.author_id added.")

        if "users" in table_names:
            user_columns = {col["name"] for col in inspector.get_columns("users")}
            if "email" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(150)"))
                logger.info("[MIGRATE] Column users.email added.")
            if "role" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'admin'"))
                logger.info("[MIGRATE] Column users.role added.")

        if "comments" in table_names:
            comment_columns = {col["name"] for col in inspector.get_columns("comments")}
            if "user_id" not in comment_columns:
                conn.execute(text("ALTER TABLE comments ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                logger.info("[MIGRATE] Column comments.user_id added.")
            if "edit_token" not in comment_columns:
                conn.execute(text("ALTER TABLE comments ADD COLUMN edit_token VARCHAR(64)"))
                logger.info("[MIGRATE] Column comments.edit_token added.")
            if "updated_at" not in comment_columns:
                conn.execute(text("ALTER TABLE comments ADD COLUMN updated_at DATETIME"))
                logger.info("[MIGRATE] Column comments.updated_at added.")

        if "push_subscriptions" in table_names:
            push_columns = {col["name"] for col in inspector.get_columns("push_subscriptions")}
            if "user_id" not in push_columns:
                conn.execute(text("ALTER TABLE push_subscriptions ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                logger.info("[MIGRATE] Column push_subscriptions.user_id added.")


def _sync_default_protest_tracks(db):
    """Sincroniza e atualiza as faixas padrao da Radio Pirata (Classicos + 2026) garantindo IDs verificados."""
    for item in DEFAULT_PROTEST_TRACKS:
        existing = (
            db.query(RadioTrack)
            .filter(RadioTrack.title.ilike(f"%{item['title'][:18]}%"))
            .first()
        )
        if existing:
            existing.youtube_id = item["youtube_id"]
            existing.youtube_url = item["youtube_url"]
            existing.genre = item["genre"]
            existing.country = item["country"]
            existing.artist = item["artist"]
            existing.description = item["description"]
        else:
            db.add(RadioTrack(
                title=item["title"],
                artist=item["artist"],
                country=item["country"],
                genre=item["genre"],
                youtube_id=item["youtube_id"],
                youtube_url=item["youtube_url"],
                description=item["description"],
                is_active=True,
                created_at=datetime.now()
            ))
    db.commit()


def init_database():
    """Cria tabelas e popula com dados iniciais limpos (1 post rico, projetos no Lab e Rádio Pirata)."""
    Base.metadata.create_all(bind=engine)
    _ensure_schema_migrations()
    db = SessionLocal()

    try:
        # 1. Usuário Administrador
        admin_user = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if not admin_user:
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
                created_at=datetime.now()
            )
            db.add(admin_user)
            db.commit()
            logger.info(f"[SEED] Usuário admin '{settings.ADMIN_USERNAME}' configurado com sucesso.")
        elif admin_user.role != "admin":
            admin_user.role = "admin"
            db.commit()

        # Rename legacy category labels to the new naming
        renamed = (
            db.query(Post)
            .filter(Post.category == "Saga dos 28")
            .update({"category": "Diário de Bordo"}, synchronize_session=False)
        )
        if renamed:
            db.commit()
            logger.info(f"[MIGRATE] Renamed {renamed} post(s) from 'Saga dos 28' to 'Diário de Bordo'.")

        # 2. Contador de Visitas Digital (zerado para os primeiros acessos)
        visit_stat = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
        if not visit_stat:
            visit_stat = SiteStat(key="total_visits", value=0)
            db.add(visit_stat)
            db.commit()
            logger.info("[SEED] Contador de visitas inicializado em 0.")

        # 3. Post Inaugural Único: Vagabond, Berserk e a Busca pelo Silêncio Interior
        posts_count = db.query(Post).count()
        if posts_count == 0:
            post_seed = Post(
                title="Vagabond, Berserk e a Busca pelo Silêncio Interior",
                slug="vagabond-berserk-e-a-busca-pelo-silencio-interior",
                category="Mangás & Cultura",
                media_url="https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=1200&auto=format&fit=crop",
                views_count=0,
                author_id=admin_user.id,
                content="""# Entre a Espada e a Serenidade: O Silêncio na Era do Ruído

Existe uma diferença brutal entre ter vinte anos e beirar os vinte e oito. Aos vinte, o mundo parece uma arena aberta: você quer provar que é capaz, devora tutoriais como se fossem duelos de vida ou morte e acredita, no íntimo, que o segredo da vida é ser o guerreiro mais barulhento e implacável da colina.

Quando li **Vagabond** pela primeira vez, minha obsessão era pela técnica de Musashi Miyamoto. A ferocidade dos cortes, a busca cega por ser "invencível sob o sol". Na mesma época, **Berserk** me fascinava pelo peso descomunal da *Dragon Slayer* e pela fúria inextinguível de Guts contra os apóstolos do destino.

Anos depois, cercado por notificações incessantes, prazos de entrega e o zumbido estéril dos algoritmos predando nossa atenção a cada segundo, reli essas duas obras. E percebi algo desconcertante: **eu não tinha entendido absolutamente nada.**

---

### 1. A Lição de Musashi: O Infinito Dentro de Si

Takehiko Inoue constrói uma das maiores viradas da história dos quadrinhos não em um campo de batalha, mas na lama de uma plantação de arroz. 

Depois de ceifar setenta homens do clã Yoshioka e quase perder a perna, Musashi é forçado a parar. Ele passa meses arando a terra com as próprias mãos, convivendo com a fome, a seca e o ritmo impiedoso das estações. É nesse silêncio desconfortável que ele compreende o ensinamento do monge Takuan:

> *"A espada não serve para cortar o outro, mas para podar o seu próprio ego. O infinito não está no horizonte lá fora; infinito é apenas a sua própria mente."*

A força real nunca foi sobre esmagar o oponente. Era sobre a ausência de intenção dividida — a capacidade de estar inteiro no momento presente, sem a ansiedade febril de validação externa.

---

### 2. A Lição de Guts: O Lutador que Aprendeu a Guardar a Fúria

Se Musashi nos ensina a podar a arrogância, Kentaro Miura nos legou um tratado sobre o que significa resistir com dignidade.

Guts carrega um trauma que destruiria qualquer psique humana. Durante muito tempo, a fúria foi o único combustível que o manteve vivo. Mas o momento em que *Berserk* atinge sua maturidade sublime é quando Guts percebe que **odiar consome a mesma energia vital que amar**. Ele decide parar de caçar a vingança para proteger a Casca e as pessoas que escolheram caminhar ao seu lado.

O "Struggler" não é aquele que grita contra a tempestade; é aquele que, mesmo ferido e no breu da madrugada, continua acendendo uma fogueira silenciosa para manter os seus aquecidos.

---

### 3. O Silêncio Como Trincheira Digital

No desenvolvimento de software e na vida real, vivemos cercados por uma febre coletiva. Tudo precisa ser imediato, tudo precisa ser compartilhado, todo mundo quer ser "Fullstack Sênior" em seis meses e postar métricas de vaidade no LinkedIn antes do café da manhã.

Mas o trabalho de verdade — o código limpo que roda por anos sem falhar, a escrita autêntica, a paz mental ao deitar — **só floresce no silêncio**.

Três regras que levo para o terminal e para a vida:
- **Respire antes de reagir:** A maioria das crises do dia a dia morre por inanição quando você se recusa a entrar em pânico.
- **Podar o supérfluo:** Menos bibliotecas de 500MB, menos reuniões desnecessárias, menos ruído. Domine o essencial.
- **Construa seu refúgio:** Se você não cultiva um espaço de silêncio na sua mente e no seu dia, você será eternamente refém do algoritmo do próximo.

Puxe a respiração fundo. Desconecte o ruído. O verdadeiro duelo sempre foi contra a nossa própria pressa.
""",
                created_at=datetime.now()
            )
            db.add(post_seed)
            db.commit()
            logger.info("[SEED] Post inaugural 'Vagabond, Berserk e a Busca pelo Silêncio Interior' inserido.")

        # 4. Projeto Comunitário no Lab: Emulador Nintendo 64 (RMG)
        lab_count = db.query(CommunitySubmission).count()
        if lab_count == 0:
            lab_seed = CommunitySubmission(
                author_name="Rosalie241",
                author_email="rosalie@rmg.emu",
                github_link="https://github.com/Rosalie241/RMG",
                title="RMG // Rosalie's Mupen GUI (N64 Emulator)",
                category="Jogos 2D",
                description="Emulador open-source de alta fidelidade para Nintendo 64 desenvolvido em C++/Qt6, baseado no Mupen64Plus com plugins gráficos modernos (GLideN64 e ParaLLEl-RDP) e suporte completo a netplay.",
                image_url="https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=800&auto=format&fit=crop",
                status="approved",
                clicks_count=12,
                created_at=datetime.now()
            )
            db.add(lab_seed)
            db.commit()
            logger.info("[SEED] Projeto 'RMG (N64 Emulator)' inserido no Lab.")

        # 5. Emulador Homologado no Lab: simple64 (Cross-Platform N64 Emulator)
        simple64_item = db.query(CommunitySubmission).filter(
            (CommunitySubmission.title.like("%simple64%")) | (CommunitySubmission.github_link.like("%simple64%"))
        ).first()
        if not simple64_item:
            simple64_seed = CommunitySubmission(
                author_name="simple64-dev",
                author_email="dev@simple64.github.io",
                github_link="https://simple64.github.io/",
                title="simple64 // Emulador N64 Moderno e Estável (Win / Mac / Linux)",
                category="Jogos 2D",
                description="Emulador moderno de Nintendo 64 (anteriormente m64p) focado em precisão absoluta, facilidade e estabilidade cross-platform. Traz os núcleos Vulkan ParaLLEl-RDP e ParaLLEl-RSP embutidos sem necessidade de plugins externos. Compatível com Windows, macOS e Linux.",
                image_url="https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=800&auto=format&fit=crop",
                status="approved",
                clicks_count=42,
                created_at=datetime.now()
            )
            db.add(simple64_seed)
            db.commit()
            logger.info("[SEED] Projeto 'simple64' inserido no Lab.")

        # 6. Sincroniza Rádio Pirata by YouTube (Clássicos Históricos + Cena 2026)
        _sync_default_protest_tracks(db)

    except Exception as e:
        db.rollback()
        logger.error(f"[SEED ERROR] Falha ao inicializar dados: {e}")
        raise e
    finally:
        db.close()


def reset_to_clean_state():
    """Limpa contadores, posts de teste e dados fake, deixando o banco no estado zero."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Zera visitas
        visit_stat = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
        if visit_stat:
            visit_stat.value = 0
        else:
            db.add(SiteStat(key="total_visits", value=0))

        # Limpa comentários, notificações e posts antigos
        db.query(Notification).delete()
        db.query(Comment).delete()
        db.query(Post).delete()
        db.query(CommunitySubmission).delete()
        db.commit()

        logger.info("[RESET] Dados antigos, fakes e contadores limpos com sucesso.")
    except Exception as e:
        db.rollback()
        logger.error(f"[RESET ERROR] Falha ao limpar banco: {e}")
        raise e
    finally:
        db.close()

    # Reaplica os dados limpos
    init_database()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_database()
    print("Banco de dados do Refúgio inicializado com sucesso!")
