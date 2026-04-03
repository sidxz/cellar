"""FastAPI application factory with Sentinel auth middleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chem_vault.infrastructure.sentinel.auth import create_sentinel

sentinel = create_sentinel()


def create_app() -> FastAPI:
    """Build the FastAPI application with auth, CORS, and routes."""
    app = FastAPI(
        title="Chem-Vault",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=sentinel.lifespan,
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

    # Health check (unauthenticated)
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
