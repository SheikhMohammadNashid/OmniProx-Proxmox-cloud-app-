# Proxmox Cloud – VM Self-Service Portal

Provision Proxmox VMs from golden cloud-init images, then SSH into them directly from the browser.

---

## Architecture

```
Browser (xterm.js)
    ↕  WebSocket  /ws/ssh
FastAPI SSH proxy  (asyncssh)
    ↕  SSH
VM cloned from golden image
```

---

## One-time: Create golden-image templates on Proxmox

Copy `SETUP_GOLDEN_IMAGE.sh` to your Proxmox node and run it as root:

```bash
scp SETUP_GOLDEN_IMAGE.sh root@<proxmox-ip>:/root/
ssh root@<proxmox-ip> 'chmod +x /root/SETUP_GOLDEN_IMAGE.sh && /root/SETUP_GOLDEN_IMAGE.sh'
```

This downloads Ubuntu 24.04, Ubuntu 22.04, and Debian 12 cloud images and converts them to Proxmox templates (VMIDs 9000–9002). Each VM creation will **clone** one of these templates — no ISO install needed.

If you want different VMIDs or extra distros, edit both the script and `CLOUD_TEMPLATE_MAP` in `backend/services/proxmox_client.py`.

---

## Run with Docker Compose

```bash
cp .env.example .env
# Fill in .env: JWT_SECRET_KEY, PROXMOX_BASE_URL, PROXMOX_NODE, etc.
docker compose up --build
```

Open `http://localhost:8000`.

---

## VM creation flow

1. Fill in the **Create VM** form — choose OS, set SSH username + password.
2. Click **Queue VM Creation** — the backend clones the golden template, injects cloud-init credentials, resizes the disk, and starts the VM.
3. When the job shows `success`, go to the **SSH Terminal** section.
4. Select the job, enter the VM's IP (check your DHCP server or Proxmox summary), enter the SSH credentials you set, click **Connect**.

---

## Changing which templates are available

Edit `CLOUD_TEMPLATE_MAP` in `backend/services/proxmox_client.py`:

```python
CLOUD_TEMPLATE_MAP: dict[str, int] = {
    "ubuntu-24.04": 9000,
    "ubuntu-22.04": 9001,
    "debian-12":    9002,
    "my-custom-os": 9010,   # add your own
}
```

Make sure the corresponding template VMID exists on your Proxmox node.

---

## Dependencies added

| Package | Why |
|---------|-----|
| `asyncssh` | Async SSH client used by the WebSocket proxy |
| `websockets` | WebSocket support for FastAPI/uvicorn |

---

## File changes from previous version

| File | Change |
|------|--------|
| `backend/services/proxmox_client.py` | Replaced ISO-based `create_vm` with `clone_and_boot_vm` using cloud-init templates |
| `backend/routes/vm_jobs.py` | Removed console URL logic; passes `ssh_user`/`ssh_password` to client |
| `backend/routes/ssh.py` | **New** — WebSocket SSH proxy via asyncssh |
| `backend/main.py` | Registers the SSH router |
| `backend/models/schemas.py` | Added `ssh_user` and `ssh_password` fields to `VMCreateRequest` |
| `backend/db/repo.py` | Added `ssh_user` column to `vm_jobs`, auto-migrates existing DB |
| `frontend/templates/app.html` | Removed console links; added SSH terminal section with xterm.js |
| `frontend/static/dashboard.js` | Removed console render; added full SSH connect/disconnect/resize logic |
| `frontend/static/styles.css` | Replaced `.console-links` with terminal + ssh-form styles |
| `SETUP_GOLDEN_IMAGE.sh` | **New** — one-shot script to create golden templates on Proxmox |
