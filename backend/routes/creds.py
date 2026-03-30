from fastapi import APIRouter, Depends

from backend.core.config import settings
from backend.core.security import get_current_user
from backend.db import repo as db
from backend.models.schemas import (
    ProxmoxCredentialsStatusResponse,
    ProxmoxCredentialsUpsertRequest,
)

router = APIRouter(prefix="/api/proxmox/creds", tags=["proxmox-creds"])


@router.get("/status", response_model=ProxmoxCredentialsStatusResponse)
def get_proxmox_creds_status(user=Depends(get_current_user)) -> ProxmoxCredentialsStatusResponse:
    creds_row = db.get_proxmox_credentials(user["id"])
    if creds_row:
        return ProxmoxCredentialsStatusResponse(
            has_creds=True,
            base_url=creds_row["base_url"],
            node=creds_row["node"],
            token_id=creds_row["token_id"],
            verify_ssl=bool(creds_row["verify_ssl"]),
            dry_run=bool(creds_row["dry_run"]),
        )

    return ProxmoxCredentialsStatusResponse(
        has_creds=False,
        base_url=settings.proxmox_base_url,
        node=settings.proxmox_node,
        token_id=None,
        verify_ssl=settings.proxmox_verify_ssl,
        dry_run=settings.proxmox_dry_run,
    )


@router.get("", response_model=ProxmoxCredentialsStatusResponse)
def get_proxmox_creds(user=Depends(get_current_user)) -> ProxmoxCredentialsStatusResponse:
    return get_proxmox_creds_status(user=user)


@router.post("", response_model=ProxmoxCredentialsStatusResponse)
def upsert_proxmox_creds(
    payload: ProxmoxCredentialsUpsertRequest,
    user=Depends(get_current_user),
) -> ProxmoxCredentialsStatusResponse:
    db.upsert_proxmox_credentials(
        user_id=user["id"],
        base_url=payload.base_url,
        node=payload.node,
        token_id=payload.token_id,
        token_secret=payload.token_secret,
        verify_ssl=payload.verify_ssl,
        dry_run=payload.dry_run,
    )
    db.add_audit_log(
        user["id"],
        "proxmox_creds_upsert",
        "proxmox_credentials",
        str(user["id"]),
        {"base_url": payload.base_url, "node": payload.node, "token_id": payload.token_id},
    )
    return ProxmoxCredentialsStatusResponse(
        has_creds=True,
        base_url=payload.base_url,
        node=payload.node,
        token_id=payload.token_id,
        verify_ssl=payload.verify_ssl,
        dry_run=payload.dry_run,
    )

