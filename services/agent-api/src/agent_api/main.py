from __future__ import annotations

from fastapi import FastAPI

from agent_api.routes.risks import router as risk_router

app = FastAPI(title="Workforce Risk Agent API", version="0.1.0")
app.include_router(risk_router)


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "live"}
