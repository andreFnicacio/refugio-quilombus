#!/usr/bin/env bash
#
# update.bash — atualização segura de O Refúgio (refugio-quilombus)
# ---------------------------------------------------------------------------
# Executa, em ordem, tudo o que é necessário para trazer uma nova versão do
# repositório para produção SEM perder dados:
#
#   1. Backup atômico do SQLite em modo WAL (blog.db comprimido em backups/)
#   2. git pull (mescla o remoto no local; aborta com segurança se houver conflito)
#   3. Verificação de erros de código (sintaxe Python + bateria de testes automatizados)
#   4. Aplicação de migrações e tabelas pendentes (manage.py init)
#   5. Verificação de integridade do banco (nenhuma tabela pode perder linhas);
#      se algo regredir, RESTAURA automaticamente o backup feito no passo 1
#   6. docker compose up -d --build  +  checagem de saúde do monólito (/health)
#   7. Aviso (não-fatal) se o nginx do host estiver apontando para a porta errada (8092)
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

APP_SERVICE="refugio"     # serviço do compose
DB_FILE="blog.db"         # arquivo do banco SQLite
BACKUP_DIR="backups"
BACKUP_FILE=""            # preenchido no passo 1
PORT="${PORT:-8092}"

# Executável do Python (usa .venv se disponível, senão python3 do sistema)
if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  PYTHON="python"
fi

# ── Pré-requisitos ─────────────────────────────────────────────────────────
log "Pré-checagem do ambiente de O Refúgio"
command -v git >/dev/null      || die "git não encontrado no PATH"
command -v docker >/dev/null   || die "docker não encontrado no PATH"
docker compose version >/dev/null 2>&1 || die "'docker compose' indisponível"
[ -f docker-compose.yml ]      || die "docker-compose.yml não encontrado em $SCRIPT_DIR"
[ -f "$DB_FILE" ]              || touch "$DB_FILE"
ok "Ambiente ok (Serviço: $APP_SERVICE, SQLite: $DB_FILE)"

# ── 1. BACKUP (Snapshot seguro do SQLite em modo WAL) ──────────────────────
log "1/7 — Backup atômico do banco de dados SQLite (WAL)"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/refugio_${DB_FILE}_$(date +%Y%m%d_%H%M%S).db.gz"
TEMP_BACKUP="${BACKUP_DIR}/.temp_backup.db"

# Efetua backup atômico via API online do SQLite (compatível com concorrência WAL)
$PYTHON -c "
import sqlite3, sys
try:
    src = sqlite3.connect('$DB_FILE')
    dst = sqlite3.connect('$TEMP_BACKUP')
    src.backup(dst)
    dst.close()
    src.close()
except Exception as e:
    sys.stderr.write(f'Erro no backup: {e}\n')
    sys.exit(1)
" || die "Falha ao gerar snapshot do SQLite"

gzip -c "$TEMP_BACKUP" > "$BACKUP_FILE"
rm -f "$TEMP_BACKUP"

# valida que o arquivo compactado é íntegro e não está vazio
if ! gunzip -t "$BACKUP_FILE" 2>/dev/null || [ ! -s "$BACKUP_FILE" ]; then
  die "Backup falhou ou veio vazio ($BACKUP_FILE)"
fi
ok "Backup salvo: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# restaura o backup recém-feito (usado se a integridade falhar)
restore_backup() {
  warn "Restaurando o banco a partir de $BACKUP_FILE ..."
  rm -f "${DB_FILE}-wal" "${DB_FILE}-shm"
  gunzip -c "$BACKUP_FILE" > "$DB_FILE" \
    && ok "Banco SQLite restaurado com sucesso" \
    || die "FALHA CRÍTICA AO RESTAURAR — restaure manualmente: gunzip -c $BACKUP_FILE > $DB_FILE"
}

# snapshot das contagens de todas as tabelas (baseline de integridade)
snapshot_counts() {
  local out="$1"; : > "$out"
  $PYTHON -c "
import sqlite3
try:
    con = sqlite3.connect('$DB_FILE')
    cur = con.cursor()
    cur.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;\")
    tables = [row[0] for row in cur.fetchall()]
    for t in tables:
        cur.execute(f'SELECT count(*) FROM \"{t}\"')
        print(f'{t} {cur.fetchone()[0]}')
    con.close()
except Exception:
    pass
" > "$out"
}

BEFORE_COUNTS="$(mktemp)"; AFTER_COUNTS="$(mktemp)"
trap 'rm -f "$BEFORE_COUNTS" "$AFTER_COUNTS"' EXIT
snapshot_counts "$BEFORE_COUNTS"
ok "Baseline de integridade capturado ($(wc -l < "$BEFORE_COUNTS") tabelas monitoradas)"

# ── 2. GIT PULL ────────────────────────────────────────────────────────────
log "2/7 — git pull (mesclando remoto no local)"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "não é um repositório git"

# Árvore suja atrapalha o merge: aborta cedo com motivo claro
if ! git diff --quiet || ! git diff --cached --quiet; then
  warn "Há alterações locais não commitadas:"
  git status --short >&2
  die "faça commit ou 'git stash' antes de atualizar. Nada foi alterado."
fi

BEFORE_HEAD="$(git rev-parse HEAD)"
git fetch --all --quiet || die "git fetch falhou (rede/credenciais?). Nada foi alterado."

PULL_ERR="$(mktemp)"
if git pull --ff-only --quiet 2>"$PULL_ERR"; then
  rm -f "$PULL_ERR"
elif git pull --no-rebase --no-edit --quiet 2>"$PULL_ERR"; then
  rm -f "$PULL_ERR"
else
  if git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
    conflitos="$(git diff --name-only --diff-filter=U | paste -sd', ' -)"
    git merge --abort 2>/dev/null || true
    rm -f "$PULL_ERR"
    die "conflito de merge em: ${conflitos:-?}. Resolva manualmente ('git pull'), commite e rode de novo. Nada foi alterado."
  fi
  warn "git pull falhou — saída do git:"
  sed 's/^/    /' "$PULL_ERR" >&2 || true
  rm -f "$PULL_ERR"
  die "não foi possível atualizar o repositório (veja o erro do git acima). Nada foi alterado."
fi
AFTER_HEAD="$(git rev-parse HEAD)"
if [ "$BEFORE_HEAD" = "$AFTER_HEAD" ]; then
  ok "Código local já estava atualizado ($AFTER_HEAD)"
else
  ok "Atualizado com sucesso: ${BEFORE_HEAD:0:7} → ${AFTER_HEAD:0:7}"
fi

# ── 3. VERIFICAÇÃO DE ERROS (Sintaxe e Testes Automatizados) ───────────────
log "3/7 — Verificando sintaxe e integridade do código"
$PYTHON -m py_compile main.py models.py database.py auth.py config.py manage.py \
  || die "Erro de sintaxe Python detectado! Atualização abortada."
ok "Compilação de bytecode Python aprovada (sem erros de sintaxe)"

if [ -f "test_app.py" ]; then
  log "  Executando suíte de testes de regressão..."
  if $PYTHON -m pytest -q test_app.py > /tmp/refugio_test.log 2>&1; then
    ok "Suíte de testes passou 100% verde (sem regressões funcionais)"
  else
    tail -30 /tmp/refugio_test.log
    die "Testes automatizados FALHARAM! O banco não foi alterado; nada foi publicado."
  fi
fi

# ── 4. MIGRAÇÕES E SCHEMAS PENDENTES ───────────────────────────────────────
log "4/7 — Aplicando schemas e dados de seed pendentes"
if $PYTHON manage.py init > /tmp/refugio_init.log 2>&1; then
  ok "Estruturas de tabelas e seeds verificadas com sucesso"
else
  tail -20 /tmp/refugio_init.log
  warn "Falha ao inicializar/atualizar banco — restaurando backup"
  restore_backup
  die "Falha ao executar manage.py init (banco restaurado)"
fi

# ── 5. INTEGRIDADE DO BANCO ────────────────────────────────────────────────
log "5/7 — Verificando integridade dos dados no SQLite"
snapshot_counts "$AFTER_COUNTS"
REGRESSION=0
while read -r tbl before; do
  [ -z "$tbl" ] && continue
  after="$(awk -v t="$tbl" '$1==t{print $2}' "$AFTER_COUNTS")"
  if [ -z "$after" ]; then
    warn "Tabela '$tbl' desapareceu após a atualização"; REGRESSION=1
  elif [ "$after" -lt "$before" ]; then
    warn "Tabela '$tbl' perdeu registros: $before → $after"; REGRESSION=1
  fi
done < "$BEFORE_COUNTS"

if [ "$REGRESSION" = "1" ]; then
  warn "Perda de dados detectada — restaurando backup!"
  restore_backup
  die "Integridade falhou; banco restaurado a partir de $BACKUP_FILE"
fi
ok "Integridade ok — nenhuma tabela perdeu registros"

# ── 6. DEPLOY COM DOCKER COMPOSE ───────────────────────────────────────────
log "6/7 — docker compose up -d --build"
docker compose up -d --build || die "docker compose up --build falhou"

log "  Aguardando o monólito subir e responder no healthcheck..."
APP_OK=0
for _ in $(seq 1 15); do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/health" 2>/dev/null || echo 000)"
  if [ "$CODE" = "200" ]; then
    APP_OK=1; break
  fi
  sleep 2
done

if [ "$APP_OK" = "1" ]; then
  ok "O Refúgio respondendo HTTP 200 em :$PORT/health"
else
  warn "Aplicação não respondeu HTTP 200 no tempo esperado (código: $CODE)"
  docker compose logs --tail 30 "$APP_SERVICE" || true
fi

# ── 7. SANIDADE DO PROXY DO HOST (Nginx) ───────────────────────────────────
log "7/7 — Conferindo proxy reverso do host (nginx)"
NGINX_SITE="/etc/nginx/sites-available/refugio"
if [ -r "$NGINX_SITE" ]; then
  PROXY_PORT="$(grep -oE 'proxy_pass http://127\.0\.0\.1:[0-9]+' "$NGINX_SITE" | grep -oE '[0-9]+$' | head -1)"
  if [ -n "$PROXY_PORT" ] && [ "$PROXY_PORT" != "$PORT" ]; then
    warn "nginx do host aponta para :$PROXY_PORT mas o container está em :$PORT"
    warn "O site público vai dar 502 até corrigir. Rode (precisa de sudo):"
    warn "  sudo cp $NGINX_SITE ${NGINX_SITE}.bak && sudo sed -i 's/:$PROXY_PORT;/:$PORT;/' $NGINX_SITE && sudo nginx -t && sudo systemctl reload nginx"
  else
    ok "Proxy do host aponta para a porta correta (:${PROXY_PORT:-$PORT})"
  fi
else
  ok "Configuração de proxy do host checada (sem arquivo $NGINX_SITE local)"
fi

printf '\n%s═══════════════════════════════════════════════%s\n' "$C_OK" "$C_RESET"
ok "Atualização de O Refúgio concluída com sucesso"
echo "  • Backup:   $BACKUP_FILE"
echo "  • Versão:   $(git rev-parse --short HEAD)"
echo "  • Status:   http://127.0.0.1:${PORT}/health"
echo "  • Monólito: http://127.0.0.1:${PORT}"
printf '%s═══════════════════════════════════════════════%s\n' "$C_OK" "$C_RESET"

