.PHONY: api api-install api-test bot bot-install web web-install migrate seed seed-reset install lint help

ROOT_VENV_PY := .venv/Scripts/python.exe
API_VENV_PY := apps/api/.venv/Scripts/python.exe

ifeq ($(wildcard $(ROOT_VENV_PY)),$(ROOT_VENV_PY))
PYTHON := $(abspath $(ROOT_VENV_PY))
else ifeq ($(wildcard $(API_VENV_PY)),$(API_VENV_PY))
PYTHON := $(abspath $(API_VENV_PY))
else
PYTHON := python
endif

# ─── API ──────────────────────────────────────────────────────────────────────
api:
	cd apps/api && "$(PYTHON)" -m uvicorn main:app --reload --port 8000

api-install:
	"$(PYTHON)" -m pip install -r apps/api/requirements.txt

api-test:
	cd apps/api && "$(PYTHON)" -m unittest discover -s tests -v

# ─── Bot ──────────────────────────────────────────────────────────────────────
bot:
	cd apps/bot && "$(PYTHON)" main.py

bot-install:
	"$(PYTHON)" -m pip install -r apps/bot/requirements.txt

# ─── Web ──────────────────────────────────────────────────────────────────────
web:
	npm --prefix apps/web run dev

web-install:
	cd apps/web && npm install

# ─── Database ─────────────────────────────────────────────────────────────────
migrate:
	"$(PYTHON)" scripts/migrate.py

seed:
	"$(PYTHON)" scripts/seed.py

seed-reset:
	"$(PYTHON)" scripts/seed.py --reset

# ─── Install all ──────────────────────────────────────────────────────────────
install: api-install bot-install web-install

# ─── Help ─────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  make api          Start FastAPI dev server (port 8000)"
	@echo "  make api-install  Install API dependencies using the preferred project venv"
	@echo "  make api-test     Run API tests using the preferred project venv"
	@echo "  make bot          Start Discord bot"
	@echo "  make web          Start Next.js dev server"
	@echo "  make migrate      Run database migration"
	@echo "  make install      Install all dependencies"
	@echo "  python interpreter: $(PYTHON)"
	@echo ""
