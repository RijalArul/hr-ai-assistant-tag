from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.actions import router as actions_router
from app.api.routes.auth import router as auth_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.rules import router as rules_router
from app.api.routes.webhooks import router as webhooks_router
from app.core.config import get_settings
from app.services.cache import init_cache_registry, close_cache_registry
from app.services.redis import init_redis, close_redis
from app.api.routes.health import router as health_router

settings = get_settings()
API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_cache_registry()
    await init_redis()
    yield
    close_cache_registry()
    await close_redis()


app = FastAPI(
    title="HR.ai API",
    version="0.1.0",
    description=(
        "HR.ai API currently includes Phase 1 trust-boundary foundations, "
        "Phase 2 action-engine surfaces for actions, rules, and webhooks, "
        "and a Phase 4 conversations API that invokes the internal Phase 3 "
        "orchestrator. Interactive docs are available at `/docs`, and the "
        "OpenAPI schema is available at `/openapi.json` for Postman import."
    ),
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=API_PREFIX)
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(conversations_router, prefix=API_PREFIX)
app.include_router(actions_router, prefix=API_PREFIX)
app.include_router(rules_router, prefix=API_PREFIX)
app.include_router(webhooks_router, prefix=API_PREFIX)
