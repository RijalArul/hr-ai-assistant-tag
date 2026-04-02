from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.core.config import get_settings
from app.services.redis import init_redis, close_redis
from app.api.routes.health import router as health_router

settings = get_settings()
API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_redis()
    yield
    await close_redis()


app = FastAPI(
    title="HR.ai API",
    version="0.1.0",
    description=(
        "Phase 1 HR.ai API for authentication and trust-boundary foundations. "
        "Interactive docs are available at `/docs`, and the OpenAPI schema is "
        "available at `/openapi.json` for Postman import."
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
