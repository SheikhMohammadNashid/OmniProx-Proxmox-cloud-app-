import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "app.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def init_db() -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            daily_quota INTEGER NOT NULL DEFAULT 3,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vm_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vmid INTEGER NOT NULL,
            vm_name TEXT NOT NULL,
            os_choice TEXT NOT NULL,
            ssh_user TEXT NOT NULL DEFAULT 'ubuntu',
            request_payload TEXT NOT NULL,
            status TEXT NOT NULL,
            proxmox_response TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    # Migrate existing DBs that don't have ssh_user column yet
    try:
        cur.execute("ALTER TABLE vm_jobs ADD COLUMN ssh_user TEXT NOT NULL DEFAULT 'ubuntu'")
    except sqlite3.OperationalError:
        pass  # column already exists

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS proxmox_credentials (
            user_id INTEGER PRIMARY KEY,
            base_url TEXT NOT NULL,
            node TEXT NOT NULL,
            token_id TEXT NOT NULL,
            token_secret TEXT NOT NULL,
            verify_ssl INTEGER NOT NULL DEFAULT 0,
            dry_run INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.commit()
    conn.close()


def create_user(
    username: str, password_hash: str, role: str = "user", daily_quota: int = 3
) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, role, daily_quota, created_at) VALUES (?, ?, ?, ?, ?)",
        (username, password_hash, role, daily_quota, utc_now_iso()),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return int(user_id)


def get_user_by_username(username: str):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def count_user_jobs_today(user_id: int) -> int:
    today = datetime.now(tz=timezone.utc).date().isoformat()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS c FROM vm_jobs WHERE user_id = ? AND substr(created_at, 1, 10) = ?",
        (user_id, today),
    )
    row = cur.fetchone()
    conn.close()
    return int(row["c"]) if row else 0


def create_vm_job(
    user_id: int,
    vmid: int,
    vm_name: str,
    os_choice: str,
    ssh_user: str,
    request_payload: dict,
) -> int:
    conn = _conn()
    cur = conn.cursor()
    now = utc_now_iso()
    cur.execute(
        """
        INSERT INTO vm_jobs (user_id, vmid, vm_name, os_choice, ssh_user, request_payload, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)
        """,
        (user_id, vmid, vm_name, os_choice, ssh_user, json.dumps(request_payload), now, now),
    )
    conn.commit()
    job_id = cur.lastrowid
    conn.close()
    return int(job_id)


def update_vm_job(
    job_id: int,
    status: str,
    proxmox_response: dict | None = None,
    error_message: str | None = None,
) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE vm_jobs
        SET status = ?, proxmox_response = ?, error_message = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            json.dumps(proxmox_response) if proxmox_response is not None else None,
            error_message,
            utc_now_iso(),
            job_id,
        ),
    )
    conn.commit()
    conn.close()


def get_vm_job(job_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vm_jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    conn.close()
    return row


def list_user_vm_jobs(user_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM vm_jobs WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def add_audit_log(
    user_id: int, action: str, target_type: str, target_id: str, details: dict
) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audit_logs (user_id, action, target_type, target_id, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, action, target_type, target_id, json.dumps(details), utc_now_iso()),
    )
    conn.commit()
    conn.close()


def list_audit_logs(limit: int = 100):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_proxmox_credentials(user_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM proxmox_credentials WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def upsert_proxmox_credentials(
    *,
    user_id: int,
    base_url: str,
    node: str,
    token_id: str,
    token_secret: str,
    verify_ssl: bool,
    dry_run: bool,
) -> None:
    conn = _conn()
    cur = conn.cursor()
    now = utc_now_iso()
    cur.execute(
        """
        INSERT INTO proxmox_credentials (
            user_id, base_url, node, token_id, token_secret,
            verify_ssl, dry_run, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            base_url = excluded.base_url,
            node = excluded.node,
            token_id = excluded.token_id,
            token_secret = excluded.token_secret,
            verify_ssl = excluded.verify_ssl,
            dry_run = excluded.dry_run,
            updated_at = excluded.updated_at
        """,
        (
            user_id, base_url, node, token_id, token_secret,
            int(bool(verify_ssl)), int(bool(dry_run)), now, now,
        ),
    )
    conn.commit()
    conn.close()
