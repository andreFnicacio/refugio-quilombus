import logging
from datetime import datetime
from database import engine, SessionLocal, Base
from models import User, Post, CommunitySubmission, Comment, SiteStat
from auth import hash_password
from config import settings

logger = logging.getLogger("refugio.init_db")


def init_database():
    """Cria tabelas e popula com dados iniciais limpos (1 post rico e 1 projeto no Lab)."""
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
            logger.info(f"[SEED] Usuário admin '{settings.ADMIN_USERNAME}' configurado com sucesso.")

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
                clicks_count=0,
                created_at=datetime.now()
            )
            db.add(lab_seed)
            db.commit()
            logger.info("[SEED] Projeto 'RMG (N64 Emulator)' inserido no Lab.")

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

        # Limpa comentários e posts antigos
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
