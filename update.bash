#!/usr/bin/env bash
#
# update.bash — atualização segura do MeuDin (meudim)
# ---------------------------------------------------------------------------
# Executa, em ordem, tudo o que é necessário para trazer uma nova versão do
# repositório para produção SEM perder dados:
#
#   1. Backup do banco (pg_dump comprimido em backups/)
#   2. git pull (mescla o remoto no local; aborta com segurança se houver conflito)
#   3. Verificação de erros de código (build do frontend / typecheck)
#   4. Aplicação de migrações pendentes (init-scripts/*.sql ainda não aplicados)
#   5. Verificação de integridade do banco (nenhuma tabela pode perder linhas);
#      se algo regredir, RESTAURA automaticamente o backup feito no passo 1
#   6. docker compose up -d --build  +  checagem de saúde dos containers
#   7. Aviso (não-fatal) se o nginx do host estiver apontando para a porta errada
#   8. Clone / espelhamento do projeto com redundância (HTTPS -> SSH -> Local)
#
# Uso:   ./update.bash
#
# Em qualquer falha o script para imediatamente (set -e) e diz exatamente o que
# deu errado. O banco só é alterado em pontos idempotentes; se a integridade
# falhar, o backup é restaurado antes de sair.
# ---------------------------------------------------------------------------

set -Eeuo pipefail

# ── Cores / logging ────────────────────────────────────────────────────────
if [ -t 1 ]; then
  C_RESET=$'\033[0m'; C_INFO=$'\033[1;34m'; C_OK=$'\033[1;32m'
  C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'
else
  C_RESET=""; C_INFO=""; C_OK=""; C_WARN=""; C_ERR=""
fi
log()  { printf '%s[ %s ]%s %s\n' "$C_INFO" "$(date '+%H:%M:%S')" "$C_RESET" "$*"; }
ok()   { printf '%s  ✓ %s%s\n' "$C_OK" "$*" "$C_RESET"; }
warn() { printf '%s  ! %s%s\n' "$C_WARN" "$*" "$C_RESET"; }
die()  { printf '%s  ✗ %s%s\n' "$C_ERR" "$*" "$C_RESET" >&2; exit 1; }

# ── Diretório do projeto (onde este script vive) ───────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DB_SERVICE="db"           # serviço do compose
BACKUP_DIR="backups"
BACKUP_FILE=""            # preenchido no passo 1

# Atalho para rodar SQL dentro do container do Postgres usando as credenciais
# que já vivem no ambiente do container (nenhum segredo fica neste script).
# `</dev/null` é essencial: sem isso, o `docker compose exec` consome o stdin
# do laço `while read` que chama o dbq (em snapshot_counts) e a iteração morre
# após a primeira linha.
dbq() { docker compose exec -T "$DB_SERVICE" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "'"$1"'"' </dev/null; }

# ── Pré-requisitos ─────────────────────────────────────────────────────────
log "Pré-checagem do ambiente"
command -v docker >/dev/null   || die "docker não encontrado no PATH"
docker compose version >/dev/null 2>&1 || die "'docker compose' indisponível"
[ -f docker-compose.yml ]      || die "docker-compose.yml não encontrado em $SCRIPT_DIR"
docker compose ps "$DB_SERVICE" --status running >/dev/null 2>&1 \
  || docker compose ps | grep -q finance_db \
  || die "container do banco ($DB_SERVICE) não está rodando — suba a stack antes de atualizar"
ok "Ambiente ok"

# ── 1. BACKUP ──────────────────────────────────────────────────────────────
log "1/7 — Backup do banco de dados"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/finance_app_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose exec -T "$DB_SERVICE" sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
  | gzip > "$BACKUP_FILE"
# valida que o dump não veio vazio/corrompido
if ! gunzip -t "$BACKUP_FILE" 2>/dev/null || [ ! -s "$BACKUP_FILE" ]; then
  die "Backup falhou ou veio vazio ($BACKUP_FILE)"
fi
ok "Backup salvo: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# restaura o backup recém-feito (usado se a integridade falhar)
restore_backup() {
  warn "Restaurando o banco a partir de $BACKUP_FILE ..."
  gunzip -c "$BACKUP_FILE" \
    | docker compose exec -T "$DB_SERVICE" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    >/dev/null 2>&1 \
    && ok "Backup restaurado" \
    || die "FALHA AO RESTAURAR — restaure manualmente: gunzip -c $BACKUP_FILE | docker compose exec -T $DB_SERVICE psql ..."
}

# snapshot das contagens de todas as tabelas públicas (baseline de integridade)
snapshot_counts() {
  local out="$1"; : > "$out"
  local tables; tables="$(dbq "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")"
  local t c
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    c="$(dbq "SELECT count(*) FROM \"$t\"")"
    printf '%s %s\n' "$t" "$c" >> "$out"
  done <<< "$tables"
}

BEFORE_COUNTS="$(mktemp)"; AFTER_COUNTS="$(mktemp)"
trap 'rm -f "$BEFORE_COUNTS" "$AFTER_COUNTS"' EXIT
snapshot_counts "$BEFORE_COUNTS"
ok "Baseline de integridade capturado ($(wc -l < "$BEFORE_COUNTS") tabelas)"

# ── 2. GIT PULL ────────────────────────────────────────────────────────────
log "2/7 — git pull (mesclando remoto no local)"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "não é um repositório git"

# Árvore suja atrapalha o merge: aborta cedo com um motivo claro em vez de
# deixar o `git pull` falhar de forma críptica no meio do caminho.
if ! git diff --quiet || ! git diff --cached --quiet; then
  warn "Há alterações locais não commitadas:"
  git status --short >&2
  die "faça commit ou 'git stash' antes de atualizar. Nada foi alterado."
fi

BEFORE_HEAD="$(git rev-parse HEAD)"
git fetch --all --quiet || die "git fetch falhou (rede/credenciais?). Nada foi alterado."

# Estratégia: tenta fast-forward; se não der (branches divergiram), faz um merge
# EXPLÍCITO. `--no-rebase` é obrigatório — a partir do git 2.27 um pull com branches
# divergentes ABORTA ("Need to specify how to reconcile divergent branches") a menos
# que a estratégia seja explícita, independentemente da config `pull.*` do host.
#
# O stderr do git é capturado (não descartado) para que a causa REAL apareça: antes,
# tudo virava um genérico "conflito de merge" — inclusive quando não havia conflito
# nenhum (era só a divergência acima), o que mascarava o problema.
PULL_ERR="$(mktemp)"
if git pull --ff-only --quiet 2>"$PULL_ERR"; then
  rm -f "$PULL_ERR"
elif git pull --no-rebase --no-edit --quiet 2>"$PULL_ERR"; then
  rm -f "$PULL_ERR"
else
  # Merge iniciado mas não concluído ⇒ conflito de conteúdo real: aborta e lista os arquivos.
  if git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
    conflitos="$(git diff --name-only --diff-filter=U | paste -sd', ' -)"
    git merge --abort 2>/dev/null || true
    rm -f "$PULL_ERR"
    die "conflito de merge em: ${conflitos:-?}. Resolva manualmente ('git pull'), commite e rode de novo. Nada foi alterado."
  fi
  # Qualquer outra falha (rede, credencial, ref protegida, etc.): mostra o erro REAL do git.
  warn "git pull falhou — saída do git:"
  sed 's/^/    /' "$PULL_ERR" >&2 || true
  rm -f "$PULL_ERR"
  die "não foi possível atualizar o repositório (veja o erro do git acima). Nada foi alterado."
fi
AFTER_HEAD="$(git rev-parse HEAD)"
if [ "$BEFORE_HEAD" = "$AFTER_HEAD" ]; then
  ok "Já estava atualizado ($AFTER_HEAD)"
else
  ok "Atualizado: ${BEFORE_HEAD:0:7} → ${AFTER_HEAD:0:7}"
fi

# ── 3. VERIFICAÇÃO DE ERROS (build / typecheck do frontend) ────────────────
log "3/7 — Verificando erros na atualização (build do frontend)"
if command -v npm >/dev/null 2>&1; then
  if [ ! -d node_modules ]; then
    log "  Instalando dependências (npm ci)..."
    npm ci >/dev/null 2>&1 || npm install >/dev/null 2>&1 || die "npm install falhou"
  fi
  if ! npm run build > /tmp/meudim_build.log 2>&1; then
    tail -30 /tmp/meudim_build.log
    die "Build do frontend FALHOU — veja o erro acima. O banco não foi alterado; nada foi publicado."
  fi
  ok "Build do frontend passou (sem erros de tipo/compilação)"
else
  warn "npm não disponível no host — pulando build local (o build roda no docker)"
fi

# ── 4. MIGRAÇÕES PENDENTES ─────────────────────────────────────────────────
log "4/7 — Aplicando migrações pendentes (init-scripts)"
# Tabela de controle das migrações já aplicadas.
dbq "CREATE TABLE IF NOT EXISTS applied_init_scripts (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())" >/dev/null
# Bootstrap: se a tabela está vazia, assume que os init-scripts ATUAIS já foram
# aplicados (volume novo → docker-entrypoint rodou todos; volume existente →
# já estavam lá). A partir daí, só migrações NOVAS (ex.: 16-*.sql) são aplicadas.
TRACKED_COUNT="$(dbq "SELECT count(*) FROM applied_init_scripts")"
if [ "${TRACKED_COUNT:-0}" = "0" ]; then
  warn "Primeira execução: registrando init-scripts atuais como já aplicados"
  for f in init-scripts/*.sql; do
    [ -e "$f" ] || continue
    bn="$(basename "$f")"
    dbq "INSERT INTO applied_init_scripts(filename) VALUES ('$bn') ON CONFLICT DO NOTHING" >/dev/null
  done
fi
APPLIED_ANY=0
for f in $(ls -1 init-scripts/*.sql 2>/dev/null | sort); do
  bn="$(basename "$f")"
  already="$(dbq "SELECT 1 FROM applied_init_scripts WHERE filename='$bn'")"
  [ "$already" = "1" ] && continue
  log "  Aplicando $bn ..."
  if docker compose exec -T "$DB_SERVICE" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < "$f" >/tmp/meudim_mig.log 2>&1; then
    dbq "INSERT INTO applied_init_scripts(filename) VALUES ('$bn') ON CONFLICT DO NOTHING" >/dev/null
    ok "  $bn aplicada"
    APPLIED_ANY=1
  else
    tail -20 /tmp/meudim_mig.log
    warn "Migração $bn FALHOU — restaurando banco e abortando"
    restore_backup
    die "Falha ao aplicar $bn (banco restaurado ao estado do backup)"
  fi
done
[ "$APPLIED_ANY" = "0" ] && ok "Nenhuma migração pendente" || ok "Migrações pendentes aplicadas"

# ── 5. INTEGRIDADE DO BANCO ────────────────────────────────────────────────
log "5/7 — Verificando integridade do banco"
snapshot_counts "$AFTER_COUNTS"
REGRESSION=0
while read -r tbl before; do
  after="$(awk -v t="$tbl" '$1==t{print $2}' "$AFTER_COUNTS")"
  # tabela sumiu ou perdeu linhas em relação ao baseline ⇒ regressão
  if [ -z "$after" ]; then
    warn "Tabela '$tbl' desapareceu após a atualização"; REGRESSION=1
  elif [ "$after" -lt "$before" ]; then
    warn "Tabela '$tbl' perdeu linhas: $before → $after"; REGRESSION=1
  fi
done < "$BEFORE_COUNTS"
if [ "$REGRESSION" = "1" ]; then
  warn "Perda de dados detectada — restaurando backup"
  restore_backup
  die "Integridade falhou; banco restaurado a partir de $BACKUP_FILE"
fi
ok "Integridade ok — nenhuma tabela perdeu dados"

# ── 6. DEPLOY ──────────────────────────────────────────────────────────────
log "6/7 — docker compose up -d --build"
docker compose up -d --build || die "docker compose up --build falhou"
# aguarda o backend reportar saúde nos logs
log "  Aguardando o backend subir..."
BACKEND_OK=0
for _ in $(seq 1 20); do
  if docker compose logs --tail 50 backend 2>/dev/null | grep -qiE "Connected to PostgreSQL|Server running on port"; then
    BACKEND_OK=1; break
  fi
  sleep 2
done
if docker compose logs --tail 80 backend 2>/dev/null | grep -qiE "error|exception|ECONNREFUSED|does not exist"; then
  warn "Possíveis erros nos logs do backend:"
  docker compose logs --tail 80 backend 2>/dev/null | grep -iE "error|exception|ECONNREFUSED|does not exist" | tail -10
fi
[ "$BACKEND_OK" = "1" ] && ok "Backend respondendo" || warn "Backend não confirmou saúde nos logs (verifique manualmente)"

# health check HTTP na porta publicada do frontend
FE_PORT="$(docker compose port frontend 80 2>/dev/null | sed 's/.*://')"
if [ -n "${FE_PORT:-}" ]; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${FE_PORT}/" || echo 000)"
  [ "$CODE" = "200" ] && ok "Frontend HTTP 200 em :$FE_PORT" || warn "Frontend respondeu HTTP $CODE em :$FE_PORT"
fi

# ── 7. SANIDADE DO PROXY DO HOST (apenas aviso) ────────────────────────────
log "7/7 — Conferindo proxy reverso do host (nginx)"
NGINX_SITE="/etc/nginx/sites-available/meudim"
if [ -n "${FE_PORT:-}" ] && [ -r "$NGINX_SITE" ]; then
  PROXY_PORT="$(grep -oE 'proxy_pass http://127\.0\.0\.1:[0-9]+' "$NGINX_SITE" | grep -oE '[0-9]+$' | head -1)"
  if [ -n "$PROXY_PORT" ] && [ "$PROXY_PORT" != "$FE_PORT" ]; then
    warn "nginx do host aponta para :$PROXY_PORT mas o container está em :$FE_PORT"
    warn "O site público vai dar 502 até corrigir. Rode (precisa de sudo):"
    warn "  sudo cp $NGINX_SITE ${NGINX_SITE}.bak && sudo sed -i 's/:$PROXY_PORT;/:$FE_PORT;/' $NGINX_SITE && sudo nginx -t && sudo systemctl reload nginx"
  else
    ok "Proxy do host aponta para a porta correta (:${PROXY_PORT:-?})"
  fi
else
  warn "Não foi possível ler $NGINX_SITE (sem permissão?) — confira o proxy manualmente"
fi

printf '\n%s═══════════════════════════════════════════════%s\n' "$C_OK" "$C_RESET"
ok "Atualização concluída com sucesso"
echo "  • Backup:   $BACKUP_FILE"
echo "  • Versão:   $(git rev-parse --short HEAD)"
echo "  • Frontend: http://127.0.0.1:${FE_PORT:-?}"
printf '%s═══════════════════════════════════════════════%s\n' "$C_OK" "$C_RESET"

# ── 8. CLONE COM REDUNDÂNCIA (Espelho de Backup do Projeto) ────────────────
log "8/8 — Sincronizando clone com redundância do projeto (refugio-quilombus)"

# URLs com redundância (HTTPS primário, SSH como fallback secundário)
REPO_URL_HTTPS="https://github.com/andreFnicacio/refugio-quilombus.git"
REPO_URL_SSH="git@github.com:andreFnicacio/refugio-quilombus.git"
CLONE_TARGET_DIR="${REDUNDANT_CLONE_DIR:-../refugio-quilombus-mirror}"

clone_project_with_redundancy() {
  local target="$1"

  if [ -d "$target/.git" ]; then
    log "  Repositório redundante já existe em '$target'. Atualizando..."
    (
      cd "$target"
      git fetch --all --quiet 2>/dev/null || true
      if git pull --no-rebase --quiet 2>/dev/null; then
        ok "Repositório redundante atualizado em $target"
        return 0
      fi
      warn "Pull no repositório existente falhou. Tentando re-sincronizar remotos..."
    )
  fi

  mkdir -p "$(dirname "$target")"

  # Tentativa 1: Clone via HTTPS
  log "  [1/3] Tentando clone via HTTPS ($REPO_URL_HTTPS)..."
  if git clone --depth 50 "$REPO_URL_HTTPS" "$target" 2>/dev/null; then
    ok "Clone redundante concluído via HTTPS em: $target"
    return 0
  fi
  warn "Tentativa 1 (HTTPS) falhou."

  # Tentativa 2: Redundância via SSH
  log "  [2/3] Tentando redundância via SSH ($REPO_URL_SSH)..."
  if git clone --depth 50 "$REPO_URL_SSH" "$target" 2>/dev/null; then
    ok "Clone redundante concluído via SSH em: $target"
    return 0
  fi
  warn "Tentativa 2 (SSH) falhou."

  # Tentativa 3: Redundância local a partir do workspace atual
  log "  [3/3] Tentando clone a partir do workspace local ($SCRIPT_DIR)..."
  if git clone --depth 50 "$SCRIPT_DIR" "$target" 2>/dev/null; then
    ok "Clone redundante concluído a partir do repositório local em: $target"
    return 0
  fi

  warn "Aviso: Todas as tentativas de clone redundante falharam (rede/permissão)."
  return 1
}

clone_project_with_redundancy "$CLONE_TARGET_DIR" || warn "Clone com redundância finalizado com avisos (veja logs acima)."
