import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.core.config import settings
from backend.db import repo as db
from backend.routes import admin, auth, creds, vm_jobs
from backend.routes.pages import build_pages_router
PROJECT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

app = FastAPI(title="Proxmox VM Self-Service API", version="0.2.0")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

db.init_db()

# Pages
pages_router = build_pages_router(templates=templates)


app.include_router(pages_router)

# API routers
app.include_router(auth.router)
app.include_router(creds.router)
app.include_router(vm_jobs.router)
app.include_router(admin.router)


@app.get("/api/os-options")
def get_os_options() -> dict:
    from backend.services.proxmox_client import OS_STORAGE_MAP

    return {"options": sorted(OS_STORAGE_MAP.keys())}


@app.get("/api/runtime-status")
def get_runtime_status() -> dict:
    from backend.services.proxmox_client import OS_STORAGE_MAP

    return {
        "dry_run": settings.proxmox_dry_run,
        "proxmox_base_url": settings.proxmox_base_url,
        "proxmox_node": settings.proxmox_node,
        "os_options_count": len(OS_STORAGE_MAP),
    }

