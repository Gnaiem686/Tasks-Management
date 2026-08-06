from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent_api.routes.risks import router as risk_router
from agent_api.routes.ui import router as ui_router

app = FastAPI(title="Workforce Risk Agent API", version="0.1.0")
app.include_router(risk_router)
app.include_router(ui_router)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "web" / "static"),
    name="static",
)


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "live"}
