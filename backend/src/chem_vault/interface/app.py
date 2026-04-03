from fastapi import FastAPI

app = FastAPI(
    title="Chem-Vault",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
