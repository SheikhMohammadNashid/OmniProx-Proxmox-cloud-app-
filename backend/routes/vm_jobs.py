import json
import threading
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from backend.core.security import get_current_user
from backend.db import repo as db
from backend.models.schemas import VMCreateRequest, VMJobCreateResponse
from backend.services.proxmox_client import ProxmoxClient

router = APIRouter(prefix="/api/vm-jobs", tags=["vm-jobs"])


def _client_from_proxmox_credentials_row(creds_row) -> ProxmoxClient:
    if not creds_row:
        return ProxmoxClient()
    return ProxmoxClient(
        base_url=creds_row["base_url"],
        node=creds_row["node"],
        token_id=creds_row["token_id"],
        token_secret=creds_row["token_secret"],
        verify_ssl=bool(creds_row["verify_ssl"]),
        dry_run=bool(creds_row["dry_run"]),
    )


def _poll_vm_ip(job_id: int, node: str, vmid: int, client: ProxmoxClient) -> None:
    """
    Runs in a plain thread. Polls guest agent for the VM IP and
    patches it into the DB when found. 10 min timeout for slow hardware.
    """
    ip = client.get_vm_ip(node, vmid, timeout=600)
    if not ip:
        return
    job_row = db.get_vm_job(job_id)
    if not job_row or job_row["status"] != "success":
        return
    response = json.loads(job_row["proxmox_response"]) if job_row["proxmox_response"] else {}
    response["vm_ip"] = ip
    db.update_vm_job(job_id, status="success", proxmox_response=response)


def _run_vm_job(job_id: int, payload: VMCreateRequest) -> None:
    db.update_vm_job(job_id, status="running")
    job_row = db.get_vm_job(job_id)
    if not job_row:
        db.update_vm_job(job_id, status="failed", error_message="Job not found")
        return
    client = _client_from_proxmox_credentials_row(
        db.get_proxmox_credentials(job_row["user_id"])
    )

    try:
        result = client.clone_and_boot_vm(
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
            ssh_user=payload.ssh_user,
            ssh_password=payload.ssh_password,
        )
        # Mark success immediately — VM is started, don't wait for IP
        db.update_vm_job(job_id, status="success", proxmox_response=result)

        # Spawn a real OS thread to poll for IP — background_tasks won't
        # work here since we're already inside a background task
        node = result.get("node", client.node)
        t = threading.Thread(
            target=_poll_vm_ip,
            args=(job_id, node, payload.hardware.vmid, client),
            daemon=True,
        )
        t.start()

    except Exception as exc:
        db.update_vm_job(job_id, status="failed", error_message=str(exc))


@router.post("", response_model=VMJobCreateResponse)
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
        ssh_user=payload.ssh_user,
        request_payload=payload.model_dump(exclude={"ssh_password"}),  # never persist password
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


@router.get("")
def list_my_vm_jobs(user=Depends(get_current_user)):
    rows = db.list_user_vm_jobs(user["id"])
    jobs = []
    for row in rows:
        proxmox_response = (
            json.loads(row["proxmox_response"]) if row["proxmox_response"] else None
        )
        jobs.append(
            {
                "id": row["id"],
                "vmid": row["vmid"],
                "vm_name": row["vm_name"],
                "os_choice": row["os_choice"],
                "ssh_user": row["ssh_user"],
                "status": row["status"],
                "proxmox_response": proxmox_response,
                "error_message": row["error_message"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return {"jobs": jobs}


@router.get("/{job_id}")
def get_vm_job(job_id: int, user=Depends(get_current_user)):
    row = db.get_vm_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    proxmox_response = json.loads(row["proxmox_response"]) if row["proxmox_response"] else None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "vmid": row["vmid"],
        "vm_name": row["vm_name"],
        "os_choice": row["os_choice"],
        "ssh_user": row["ssh_user"],
        "status": row["status"],
        "proxmox_response": proxmox_response,
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.post("/{job_id}/fetch-ip")
def fetch_ip_for_job(job_id: int, user=Depends(get_current_user)):
    """Manually trigger IP polling for an existing successful job."""
    row = db.get_vm_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    if row["status"] != "success":
        raise HTTPException(status_code=400, detail="Job is not in success state")

    # Check if we already have an IP
    existing = json.loads(row["proxmox_response"]) if row["proxmox_response"] else {}
    if existing.get("vm_ip"):
        return {"vm_ip": existing["vm_ip"], "cached": True}

    client = _client_from_proxmox_credentials_row(
        db.get_proxmox_credentials(row["user_id"])
    )
    node = existing.get("node", client.node)
    vmid = row["vmid"]

    # Spawn background thread — return immediately, let polling happen async
    t = threading.Thread(
        target=_poll_vm_ip,
        args=(job_id, node, vmid, client),
        daemon=True,
    )
    t.start()

    return {"message": "IP polling started — check back in 30 seconds", "vm_ip": None}
