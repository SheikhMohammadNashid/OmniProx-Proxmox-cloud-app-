import time
from typing import Any

import requests

from backend.core.config import settings

# Maps OS choice → template VMID on your Proxmox node.
# Run SETUP_GOLDEN_IMAGE.sh on your Proxmox node once to create these templates.
CLOUD_TEMPLATE_MAP: dict[str, int] = {
    "ubuntu-24.04": 9000,
    "ubuntu-22.04": 9001,
    "debian-12": 9002,
}

# Alias so any code still importing OS_STORAGE_MAP doesn't break.
OS_STORAGE_MAP = CLOUD_TEMPLATE_MAP


class ProxmoxClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        node: str | None = None,
        token_id: str | None = None,
        token_secret: str | None = None,
        verify_ssl: bool | None = None,
        dry_run: bool | None = None,
    ) -> None:
        self.base_url = (base_url or settings.proxmox_base_url).rstrip("/")
        self.node = node or settings.proxmox_node
        self.verify_ssl = (
            verify_ssl if verify_ssl is not None else settings.proxmox_verify_ssl
        )
        self.dry_run = dry_run if dry_run is not None else settings.proxmox_dry_run
        self.headers = {
            "Authorization": (
                f"PVEAPIToken={(token_id or settings.proxmox_token_id)}="
                f"{(token_secret or settings.proxmox_token_secret)}"
            )
        }

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _get(self, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        r = requests.get(url, headers=self.headers, verify=self.verify_ssl, timeout=20, **kwargs)
        r.raise_for_status()
        # Note: r.json().get("data", {}) returns None if JSON has "data": null — breaks callers.
        payload = r.json()
        data = payload.get("data")
        return data if data is not None else {}

    def _agent_network_get_interfaces_raw(self, node: str, vmid: int) -> Any:
        """
        Proxmox registers this agent call for POST (same as the web UI).
        Older clusters may only accept GET — fall back on 405.
        """
        url = f"{self.base_url}/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces"
        r = requests.post(url, headers=self.headers, verify=self.verify_ssl, timeout=20)
        if r.status_code == 405:
            r = requests.get(url, headers=self.headers, verify=self.verify_ssl, timeout=20)
        r.raise_for_status()
        payload = r.json()
        data = payload.get("data")
        return data if data is not None else {}

    def _post(self, path: str, data: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        r = requests.post(url, headers=self.headers, data=data, verify=self.verify_ssl, timeout=20)
        if not r.ok:
            raise RuntimeError(f"Proxmox HTTP {r.status_code} on POST {path}: {r.text}")
        return r.json().get("data")

    def _put(self, path: str, data: dict) -> Any:
        url = f"{self.base_url}{path}"
        r = requests.put(url, headers=self.headers, data=data, verify=self.verify_ssl, timeout=20)
        if not r.ok:
            raise RuntimeError(f"Proxmox HTTP {r.status_code} on PUT {path}: {r.text}")
        return r.json().get("data")

    def _wait_for_task(self, node: str, upid: str, timeout: int = 120) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self._get(f"/nodes/{node}/tasks/{upid}/status")
            if status.get("status") == "stopped":
                exit_status = status.get("exitstatus", "")
                if exit_status != "OK":
                    raise RuntimeError(f"Task {upid} failed: {exit_status}")
                return
            time.sleep(3)
        raise RuntimeError(f"Task {upid} timed out after {timeout}s")

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def list_nodes(self) -> list[dict[str, Any]]:
        if self.dry_run:
            return [{"node": self.node, "status": "dry-run"}]
        return self._get("/nodes") or []

    def get_permissions_for_path(self, path: str) -> dict[str, Any]:
        if self.dry_run:
            return {path: {"dry_run": True}}
        return self._get("/access/permissions", params={"path": path})

    def validate_create_vm_permissions(self) -> dict[str, Any]:
        paths = ["/", "/vms", f"/nodes/{self.node}", "/storage/local", "/storage/local-lvm"]
        permission_data = {
            path: self.get_permissions_for_path(path).get(path, {}) for path in paths
        }
        missing_paths = [path for path, perms in permission_data.items() if not perms]
        return {"paths": permission_data, "missing_permission_paths": missing_paths}

    @staticmethod
    def _normalize_agent_interface_list(raw: Any) -> list[dict[str, Any]]:
        """Turn assorted Proxmox / QEMU guest-agent envelopes into a list of interface dicts."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        if not isinstance(raw, dict):
            return []
        for key in ("result", "return"):
            inner = raw.get(key)
            if isinstance(inner, dict) and "error" in inner:
                return []
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
        for v in raw.values():
            if (
                isinstance(v, list)
                and v
                and isinstance(v[0], dict)
                and ("name" in v[0] or "ip-addresses" in v[0])
            ):
                return [x for x in v if isinstance(x, dict)]
        return []

    @staticmethod
    def _first_usable_ipv4(ifaces: list[dict[str, Any]]) -> str | None:
        for iface in ifaces:
            name = iface.get("name", "")
            if name in ("lo", "lo0"):
                continue
            for addr in iface.get("ip-addresses") or []:
                if not isinstance(addr, dict):
                    continue
                atype = str(addr.get("ip-address-type", "")).lower()
                if atype != "ipv4":
                    continue
                ip = (addr.get("ip-address") or "").strip()
                if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                    return ip
        return None

    def get_vm_ip(self, node: str, vmid: int, timeout: int = 120) -> str | None:
        """
        Poll the QEMU guest agent for a non-loopback IPv4 address.
        Handles all Proxmox API response wrapper formats.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = self._agent_network_get_interfaces_raw(node, vmid)
                ifaces = self._normalize_agent_interface_list(raw)
                ip = self._first_usable_ipv4(ifaces)
                if ip:
                    return ip
            except Exception:
                pass  # agent not ready yet — keep polling
            time.sleep(8)  # 8s between polls — gentler on slow hardware
        return None

    def clone_and_boot_vm(
        self,
        *,
        vmid: int,
        name: str,
        cores: int,
        sockets: int,
        cpu_type: str,
        cpu_limit: int,
        cpu_units: int,
        memory_mb: int,
        balloon_mb: int,
        disk_gb: int,
        storage: str,
        disk_cache: str,
        disk_discard: bool,
        disk_ssd_emulation: bool,
        bridge: str,
        network_model: str,
        network_firewall: bool,
        machine: str,
        bios: str,
        scsi_controller: str,
        pool: str | None,
        os_choice: str,
        ssh_user: str,
        ssh_password: str,
    ) -> dict[str, Any]:
        """Clone a golden-image template, inject cloud-init creds, resize disk, start VM."""
        template_vmid = CLOUD_TEMPLATE_MAP[os_choice]

        if self.dry_run:
            return {
                "dry_run": True,
                "template_vmid": template_vmid,
                "new_vmid": vmid,
                "os_choice": os_choice,
                "ssh_user": ssh_user,
                "note": "No real VM was created (dry-run mode).",
            }

        node = self.node

        # Step 1: Clone the template
        clone_payload: dict[str, Any] = {
            "newid": vmid,
            "name": name,
            "full": 1,
            "storage": storage,
        }
        if pool:
            clone_payload["pool"] = pool

        upid = self._post(f"/nodes/{node}/qemu/{template_vmid}/clone", data=clone_payload)
        if upid:
            self._wait_for_task(node, upid)

        # Step 2: Configure hardware + cloud-init
        net0 = f"{network_model},bridge={bridge}"
        if network_firewall:
            net0 = f"{net0},firewall=1"

        config_payload: dict[str, Any] = {
            "cores": cores,
            "sockets": sockets,
            "cpu": cpu_type,
            "cpulimit": cpu_limit,
            "cpuunits": cpu_units,
            "memory": memory_mb,
            "balloon": balloon_mb,
            "machine": machine,
            "bios": bios,
            "scsihw": scsi_controller,
            "net0": net0,
            "ciuser": ssh_user,
            "cipassword": ssh_password,
            "ipconfig0": "ip=dhcp",
            "agent": 1,
            # Vendor cloud-init: SSH password + qemu-guest-agent (see snippets/enable-ssh-password.yaml.example)
            "cicustom": "vendor=local:snippets/enable-ssh-password.yaml",
        }
        self._put(f"/nodes/{node}/qemu/{vmid}/config", data=config_payload)

        # Step 3: Resize disk to requested size
        self._put(
            f"/nodes/{node}/qemu/{vmid}/resize",
            data={"disk": "scsi0", "size": f"{disk_gb}G"},
        )

        # Step 4: Start the VM
        start_upid = self._post(f"/nodes/{node}/qemu/{vmid}/status/start")
        if start_upid:
            self._wait_for_task(node, start_upid, timeout=60)

        # Return immediately — IP is fetched separately in background
        return {
            "success": True,
            "vmid": vmid,
            "node": node,
            "template_vmid": template_vmid,
            "os_choice": os_choice,
            "ssh_user": ssh_user,
            "vm_ip": None,  # filled in by _poll_vm_ip background task
        }

    def create_vm(self, **kwargs) -> dict[str, Any]:
        """Backward-compat alias → clone_and_boot_vm."""
        return self.clone_and_boot_vm(**kwargs)
