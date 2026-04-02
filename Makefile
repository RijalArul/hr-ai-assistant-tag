.PHONY: api bot web migrate install lint help

# ─── API ──────────────────────────────────────────────────────────────────────
api:
	cd apps/api && uvicorn app.main:app --reload --port 8000

api-install:
	cd apps/api && pip install -r requirements.txt

# ─── Bot ──────────────────────────────────────────────────────────────────────
bot:
	cd apps/bot && python main.py

bot-install:
	cd apps/bot && pip install -r requirements.txt

# ─── Web ──────────────────────────────────────────────────────────────────────
web:
	npm --prefix apps/web run dev

web-install:
	cd apps/web && npm install

# ─── Database ─────────────────────────────────────────────────────────────────
migrate:
	python scripts/migrate.py

# ─── Install all ──────────────────────────────────────────────────────────────
install: api-install bot-install web-install

# ─── Help ─────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  make api          Start FastAPI dev server (port 8000)"
	@echo "  make bot          Start Discord bot"
	@echo "  make web          Start Next.js dev server"
	@echo "  make migrate      Run database migration"
	@echo "  make install      Install all dependencies"
	@echo ""
