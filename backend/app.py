"""Minimal HTTP application for the repository bootstrap."""

from fastapi import FastAPI

app = FastAPI(title="FuelRoute ES")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
