import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.core.config import settings
from backend.db import repo as db
from backend.routes import admin, auth, creds, vm_jobs
from backend.routes.pages import build_pages_router
from backend.services.proxmox_client import OS_STORAGE_MAP

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="Proxmox VM Self-Service API", version="0.2.0")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

db.init_db()

# Pages
pages_router = build_pages_router(templates=templates)


@pages_router.get("/app", include_in_schema=False)
def _app_page_override(request):  # type: ignore[no-redef]
    return templates.TemplateResponse(
        request=request,
        name="app.html",
        context={"available_oses": sorted(OS_STORAGE_MAP.keys())},
    )


app.include_router(pages_router)

# API routers
app.include_router(auth.router)
app.include_router(creds.router)
app.include_router(vm_jobs.router)
app.include_router(admin.router)


@app.get("/api/os-options")
def get_os_options() -> dict:
    return {"options": sorted(OS_STORAGE_MAP.keys())}


@app.get("/api/runtime-status")
def get_runtime_status() -> dict:
    return {
        "dry_run": settings.proxmox_dry_run,
        "proxmox_base_url": settings.proxmox_base_url,
        "proxmox_node": settings.proxmox_node,
        "os_options_count": len(OS_STORAGE_MAP),
    }

