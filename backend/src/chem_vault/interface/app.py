"""FastAPI application factory with Sentinel auth, DI container, and error handlers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chem_vault.infrastructure.di.container import create_container
from chem_vault.infrastructure.sentinel.auth import create_sentinel
from chem_vault.interface.error_handlers import register_error_handlers

sentinel = create_sentinel()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App lifespan — initialize container, register Sentinel actions, cleanup."""
    # Initialize DI container and attach to app state
    container = create_container()
    app.state.container = container

    # Delegate to Sentinel's lifespan (registers service actions, fetches JWKS)
    async with sentinel.lifespan(app):
        yield

    # Cleanup: dispose the database engine
    from sqlalchemy.ext.asyncio import AsyncEngine

    engine = container[AsyncEngine]
    await engine.dispose()


def create_app() -> FastAPI:
    """Build the FastAPI application with auth, CORS, DI, and error handling."""
    app = FastAPI(
        title="Chem-Vault",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # Auth middleware — validates IdP + Sentinel authz tokens
    sentinel.protect(
        app,
        exclude_paths=["/health", "/docs", "/openapi.json"],
    )

    # CORS — added last so it runs first (LIFO)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Domain error → HTTP response mapping
    register_error_handlers(app)

    # Routes
    from chem_vault.interface.routes.user import router as user_router

    app.include_router(user_router)

    # Health check (unauthenticated)
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
