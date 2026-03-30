# Proxmox VM Self-Service (FastAPI)

This project provides:
- A web form where users select VM hardware and OS.
- Per-user Proxmox credential storage (so the app is modular).
- FastAPI endpoints for VM provisioning (queued background jobs).
- A safe `dry_run` mode to test without creating real VMs.

## 1) First-time setup

Create your Python venv and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `.env` with your Proxmox API token (used as defaults until each user saves their own creds).

Notes:
- The app stores users + VM jobs in the local SQLite file `app.db` (do not commit it).
- Each user must open `/creds` and save Proxmox credentials for their account before VM creation will work reliably.

## 2) Run the app

Local dev:

```bash
uvicorn backend.main:app --reload
```

Open:
- `http://127.0.0.1:8000/` (redirects to UI)
- `http://127.0.0.1:8000/docs` (Swagger UI)

Docker:

```bash
docker compose up --build
```

## 3) Register -> Login -> Add Proxmox credentials

1. Go to `/register` and create an app account.
2. Login at `/login`.
3. If your Proxmox creds are not saved yet, the UI will redirect you to `/creds`.
4. Enter:
   - `Proxmox Base URL`
   - `Node`
   - `Token ID`
   - `Token Secret`
   - `Verify SSL` (usually OFF if you use a self-signed cert)
   - `Dry run` (ON = no VM will be created)
5. Save, then you’ll be redirected to `/app`.

If `Dry run` is enabled, VM jobs will be marked successful but **no VM is created in Proxmox**.

## 4) OS ISO storage mapping (required for all installs/users)

Other users must update the ISO storage mapping in:
- `backend/services/proxmox_client.py` → `OS_STORAGE_MAP` (current canonical location)

Why:
- The dropdown OS values are validated against `OS_STORAGE_MAP`.
- The app uses those mapped Proxmox ISO paths when building the VM payload.

Example:
- If your Proxmox ISO storage uses a different storage name or paths than `local:iso/...`, you must edit `OS_STORAGE_MAP` accordingly.
- Also confirm the ISO filenames referenced in `OS_STORAGE_MAP` exist in Proxmox under that storage.

After updating `OS_STORAGE_MAP`, restart the app and then use `/creds` + the UI normally.

## 5) VM creation + job status

- Creating a VM queues a background job (`/api/vm-jobs`).
- The jobs list (`/api/vm-jobs`) includes `proxmox_response`, so you can see whether the app was in dry-run or received a real Proxmox response.

