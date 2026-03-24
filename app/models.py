from pydantic import BaseModel, Field, field_validator

from app.proxmox_client import OS_STORAGE_MAP


class VMHardwareSpec(BaseModel):
    vmid: int = Field(..., ge=100, le=999999)
    name: str = Field(..., min_length=2, max_length=63)
    cores: int = Field(..., ge=1, le=32)
    memory_mb: int = Field(..., ge=512, le=262144)
    disk_gb: int = Field(..., ge=5, le=2048)
    bridge: str = Field(default="vmbr0", min_length=3, max_length=32)
    storage: str = Field(default="local-lvm", min_length=2, max_length=64)
    sockets: int = Field(default=1, ge=1, le=8)
    cpu_type: str = Field(default="host", min_length=2, max_length=32)
    cpu_limit: int = Field(default=0, ge=0, le=128)
    cpu_units: int = Field(default=1024, ge=8, le=500000)
    machine: str = Field(default="q35", min_length=2, max_length=16)
    bios: str = Field(default="ovmf", min_length=2, max_length=16)
    scsi_controller: str = Field(default="virtio-scsi-single", min_length=2, max_length=32)
    balloon_mb: int = Field(default=0, ge=0, le=262144)
    network_model: str = Field(default="virtio", min_length=2, max_length=16)
    network_firewall: bool = Field(default=True)
    disk_cache: str = Field(default="none", min_length=2, max_length=16)
    disk_discard: bool = Field(default=True)
    disk_ssd_emulation: bool = Field(default=True)
    pool: str | None = Field(default=None, min_length=2, max_length=64)

    @field_validator("name")
    @classmethod
    def normalize_vm_name(cls, value: str) -> str:
        # Proxmox requires VM name to be DNS-safe.
        normalized = value.strip().lower()
        normalized = normalized.replace("_", "-").replace(" ", "-")
        cleaned = []
        for char in normalized:
            if char.isalnum() or char == "-":
                cleaned.append(char)
            else:
                cleaned.append("-")
        normalized = "".join(cleaned).strip("-")
        while "--" in normalized:
            normalized = normalized.replace("--", "-")

        if len(normalized) < 2:
            raise ValueError(
                "VM name is invalid after normalization. Use letters, digits, and hyphens."
            )
        if len(normalized) > 63:
            normalized = normalized[:63].rstrip("-")
        return normalized


class VMCreateRequest(BaseModel):
    hardware: VMHardwareSpec
    os_choice: str

    @field_validator("os_choice")
    @classmethod
    def validate_os_choice(cls, value: str) -> str:
        if value not in OS_STORAGE_MAP:
            supported = ", ".join(sorted(OS_STORAGE_MAP.keys()))
            raise ValueError(f"Unsupported os_choice '{value}'. Supported: {supported}")
        return value


class VMCreateResponse(BaseModel):
    success: bool
    message: str
    vmid: int
    proxmox_response: dict


class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class UserLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VMJobCreateResponse(BaseModel):
    job_id: int
    status: str
    message: str
