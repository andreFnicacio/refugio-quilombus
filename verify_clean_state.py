"""
Script de verificação dos contadores e estado limpo inicial de O Refúgio.
Testa:
  1. Estado inicial limpo (1 post rico de Vagabond/Berserk, 1 projeto N64 no Lab, 0 dados fake).
  2. Contador de visitas globais (Odômetro digital) incrementando a cada acesso.
  3. Contador de visualizações do post inaugural incrementando ao acessar /post/{slug}.
  4. Contador de cliques do projeto no Lab incrementando ao passar por /lab/redirect/{id}.
"""
import sys
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
from models import Post, CommunitySubmission, SiteStat, Comment
from init_db import reset_to_clean_state


def run_verification():
    print("==================================================================")
    print("⚔️  INICIANDO VERIFICAÇÃO DO ESTADO LIMPO E CONTADORES // O REFÚGIO")
    print("==================================================================")

    # 1. Reseta o banco para o estado inaugural limpo
    reset_to_clean_state()
    db = SessionLocal()
    posts = db.query(Post).all()
    labs = db.query(CommunitySubmission).all()
    visits_stat = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
    comments_count = db.query(Comment).count()
    db.close()

    print(f"[*] Posts no banco: {len(posts)}")
    print(f"[*] Projetos no Lab: {len(labs)}")
    print(f"[*] Comentários no banco: {comments_count}")
    print(f"[*] Visitas iniciais: {visits_stat.value if visits_stat else None}")

    assert len(posts) == 1, "Deveria existir exatamente 1 post."
    assert posts[0].slug == "vagabond-berserk-e-a-busca-pelo-silencio-interior"
    assert len(labs) == 1, "Deveria existir exatamente 1 projeto no Lab."
    assert "Rosalie" in labs[0].title
    assert comments_count == 0, "Deveria haver 0 comentários fakes."
    assert visits_stat.value == 0, "Visitas deveriam começar em 0."
    print("  ✓ Estado limpo validado com sucesso!")

    # 2. Testando TestClient
    with TestClient(app) as client:
        # Acesso à Home Page (deve incrementar visitas)
        print("\n[*] Simulando primeiro acesso à Home Page (/) ...")
        resp_home = client.get("/")
        assert resp_home.status_code == 200
        assert "Vagabond, Berserk e a Busca pelo Silêncio Interior" in resp_home.text

        db = SessionLocal()
        stat_after_visit = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
        print(f"  ✓ Contador de visitas atualizado para: {stat_after_visit.value}")
        assert stat_after_visit.value == 1, "Visitas deveriam ter incrementado para 1."
        db.close()

        # Acesso ao Post (deve incrementar views do post)
        post_slug = "vagabond-berserk-e-a-busca-pelo-silencio-interior"
        print(f"\n[*] Simulando acesso ao post inaugural (/post/{post_slug}) ...")
        resp_post = client.get(f"/post/{post_slug}")
        assert resp_post.status_code == 200
        assert "Entre a Espada e a Serenidade" in resp_post.text

        db = SessionLocal()
        post_after_view = db.query(Post).filter(Post.slug == post_slug).first()
        print(f"  ✓ Visualizações do post atualizadas para: {post_after_view.views_count}")
        assert post_after_view.views_count == 1, "Views do post deveriam ter incrementado para 1."
        db.close()

        # Clique no Projeto do Lab (deve redirecionar e incrementar cliques)
        db = SessionLocal()
        lab_project = db.query(CommunitySubmission).first()
        project_id = lab_project.id
        initial_clicks = lab_project.clicks_count
        target_link = lab_project.github_link
        db.close()

        print(f"\n[*] Simulando clique no projeto do Lab (/lab/redirect/{project_id}) ...")
        resp_click = client.get(f"/lab/redirect/{project_id}", follow_redirects=False)
        assert resp_click.status_code == 303
        assert resp_click.headers["location"] == target_link

        db = SessionLocal()
        lab_after_click = db.query(CommunitySubmission).filter(CommunitySubmission.id == project_id).first()
        print(f"  ✓ Contador de cliques do projeto atualizado para: {lab_after_click.clicks_count}")
        assert lab_after_click.clicks_count == initial_clicks + 1, "Cliques deveriam ter incrementado em 1."
        db.close()

    print("\n==================================================================")
    print("🎉 TODAS AS VERIFICAÇÕES PASSARAM COM 100% DE SUCESSO!")
    print("   - Contador de Visitas Globais (Odômetro): FUNCIONANDO")
    print("   - Contador de Views do Post: FUNCIONANDO")
    print("   - Contador de Cliques do Lab: FUNCIONANDO")
    print("   - Base limpa para os primeiros acessos reais.")
    print("==================================================================")


if __name__ == "__main__":
    run_verification()
