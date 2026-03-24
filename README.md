# Proxmox VM Self-Service (FastAPI)

This project provides:
- A web form where users select VM hardware and OS.
- FastAPI endpoints for VM provisioning.
- A safe `dry_run` mode for testing before provisioning real VMs.
- API tests using `pytest`.

## 1) Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `.env` with your real Proxmox details and API token.

## 2) Run locally

```bash
uvicorn app.main:app --reload
```

Open:
- `http://127.0.0.1:8000/` (web UI)
- `http://127.0.0.1:8000/docs` (Swagger UI)

## 3) Test safely before go-live

Keep `PROXMOX_DRY_RUN=true` in `.env` while validating:

```bash
pytest -q
```

When dry run is enabled, the backend returns the payload that would be sent to Proxmox, without creating a VM.

## 4) Go-live checklist

1. Confirm OS ISO names in `app/proxmox_client.py` (`OS_STORAGE_MAP`) match your actual Proxmox ISO storage.
2. Set `PROXMOX_DRY_RUN=false`.
3. Create a test VM from UI.
4. Verify VM appears in Proxmox with expected CPU/RAM/Disk/network.
5. Add authentication (SSO or app login) before exposing this app to users.

## 5) Recommended next hardening

- Add user auth + RBAC.
- Enforce per-user quotas.
- Add audit logs for every create request.
- Add background task queue + job status endpoint.
