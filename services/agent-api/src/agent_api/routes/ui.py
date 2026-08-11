from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()
TEMPLATE = Path(__file__).parents[1] / "web" / "templates" / "chat.html"


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def manager_ui() -> HTMLResponse:
    return HTMLResponse(
        TEMPLATE.read_text(),
        headers={
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self'; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            ),
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )
