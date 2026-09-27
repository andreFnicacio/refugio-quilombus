#!/usr/bin/env python3
import sys
import uvicorn
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from datetime import datetime

from database import SessionLocal, engine, Base
from models import User, Post, CommunitySubmission, Comment, SiteStat
from auth import hash_password
from init_db import init_database
from config import settings

app = typer.Typer(
    help="CLI de Gerenciamento do Refúgio Blog & Community Hub",
    add_completion=False
)
console = Console()

SAMURAI_SKULL_ASCII = """
[bold #00ff66]               .---.
              /     \\
             | () () |
              \\  _  /
               |||||  [/][bold #ff0055]___[/][bold #00ff66]
              .-'`'-. [/][bold #ff0055]|   |[/][bold #00ff66]
             / /| |\\ \\[/][bold #ff0055]|===|[/][bold #00ff66]
            / / |_| \\ \\[/][bold #ff0055]|   |[/][bold #00ff66]
           /_/       \\_\\[/][bold #ff0055]|___|[/]
[bold #00f0ff]       ⚔️  CYBERPUNK SAMURAI SKULL  ⚔️ [/]
[bold #ffb000]       === O REFÚGIO // CONTROL CLI ===[/]
"""


def print_banner():
    console.print(Panel(
        SAMURAI_SKULL_ASCII.strip(),
        border_style="#00ff66",
        box=box.HEAVY,
        subtitle="[bold #ffb000]v1.0.0 // IndieWeb Monolith[/]"
    ))


@app.command()
def run(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host para escutar"),
    port: int = typer.Option(8000, "--port", "-p", help="Porta TCP"),
    reload: bool = typer.Option(True, "--reload/--no-reload", help="Hot-reload em dev")
):
    """Inicia o servidor web assíncrono do Refúgio com Uvicorn."""
    print_banner()
    console.print(f"[bold #00ff66]>> Iniciando servidor FastAPI em http://{host}:{port}...[/]")
    console.print("[dim]Pressione CTRL+C para encerrar o terminal.[/]\n")
    uvicorn.run("main:app", host=host, port=port, reload=reload)


@app.command()
def init():
    """Executa a rotina de inicialização e seed data anti-tela pelada."""
    print_banner()
    console.print("[bold #ffb000]>> Inicializando banco de dados SQLite e injetando seeds...[/]")
    init_database()
    console.print("[bold #00ff66]✔ Banco de dados pronto e populado com sucesso![/]")


@app.command()
def createsuperuser(
    username: str = typer.Option(..., prompt=True, help="Nome de usuário do admin"),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="Senha de acesso")
):
    """Cria um novo operador administrador no banco de dados."""
    print_banner()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username.strip()).first()
        if existing:
            console.print(f"[bold #ff0055]✖ Erro: O usuário '{username}' já existe no terminal![/]")
            raise typer.Exit(code=1)

        user = User(
            username=username.strip(),
            password_hash=hash_password(password),
            created_at=datetime.now()
        )
        db.add(user)
        db.commit()
        console.print(f"[bold #00ff66]✔ Usuário administrador '{username}' forjado com sucesso![/]")
    finally:
        db.close()


@app.command()
def stats():
    """Exibe estatísticas de telemetria e integridade do banco de dados."""
    print_banner()
    db = SessionLocal()
    try:
        total_posts = db.query(Post).count()
        total_comments = db.query(Comment).count()
        total_subs = db.query(CommunitySubmission).count()
        pending_subs = db.query(CommunitySubmission).filter(CommunitySubmission.status == "pending").count()
        approved_subs = db.query(CommunitySubmission).filter(CommunitySubmission.status == "approved").count()
        visit_stat = db.query(SiteStat).filter(SiteStat.key == "total_visits").first()
        total_visits = visit_stat.value if visit_stat else 0

        table = Table(title="[bold #00f0ff]TELEMETRIA DO SISTEMA O REFÚGIO[/]", box=box.ROUNDED)
        table.add_column("Métrica", style="bold #ffb000")
        table.add_column("Valor Atual", style="bold #00ff66")

        table.add_row("Posts Publicados", str(total_posts))
        table.add_row("Total de Comentários", str(total_comments))
        table.add_row("Projetos no Lab (Total)", str(total_subs))
        table.add_row("Projetos Aprovados", str(approved_subs))
        table.add_row("Projetos Pendentes de Moderação", str(pending_subs))
        table.add_row("Contador Digital de Visitas", str(total_visits))

        console.print(table)
    finally:
        db.close()


@app.command()
def health():
    """Verifica saúde e conectividade do monólito."""
    print_banner()
    try:
        db = SessionLocal()
        db.execute(Base.metadata.tables["users"].select().limit(1))
        db.close()
        console.print("[bold #00ff66]✔ Health Check OK: Conexão SQLite e tabelas operacionais.[/]")
    except Exception as e:
        console.print(f"[bold #ff0055]✖ Falha no Health Check: {e}[/]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
