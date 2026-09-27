# ⚔️ O Refúgio // IndieWeb Cyberpunk Monolith

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLite WAL](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![Tests](https://img.shields.io/badge/Tests-21%20Passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](test_app.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Style: Neo--Brutalism](https://img.shields.io/badge/Design-Neo--Brutalism-FF3366?style=for-the-badge)](#-design-system--estética)

> **"A internet corporativa virou um shopping center de dados. O Refúgio é o nosso bunker de código, ideias cruas e autonomia digital."**

**O Refúgio** é um monólito de blog técnico e hub comunitário indie construído com foco em **FinOps radical**, **alta performance**, **estética Neo-Brutalist / 16-bit Retro** e **zero dependências inchadas (bloatware)**. Aqui não tem Single Page Application de 50MB nem faturas absurdas de nuvem: apenas Python moderno com FastAPI, Jinja2 server-side rendering, SQLite de alta concorrência em modo WAL e CSS artesanal.

---

## 📑 Sumário

- [Visão Geral e Filosofia](#-visão-geral-e-filosofia)
- [Design System & Estética](#-design-system--estética)
- [Stack Tecnológica e Apps Utilizados](#-stack-tecnológica-e-apps-utilizados)
- [Arquitetura do Projeto](#-arquitetura-do-projeto)
- [Processo de Desenvolvimento Local](#-processo-de-desenvolvimento-local)
- [Gerenciamento e CLI Interativa](#-gerenciamento-e-cli-interativa)
- [Bateria de Testes e Validação](#-bateria-de-testes-e-validação)
- [Deploy com Docker & FinOps](#-deploy-com-docker--finops)
- [Guia de Contribuição Open Source](#-guia-de-contribuição-open-source)
- [Licença](#-licença)

---

## 🧭 Visão Geral e Filosofia

O projeto foi concebido a partir de três pilares:
1. **Soberania Digital & FinOps**: Pode ser hospedado em uma VPS modesta de $3-5/mês sem suar, consumindo menos de 100MB de RAM.
2. **Segurança em Camadas**: Sanitização estrita contra XSS em Markdown e inputs, proteção contra DoS via rate limiting por IP, sessões assinadas criptograficamente e validação de Magic Bytes em uploads.
3. **Resiliência e Simplicidade**: Monólito modular sem microsserviços desnecessários. O banco SQLite opera em modo Write-Ahead Logging (WAL) com pool assíncrono para garantir leituras e escritas concorrentes sem locks de tabela.

---

## 🎨 Design System & Estética

A interface visual combina a ousadia do **Neo-Brutalismo** com a nostalgia nostálgica da era **16-bit Cyberpunk**:
- **Bordas Grossas e Contraste Alto**: `border: 3px solid #000;` com sombras duras (`box-shadow: 4px 4px 0px #000;`).
- **Paleta de Cores Marcante**:
  - `Amarelo Retro`: `#FFE600` (fundos de destaque e badges)
  - `Ciano Neon`: `#00F0FF` (links, destaques e tags)
  - `Rosa Choque`: `#FF3366` (alertas, tags de perigo e ações principais)
  - `Verde Terminal`: `#00FF66` (status ativos e terminal tickers)
  - `Preto Absoluto`: `#121212` e `#000000` (linhas, textos e contrastes)
- **Tipografia**: Headers e elementos retro utilizam fontes monospace (`Courier New`, `Fira Code`, `JetBrains Mono`), enquanto o corpo textual oferece leitura fluida.
- **Zero Frameworks JS Pesados**: Micro-interações nativas em Vanilla JavaScript com suporte a relógio UTC em tempo real, abas do Lab e feedback reativo de likes.

---

## 🛠️ Stack Tecnológica e Apps Utilizados

O monólito utiliza apenas tecnologias de alto desempenho com foco em durabilidade:

| Camada | Tecnologia / Pacote | Propósito |
| :--- | :--- | :--- |
| **Linguagem** | Python 3.11+ | Tipagem estrita, performance assíncrona moderna. |
| **Framework Web** | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | Roteamento assíncrono ultrarrápido, OpenAPI automática e handlers robustos. |
| **Template Engine** | [Jinja2](https://jinja.palletsprojects.com/) | Renderização server-side rápida, templates modulares e sem hydration delays. |
| **Banco de Dados** | SQLite 3 (`journal_mode=WAL`) | Persistência local em arquivo único, atomicidade e concorrência multithread. |
| **ORM & Modelagem** | [SQLAlchemy 2.0](https://www.sqlalchemy.org/) + [Pydantic v2](https://docs.pydantic.dev/) | Mapeamento declarativo, migrations manuais limpas e validação de payloads. |
| **Sanitização & Anti-XSS** | [Bleach](https://bleach.readthedocs.io/) + [Markdown](https://python-markdown.github.io/) | Conversão de Markdown para HTML seguro, com whitelist estrita de tags e atributos. |
| **Rate Limiting** | [SlowAPI](https://github.com/laurentS/slowapi) | Prevenção contra abusos e spam de requisições por IP nas rotas sensíveis. |
| **Auth & Criptografia** | [Passlib (Bcrypt)](https://passlib.readthedocs.io/) + [ItsDangerous](https://itsdangerous.palletsprojects.com/) | Hashing seguro de senhas com salting e cookies de sessão assinados com timestamp. |
| **E-mails Transacionais** | [aiosmtplib](https://aiosmtplib.readthedocs.io/) | Envio assíncrono de notificações de newsletter com fallback transparente para stdout. |
| **CLI & DX** | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) | Interface de linha de comando estilizada com arte ASCII Cyberpunk Samurai. |
| **Testes Automatizados** | [Pytest](https://docs.pytest.org/) + [HTTPX](https://www.python-httpx.org/) | Testes de integração, concorrência e suite de segurança ponta a ponta. |
| **Containers & Ops** | [Docker](https://www.docker.com/) + [Docker Compose](https://docs.docker.com/compose/) | Empacotamento com health checks e volumes persistentes no host. |

---

## 📁 Arquitetura do Projeto

A organização de diretórios do projeto segue o padrão monólito limpo:

```text
refugio-quilombus/
├── .env.example                     # Modelo com variáveis de ambiente do sistema
├── .gitignore                       # Ignora .env, bancos SQLite e mídias do upload
├── Dockerfile                       # Container leve com healthcheck integrado
├── docker-compose.yml               # Orquestração com volumes persistentes
├── Makefile                         # Comandos de automação para o ciclo de vida
├── Manifesto_Plano_de_Acao_O_Refugio.md # Documentação da visão do produto
├── requirements.txt                 # Dependências versionadas do ecossistema Python
│
├── config.py                        # Settings centrais com Pydantic BaseSettings
├── database.py                      # Conexão com SQLite em modo WAL e SessionLocal
├── models.py                        # Modelos SQLAlchemy (Post, User, Project, etc.)
├── schemas.py                       # Schemas Pydantic para validação e serialização
├── auth.py                          # Lógica de sessões, hash bcrypt e magic bytes
├── email_service.py                 # Envio assíncrono de e-mails transacionais
├── main.py                          # Aplicação FastAPI, rotas web, APIs e middlewares
├── init_db.py                       # Criação de tabelas e injeção de dados de seed
├── manage.py                        # CLI interativa para administração e telemetria
│
├── static/                          # Arquivos estáticos servidos pelo monólito
│   ├── css/
│   │   └── style.css                # Design System Neo-Brutalism artesanal
│   ├── js/
│   │   └── main.js                  # Micro-interações, relógio UTC e reatividade
│   └── uploads/
│       └── .gitkeep                 # Diretório de persistência de uploads locais
│
├── templates/                       # Templates HTML Jinja2
│   ├── base.html                    # Layout mestre com navegação e footer
│   ├── index.html                   # Feed principal de publicações e newsletter
│   ├── post.html                    # Visualização de post individual e comentários
│   ├── lab.html                     # Community Lab (projetos da comunidade e upvotes)
│   ├── about.html                   # Manifesto e princípios do bunker
│   ├── login.html                   # Autenticação de operadores e autores
│   ├── admin.html                   # Dashboard de gestão de conteúdo
│   ├── admin_edit.html              # Edição e publicação com live preview
│   └── 404.html                     # Página retro de erro 404 / 500
│
└── test_app.py                      # Suíte de testes automatizados (21 testes)
```

---

## 🚀 Processo de Desenvolvimento Local

### 1. Pré-requisitos
- **Python 3.11+**
- Gerenciador de pacotes **uv** (fortemente recomendado) ou **pip**
- **Git**
- **Docker** (opcional, para testes de container)

### 2. Clonando o Repositório
```bash
git clone https://github.com/andreFnicacio/refugio-quilombus.git
cd refugio-quilombus
```

### 3. Setup com Makefile (Automatizado)
O projeto possui um [Makefile](Makefile) inteligente que detecta automaticamente se você possui o `uv` instalado para otimizar o tempo de sincronização:

```bash
# Cria o ambiente virtual (.venv), instala dependências e inicializa o banco SQLite
make setup
```

Caso queira fazer manualmente:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py init
```

### 4. Executando o Servidor de Desenvolvimento
Inicie o monólito com recarregamento em tempo real (hot-reload):
```bash
make run
```
O servidor estará disponível em: **`http://localhost:8000`**

---

## 💻 Gerenciamento e CLI Interativa

O arquivo [manage.py](manage.py) implementa um utilitário CLI completo com interface estilizada via [Rich](https://rich.readthedocs.io/):

```bash
# Ver todos os comandos disponíveis
python manage.py --help

# Inicializar o banco de dados e aplicar seed data anti-tela pelada
make seed

# Exibir painel de telemetria com arte Cyberpunk Samurai
make stats

# Executar healthcheck no banco de dados e serviços
make health

# Criar um novo operador ou administrador
make superuser
```

---

## 🧪 Bateria de Testes e Validação

A estabilidade e segurança do monólito são garantidas por uma bateria de 21 testes unitários e de integração contidos em [test_app.py](test_app.py).

### Executando os Testes
Para rodar a suíte completa com relatório detalhado:
```bash
make test
```
Ou diretamente via `pytest`:
```bash
pytest -v test_app.py
```

### O que é coberto pelos testes:
- **Rotas Públicas e Renderização**: Validação de status 200 e integridade de conteúdo na Home (`/`), Sobre (`/about`), Lab (`/lab`), Post (`/post/{slug}`) e RSS Feed (`/feed.xml`).
- **Segurança & Anti-XSS**: Sanitização de scripts maliciosos injetados via Markdown ou nomes de projetos com `bleach`.
- **Prevenção de DoS (Rate Limiting)**: Disparo massivo de requisições para validação do bloqueio HTTP 429 via `slowapi`.
- **Validação de Uploads (Magic Bytes)**: Bloqueio imediato de arquivos maliciosos renomeados (ex: `.exe` ou scripts disfarçados de `.png`).
- **Concorrência SQLite WAL**: Teste com 10 threads concorrentes realizando escritas simultâneas de upvotes para assegurar que nenhum erro de `database is locked` aconteça.
- **Fluxo de Newsletter**: Inscrição, sanitização e prevenção de e-mails duplicados.
- **Proteção do Painel Administrativo**: Bloqueio de acessos não autorizados sem cookie de sessão assinado.

---

## 🐳 Deploy com Docker & FinOps

O projeto foi desenhado sob princípios de FinOps para operar com máxima eficiência de recursos:

### 1. Build e Execução com Docker Compose
```bash
# Constrói a imagem e sobe o monólito em background
docker compose up -d --build
```

### 2. Persistência de Dados no Host
O [docker-compose.yml](docker-compose.yml) utiliza bind mounts mapeando diretamente no host:
- `./blog.db`: O arquivo SQLite principal é persistido no host, evitando perda de dados na reconstrução do container.
- `./static/uploads`: Todas as imagens e capas enviadas ficam salvas na máquina física.

### 3. Verificação de Saúde (Health Check)
O container possui healthcheck nativo configurado via endpoint `/health`:
```bash
curl -I http://localhost:8000/health
```

---

## 🤝 Guia de Contribuição Open Source

Contribuições são muito bem-vindas! Este é um espaço aberto para desenvolvedores que valorizam a web aberta, monólitos elegantes e interfaces autênticas.

### 1. Princípios de Contribuição
- **Zero Bloatware**: Não adicione dependências pesadas sem uma justificativa técnica concreta.
- **Estética Coesa**: Respeite as variáveis do Design System Neo-Brutalist em [static/css/style.css](static/css/style.css).
- **Segurança em Primeiro Lugar**: Qualquer entrada de usuário refletida no HTML deve ser sanitizada com `bleach`.
- **Testes Obrigatórios**: Qualquer nova funcionalidade ou correção de bug deve acompanhar testes adicionais em [test_app.py](test_app.py).

### 2. Fluxo de Trabalho (Git Flow)

1. **Faça um Fork** do projeto no GitHub.
2. **Crie uma branch** para sua funcionalidade ou correção:
   ```bash
   git checkout -b feat/sua-feature-incrivel
   # ou
   git checkout -b fix/correcao-do-bug
   ```
3. **Escreva seu código e testes**.
4. **Valide a suíte de testes localmente**:
   ```bash
   make test
   ```
5. **Limpe caches antes de commitar**:
   ```bash
   make clean
   ```
6. **Commite suas mudanças** seguindo o padrão [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` Nova funcionalidade
   - `fix:` Correção de bug
   - `refactor:` Refatoração de código sem alteração de comportamento
   - `test:` Inclusão ou modificação de testes
   - `docs:` Alterações em documentação
   - `chore:` Atualizações de build, dependências ou ferramentas
7. **Envie um Pull Request** detalhando:
   - O que foi alterado.
   - Motivação da mudança.
   - Print da bateria de testes passando com sucesso.

---

## 📜 Licença

Distribuído sob a licença **MIT**. Veja o arquivo [LICENSE](LICENSE) para mais informações.

---

<p align="center">
  <b>⚔️ O Refúgio // Feito com independência, café forte e zero telemetria invasiva. ⚔️</b>
</p>
