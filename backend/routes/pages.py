from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.services.proxmox_client import OS_STORAGE_MAP


def build_pages_router(*, templates) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    def home() -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=302)

    @router.get("/login", response_class=HTMLResponse)
    def login_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="login.html", context={})

    @router.get("/register", response_class=HTMLResponse)
    def register_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request, name="register.html", context={}
        )

    @router.get("/app", response_class=HTMLResponse)
    def app_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="app.html",
            context={"available_oses": sorted(OS_STORAGE_MAP.keys())},
        )

    @router.get("/creds", response_class=HTMLResponse)
    def creds_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="creds.html", context={})

    return router

