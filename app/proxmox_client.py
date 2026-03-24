from typing import Any

import requests

from app.config import settings


OS_STORAGE_MAP = {
    "ubuntu-24.04": "local:iso/ubuntu-24.04.4-live-server-amd64.iso",
    "alpine-standard-3.23.3": "local:iso/alpine-standard-3.23.3-x86_64.iso",
    "centos-stream-10": "local:iso/CentOS-Stream-10-latest-x86_64-dvd1.iso",
}


class ProxmoxClient:
    def __init__(self) -> None:
        self.base_url = settings.proxmox_base_url.rstrip("/")
        self.node = settings.proxmox_node
        self.verify_ssl = settings.proxmox_verify_ssl
        self.headers = {
            "Authorization": (
                f"PVEAPIToken={settings.proxmox_token_id}={settings.proxmox_token_secret}"
            )
        }

    def list_nodes(self) -> list[dict[str, Any]]:
        if settings.proxmox_dry_run:
            return [{"node": self.node, "status": "dry-run"}]

        url = f"{self.base_url}/nodes"
        response = requests.get(
            url, headers=self.headers, verify=self.verify_ssl, timeout=20
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", [])

    def get_permissions_for_path(self, path: str) -> dict[str, Any]:
        if settings.proxmox_dry_run:
            return {path: {"dry_run": True}}
        url = f"{self.base_url}/access/permissions"
        response = requests.get(
            url,
            headers=self.headers,
            params={"path": path},
            verify=self.verify_ssl,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", {})

    def validate_create_vm_permissions(self) -> dict[str, Any]:
        paths = ["/", "/vms", f"/nodes/{self.node}", "/storage/local", "/storage/local-lvm"]
        permission_data = {path: self.get_permissions_for_path(path).get(path, {}) for path in paths}
        missing_paths = [path for path, perms in permission_data.items() if not perms]
        return {"paths": permission_data, "missing_permission_paths": missing_paths}

    def _create_vm_on_node(self, *, node: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/nodes/{node}/qemu"
        response = requests.post(
            url, headers=self.headers, data=payload, verify=self.verify_ssl, timeout=20
        )
        if not response.ok:
            raise RuntimeError(
                f"Proxmox HTTP {response.status_code} error on node '{node}': {response.text}"
            )
        return response.json()

    def create_vm(
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
    ) -> dict[str, Any]:
        cdrom_path = OS_STORAGE_MAP[os_choice]
        scsi0_options = [f"{storage}:{disk_gb}", f"cache={disk_cache}"]
        if disk_discard:
            scsi0_options.append("discard=on")
        if disk_ssd_emulation:
            scsi0_options.append("ssd=1")

        net0 = f"{network_model},bridge={bridge}"
        if network_firewall:
            net0 = f"{net0},firewall=1"

        payload = {
            "vmid": vmid,
            "name": name,
            "sockets": sockets,
            "cores": cores,
            "cpu": cpu_type,
            "cpulimit": cpu_limit,
            "cpuunits": cpu_units,
            "memory": memory_mb,
            "balloon": balloon_mb,
            "machine": machine,
            "bios": bios,
            "net0": net0,
            "scsihw": scsi_controller,
            "scsi0": ",".join(scsi0_options),
            "ide2": f"{cdrom_path},media=cdrom",
            "boot": "order=scsi0;ide2;net0",
            "ostype": "l26" if os_choice != "windows-11" else "win11",
            "agent": 1,
        }
        if pool:
            payload["pool"] = pool

        if settings.proxmox_dry_run:
            return {"dry_run": True, "payload": payload}
        try:
            return self._create_vm_on_node(node=self.node, payload=payload)
        except RuntimeError as exc:
            message = str(exc).lower()
            if "hostname lookup" not in message and "failed to get address info" not in message:
                raise

            nodes = self.list_nodes()
            if not nodes:
                raise

            fallback_node = nodes[0].get("node")
            if not fallback_node or fallback_node == self.node:
                raise

            result = self._create_vm_on_node(node=fallback_node, payload=payload)
            result["fallback_node_used"] = fallback_node
            result["configured_node"] = self.node
            return result
