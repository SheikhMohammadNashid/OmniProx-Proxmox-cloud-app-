from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    proxmox_base_url: str = "https://YOUR-PROXMOX-IP:8006/api2/json"
    proxmox_node: str = "pve"
    proxmox_token_id: str = "root@pam!fastapi"
    proxmox_token_secret: str = "CHANGE_ME"
    proxmox_verify_ssl: bool = False
    proxmox_dry_run: bool = True
    jwt_secret_key: str = "change-this-in-production-long-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8")


settings = Settings()
