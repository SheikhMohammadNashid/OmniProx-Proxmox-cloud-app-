import json

from fastapi import APIRouter, Depends, HTTPException

from backend.core.security import require_admin
from backend.services.proxmox_client import ProxmoxClient

router = APIRouter(prefix="/api/proxmox", tags=["proxmox-admin"])


def get_proxmox_client(user=Depends(require_admin)) -> ProxmoxClient:
    # Admin-only endpoints: use defaults from env unless admin saved creds.
    # (Keeping behavior aligned with existing implementation.)
    from backend.db import repo as db

    creds_row = db.get_proxmox_credentials(user["id"])
    if creds_row:
        return ProxmoxClient(
            base_url=creds_row["base_url"],
            node=creds_row["node"],
            token_id=creds_row["token_id"],
            token_secret=creds_row["token_secret"],
            verify_ssl=bool(creds_row["verify_ssl"]),
            dry_run=bool(creds_row["dry_run"]),
        )
    return ProxmoxClient()


@router.get("/nodes")
def get_proxmox_nodes(client: ProxmoxClient = Depends(get_proxmox_client)) -> dict:
    try:
        nodes = client.list_nodes()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Proxmox node lookup failed: {exc}") from exc
    return {"configured_node": client.node, "nodes": nodes}


@router.get("/permission-check")
def get_proxmox_permission_check(client: ProxmoxClient = Depends(get_proxmox_client)) -> dict:
    try:
        permission_report = client.validate_create_vm_permissions()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Proxmox permission check failed: {exc}") from exc

    return {
        "configured_node": client.node,
        "missing_permission_paths": permission_report["missing_permission_paths"],
        "permissions_by_path": permission_report["paths"],
    }


@router.get("/audit-logs")
def get_audit_logs(user=Depends(require_admin)):
    from backend.db import repo as db

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

