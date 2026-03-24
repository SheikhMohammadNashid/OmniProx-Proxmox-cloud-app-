import json

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db
from app.auth import create_access_token, get_current_user, hash_password, require_admin, verify_password
from app.config import settings
from app.models import (
    TokenResponse,
    UserRegisterRequest,
    VMCreateRequest,
    VMCreateResponse,
    VMJobCreateResponse,
)
from app.proxmox_client import OS_STORAGE_MAP, ProxmoxClient

app = FastAPI(title="Proxmox VM Self-Service API", version="0.1.0")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

db.init_db()


def get_proxmox_client() -> ProxmoxClient:
    return ProxmoxClient()


def _run_vm_job(job_id: int, payload: VMCreateRequest) -> None:
    client_factory = app.dependency_overrides.get(get_proxmox_client, ProxmoxClient)
    client = client_factory()
    db.update_vm_job(job_id, status="running")
    try:
        result = client.create_vm(
            vmid=payload.hardware.vmid,
            name=payload.hardware.name,
            cores=payload.hardware.cores,
            sockets=payload.hardware.sockets,
            cpu_type=payload.hardware.cpu_type,
            cpu_limit=payload.hardware.cpu_limit,
            cpu_units=payload.hardware.cpu_units,
            memory_mb=payload.hardware.memory_mb,
            balloon_mb=payload.hardware.balloon_mb,
            disk_gb=payload.hardware.disk_gb,
            storage=payload.hardware.storage,
            disk_cache=payload.hardware.disk_cache,
            disk_discard=payload.hardware.disk_discard,
            disk_ssd_emulation=payload.hardware.disk_ssd_emulation,
            bridge=payload.hardware.bridge,
            network_model=payload.hardware.network_model,
            network_firewall=payload.hardware.network_firewall,
            machine=payload.hardware.machine,
            bios=payload.hardware.bios,
            scsi_controller=payload.hardware.scsi_controller,
            pool=payload.hardware.pool,
            os_choice=payload.os_choice,
        )
        db.update_vm_job(job_id, status="success", proxmox_response=result)
    except Exception as exc:
        db.update_vm_job(job_id, status="failed", error_message=str(exc))


@app.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="login.html", context={})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="register.html", context={})


@app.get("/app", response_class=HTMLResponse)
def app_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="app.html",
        context={"available_oses": sorted(OS_STORAGE_MAP.keys())},
    )


@app.post("/api/auth/register")
def register_user(payload: UserRegisterRequest):
    if db.get_user_by_username(payload.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    role = "admin" if payload.username == "admin" else "user"
    user_id = db.create_user(payload.username, hash_password(payload.password), role=role)
    db.add_audit_log(user_id, "user_register", "user", str(user_id), {"username": payload.username})
    return {"success": True, "user_id": user_id, "role": role}


@app.post("/api/auth/login", response_model=TokenResponse)
def login_user(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = db.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user["username"])
    db.add_audit_log(user["id"], "user_login", "user", str(user["id"]), {"username": user["username"]})
    return TokenResponse(access_token=token)


@app.get("/api/auth/me")
def get_me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "daily_quota": user["daily_quota"],
    }


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


@app.get("/api/proxmox/nodes")
def get_proxmox_nodes(
    client: ProxmoxClient = Depends(get_proxmox_client), user=Depends(require_admin)
) -> dict:
    try:
        nodes = client.list_nodes()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Proxmox node lookup failed: {exc}") from exc
    return {"configured_node": settings.proxmox_node, "nodes": nodes}


@app.get("/api/proxmox/permission-check")
def get_proxmox_permission_check(
    client: ProxmoxClient = Depends(get_proxmox_client), user=Depends(require_admin)
) -> dict:
    try:
        permission_report = client.validate_create_vm_permissions()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Proxmox permission check failed: {exc}"
        ) from exc

    return {
        "configured_node": settings.proxmox_node,
        "missing_permission_paths": permission_report["missing_permission_paths"],
        "permissions_by_path": permission_report["paths"],
    }


@app.post("/api/vm-jobs", response_model=VMJobCreateResponse)
def create_vm_job(
    payload: VMCreateRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
) -> VMJobCreateResponse:
    jobs_today = db.count_user_jobs_today(user["id"])
    if jobs_today >= user["daily_quota"]:
        raise HTTPException(
            status_code=429,
            detail=f"Daily quota exceeded ({user['daily_quota']} VM create requests per day).",
        )

    job_id = db.create_vm_job(
        user_id=user["id"],
        vmid=payload.hardware.vmid,
        vm_name=payload.hardware.name,
        os_choice=payload.os_choice,
        request_payload=payload.model_dump(),
    )
    db.add_audit_log(
        user["id"],
        "vm_job_create",
        "vm_job",
        str(job_id),
        {"vmid": payload.hardware.vmid, "name": payload.hardware.name},
    )
    background_tasks.add_task(_run_vm_job, job_id, payload)
    return VMJobCreateResponse(job_id=job_id, status="queued", message="VM job queued")


@app.get("/api/vm-jobs")
def list_my_vm_jobs(user=Depends(get_current_user)):
    rows = db.list_user_vm_jobs(user["id"])
    jobs = []
    for row in rows:
        jobs.append(
            {
                "id": row["id"],
                "vmid": row["vmid"],
                "vm_name": row["vm_name"],
                "os_choice": row["os_choice"],
                "status": row["status"],
                "error_message": row["error_message"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return {"jobs": jobs}


@app.get("/api/vm-jobs/{job_id}")
def get_vm_job(job_id: int, user=Depends(get_current_user)):
    row = db.get_vm_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "vmid": row["vmid"],
        "vm_name": row["vm_name"],
        "status": row["status"],
        "proxmox_response": json.loads(row["proxmox_response"]) if row["proxmox_response"] else None,
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@app.get("/api/audit-logs")
def get_audit_logs(user=Depends(require_admin)):
    rows = db.list_audit_logs(limit=100)
    logs = []
    for row in rows:
        logs.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "action": row["action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "details": json.loads(row["details"]),
                "created_at": row["created_at"],
            }
        )
    return {"logs": logs}


@app.post("/api/vms", response_model=VMCreateResponse)
def create_vm(
    payload: VMCreateRequest,
    client: ProxmoxClient = Depends(get_proxmox_client),
    user=Depends(require_admin),
) -> VMCreateResponse:
    try:
        result = client.create_vm(
            vmid=payload.hardware.vmid,
            name=payload.hardware.name,
            cores=payload.hardware.cores,
            sockets=payload.hardware.sockets,
            cpu_type=payload.hardware.cpu_type,
            cpu_limit=payload.hardware.cpu_limit,
            cpu_units=payload.hardware.cpu_units,
            memory_mb=payload.hardware.memory_mb,
            balloon_mb=payload.hardware.balloon_mb,
            disk_gb=payload.hardware.disk_gb,
            storage=payload.hardware.storage,
            disk_cache=payload.hardware.disk_cache,
            disk_discard=payload.hardware.disk_discard,
            disk_ssd_emulation=payload.hardware.disk_ssd_emulation,
            bridge=payload.hardware.bridge,
            network_model=payload.hardware.network_model,
            network_firewall=payload.hardware.network_firewall,
            machine=payload.hardware.machine,
            bios=payload.hardware.bios,
            scsi_controller=payload.hardware.scsi_controller,
            pool=payload.hardware.pool,
            os_choice=payload.os_choice,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Proxmox call failed: {exc}") from exc

    return VMCreateResponse(
        success=True,
        message="VM creation request accepted by backend",
        vmid=payload.hardware.vmid,
        proxmox_response=result,
    )
