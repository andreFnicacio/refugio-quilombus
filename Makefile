.PHONY: help setup venv run seed stats health superuser test clean

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

UV := $(shell command -v uv 2> /dev/null)

help:
	@echo "=========================================================="
	@echo "⚔️  O REFÚGIO // MAKEFILE DE AUTOMAÇÃO (INDIEWEB 2026) ⚔️ "
	@echo "=========================================================="
	@echo "Comandos disponíveis:"
	@echo "  make setup       - Prepara ambiente virtual (.venv) e instala dependências"
	@echo "  make run         - Inicia o servidor FastAPI com hot-reload"
	@echo "  make seed        - Inicializa banco SQLite e aplica seed data anti-tela pelada"
	@echo "  make stats       - Exibe telemetria do monólito com arte Cyberpunk"
	@echo "  make health      - Executa verificação de saúde do banco e serviços"
	@echo "  make superuser   - Cria um novo usuário operador administrador"
	@echo "  make test        - Roda os testes automatizados da aplicação"
	@echo "  make clean       - Limpa caches e arquivos temporários"
	@echo "=========================================================="

setup: venv
ifdef UV
	@echo ">> Detectado UV. Sincronizando dependências com alta velocidade..."
	uv pip install -r requirements.txt
else
	@echo ">> UV não encontrado no PATH. Instalando via pip tradicional..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
endif
	@if [ ! -f .env ]; then cp .env.example .env && echo ">> .env criado a partir de .env.example"; fi
	@$(PYTHON) manage.py init
	@echo ">> Setup completo com sucesso!"

venv:
	@if [ ! -d $(VENV) ]; then \
		echo ">> Criando ambiente virtual oculto ($(VENV))..."; \
		python3 -m venv $(VENV); \
	fi

run:
	@$(PYTHON) manage.py run

seed:
	@$(PYTHON) manage.py init

stats:
	@$(PYTHON) manage.py stats

health:
	@$(PYTHON) manage.py health

superuser:
	@$(PYTHON) manage.py createsuperuser

test:
	@$(PYTHON) -m pytest -v test_app.py

clean:
	@echo ">> Limpando caches..."
	rm -rf __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo ">> Limpeza concluída!"
