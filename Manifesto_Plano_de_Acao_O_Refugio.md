# MANIFESTO & PLANO DE AÇÃO (REVISADO & EXPANDIDO): O REFÚGIO (Indie Blog & Community Hub)

## Índice

1. Visão Geral e Filosofia do Projeto  
2. Identidade Visual & Design System (Neo-Brutalism / Retrô 16-bits)  
3. Arquitetura Técnica & Configuração de Ambiente  
4. Estrutura de Pastas Oficial do Monolito  
5. Esquema do Banco de Dados (Database Schema)  
6. Segurança, Autenticação e Gestão de Sessões  
7. Funcionalidades Core & Regras de Negócio Avançadas (Uploads, Paginação, Anti-Spam)  
8. Sistema de Notificações via Gmail (Background Tasks)  
9. Inicialização Automática e Seed Data (Anti-Tela Pelada)  
10. Diretrizes Finais para a IA (Antigravity/Gemini)

---

## 1\. Visão Geral e Filosofia do Projeto

O **Refúgio** é um espaço autoral, independente e fora dos grilhões de algoritmos de grandes redes sociais. Funciona como um monolito enxuto construído sob a filosofia da *IndieWeb*. Seus pilares são:

* **Diário de Bordo Pessoal:** Acompanhamento da saga dos 28 anos (amadurecimento, transição profissional, saúde e rotina).  
* **Hobbies & Cultura:** Textos reflexivos sobre mangás, filmes, jogos e experiências cotidianas.  
* **Laboratório & Hub da Comunidade:** Espaço colaborativo para amigos e desenvolvedores publicarem projetos open-source, scripts e minijogos, contando com sistema de contagem de cliques, ranking (Top 5\) e moderação.

---

## 2\. Identidade Visual & Design System (Neo-Brutalism / Retrô 16-bits)

Para evitar o visual genérico e a frieza do minimalismo estéril corporativo, a interface combina o **Neo-Brutalismo** com a nostalgia aconchegante da internet dos anos 90/2000 e a robustez dos jogos 16-bits.

* **Paleta de Cores:**  
  * Fundo: Tons escuros profundos (`#0a0e17` / `#0d0d0d`) simulando terminais de alta performance.  
  * Destaques/Bordas: Bordas sólidas (1px a 2px) em verde terminal (`#00ff66`), âmbar clássico (`#ffb000`) ou neon ciberespaço.  
* **Tipografia:**  
  * Títulos e Elementos de UI: Fontes monoespaçadas ou pixeladas (*JetBrains Mono*, *VT323* ou *Share Tech Mono*).  
  * Textos Corridos: Tipografia limpa de altíssima legibilidade (*Inter* ou *Lora* para dar o toque de diário clássico).  
* **Detalhes de Interface:** Botões com efeito físico de clique (deslocamento de 1px), janelas modais estruturadas, widget de terminal de status no topo e contador de visitas digital no rodapé.

---

## 3\. Arquitetura Técnica & Configuração de Ambiente

* **Backend:** Python 3.10+ com **FastAPI** (assíncrono, estruturado e performático).  
* **Banco de Dados:** **SQLite** (armazenado em um único arquivo `.db`, permitindo backups instantâneos).  
* **Template Engine:** **Jinja2** integrado nativamente, complementado com HTML/CSS puro e leves toques de Alpine.js ou Vanilla JS para interações dinâmicas.  
* **Configuração de Variáveis (`.env`):** Uso obrigatório de `pydantic-settings` ou `python-dotenv` para gerenciar segredos (credenciais de admin, senha de app do Gmail, chaves de sessão).

---

## 4\. Estrutura de Pastas Oficial do Monolito

refugio\_blog/

│

├── .env                 \# Variáveis de ambiente sensíveis (IGNORAR NO GIT)

├── .env.example         \# Exemplo de configuração de ambiente

├── main.py              \# Inicialização do FastAPI e registro de rotas

├── database.py          \# Configuração da sessão do SQLite (SQLAlchemy)

├── models.py            \# Definição das tabelas do banco de dados

├── schemas.py           \# Validação e serialização de dados (Pydantic)

├── email\_service.py     \# Lógica assíncrona de disparo via SMTP do Gmail

│

├── templates/           \# Templates HTML (Jinja2)

│   ├── base.html        \# Layout global (Header, Footer, Estilos e Terminal de Status)

│   ├── index.html       \# Timeline / Diário de Bordo (Feed com paginação)

│   ├── post.html        \# Leitura de post individual \+ Seção de Comentários

│   ├── lab.html         \# O Laboratório da Comunidade \+ Top 5 \+ Modal de Envio

│   └── admin.html       \# Painel de Administração Protegido (CRUD e Moderação)

│

├── static/              \# Arquivos estáticos

│   ├── css/             \# Folhas de estilo (Neo-Brutalism / Retrô)

│   ├── js/              \# Scripts leves de interatividade (Modais, cliques)

│   └── uploads/         \# Armazenamento local seguro para mídias do admin

│

├── requirements.txt     \# Dependências (fastapi, uvicorn, sqlalchemy, jinja2, pydantic-settings, passlib, bcrypt)

└── blog.db              \# Banco de dados SQLite

---

## 5\. Esquema do Banco de Dados (Database Schema)

1. **Tabela `users` (Administradores):**  
     
   * `id` (Integer, Primary Key)  
   * `username` (String, Unique)  
   * `password_hash` (String \- Criptografado com Bcrypt/Passlib)

   

2. **Tabela `posts` (Diário de Bordo & Hobbies):**  
     
   * `id` (Integer, Primary Key)  
   * `title` (String)  
   * `slug` (String, Unique \- gerado automaticamente para URLs amigáveis)  
   * `content` (Text \- Suporta HTML rico ou Markdown renderizado)  
   * `category` (String \- ex: "Saga dos 28", "Mangás", "Dev & Tech")  
   * `media_url` (String, Nullable \- Imagem ou vídeo de capa)  
   * `views_count` (Integer, Default 0\)  
   * `created_at` (DateTime)  
   * `updated_at` (DateTime)

   

3. **Tabela `community_submissions` (O Laboratório / Repositórios):**  
     
   * `id` (Integer, Primary Key)  
   * `author_name` (String)  
   * `author_email` (String)  
   * `github_link` (String)  
   * `title` (String)  
   * `category` (String \- ex: "Jogos 2D", "Ferramentas de IA", "Scripts Úteis")  
   * `description` (Text)  
   * `image_url` (String, Nullable)  
   * `status` (String \- 'pending', 'approved', 'rejected')  
   * `clicks_count` (Integer, Default 0\)  
   * `created_at` (DateTime)

   

4. **Tabela `comments` (Comentários nos Posts):**  
     
   * `id` (Integer, Primary Key)  
   * `post_id` (Integer, Foreign Key \-\> posts.id, Cascade Delete)  
   * `author_name` (String)  
   * `author_email` (String)  
   * `content` (Text)  
   * `notify_replies` (Boolean, Default False)  
   * `created_at` (DateTime)

---

## 6\. Segurança, Autenticação e Gestão de Sessões

* **Proteção do Admin:** O acesso à rota `/admin` e às rotas de mutação (Criar, Editar, Excluir, Aprovar) deve ser estritamente protegido por **Cookies HTTP-only** assinados ou tokens de sessão seguros verificados por dependências do FastAPI (`Depends`).  
* **Segurança de Senhas:** Senhas nunca devem ser salvas em texto plano; utilizar `passlib` com o algoritmo `bcrypt`.  
* **Validação de Uploads:** Na área administrativa, uploads de imagens em `/static/uploads/` devem validar a extensão do arquivo (somente `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`) e limitar o tamanho máximo para evitar exaustão de armazenamento do servidor.

---

## 7\. Funcionalidades Core & Regras de Negócio Avançadas

* **Timeline e Paginação:** A página inicial não deve carregar todos os posts de uma vez se o volume crescer; implementar paginação simples baseada em offset/limite (ex: 10 posts por página) ou scroll infinito leve.  
* **Sistema de Cliques & Top 5:** Cada redirecionamento ou clique em um projeto do laboratório incrementa o `clicks_count`. A query de ranking deve ser otimizada: `SELECT * FROM community_submissions WHERE status = 'approved' ORDER BY clicks_count DESC LIMIT 5;`.  
* **Proteção Anti-Spam Básica (Honeypot):** No formulário de submissão da comunidade e nos comentários, adicionar um campo invisível (honeypot) para bloquear bots automáticos de spam sem precisar de CAPTCHAs complexos que estragam a experiência do usuário.

---

## 8\. Sistema de Notificações via Gmail (Background Tasks)

* **Assincronicidade:** O envio de e-mails de notificação de resposta a comentários deve utilizar o recurso `BackgroundTasks` do FastAPI. Isso garante que a resposta ao usuário seja instantânea, sem travamentos caso o servidor SMTP demore a responder.  
* **Configuração SMTP:** Conectado via porta TLS do Gmail utilizando uma **Senha de Aplicativo** (App Password) gerada na conta Google, mantendo as credenciais seguras no arquivo `.env`.

---

## 9\. Inicialização Automática e Seed Data (Anti-Tela Pelada)

* **Script de Startup (`init_db.py` ou rotina de inicialização):**  
  * Verifica se o banco de dados e as tabelas existem.  
  * Cria automaticamente o usuário administrador padrão utilizando as credenciais definidas no `.env` caso não exista nenhum usuário cadastrado.  
  * Injeção automática do **"Post Manifesto de Inauguração"** na primeira execução, acompanhado de uma referência visual nostálgica permanente.  
  * O site nasce pronto, funcional e com alma, mesmo antes do primeiro post manual.

---

## 10\. Diretrizes Finais para a IA (Antigravity/Gemini)

* **Flexibilidade Iterativa:** Este plano atua como uma diretriz viva. Durante a geração de código, o modelo tem liberdade criativa para estruturar CSS responsivo, ajustar rotas auxiliares e refinar os templates Jinja2 para atingir o design perfeito.  
* **Simplicidade com Qualidade:** Manter o monolito limpo, documentado e modular, priorizando a robustez e a facilidade de manutenção a longo prazo.