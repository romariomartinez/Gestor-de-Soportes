from __future__ import annotations

import cgi
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import time
import unicodedata
import uuid
import zipfile
from datetime import datetime, timedelta
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, unquote, urlsplit
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"
DB_PATH = DATA_DIR / "eps_soportes.sqlite3"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


load_env_file(BASE_DIR / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = (
    os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    or (os.environ.get("SUPABASE_KEY") if (os.environ.get("SUPABASE_KEY") or "").startswith("sb_publishable_") else "")
    or ""
)
SUPABASE_SERVICE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_SECRET_KEY")
    or ""
)
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "soportes-eps")
SUPABASE_PULL_ON_START = os.environ.get("SUPABASE_PULL_ON_START", "1").lower() not in {"0", "false", "no"}
SUPABASE_SYNC_ON_WRITE = os.environ.get("SUPABASE_SYNC_ON_WRITE", "1").lower() not in {"0", "false", "no"}
KEEPALIVE_SECRET = os.environ.get("KEEPALIVE_SECRET", "").strip()
DATA_BACKEND = os.environ.get("DATA_BACKEND", "supabase").strip().lower()
USE_SUPABASE_ONLY = DATA_BACKEND == "supabase"

MONTH_NAMES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

CORTE_LABELS = {
    "1": "Corte 1",
    "2": "Corte 2",
    "3": "Corte 3",
}

SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

ROLE_PERMISSIONS = {
    "Administrador": {
        "upload",
        "edit_support",
        "delete_support",
        "download",
        "manage_eps",
        "manage_users",
        "view_reports",
        "configure",
    },
    "Digitador": {"upload", "edit_support", "download", "view_reports"},
    "Consulta": {"download", "view_reports"},
}

SESSIONS: dict[str, dict[str, Any]] = {}

DEFAULT_USERS = [
    ("María Gómez", "admin@eps.local", "INITIAL_ADMIN_PASSWORD", "Administrador"),
    ("Juan Pérez", "digitador@eps.local", "INITIAL_DIGITADOR_PASSWORD", "Digitador"),
    ("Laura Torres", "consulta@eps.local", "INITIAL_CONSULTA_PASSWORD", "Consulta"),
]

DEFAULT_EPS_ROWS = [
    ("Nueva EPS", "900156264-2", "NEPS", "#1457e8", "nueva eps,nueva empresa promotora de salud"),
    ("Sanitas", "800251440-6", "SAN", "#2287d8", "eps sanitas,sanitas eps"),
    ("Coosalud", "900226715-3", "COO", "#21a67a", "coosalud eps"),
    ("Salud Total", "800130907-4", "ST", "#76b94a", "salud total eps"),
    ("Sura", "800088702-2", "SURA", "#f28f2c", "eps sura,suramericana"),
    ("Compensar", "860066942-7", "COMP", "#eb3f59", "eps compensar"),
    ("Famisanar", "830003564-7", "FAM", "#7c5dd8", "eps famisanar"),
    ("CONSORCIO AUDITOOL 25", "", "AUDITOOL", "#28567a", "auditool,consorcio auditool"),
    ("Mutual Ser", "806008394-7", "MUT", "#18a4a6", "mutualser"),
    ("FOMAG", "830053105-3", "FOMAG", "#0a8fc4", "fomag,fondo nacional de prestaciones sociales del magisterio"),
]


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().lower()


def slugify(value: str, fallback: str = "archivo") -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return value[:120] or fallback


def configured_default_users() -> list[tuple[str, str, str, str]]:
    users = []
    for name, email, password_env, role in DEFAULT_USERS:
        password = os.environ.get(password_env)
        if password:
            users.append((name, email, password, role))
    return users


def technical_user_email(name: str, existing_emails: set[str] | None = None) -> str:
    existing_emails = existing_emails or set()
    base = slugify(name, "usuario").lower()
    email = f"{base}@usuarios.local"
    while email in existing_emails:
        email = f"{base}-{uuid.uuid4().hex[:6]}@usuarios.local"
    return email


def supabase_key_role(value: str) -> str:
    if value.startswith("sb_secret_"):
        return "secret"
    if value.startswith("sb_publishable_"):
        return "publishable"
    parts = value.split(".")
    if len(parts) >= 2:
        try:
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
            return str(data.get("role") or "")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return ""
    return ""


def has_supabase_server_key() -> bool:
    role = supabase_key_role(SUPABASE_SERVICE_KEY)
    return bool(SUPABASE_SERVICE_KEY and role not in {"publishable", "anon"})


def json_dumps(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"{salt.hex()}:{digest.hex()}"


def support_upload_fingerprint(content: bytes) -> str:
    return f"{hashlib.sha256(content).hexdigest()}:{uuid.uuid4().hex}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        expected = hash_password(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
        return hmac.compare_digest(expected, digest_hex)
    except ValueError:
        return False


def session_secret() -> str:
    return os.environ.get("SESSION_SECRET") or SUPABASE_SERVICE_KEY or SUPABASE_PUBLISHABLE_KEY or "local-session-secret"


def create_session_token(user_id: int, hours: int = 8) -> str:
    expires = int(time.time() + hours * 60 * 60)
    payload = f"{int(user_id)}:{expires}:{secrets.token_urlsafe(12)}"
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    signature = hmac.new(session_secret().encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def read_session_token(token: str | None) -> dict[str, int] | None:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    expected = hmac.new(session_secret().encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = base64.urlsafe_b64decode((encoded + padding).encode("ascii")).decode("utf-8")
        user_id, expires, _nonce = payload.split(":", 2)
        expires_int = int(expires)
        if expires_int < time.time():
            return None
        return {"user_id": int(user_id), "expires": expires_int}
    except (ValueError, UnicodeDecodeError):
        return None


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS eps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                nit TEXT,
                code TEXT,
                color TEXT NOT NULL DEFAULT '#1769e0',
                logo_url TEXT,
                aliases TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                path TEXT NOT NULL,
                eps_id INTEGER,
                eps_name TEXT,
                radication_date TEXT,
                radicado TEXT,
                factura TEXT,
                corte TEXT,
                invoice_count INTEGER NOT NULL DEFAULT 1,
                invoice_numbers TEXT,
                nit_eps TEXT,
                valor_radicado TEXT,
                year INTEGER,
                month INTEGER,
                uploaded_at TEXT NOT NULL,
                uploaded_by INTEGER NOT NULL,
                uploaded_by_name TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                observations TEXT,
                extracted_text TEXT,
                FOREIGN KEY (eps_id) REFERENCES eps(id),
                FOREIGN KEY (uploaded_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                details TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_supports_filters
                ON supports (eps_name, year, month, radication_date, radicado, factura, status);
            CREATE INDEX IF NOT EXISTS idx_supports_hash ON supports (sha256);
            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at);
            """
        )

        support_columns = {row["name"] for row in conn.execute("PRAGMA table_info(supports)").fetchall()}
        migrations = {
            "corte": "ALTER TABLE supports ADD COLUMN corte TEXT",
            "invoice_count": "ALTER TABLE supports ADD COLUMN invoice_count INTEGER NOT NULL DEFAULT 1",
            "invoice_numbers": "ALTER TABLE supports ADD COLUMN invoice_numbers TEXT",
        }
        for column, statement in migrations.items():
            if column not in support_columns:
                conn.execute(statement)

        for row in conn.execute(
            "SELECT id, original_filename, factura, corte, invoice_count, status, extracted_text FROM supports"
        ).fetchall():
            invoice_numbers, invoice_count = extract_invoice_numbers(row["extracted_text"] or "", row["factura"])
            detected_corte = detect_corte(row["extracted_text"] or "", row["original_filename"])
            updates = {
                "invoice_count": max(int(row["invoice_count"] or 0), invoice_count),
                "invoice_numbers": ",".join(invoice_numbers) if invoice_numbers else None,
                "corte": row["corte"] or detected_corte or None,
                "status": "pendiente_revision"
                if row["status"] != "eliminado" and not (row["corte"] or detected_corte)
                else row["status"],
            }
            conn.execute(
                """
                UPDATE supports
                SET invoice_count = ?, invoice_numbers = ?, corte = ?, status = ?
                WHERE id = ?
                """,
                (updates["invoice_count"], updates["invoice_numbers"], updates["corte"], updates["status"], row["id"]),
            )

        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            for name, email, password, role in configured_default_users():
                conn.execute(
                    """
                    INSERT INTO users (name, email, password_hash, role, active, created_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    (name, email, hash_password(password), role, now_iso()),
                )

        eps_rows = [
            ("Nueva EPS", "900156264-2", "NEPS", "#1457e8", "nueva eps,nueva empresa promotora de salud"),
            ("Sanitas", "800251440-6", "SAN", "#2287d8", "eps sanitas,sanitas eps"),
            ("Coosalud", "900226715-3", "COO", "#21a67a", "coosalud eps"),
            ("Salud Total", "800130907-4", "ST", "#76b94a", "salud total eps"),
            ("Sura", "800088702-2", "SURA", "#f28f2c", "eps sura,suramericana"),
            ("Compensar", "860066942-7", "COMP", "#eb3f59", "eps compensar"),
            ("Famisanar", "830003564-7", "FAM", "#7c5dd8", "eps famisanar"),
            ("CONSORCIO AUDITOOL 25", "", "AUDITOOL", "#28567a", "auditool,consorcio auditool"),
            ("Mutual Ser", "806008394-7", "MUT", "#18a4a6", "mutualser"),
            ("FOMAG", "830053105-3", "FOMAG", "#0a8fc4", "fomag,fondo nacional de prestaciones sociales del magisterio"),
        ]
        for name, nit, code, color, aliases in eps_rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO eps (name, nit, code, color, aliases, active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (name, nit, code, color, aliases, now_iso()),
            )

        defaults = {
            "system_name": "Soportes EPS",
            "company_name": "Gestor de Radicaciones",
            "primary_color": "#1457e8",
            "page_size": "10",
        }
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def audit(
    conn: sqlite3.Connection,
    user: dict[str, Any] | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    details: dict[str, Any] | str | None,
    ip_address: str | None,
) -> None:
    detail_text = json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else details
    conn.execute(
        """
        INSERT INTO audit_logs (user_id, user_name, action, entity_type, entity_id, details, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"] if user else None,
            user["name"] if user else None,
            action,
            entity_type,
            entity_id,
            detail_text,
            ip_address,
            now_iso(),
        ),
    )


def supabase_enabled() -> bool:
    return bool(SUPABASE_URL and has_supabase_server_key())


def supabase_config_message() -> str:
    if not SUPABASE_URL:
        return "Falta SUPABASE_URL en .env"
    role = supabase_key_role(SUPABASE_SERVICE_KEY)
    if role in {"publishable", "anon"}:
        return "La variable SUPABASE_SERVICE_ROLE_KEY tiene una llave publica/anon. Usa una llave secreta del servidor: sb_secret_... o la legacy service_role."
    if not SUPABASE_SERVICE_KEY and SUPABASE_PUBLISHABLE_KEY:
        return "Hay una publishable key configurada, pero falta SUPABASE_SECRET_KEY o SUPABASE_SERVICE_ROLE_KEY para sincronizar desde el backend"
    if not SUPABASE_SERVICE_KEY:
        return "Falta SUPABASE_SECRET_KEY o SUPABASE_SERVICE_ROLE_KEY en .env"
    return "Supabase configurado"


class SupabaseClient:
    def __init__(self) -> None:
        if not supabase_enabled():
            raise RuntimeError(supabase_config_message())
        self.base_url = SUPABASE_URL
        self.service_key = SUPABASE_SERVICE_KEY

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
        }
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        url: str,
        payload: Any | None = None,
        raw: bytes | None = None,
        headers: dict[str, str] | None = None,
        expect_json: bool = True,
    ) -> Any:
        body = raw
        request_headers = self._headers(headers)
        if payload is not None:
            body = json_dumps(payload)
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=45) as response:
                data = response.read()
                if expect_json:
                    return json.loads(data.decode("utf-8") or "null")
                return data
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            lowered = detail.lower()
            if exc.code in {401, 403} and ("permission denied" in lowered or "42501" in lowered):
                raise RuntimeError(
                    "Supabase rechazo la solicitud por permisos. En Vercel configura SUPABASE_SERVICE_ROLE_KEY "
                    "con una llave secreta del servidor (sb_secret_... o legacy service_role), no con la publishable/anon key."
                ) from exc
            raise RuntimeError(f"Supabase {method} {url} respondio {exc.code}: {detail[:700]}") from exc
        except URLError as exc:
            raise RuntimeError(f"No se pudo conectar a Supabase: {exc}") from exc

    def rest_select(self, table: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        query = urlencode(params or {})
        suffix = f"?{query}" if query else ""
        return self.request("GET", f"{self.base_url}/rest/v1/{table}{suffix}")

    def rest_upsert(self, table: str, rows: list[dict[str, Any]], conflict: str) -> None:
        if not rows:
            return
        query = urlencode({"on_conflict": conflict})
        self.request(
            "POST",
            f"{self.base_url}/rest/v1/{table}?{query}",
            payload=rows,
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            expect_json=False,
        )

    def rest_insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        rows = self.request(
            "POST",
            f"{self.base_url}/rest/v1/{table}",
            payload=row,
            headers={"Prefer": "return=representation"},
        )
        return rows[0] if rows else {}

    def rest_update(self, table: str, filters: dict[str, str], values: dict[str, Any]) -> dict[str, Any]:
        query = urlencode(filters)
        rows = self.request(
            "PATCH",
            f"{self.base_url}/rest/v1/{table}?{query}",
            payload=values,
            headers={"Prefer": "return=representation"},
        )
        return rows[0] if rows else {}

    def rest_delete(self, table: str, filters: dict[str, str]) -> None:
        query = urlencode(filters)
        self.request(
            "DELETE",
            f"{self.base_url}/rest/v1/{table}?{query}",
            headers={"Prefer": "return=minimal"},
            expect_json=False,
        )

    def ensure_bucket(self) -> None:
        payload = {"id": SUPABASE_BUCKET, "name": SUPABASE_BUCKET, "public": False}
        try:
            self.request("POST", f"{self.base_url}/storage/v1/bucket", payload=payload, expect_json=False)
        except RuntimeError as exc:
            message = str(exc).lower()
            if "already exists" not in message and "duplicate" not in message and "409" not in message:
                raise

    def object_url(self, storage_path: str) -> str:
        object_path = quote(storage_path.replace("\\", "/").lstrip("/"), safe="/")
        bucket = quote(SUPABASE_BUCKET, safe="")
        return f"{self.base_url}/storage/v1/object/{bucket}/{object_path}"

    def upload_object(self, storage_path: str, payload: bytes, content_type: str = "application/pdf") -> None:
        self.request(
            "POST",
            self.object_url(storage_path),
            raw=payload,
            headers={"Content-Type": content_type, "x-upsert": "true"},
            expect_json=False,
        )

    def download_object(self, storage_path: str) -> bytes:
        return self.request("GET", self.object_url(storage_path), expect_json=False)


SUPABASE_LAST_SYNC: dict[str, Any] = {"ok": False, "message": "Sin sincronizar"}


def supabase_path(path: str | None) -> str:
    return (path or "").replace("\\", "/").lstrip("/")


def audit_fingerprint(row: sqlite3.Row | dict[str, Any]) -> str:
    data = dict(row)
    base = "|".join(
        str(data.get(key) or "")
        for key in ["user_name", "action", "entity_type", "entity_id", "details", "ip_address", "created_at"]
    )
    return hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()


def chunked(rows: list[dict[str, Any]], size: int = 100) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def sync_all_to_supabase(upload_files: bool = True) -> dict[str, Any]:
    if not supabase_enabled():
        return {"enabled": False, "ok": False, "message": "Supabase no esta configurado"}

    client = SupabaseClient()
    client.ensure_bucket()
    stats: dict[str, Any] = {"enabled": True, "ok": True, "uploaded_files": 0}
    with db() as conn:
        app_users = [
            {
                "local_id": row["id"],
                "name": row["name"],
                "email": row["email"],
                "password_hash": row["password_hash"],
                "role": row["role"],
                "active": int(row["active"]),
                "created_at": row["created_at"],
            }
            for row in conn.execute("SELECT * FROM users").fetchall()
        ]
        eps_rows = [
            {
                "local_id": row["id"],
                "name": row["name"],
                "nit": row["nit"],
                "code": row["code"],
                "color": row["color"],
                "logo_url": row["logo_url"],
                "aliases": row["aliases"],
                "active": int(row["active"]),
                "created_at": row["created_at"],
            }
            for row in conn.execute("SELECT * FROM eps").fetchall()
        ]
        support_rows = [
            {
                "local_id": row["id"],
                "original_filename": row["original_filename"],
                "stored_filename": row["stored_filename"],
                "path": supabase_path(row["path"]),
                "storage_path": supabase_path(row["path"]),
                "eps_id": row["eps_id"],
                "eps_name": row["eps_name"],
                "radication_date": row["radication_date"],
                "radicado": row["radicado"],
                "factura": row["factura"],
                "corte": row["corte"],
                "invoice_count": int(row["invoice_count"] or 0),
                "invoice_numbers": row["invoice_numbers"],
                "nit_eps": row["nit_eps"],
                "valor_radicado": row["valor_radicado"],
                "year": row["year"],
                "month": row["month"],
                "uploaded_at": row["uploaded_at"],
                "uploaded_by": row["uploaded_by"],
                "uploaded_by_name": row["uploaded_by_name"],
                "size_bytes": int(row["size_bytes"] or 0),
                "sha256": row["sha256"],
                "status": row["status"],
                "observations": row["observations"],
                "extracted_text": row["extracted_text"],
            }
            for row in conn.execute("SELECT * FROM supports").fetchall()
        ]
        audit_rows = [
            {
                "local_id": row["id"],
                "fingerprint": audit_fingerprint(row),
                "user_id": row["user_id"],
                "user_name": row["user_name"],
                "action": row["action"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "details": row["details"],
                "ip_address": row["ip_address"],
                "created_at": row["created_at"],
            }
            for row in conn.execute("SELECT * FROM audit_logs").fetchall()
        ]
        settings_rows = [{"key": row["key"], "value": row["value"]} for row in conn.execute("SELECT * FROM settings").fetchall()]

    for rows, table, conflict in [
        (app_users, "app_users", "email"),
        (eps_rows, "eps", "name"),
        (settings_rows, "settings", "key"),
        (support_rows, "supports", "sha256"),
        (audit_rows, "audit_logs", "fingerprint"),
    ]:
        for batch in chunked(rows):
            client.rest_upsert(table, batch, conflict)
        stats[table] = len(rows)

    if upload_files:
        for row in support_rows:
            path = (BASE_DIR / row["path"]).resolve()
            if str(path).startswith(str(STORAGE_DIR.resolve())) and path.exists():
                client.upload_object(row["storage_path"], path.read_bytes())
                stats["uploaded_files"] += 1

    stats["message"] = f"Sincronizado con Supabase: {len(support_rows)} soportes"
    return stats


def local_user_for_restore(conn: sqlite3.Connection, user_name: str | None, uploaded_by: int | None = None) -> int:
    if uploaded_by:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (uploaded_by,)).fetchone()
        if row:
            return int(row["id"])
    if user_name:
        row = conn.execute("SELECT id FROM users WHERE lower(name) = lower(?)", (user_name,)).fetchone()
        if row:
            return int(row["id"])
    row = conn.execute("SELECT id FROM users WHERE active = 1 ORDER BY role = 'Administrador' DESC, id LIMIT 1").fetchone()
    return int(row["id"]) if row else 1


def restore_from_supabase(download_files: bool = False) -> dict[str, Any]:
    if not supabase_enabled():
        return {"enabled": False, "ok": False, "message": "Supabase no esta configurado"}

    client = SupabaseClient()
    stats: dict[str, Any] = {"enabled": True, "ok": True, "downloaded_files": 0}
    remote_users = client.rest_select("app_users", {"select": "*", "limit": 10000})
    remote_eps = client.rest_select("eps", {"select": "*", "limit": 10000})
    remote_settings = client.rest_select("settings", {"select": "*", "limit": 10000})
    remote_supports = client.rest_select("supports", {"select": "*", "limit": 10000})
    remote_audit = client.rest_select("audit_logs", {"select": "*", "limit": 10000})

    with db() as conn:
        for item in remote_users:
            row = conn.execute("SELECT id FROM users WHERE lower(email) = lower(?)", (item.get("email"),)).fetchone()
            values = (
                item.get("name") or "Usuario",
                item.get("email"),
                item.get("password_hash") or hash_password(secrets.token_urlsafe(24)),
                item.get("role") or "Consulta",
                int(item.get("active", 1)),
                item.get("created_at") or now_iso(),
            )
            if row:
                conn.execute(
                    "UPDATE users SET name = ?, email = ?, password_hash = ?, role = ?, active = ?, created_at = ? WHERE id = ?",
                    (*values, row["id"]),
                )
            elif item.get("email"):
                local_id = item.get("local_id")
                if local_id and not conn.execute("SELECT id FROM users WHERE id = ?", (local_id,)).fetchone():
                    conn.execute(
                        "INSERT INTO users (id, name, email, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (local_id, *values),
                    )
                else:
                    conn.execute(
                        "INSERT INTO users (name, email, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        values,
                    )

        for item in remote_eps:
            if not item.get("name"):
                continue
            row = conn.execute("SELECT id FROM eps WHERE lower(name) = lower(?)", (item.get("name"),)).fetchone()
            values = (
                item.get("name"),
                item.get("nit"),
                item.get("code"),
                item.get("color") or "#1769e0",
                item.get("logo_url"),
                item.get("aliases") or "",
                int(item.get("active", 1)),
                item.get("created_at") or now_iso(),
            )
            if row:
                conn.execute(
                    "UPDATE eps SET name = ?, nit = ?, code = ?, color = ?, logo_url = ?, aliases = ?, active = ?, created_at = ? WHERE id = ?",
                    (*values, row["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO eps (name, nit, code, color, logo_url, aliases, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )

        for item in remote_settings:
            if item.get("key"):
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (item.get("key"), item.get("value") or ""))

        for item in remote_supports:
            if not item.get("sha256"):
                continue
            eps_row = get_or_create_eps(conn, item.get("eps_name") or "", item.get("nit_eps"))
            uploaded_by = local_user_for_restore(conn, item.get("uploaded_by_name"), item.get("uploaded_by"))
            storage_path = supabase_path(item.get("storage_path") or item.get("path"))
            stored_filename = item.get("stored_filename") or Path(storage_path).name or slugify(item.get("original_filename") or "soporte.pdf")
            values = (
                item.get("original_filename") or stored_filename,
                stored_filename,
                storage_path,
                eps_row["id"] if eps_row else None,
                eps_row["name"] if eps_row else item.get("eps_name"),
                item.get("radication_date"),
                item.get("radicado"),
                item.get("factura"),
                item.get("corte"),
                int(item.get("invoice_count") or 0),
                item.get("invoice_numbers"),
                item.get("nit_eps"),
                item.get("valor_radicado"),
                item.get("year"),
                item.get("month"),
                item.get("uploaded_at") or now_iso(),
                uploaded_by,
                item.get("uploaded_by_name") or "Usuario migrado",
                int(item.get("size_bytes") or 0),
                item.get("sha256"),
                item.get("status") or "guardado",
                item.get("observations") or "",
                item.get("extracted_text") or "",
            )
            row = conn.execute("SELECT id FROM supports WHERE sha256 = ?", (item.get("sha256"),)).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE supports
                    SET original_filename = ?, stored_filename = ?, path = ?, eps_id = ?, eps_name = ?, radication_date = ?,
                        radicado = ?, factura = ?, corte = ?, invoice_count = ?, invoice_numbers = ?, nit_eps = ?,
                        valor_radicado = ?, year = ?, month = ?, uploaded_at = ?, uploaded_by = ?, uploaded_by_name = ?,
                        size_bytes = ?, sha256 = ?, status = ?, observations = ?, extracted_text = ?
                    WHERE id = ?
                    """,
                    (*values, row["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO supports (
                        original_filename, stored_filename, path, eps_id, eps_name, radication_date,
                        radicado, factura, corte, invoice_count, invoice_numbers, nit_eps, valor_radicado, year, month,
                        uploaded_at, uploaded_by, uploaded_by_name, size_bytes, sha256, status, observations, extracted_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )

        for item in remote_audit:
            fingerprint = item.get("fingerprint")
            exists = conn.execute(
                """
                SELECT id FROM audit_logs
                WHERE created_at = ? AND action = ? AND entity_type = ? AND COALESCE(details, '') = COALESCE(?, '')
                LIMIT 1
                """,
                (item.get("created_at"), item.get("action"), item.get("entity_type"), item.get("details")),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO audit_logs (user_id, user_name, action, entity_type, entity_id, details, ip_address, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.get("user_id"),
                        item.get("user_name"),
                        item.get("action"),
                        item.get("entity_type"),
                        item.get("entity_id"),
                        item.get("details") or fingerprint,
                        item.get("ip_address"),
                        item.get("created_at") or now_iso(),
                    ),
                )
        conn.commit()

    if download_files:
        for item in remote_supports:
            storage_path = supabase_path(item.get("storage_path") or item.get("path"))
            local_path = (BASE_DIR / storage_path).resolve()
            if not str(local_path).startswith(str(STORAGE_DIR.resolve())) or local_path.exists():
                continue
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(client.download_object(storage_path))
            stats["downloaded_files"] += 1

    stats.update(
        {
            "app_users": len(remote_users),
            "eps": len(remote_eps),
            "settings": len(remote_settings),
            "supports": len(remote_supports),
            "audit_logs": len(remote_audit),
            "message": f"Restaurado desde Supabase: {len(remote_supports)} soportes",
        }
    )
    return stats


def sync_supabase_after_write(upload_files: bool = True) -> None:
    global SUPABASE_LAST_SYNC
    if not (supabase_enabled() and SUPABASE_SYNC_ON_WRITE):
        return
    try:
        SUPABASE_LAST_SYNC = sync_all_to_supabase(upload_files=upload_files)
    except Exception as exc:
        SUPABASE_LAST_SYNC = {"enabled": True, "ok": False, "message": str(exc)}
        print(f"[supabase] {exc}", file=sys.stderr)


def ensure_support_file_from_supabase(row: sqlite3.Row | dict[str, Any]) -> Path:
    data = dict(row)
    path = (BASE_DIR / data["path"]).resolve()
    if not str(path).startswith(str(STORAGE_DIR.resolve())):
        raise FileNotFoundError("Ruta de soporte no permitida")
    if path.exists() or not supabase_enabled():
        return path
    client = SupabaseClient()
    storage_path = supabase_path(data.get("path"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(client.download_object(storage_path))
    return path


def sb_all(table: str, order: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"select": "*", "limit": 10000}
    if order:
        params["order"] = order
    return SupabaseClient().rest_select(table, params)


def sb_find_by_id(table: str, item_id: int) -> dict[str, Any] | None:
    rows = SupabaseClient().rest_select(table, {"select": "*", "id": f"eq.{item_id}", "limit": 1})
    return rows[0] if rows else None


def sb_update_by_id(table: str, item_id: int, values: dict[str, Any]) -> dict[str, Any]:
    return SupabaseClient().rest_update(table, {"id": f"eq.{item_id}"}, values)


def sb_get_or_create_eps(eps_name: str, nit: str | None = None) -> dict[str, Any] | None:
    eps_name = (eps_name or "").strip()
    if not eps_name:
        return None
    client = SupabaseClient()
    rows = client.rest_select("eps", {"select": "*", "limit": 10000})
    for row in rows:
        if str(row.get("name") or "").lower() == eps_name.lower():
            return row
    return client.rest_insert(
        "eps",
        {
            "name": eps_name,
            "nit": nit,
            "code": slugify(eps_name).upper()[:10],
            "color": "#" + hashlib.sha1(eps_name.encode("utf-8")).hexdigest()[:6],
            "aliases": "",
            "active": 1,
            "created_at": now_iso(),
        },
    )


def sb_seed_defaults() -> None:
    client = SupabaseClient()
    client.ensure_bucket()
    default_users = configured_default_users()
    if default_users and not client.rest_select("app_users", {"select": "id", "limit": 1}):
        client.rest_upsert(
            "app_users",
            [
                {
                    "name": name,
                    "email": email,
                    "password_hash": hash_password(password),
                    "role": role,
                    "active": 1,
                    "created_at": now_iso(),
                }
                for name, email, password, role in default_users
            ],
            "email",
        )
    if not client.rest_select("eps", {"select": "id", "limit": 1}):
        client.rest_upsert(
            "eps",
            [
                {
                    "name": name,
                    "nit": nit,
                    "code": code,
                    "color": color,
                    "aliases": aliases,
                    "active": 1,
                    "created_at": now_iso(),
                }
                for name, nit, code, color, aliases in DEFAULT_EPS_ROWS
            ],
            "name",
        )
    existing_settings = {row["key"] for row in client.rest_select("settings", {"select": "key", "limit": 10000})}
    missing_settings = [
        row
        for row in [
            {"key": "system_name", "value": "Soportes EPS"},
            {"key": "company_name", "value": "Gestor de Radicaciones"},
            {"key": "primary_color", "value": "#1457e8"},
            {"key": "page_size", "value": "10"},
        ]
        if row["key"] not in existing_settings
    ]
    if missing_settings:
        client.rest_upsert("settings", missing_settings, "key")


def sb_audit(
    user: dict[str, Any] | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    details: dict[str, Any] | str | None,
    ip_address: str | None,
) -> None:
    created_at = now_iso()
    detail_text = json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else details
    row = {
        "fingerprint": uuid.uuid4().hex,
        "user_id": user.get("id") if user else None,
        "user_name": user.get("name") if user else None,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": detail_text,
        "ip_address": ip_address,
        "created_at": created_at,
    }
    SupabaseClient().rest_insert("audit_logs", row)


def sb_support_storage_path(
    metadata: dict[str, Any],
    original_filename: str,
    radicado: str | None,
    existing_paths: set[str] | None = None,
) -> str:
    existing_paths = existing_paths or set()
    date_value = metadata.get("radication_date")
    eps_name = metadata.get("eps_name") or "EPS_Sin_Detectar"
    if date_value:
        dt = datetime.strptime(date_value, "%Y-%m-%d")
        folder = f"storage/{dt.year}/{dt.month:02d}-{MONTH_NAMES[dt.month]}/{slugify(eps_name, 'EPS')}"
    else:
        folder = "storage/pendientes"
    base_name = slugify(radicado or Path(original_filename).stem, "soporte")
    candidate = f"{folder}/{base_name}.pdf"
    counter = 2
    while candidate in existing_paths:
        candidate = f"{folder}/{base_name}_{counter}.pdf"
        counter += 1
    return candidate


def sb_support_rows(include_deleted: bool = False) -> list[dict[str, Any]]:
    rows = sb_all("supports")
    if include_deleted:
        return rows
    return [row for row in rows if row.get("status") != "eliminado"]


def text_contains(value: Any, needle: str) -> bool:
    return needle.lower() in str(value or "").lower()


def sb_filtered_supports(query: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows = sb_support_rows()
    eps = (query.get("eps") or [""])[0].strip()
    status = (query.get("status") or [""])[0].strip()
    uploaded_by = (query.get("uploaded_by") or [""])[0].strip()
    raw_year = (query.get("year") or [""])[0].strip()
    raw_month = (query.get("month") or [""])[0].strip()
    corte = (query.get("corte") or [""])[0].strip()
    date_from = (query.get("date_from") or [""])[0].strip()
    date_to = (query.get("date_to") or [""])[0].strip()
    filename = (query.get("filename") or [""])[0].strip()
    radicado = (query.get("radicado") or [""])[0].strip()
    factura = (query.get("factura") or [""])[0].strip()
    search = (query.get("search") or [""])[0].strip()

    def keep(row: dict[str, Any]) -> bool:
        if eps and row.get("eps_name") != eps:
            return False
        if status and row.get("status") != status:
            return False
        if uploaded_by and row.get("uploaded_by_name") != uploaded_by:
            return False
        if corte and str(row.get("corte") or "") != corte:
            return False
        row_date = str(row.get("radication_date") or "")
        if raw_year and str(row.get("year") or "") != raw_year:
            return False
        if raw_month and str(row.get("month") or "") != raw_month:
            return False
        if date_from and row_date < date_from:
            return False
        if date_to and row_date > date_to:
            return False
        if filename and not text_contains(row.get("original_filename"), filename):
            return False
        if radicado and not (text_contains(row.get("radicado"), radicado) or text_contains(row.get("extracted_text"), radicado)):
            return False
        if factura and not (
            text_contains(row.get("factura"), factura)
            or text_contains(row.get("invoice_numbers"), factura)
            or text_contains(row.get("extracted_text"), factura)
        ):
            return False
        if search and not any(
            text_contains(row.get(field), search)
            for field in ["eps_name", "radicado", "factura", "invoice_numbers", "original_filename", "extracted_text"]
        ):
            return False
        return True

    return [row for row in rows if keep(row)]


def sb_sort_supports(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (str(row.get("radication_date") or row.get("uploaded_at") or ""), int(row.get("id") or 0)),
        reverse=True,
    )


def sb_group_counts(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get(key) or "Sin dato")
        counts[label] = counts.get(label, 0) + 1
    return [{"label": label, "total": total} for label, total in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def sb_month_year(row: dict[str, Any]) -> tuple[int | None, int | None]:
    if row.get("year") and row.get("month"):
        return int(row["year"]), int(row["month"])
    year, month = support_cycle_year_month(str(row.get("radication_date") or ""), str(row.get("corte") or ""))
    if year and month:
        return year, month
    return None, None


FOMAG_TABLE_CHAR_MAP = {
    "D": "0",
    "?": "1",
    "@": "2",
    "m": "3",
    "H": "4",
    "n": "5",
    "E": "6",
    "r": "7",
    "I": "8",
    "q": "9",
    "‘": "F",
    "`": "F",
    "'": "F",
    "o": "V",
    "p": "E",
}

FOMAG_CID_CHAR_MAP = {
    "25": "0",
    "13": "1",
    "16": "2",
    "14": "3",
    "22": "4",
    "21": "5",
    "17": "6",
    "24": "7",
    "15": "8",
    "23": "9",
    "18": "F",
    "19": "V",
    "20": "E",
}

FOMAG_DATE_CHAR_MAP = {
    "c": "0",
    "f": "1",
    "b": "2",
    "h": "4",
    "d": "6",
    "j": "7",
    "i": "8",
    "e": "-",
    "g": ":",
    "U": " ",
}


def decode_fomag_ascii_token(token: str) -> str:
    return "".join(FOMAG_TABLE_CHAR_MAP.get(ch, "") for ch in token)


def decode_fomag_cid_token(token: str) -> str:
    decoded = []
    for cid in re.findall(r"\(cid:(\d+)\)", token):
        decoded.append(FOMAG_CID_CHAR_MAP.get(cid, ""))
    return "".join(decoded)


def repair_fomag_gmail_text(text: str) -> str:
    """Recover useful fields from Gmail/FOMAG PDFs with broken embedded font maps."""
    ascii_rows: list[tuple[str, str, str]] = []
    ascii_pattern = re.compile(
        r"([?@mHnEDrIq]{7,12})\s+([‘`']opp[?@mHnEDrIq]{4,12})\s+([‘`']opp[?@mHnEDrIq]{4,12})"
    )
    for raw_radicado, raw_factura, raw_paquete in ascii_pattern.findall(text):
        row = (
            decode_fomag_ascii_token(raw_radicado),
            decode_fomag_ascii_token(raw_factura),
            decode_fomag_ascii_token(raw_paquete),
        )
        if row[0].isdigit() and row[1].startswith("FVEE"):
            ascii_rows.append(row)

    cid_rows: list[tuple[str, str, str]] = []
    cid_token = r"(?:\(cid:\d+\)){6,12}"
    cid_pattern = re.compile(rf"({cid_token})\s+({cid_token})\s+({cid_token})")
    for raw_radicado, raw_factura, raw_paquete in cid_pattern.findall(text):
        row = (
            decode_fomag_cid_token(raw_radicado),
            decode_fomag_cid_token(raw_factura),
            decode_fomag_cid_token(raw_paquete),
        )
        if row[0].isdigit() and row[1].startswith("FVEE"):
            cid_rows.append(row)

    rows: list[tuple[str, str, str]] = []
    seen = set()
    for row in [*ascii_rows, *cid_rows]:
        key = (row[0], row[1])
        if key not in seen:
            rows.append(row)
            seen.add(key)

    date_value = ""
    for match in re.finditer(r"[bcdefUghij]{10,24}", text):
        decoded = "".join(FOMAG_DATE_CHAR_MAP.get(ch, "") for ch in match.group(0))
        date_match = re.search(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?", decoded)
        if date_match:
            date_value = date_match.group(0)
            break

    if not rows and not date_value:
        return text

    repaired = ["FOMAG", "Radicación de facturas"]
    if date_value:
        repaired.append(f"Fecha de radicación: {date_value}")
    if rows:
        repaired.append(f"Cargue exitoso: {len(rows)} facturas procesadas")
        repaired.append(f"Número de radicado: {rows[0][0]}")
        repaired.append(f"Número de factura: {rows[0][1]}")
        repaired.extend(f"Radicado: {radicado} Factura: {factura} Paquete: {paquete}" for radicado, factura, paquete in rows)
    return text + "\n\n--- TEXTO REPARADO FOMAG/GMAIL ---\n" + "\n".join(repaired)


AUDITOOL_GMAIL_CHAR_MAP = {
    "?": "1",
    "D": "2",
    "m": "3",
    "l": "4",
    "I": "5",
    "F": "6",
    "@": "7",
    "k": "8",
    "t": "9",
    "E": "0",
    "v": "/",
    "w": "F",
    "T": "V",
    "Y": "E",
    "e": ",",
}


def decode_auditool_gmail_token(token: str) -> str:
    return "".join(AUDITOOL_GMAIL_CHAR_MAP.get(ch, ch) for ch in token)


def repair_auditool_gmail_text(text: str, filename: str = "") -> str:
    """Recover Auditool Gmail supports with encoded body fields."""
    radicado = ""
    filename_match = re.search(r"radicado\s+no\.?\s*([0-9]{4,20})", filename, re.IGNORECASE)
    if filename_match:
        radicado = filename_match.group(1)
    else:
        for raw_value in re.findall(r"[tk?@]{4,20}", text):
            decoded = decode_auditool_gmail_token(raw_value)
            if re.fullmatch(r"\d{4,20}", decoded):
                radicado = decoded
                break

    date_value = ""
    for raw_value in re.findall(r"[?@vDEF]{8}", text):
        decoded = decode_auditool_gmail_token(raw_value)
        if re.fullmatch(r"\d{2}/\d{2}/\d{2}", decoded):
            date_value = decoded
            break

    invoices: list[str] = []
    seen = set()
    for raw_value in re.findall(r"wTYY[?I@DFmltewTYY]+", text):
        decoded = decode_auditool_gmail_token(raw_value)
        for invoice in re.findall(r"FVEE[0-9A-Z._/-]+", decoded, flags=re.IGNORECASE):
            invoice = invoice.upper().strip(".,;:")
            if invoice not in seen:
                invoices.append(invoice)
                seen.add(invoice)

    if not (radicado or date_value or invoices):
        return text

    repaired = ["CONSORCIO AUDITOOL 25", "Auditool", "Proceso en revision de radicacion"]
    if date_value:
        repaired.append(f"Fecha de radicacion: {date_value}")
    if radicado:
        repaired.append(f"Numero de radicado: {radicado}")
        repaired.append(f"Radicado IPS No: {radicado}")
    if invoices:
        repaired.append(f"Cargue exitoso: {len(invoices)} facturas procesadas")
        repaired.append(f"Numero de factura: {invoices[0]}")
        repaired.extend(f"Factura: {invoice}" for invoice in invoices)
    repaired.append("Estado: En tramite de radicacion")
    return text + "\n\n--- TEXTO REPARADO AUDITOOL/GMAIL ---\n" + "\n".join(repaired)


FAMISANAR_GMAIL_CHAR_MAP = {
    "|": "F",
    "}": "A",
    "~": "C",
    "p": "I",
    "cid:126": "C",
    "cid:127": "T",
    "cid:128": "U",
    "cid:129": "R",
    "cid:130": "D",
    "cid:131": "O",
    "cid:132": "V",
    "cid:133": "E",
    "cid:134": "1",
    "cid:135": "5",
    "cid:136": "4",
    "cid:137": "6",
    "cid:138": "2",
    "cid:139": "8",
    "cid:140": "7",
    "cid:141": "3",
    "cid:142": "9",
    "cid:143": "0",
}


FAMISANAR_GMAIL_DATE_CHAR_MAP = {
    "@": "1",
    "A": " ",
    "B": "d",
    "6": "e",
    "C": "j",
    "D": "u",
    "<": "n",
    "5": "i",
    ">": "o",
    "E": "2",
    "F": "0",
    "G": "6",
    "3": "a",
    "H": "l",
    ";": "s",
    "I": "9",
    "J": ":",
    "K": "3",
}


def decode_famisanar_gmail_token(token: str) -> str:
    decoded = []
    for match in re.finditer(r"\(cid:(\d+)\)|.", token):
        key = f"cid:{match.group(1)}" if match.group(1) else match.group(0)
        decoded.append(FAMISANAR_GMAIL_CHAR_MAP.get(key, ""))
    return "".join(decoded)


def decode_famisanar_gmail_date_token(token: str) -> str:
    return "".join(FAMISANAR_GMAIL_DATE_CHAR_MAP.get(ch, "") for ch in token)


def extract_famisanar_gmail_date(text: str) -> str:
    for raw_value in re.findall(r"\S*AB6A\S*AB6A\S*", text):
        decoded = decode_famisanar_gmail_date_token(raw_value)
        date_match = re.search(r"\d{1,2}\s+de\s+[a-z]+\s+de\s+\d{4}", decoded, flags=re.IGNORECASE)
        if date_match:
            return date_match.group(0)
    return ""


def repair_famisanar_gmail_text(text: str, filename: str = "") -> str:
    """Recover Famisanar Gmail supports where the factura/radicado table uses an embedded font."""
    rows: list[tuple[str, str]] = []
    seen = set()
    row_pattern = re.compile(r"(\|(?:\(cid:\d+\)){7,12})\s+((?:\(cid:\d+\)){6,12})")
    for raw_invoice, raw_radicado in row_pattern.findall(text):
        invoice = decode_famisanar_gmail_token(raw_invoice)
        radicado = decode_famisanar_gmail_token(raw_radicado)
        if not (invoice.startswith("FVEE") and radicado.isdigit()):
            continue
        key = (invoice, radicado)
        if key not in seen:
            rows.append(key)
            seen.add(key)

    date_value = extract_famisanar_gmail_date(text)
    if not (rows or date_value or "famisanar" in normalize_text(filename)):
        return text

    repaired = ["Famisanar", "EPS Famisanar", "Relacion de facturas radicadas"]
    if date_value:
        repaired.append(f"Fecha de radicacion: {date_value}")
    if rows:
        repaired.append(f"Cargue exitoso: {len(rows)} facturas procesadas")
        repaired.append(f"Numero de radicado: {rows[0][1]}")
        repaired.append(f"Numero de factura: {rows[0][0]}")
        for invoice, radicado in rows:
            repaired.append(f"Radicado: {radicado} Factura: {invoice}")
            repaired.append(f"Factura: {invoice}")
    return text + "\n\n--- TEXTO REPARADO FAMISANAR/GMAIL ---\n" + "\n".join(repaired)


def repair_known_gmail_text(text: str, filename: str = "") -> str:
    repaired = repair_fomag_gmail_text(text)
    repaired = repair_auditool_gmail_text(repaired, filename)
    repaired = repair_famisanar_gmail_text(repaired, filename)
    return repaired


def extract_pdf_text(pdf_path: Path) -> str:
    try:
        import pdfplumber

        parts = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
        text = "\n".join(parts).strip()
        if text:
            return repair_known_gmail_text(text, pdf_path.name)
    except Exception:
        pass

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        return repair_known_gmail_text("\n".join(page.extract_text() or "" for page in reader.pages).strip(), pdf_path.name)
    except Exception as exc:
        return f"[No se pudo extraer texto automáticamente: {exc}]"


def parse_date(value: str) -> str | None:
    clean = normalize_text(value).replace(".", "")
    formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"]
    for fmt in formats:
        try:
            return datetime.strptime(clean, fmt).date().isoformat()
        except ValueError:
            pass

    match = re.search(
        r"(\d{1,2})\s+de\s+([a-z]+)\s+(?:de\s+)?(\d{4})",
        clean,
        flags=re.IGNORECASE,
    )
    if match:
        day = int(match.group(1))
        month = SPANISH_MONTHS.get(match.group(2))
        year = int(match.group(3))
        if month:
            try:
                return datetime(year, month, day).date().isoformat()
            except ValueError:
                return None
    return None


def find_first(patterns: list[str], text: str, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            for group in match.groups():
                if group:
                    return group.strip(" \t\r\n:;,.")
    return None


def detect_corte(text: str, filename: str = "") -> str:
    haystack = normalize_text(f"{filename}\n{text}")
    match = re.search(r"\bcorte\s*(?:n(?:o|ro|umero)?\.?\s*)?([123])\b", haystack)
    if match:
        return match.group(1)
    match = re.search(r"\bc\s*[-_ ]?([123])\b", haystack)
    return match.group(1) if match else ""


def extract_invoice_numbers(text: str, factura: str | None = None) -> tuple[list[str], int]:
    numbers: list[str] = []
    seen = set()

    for pattern in [
        r"\bfactura\b\s*[:#\-]?\s*([A-Z0-9][A-Z0-9._/\-]{3,30})",
        r"\b(FVEE[-_ ]?[A-Z0-9]{3,25})\b",
        r"\b(FE[-_ ]?[A-Z0-9]{3,25})\b",
    ]:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1).strip(" \t\r\n:;,.").upper().replace(" ", "")
            if value in {"FECHA", "FACTURAS", "FACTURA"}:
                continue
            if value not in seen:
                numbers.append(value)
                seen.add(value)

    if factura:
        value = factura.strip().upper().replace(" ", "")
        if value and value not in seen:
            numbers.insert(0, value)
            seen.add(value)

    processed_match = re.search(r"cargue\s+exitoso\s*:\s*(\d+)\s+facturas\s+procesadas", text, re.IGNORECASE)
    processed_count = int(processed_match.group(1)) if processed_match else 0
    if numbers:
        return numbers, len(numbers)
    return numbers, processed_count or (1 if factura else 0)


def find_eps_from_text(text: str, eps_rows: list[sqlite3.Row]) -> dict[str, Any] | None:
    normalized = normalize_text(text)
    best: dict[str, Any] | None = None
    best_len = 0
    for row in eps_rows:
        names = [row["name"]]
        if row["aliases"]:
            names.extend(part.strip() for part in row["aliases"].split(",") if part.strip())
        for name in names:
            needle = normalize_text(name)
            if needle and re.search(rf"\b{re.escape(needle)}\b", normalized) and len(needle) > best_len:
                best = dict(row)
                best_len = len(needle)
    if best:
        return best

    guessed = find_first(
        [
            r"(?:nombre\s+de\s+la\s+eps|eps|entidad|aseguradora)\s*[:\-]\s*([A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9 .&_-]{2,60})",
        ],
        text,
    )
    if guessed:
        return {"id": None, "name": guessed.title(), "nit": None, "color": "#1769e0"}
    return None


def extract_metadata(pdf_path: Path, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    text = extract_pdf_text(pdf_path)
    if conn is not None:
        eps_rows = conn.execute("SELECT * FROM eps WHERE active = 1").fetchall()
    elif USE_SUPABASE_ONLY:
        eps_rows = [row for row in SupabaseClient().rest_select("eps", {"select": "*", "active": "eq.1", "limit": 10000})]
    else:
        eps_rows = []
    eps_match = find_eps_from_text(text, eps_rows)

    date_value = find_first(
        [
            r"(?:fecha\s*(?:de)?\s*radicaci[oó]n|fecha\s*radicado|radicado\s*el|fecha\s*de\s*recepci[oó]n)\s*[:#\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(?:fecha\s*(?:de)?\s*radicaci[oó]n|fecha\s*radicado|radicado\s*el|fecha\s*de\s*recepci[oó]n)\s*[:#\-]?\s*(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
            r"(?:fecha\s*(?:de)?\s*radicaci[oó]n|fecha\s*radicado|radicado\s*el|fecha\s*de\s*recepci[oó]n)\s*[:#\-]?\s*(\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+\s+de\s+\d{4})",
            r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b",
            r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
        ],
        text,
    )
    radication_date = parse_date(date_value or "") if date_value else None

    radicado = find_first(
        [
            r"(?:n[uú]mero\s*(?:de)?\s*radicad[oa]\b|no\.?\s*radicad[oa]\b|nro\.?\s*radicad[oa]\b|radicad[oa]\b|rad\.)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9._/\-]{3,30})",
            r"\b(RAD[-_ ]?[0-9A-Z._/\-]{4,30})\b",
        ],
        text,
    )
    factura = find_first(
        [
            r"(?:n[uú]mero\s*(?:de)?\s*factura\b|no\.?\s*factura\b|factura\b)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9._/\-]{3,30})",
            r"\b(FE[-_ ]?[0-9A-Z._/\-]{4,30})\b",
        ],
        text,
    )
    invoice_numbers, invoice_count = extract_invoice_numbers(text, factura)
    corte = detect_corte(text, pdf_path.name)
    nit = find_first([r"\bNIT\s*[:#\-]?\s*([0-9]{6,12}(?:[- ][0-9])?)"], text)
    valor = find_first(
        [
            r"(?:valor\s*radicado|valor\s*total|total\s*radicado|total)\s*[:$ \-]?\s*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)",
        ],
        text,
    )

    missing = []
    if not eps_match:
        missing.append("eps_name")
    if not radication_date:
        missing.append("radication_date")
    if not corte:
        missing.append("corte")

    return {
        "eps_id": eps_match["id"] if eps_match else None,
        "eps_name": eps_match["name"] if eps_match else "",
        "radication_date": radication_date or "",
        "radicado": radicado or "",
        "factura": factura or "",
        "corte": corte,
        "invoice_count": invoice_count,
        "invoice_numbers": ",".join(invoice_numbers),
        "nit_eps": nit or (eps_match.get("nit") if eps_match else "") or "",
        "valor_radicado": valor or "",
        "missing": missing,
        "status": "pendiente_revision" if missing else "guardado",
        "extracted_text": text[:80_000],
    }


def get_or_create_eps(conn: sqlite3.Connection, eps_name: str, nit: str | None = None) -> sqlite3.Row | None:
    eps_name = (eps_name or "").strip()
    if not eps_name:
        return None
    row = conn.execute("SELECT * FROM eps WHERE lower(name) = lower(?)", (eps_name,)).fetchone()
    if row:
        return row
    color = "#" + hashlib.sha1(eps_name.encode("utf-8")).hexdigest()[:6]
    conn.execute(
        """
        INSERT INTO eps (name, nit, code, color, aliases, active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        (eps_name, nit, slugify(eps_name).upper()[:10], color, "", now_iso()),
    )
    return conn.execute("SELECT * FROM eps WHERE lower(name) = lower(?)", (eps_name,)).fetchone()


def classify_path(
    metadata: dict[str, Any],
    original_filename: str,
    radicado: str | None = None,
    current_path: Path | None = None,
) -> Path:
    date_value = metadata.get("radication_date")
    eps_name = metadata.get("eps_name") or "EPS_Sin_Detectar"
    if date_value:
        dt = datetime.strptime(date_value, "%Y-%m-%d")
        folder = STORAGE_DIR / str(dt.year) / f"{dt.month:02d}-{MONTH_NAMES[dt.month]}" / slugify(eps_name, "EPS")
    else:
        folder = STORAGE_DIR / "pendientes"
    folder.mkdir(parents=True, exist_ok=True)
    base_name = slugify(radicado or Path(original_filename).stem, "soporte")
    candidate = folder / f"{base_name}.pdf"
    counter = 2
    while candidate.exists():
        if current_path and candidate.resolve() == current_path.resolve():
            return candidate
        candidate = folder / f"{base_name}_{counter}.pdf"
        counter += 1
    return candidate


def support_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    if data.get("month"):
        data["month_name"] = MONTH_NAMES.get(int(data["month"]), "")
    data["corte_label"] = CORTE_LABELS.get(str(data.get("corte") or ""), "Sin corte")
    data["invoice_count"] = int(data.get("invoice_count") or 0)
    data["size_label"] = human_size(int(data.get("size_bytes") or 0))
    return data


def human_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} GB"


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def corte_ranges(year: int, month: int) -> list[dict[str, Any]]:
    next_year, next_month_value = next_month(year, month)
    return [
        {
            "id": "1",
            "label": "Corte 1",
            "detail": f"15 al 25 de {MONTH_NAMES[month]}",
            "start": datetime(year, month, 15).date().isoformat(),
            "end": datetime(year, month, 25).date().isoformat(),
        },
        {
            "id": "2",
            "label": "Corte 2",
            "detail": f"25 de {MONTH_NAMES[month]} al 5 de {MONTH_NAMES[next_month_value]}",
            "start": datetime(year, month, 25).date().isoformat(),
            "end": datetime(next_year, next_month_value, 5).date().isoformat(),
        },
        {
            "id": "3",
            "label": "Corte 3",
            "detail": f"5 al 15 de {MONTH_NAMES[next_month_value]}",
            "start": datetime(next_year, next_month_value, 5).date().isoformat(),
            "end": datetime(next_year, next_month_value, 15).date().isoformat(),
        },
    ]


def corte_range(year: int, month: int, corte: str) -> tuple[str, str] | None:
    ranges = corte_ranges(year, month)
    if corte == "ciclo":
        return ranges[0]["start"], ranges[-1]["end"]
    for item in ranges:
        if item["id"] == corte:
            return item["start"], item["end"]
    return None


def cycle_filter_range(raw_year: str, raw_month: str, corte: str = "") -> tuple[str, str] | None:
    if not (raw_year and raw_month):
        return None
    try:
        year = int(raw_year)
        month = int(raw_month)
    except ValueError:
        return None
    if month < 1 or month > 12:
        return None
    return corte_range(year, month, corte or "ciclo")


def support_cycle_year_month(radication_date: str | None, corte: str | None) -> tuple[int | None, int | None]:
    if not radication_date:
        return None, None
    try:
        dt = datetime.strptime(radication_date, "%Y-%m-%d")
    except ValueError:
        return None, None
    corte_value = str(corte or "")
    if corte_value == "2" and dt.day <= 5:
        return previous_month(dt.year, dt.month)
    if corte_value == "3":
        return previous_month(dt.year, dt.month)
    return dt.year, dt.month


def parse_support_cycle_fields(payload: dict[str, Any]) -> tuple[int | None, int | None]:
    raw_year = str(payload.get("year") or "").strip()
    raw_month = str(payload.get("month") or "").strip()
    if not (raw_year and raw_month):
        return None, None
    try:
        year = int(raw_year)
        month = int(raw_month)
    except ValueError as exc:
        raise ValueError("El año y mes del corte deben ser numericos") from exc
    if month < 1 or month > 12:
        raise ValueError("El mes del corte no es valido")
    return year, month


def require_manual_cycle(metadata: dict[str, Any]) -> None:
    missing = list(metadata.get("missing") or [])
    for field in ["year", "month"]:
        if field not in missing:
            missing.append(field)
    metadata["missing"] = missing
    metadata["status"] = "pendiente_revision"


def parse_filters(query: dict[str, list[str]]) -> tuple[str, list[Any]]:
    clauses = ["status != 'eliminado'"]
    params: list[Any] = []
    corte = (query.get("corte") or [""])[0].strip()
    raw_year = (query.get("year") or [""])[0].strip()
    raw_month = (query.get("month") or [""])[0].strip()
    field_map = {
        "eps": "eps_name",
        "status": "status",
        "uploaded_by": "uploaded_by_name",
    }
    for key, column in field_map.items():
        value = (query.get(key) or [""])[0].strip()
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)

    if raw_year:
        clauses.append("year = ?")
        params.append(raw_year)
    if raw_month:
        clauses.append("month = ?")
        params.append(raw_month)
    if corte:
        clauses.append("corte = ?")
        params.append(corte)

    date_from = (query.get("date_from") or [""])[0].strip()
    date_to = (query.get("date_to") or [""])[0].strip()
    if date_from:
        clauses.append("radication_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("radication_date <= ?")
        params.append(date_to)

    text_fields = {"filename": "original_filename"}
    for key, column in text_fields.items():
        value = (query.get(key) or [""])[0].strip()
        if value:
            clauses.append(f"COALESCE({column}, '') LIKE ?")
            params.append(f"%{value}%")

    for key, column in {"radicado": "radicado"}.items():
        value = (query.get(key) or [""])[0].strip()
        if value:
            clauses.append(f"(COALESCE({column}, '') LIKE ? OR COALESCE(extracted_text, '') LIKE ?)")
            like = f"%{value}%"
            params.extend([like, like])

    factura_value = (query.get("factura") or [""])[0].strip()
    if factura_value:
        clauses.append(
            """
            (
                COALESCE(factura, '') LIKE ?
                OR COALESCE(invoice_numbers, '') LIKE ?
                OR COALESCE(extracted_text, '') LIKE ?
            )
            """
        )
        like = f"%{factura_value}%"
        params.extend([like, like, like])

    search = (query.get("search") or [""])[0].strip()
    if search:
        clauses.append(
            """
            (
                COALESCE(eps_name, '') LIKE ?
                OR COALESCE(radicado, '') LIKE ?
                OR COALESCE(factura, '') LIKE ?
                OR COALESCE(invoice_numbers, '') LIKE ?
                OR COALESCE(original_filename, '') LIKE ?
                OR COALESCE(extracted_text, '') LIKE ?
            )
            """
        )
        like = f"%{search}%"
        params.extend([like, like, like, like, like, like])

    return " AND ".join(clauses), params


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "SoportesEPS/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))

    def do_GET(self) -> None:
        self.route()

    def do_POST(self) -> None:
        self.route()

    def do_PUT(self) -> None:
        self.route()

    def do_DELETE(self) -> None:
        self.route()

    def route(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path == "/" or path == "/index.html":
                return self.serve_file(STATIC_DIR / "index.html")
            if path.startswith("/static/"):
                requested = (STATIC_DIR / path.removeprefix("/static/")).resolve()
                if not str(requested).startswith(str(STATIC_DIR.resolve())):
                    return self.error_json(403, "Ruta no permitida")
                return self.serve_file(requested)
            if path.startswith("/api/"):
                return self.route_api(path, query)
            return self.error_json(404, "No encontrado")
        except PermissionError as exc:
            return self.error_json(403, str(exc))
        except Exception as exc:
            return self.error_json(500, f"Error interno: {exc}")

    def route_api(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/login" and self.command == "POST":
            return self.login()
        if path == "/api/session" and self.command == "GET":
            return self.session_status()
        if path == "/api/keepalive" and self.command == "GET":
            return self.keepalive(query)

        user = self.require_user()
        if user is None:
            return

        if path == "/api/logout" and self.command == "POST":
            return self.logout(user)
        if path == "/api/me" and self.command == "GET":
            return self.json_response({"user": user, "permissions": sorted(ROLE_PERMISSIONS.get(user["role"], set()))})
        if path == "/api/dashboard" and self.command == "GET":
            return self.dashboard(query)
        if path == "/api/supports" and self.command == "GET":
            return self.list_supports(query)
        if path == "/api/supports/upload" and self.command == "POST":
            return self.upload_supports(user)
        if path == "/api/supports/zip" and self.command == "GET":
            return self.download_zip(user, query)
        if path == "/api/eps" and self.command == "GET":
            return self.list_eps()
        if path == "/api/eps" and self.command == "POST":
            self.require_permission(user, "manage_eps")
            return self.create_eps(user)
        if path == "/api/users" and self.command == "GET":
            self.require_permission(user, "manage_users")
            return self.list_users()
        if path == "/api/users" and self.command == "POST":
            self.require_permission(user, "manage_users")
            return self.create_user(user)
        if path == "/api/reports" and self.command == "GET":
            self.require_permission(user, "view_reports")
            return self.reports()
        if path == "/api/cortes" and self.command == "GET":
            self.require_permission(user, "view_reports")
            return self.cortes(query)
        if path == "/api/settings" and self.command == "GET":
            return self.settings()
        if path == "/api/settings" and self.command == "PUT":
            self.require_permission(user, "configure")
            return self.update_settings(user)
        if path == "/api/supabase/status" and self.command == "GET":
            self.require_permission(user, "configure")
            return self.supabase_status()
        if path == "/api/supabase/sync" and self.command == "POST":
            self.require_permission(user, "configure")
            return self.supabase_sync()

        parts = [part for part in path.split("/") if part]
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "supports":
            support_id = int(parts[2])
            if len(parts) == 3:
                if self.command == "GET":
                    return self.get_support(support_id)
                if self.command == "PUT":
                    self.require_permission(user, "edit_support")
                    return self.update_support(user, support_id)
                if self.command == "DELETE":
                    self.require_permission(user, "delete_support")
                    return self.delete_support(user, support_id)
            if len(parts) == 4 and parts[3] == "file" and self.command == "GET":
                return self.serve_support_file(user, support_id, inline=True)
            if len(parts) == 4 and parts[3] == "download" and self.command == "GET":
                self.require_permission(user, "download")
                return self.serve_support_file(user, support_id, inline=False)

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "eps":
            eps_id = int(parts[2])
            self.require_permission(user, "manage_eps")
            if self.command == "PUT":
                return self.update_eps(user, eps_id)
            if self.command == "DELETE":
                return self.delete_eps(user, eps_id)

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "users":
            target_id = int(parts[2])
            self.require_permission(user, "manage_users")
            if self.command == "PUT":
                return self.update_user(user, target_id)
            if self.command == "DELETE":
                return self.deactivate_user(user, target_id)

        return self.error_json(404, "API no encontrada")

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            return self.error_json(404, "Archivo no encontrado")
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def json_response(self, data: Any, status: int = 200) -> None:
        payload = json_dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def error_json(self, status: int, message: str) -> None:
        self.json_response({"error": message}, status)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def keepalive_authorized(self, query: dict[str, list[str]]) -> bool:
        token = (query.get("token") or [""])[0]
        if KEEPALIVE_SECRET and hmac.compare_digest(token, KEEPALIVE_SECRET):
            return True
        user_agent = self.headers.get("User-Agent", "")
        cron_schedule = self.headers.get("x-vercel-cron-schedule", "")
        return user_agent == "vercel-cron/1.0" or bool(cron_schedule)

    def keepalive(self, query: dict[str, list[str]]) -> None:
        if not self.keepalive_authorized(query):
            return self.error_json(403, "Keepalive no autorizado")
        if not supabase_enabled():
            return self.error_json(503, supabase_config_message())

        started = time.time()
        SupabaseClient().rest_select("settings", {"select": "key", "limit": "1"})
        self.json_response(
            {
                "ok": True,
                "backend": DATA_BACKEND,
                "checked_at": now_iso(),
                "latency_ms": int((time.time() - started) * 1000),
            }
        )

    def current_session_token(self) -> str | None:
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        jar = cookies.SimpleCookie(cookie_header)
        morsel = jar.get("eps_session")
        return morsel.value if morsel else None

    def require_user(self) -> dict[str, Any] | None:
        token = self.current_session_token()
        session = SESSIONS.get(token or "")
        if not session or session["expires"] < time.time():
            signed_session = read_session_token(token)
            if not signed_session:
                return self.error_json(401, "Sesión requerida")
            user_id = int(signed_session["user_id"])
        else:
            session["expires"] = time.time() + 8 * 60 * 60
            user_id = int(session["user_id"])
        if USE_SUPABASE_ONLY:
            row = sb_find_by_id("app_users", user_id)
            if not row or int(row.get("active") or 0) != 1:
                return self.error_json(401, "Usuario inactivo")
            return {
                "id": row["id"],
                "name": row["name"],
                "email": row["email"],
                "role": row["role"],
                "active": row["active"],
            }
        with db() as conn:
            row = conn.execute(
                "SELECT id, name, email, role, active, created_at FROM users WHERE id = ? AND active = 1",
                (user_id,),
            ).fetchone()
        if not row:
            return self.error_json(401, "Usuario inactivo")
        return dict(row)

    def require_permission(self, user: dict[str, Any], permission: str) -> None:
        if permission not in ROLE_PERMISSIONS.get(user["role"], set()):
            raise PermissionError("No tienes permiso para esta acción")

    def session_status(self) -> None:
        token = self.current_session_token()
        session = SESSIONS.get(token or "")
        if not session or session["expires"] < time.time():
            signed_session = read_session_token(token)
            if not signed_session:
                return self.json_response({"authenticated": False})
            user_id = int(signed_session["user_id"])
        else:
            session["expires"] = time.time() + 8 * 60 * 60
            user_id = int(session["user_id"])
        if USE_SUPABASE_ONLY:
            row = sb_find_by_id("app_users", user_id)
            if not row or int(row.get("active") or 0) != 1:
                return self.json_response({"authenticated": False})
            user = {
                "id": row["id"],
                "name": row["name"],
                "email": row["email"],
                "role": row["role"],
                "active": row["active"],
            }
            return self.json_response(
                {
                    "authenticated": True,
                    "user": user,
                    "permissions": sorted(ROLE_PERMISSIONS.get(user["role"], set())),
                }
            )
        with db() as conn:
            row = conn.execute(
                "SELECT id, name, email, role, active, created_at FROM users WHERE id = ? AND active = 1",
                (user_id,),
            ).fetchone()
        if not row:
            return self.json_response({"authenticated": False})
        user = dict(row)
        return self.json_response(
            {
                "authenticated": True,
                "user": user,
                "permissions": sorted(ROLE_PERMISSIONS.get(user["role"], set())),
            }
        )

    def login(self) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_login()
        payload = self.read_json()
        identifier = (payload.get("username") or payload.get("email") or "").strip()
        identifier_norm = normalize_text(identifier)
        password = payload.get("password") or ""
        with db() as conn:
            rows = conn.execute("SELECT * FROM users WHERE active = 1").fetchall()
            row = next(
                (
                    item
                    for item in rows
                    if normalize_text(item["name"]) == identifier_norm
                    or str(item["email"] or "").strip().lower() == identifier.lower()
                ),
                None,
            )
            if not row or not verify_password(password, row["password_hash"]):
                return self.error_json(401, "Usuario o contraseña incorrectos")
            token = create_session_token(int(row["id"]))
            SESSIONS[token] = {"user_id": row["id"], "expires": time.time() + 8 * 60 * 60}
            audit(conn, dict(row), "login", "user", row["id"], {"usuario": identifier}, self.client_address[0])
            conn.commit()

        jar = cookies.SimpleCookie()
        jar["eps_session"] = token
        jar["eps_session"]["path"] = "/"
        jar["eps_session"]["httponly"] = True
        jar["eps_session"]["samesite"] = "Lax"
        payload = json_dumps(
            {
                "user": {
                    "id": row["id"],
                    "name": row["name"],
                    "email": row["email"],
                    "role": row["role"],
                    "active": row["active"],
                },
                "permissions": sorted(ROLE_PERMISSIONS.get(row["role"], set())),
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", jar.output(header="").strip())
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def supabase_login(self) -> None:
        payload = self.read_json()
        identifier = (payload.get("username") or payload.get("email") or "").strip()
        identifier_norm = normalize_text(identifier)
        password = payload.get("password") or ""
        rows = SupabaseClient().rest_select("app_users", {"select": "*", "active": "eq.1", "limit": 10000})
        row = next(
            (
                item
                for item in rows
                if normalize_text(item.get("name") or "") == identifier_norm
                or str(item.get("email") or "").strip().lower() == identifier.lower()
            ),
            None,
        )
        if not row or not verify_password(password, row.get("password_hash") or ""):
            return self.error_json(401, "Usuario o contraseña incorrectos")
        token = create_session_token(int(row["id"]))
        SESSIONS[token] = {"user_id": row["id"], "expires": time.time() + 8 * 60 * 60}
        user = {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "role": row["role"],
            "active": row["active"],
        }
        sb_audit(user, "login", "user", row["id"], {"usuario": identifier}, self.client_address[0])

        jar = cookies.SimpleCookie()
        jar["eps_session"] = token
        jar["eps_session"]["path"] = "/"
        jar["eps_session"]["httponly"] = True
        jar["eps_session"]["samesite"] = "Lax"
        response = json_dumps({"user": user, "permissions": sorted(ROLE_PERMISSIONS.get(row["role"], set()))})
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", jar.output(header="").strip())
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def logout(self, user: dict[str, Any]) -> None:
        token = self.current_session_token()
        if token:
            SESSIONS.pop(token, None)
        if USE_SUPABASE_ONLY:
            sb_audit(user, "logout", "user", user["id"], None, self.client_address[0])
            jar = cookies.SimpleCookie()
            jar["eps_session"] = ""
            jar["eps_session"]["path"] = "/"
            jar["eps_session"]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
            payload = json_dumps({"ok": True})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", jar.output(header="").strip())
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        with db() as conn:
            audit(conn, user, "logout", "user", user["id"], None, self.client_address[0])
            conn.commit()
        jar = cookies.SimpleCookie()
        jar["eps_session"] = ""
        jar["eps_session"]["path"] = "/"
        jar["eps_session"]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        payload = json_dumps({"ok": True})
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", jar.output(header="").strip())
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def supabase_dashboard(self, query: dict[str, list[str]]) -> None:
        rows = sb_filtered_supports(query)
        all_rows = sb_support_rows()
        eps_rows = [row for row in sb_all("eps") if int(row.get("active") or 0) == 1]
        audit_rows = sb_all("audit_logs")
        today = datetime.now().date().isoformat()
        month_start = datetime.now().replace(day=1).date().isoformat()
        by_eps = sb_group_counts(rows, "eps_name")[:8]
        recent = [support_public(row) for row in sb_sort_supports(all_rows)[:8]]
        years = sorted({int(row["year"]) for row in all_rows if row.get("year")}, reverse=True)
        users = sb_group_counts(all_rows, "uploaded_by_name")[:5]
        by_month_counts: dict[tuple[int, int], int] = {}
        for row in all_rows:
            year, month = sb_month_year(row)
            if year and month:
                key = (year, month)
                by_month_counts[key] = by_month_counts.get(key, 0) + 1
        by_month = [
            {"year": year, "month": month, "total": total}
            for (year, month), total in sorted(by_month_counts.items(), reverse=True)[:12]
        ]
        self.json_response(
            {
                "stats": {
                    "total_supports": len(rows),
                    "eps_total": len(eps_rows),
                    "today_count": sum(1 for row in all_rows if str(row.get("uploaded_at") or "")[:10] == today),
                    "month_count": sum(1 for row in all_rows if str(row.get("uploaded_at") or "")[:10] >= month_start),
                    "downloads": sum(1 for row in audit_rows if row.get("action") in {"download_pdf", "download_zip"}),
                    "pending": sum(1 for row in rows if row.get("status") == "pendiente_revision"),
                },
                "by_eps": by_eps,
                "by_month": by_month,
                "recent": recent,
                "years": years,
                "users": users,
            }
        )

    def supabase_list_supports(self, query: dict[str, list[str]]) -> None:
        rows = sb_sort_supports(sb_filtered_supports(query))
        page = max(1, int((query.get("page") or ["1"])[0] or "1"))
        limit = min(100, max(5, int((query.get("limit") or ["10"])[0] or "10")))
        offset = (page - 1) * limit
        self.json_response(
            {
                "items": [support_public(row) for row in rows[offset : offset + limit]],
                "total": len(rows),
                "page": page,
                "limit": limit,
            }
        )

    def supabase_get_support(self, support_id: int) -> None:
        row = sb_find_by_id("supports", support_id)
        if not row:
            return self.error_json(404, "Soporte no encontrado")
        self.json_response({"item": support_public(row)})

    def supabase_find_duplicate(self, filename: str, sha: str, radicado: str | None, exclude_id: int | None = None) -> dict[str, Any] | None:
        for row in sb_support_rows(include_deleted=True):
            if exclude_id and int(row.get("id") or 0) == exclude_id:
                continue
            deleted = row.get("status") == "eliminado"
            checks = [
                ("hash", row.get("sha256") == sha),
            ]
            if not deleted:
                checks.append(("nombre de archivo", str(row.get("original_filename") or "").lower() == filename.lower()))
            if radicado and not deleted:
                checks.insert(1, ("numero de radicado", str(row.get("radicado") or "").lower() == radicado.lower()))
            for reason, matched in checks:
                if matched:
                    data = dict(row)
                    data["reason"] = reason
                    return data
        return None

    def supabase_duplicate_upload_result(self, user: dict[str, Any], original: str, duplicate: dict[str, Any] | None) -> dict[str, Any]:
        duplicate = duplicate or {"reason": "hash"}
        message = "Este soporte ya fue cargado anteriormente."
        if duplicate.get("status") == "eliminado":
            message = "Este PDF ya existe en Supabase como soporte eliminado. No se puede cargar dos veces el mismo archivo."
        sb_audit(
            user,
            "duplicate_pdf",
            "support",
            duplicate.get("id"),
            {"filename": original, "duplicate_by": duplicate.get("reason") or "hash"},
            self.client_address[0],
        )
        return {
            "filename": original,
            "status": "duplicado",
            "message": message,
            "duplicate": duplicate,
        }

    def supabase_restore_deleted_support(
        self,
        user: dict[str, Any],
        deleted: dict[str, Any],
        original: str,
        sha: str,
        content: bytes,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        eps_row = sb_get_or_create_eps(metadata["eps_name"], metadata.get("nit_eps")) if metadata["eps_name"] else None
        if eps_row:
            metadata["eps_id"] = eps_row["id"]
            metadata["eps_name"] = eps_row["name"]
        require_manual_cycle(metadata)
        year = month = None
        deleted_id = int(deleted.get("id") or 0)
        existing_paths = {
            supabase_path(row.get("path"))
            for row in sb_support_rows(include_deleted=True)
            if int(row.get("id") or 0) != deleted_id
        }
        storage_path = sb_support_storage_path(metadata, original, metadata.get("radicado"), existing_paths)
        SupabaseClient().upload_object(storage_path, content)
        row = sb_update_by_id(
            "supports",
            deleted_id,
            {
                "original_filename": original,
                "stored_filename": Path(storage_path).name,
                "path": storage_path,
                "storage_path": storage_path,
                "eps_id": metadata.get("eps_id"),
                "eps_name": metadata.get("eps_name") or None,
                "radication_date": metadata.get("radication_date") or None,
                "radicado": metadata.get("radicado") or None,
                "factura": metadata.get("factura") or None,
                "corte": metadata.get("corte") or None,
                "invoice_count": metadata.get("invoice_count") or 0,
                "invoice_numbers": metadata.get("invoice_numbers") or None,
                "nit_eps": metadata.get("nit_eps") or None,
                "valor_radicado": metadata.get("valor_radicado") or None,
                "year": year,
                "month": month,
                "uploaded_at": now_iso(),
                "uploaded_by": user["id"],
                "uploaded_by_name": user["name"],
                "size_bytes": len(content),
                "sha256": sha,
                "status": metadata["status"],
                "observations": "",
                "extracted_text": metadata["extracted_text"],
            },
        )
        sb_audit(
            user,
            "restore_deleted_pdf",
            "support",
            row.get("id"),
            {"filename": original, "status": metadata["status"], "missing": metadata["missing"]},
            self.client_address[0],
        )
        return {
            "filename": original,
            "status": metadata["status"],
            "message": "Soporte restaurado desde un registro eliminado.",
            "missing": metadata["missing"],
            "item": support_public(row),
        }

    def supabase_upload_supports(self, user: dict[str, Any]) -> None:
        self.require_permission(user, "upload")
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return self.error_json(400, "Se esperaba multipart/form-data")
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        file_items = form["files"] if "files" in form else []
        if not isinstance(file_items, list):
            file_items = [file_items]

        client = SupabaseClient()
        client.ensure_bucket()
        results = []
        for item in file_items:
            if not getattr(item, "filename", None):
                continue
            original = Path(item.filename).name
            if not original.lower().endswith(".pdf"):
                results.append({"filename": original, "status": "rechazado", "message": "Solo se permiten archivos PDF."})
                continue
            content = item.file.read()
            if len(content) > MAX_UPLOAD_BYTES:
                results.append({"filename": original, "status": "rechazado", "message": "El PDF supera el limite de 25 MB."})
                continue

            sha = support_upload_fingerprint(content)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                temp_path = Path(tmp.name)
                tmp.write(content)
            try:
                metadata = extract_metadata(temp_path, None)
            finally:
                temp_path.unlink(missing_ok=True)
            require_manual_cycle(metadata)

            eps_row = sb_get_or_create_eps(metadata["eps_name"], metadata.get("nit_eps")) if metadata["eps_name"] else None
            if eps_row:
                metadata["eps_id"] = eps_row["id"]
                metadata["eps_name"] = eps_row["name"]
            existing_paths = {supabase_path(row.get("path")) for row in sb_support_rows(include_deleted=True)}
            storage_path = sb_support_storage_path(metadata, original, metadata.get("radicado"), existing_paths)
            year = month = None
            client.upload_object(storage_path, content)
            row = client.rest_insert(
                "supports",
                {
                    "original_filename": original,
                    "stored_filename": Path(storage_path).name,
                    "path": storage_path,
                    "storage_path": storage_path,
                    "eps_id": metadata.get("eps_id"),
                    "eps_name": metadata.get("eps_name") or None,
                    "radication_date": metadata.get("radication_date") or None,
                    "radicado": metadata.get("radicado") or None,
                    "factura": metadata.get("factura") or None,
                    "corte": metadata.get("corte") or None,
                    "invoice_count": metadata.get("invoice_count") or 0,
                    "invoice_numbers": metadata.get("invoice_numbers") or None,
                    "nit_eps": metadata.get("nit_eps") or None,
                    "valor_radicado": metadata.get("valor_radicado") or None,
                    "year": year,
                    "month": month,
                    "uploaded_at": now_iso(),
                    "uploaded_by": user["id"],
                    "uploaded_by_name": user["name"],
                    "size_bytes": len(content),
                    "sha256": sha,
                    "status": metadata["status"],
                    "observations": "",
                    "extracted_text": metadata["extracted_text"],
                },
            )
            sb_audit(user, "upload_pdf", "support", row.get("id"), {"filename": original, "status": metadata["status"], "missing": metadata["missing"]}, self.client_address[0])
            results.append(
                {
                    "filename": original,
                    "status": metadata["status"],
                    "message": "Datos extraidos correctamente." if metadata["status"] == "guardado" else "Faltan datos para revision.",
                    "missing": metadata["missing"],
                    "item": support_public(row),
                }
            )
        self.json_response({"results": results})

    def supabase_update_support(self, user: dict[str, Any], support_id: int) -> None:
        payload = self.read_json()
        row = sb_find_by_id("supports", support_id)
        if not row:
            return self.error_json(404, "Soporte no encontrado")
        eps_name = (payload.get("eps_name") or "").strip()
        radication_date = (payload.get("radication_date") or "").strip()
        radicado = (payload.get("radicado") or "").strip()
        factura = (payload.get("factura") or "").strip()
        corte = (payload.get("corte") or "").strip()
        nit_eps = (payload.get("nit_eps") or "").strip()
        valor = (payload.get("valor_radicado") or "").strip()
        observations = (payload.get("observations") or "").strip()
        if corte and corte not in CORTE_LABELS:
            return self.error_json(400, "El corte debe ser 1, 2 o 3")
        try:
            invoice_count = max(0, int((payload.get("invoice_count") or row.get("invoice_count") or 0)))
            year, month = parse_support_cycle_fields(payload)
        except ValueError:
            return self.error_json(400, "La cantidad de facturas, año y mes del corte deben ser validos")
        status = "guardado" if eps_name and radication_date and corte and year and month else "pendiente_revision"
        if radication_date:
            try:
                datetime.strptime(radication_date, "%Y-%m-%d")
            except ValueError:
                return self.error_json(400, "La fecha de radicacion no es valida")
        eps_row = sb_get_or_create_eps(eps_name, nit_eps) if eps_name else None
        existing_paths = {supabase_path(item.get("path")) for item in sb_support_rows(include_deleted=True) if int(item.get("id") or 0) != support_id}
        new_path = sb_support_storage_path({"eps_name": eps_name, "radication_date": radication_date}, row["original_filename"], radicado or row.get("radicado"), existing_paths)
        old_path = supabase_path(row.get("storage_path") or row.get("path"))
        if old_path and old_path != new_path:
            pdf_payload = SupabaseClient().download_object(old_path)
            SupabaseClient().upload_object(new_path, pdf_payload)
        updated = sb_update_by_id(
            "supports",
            support_id,
            {
                "eps_id": eps_row["id"] if eps_row else None,
                "eps_name": eps_row["name"] if eps_row else None,
                "radication_date": radication_date or None,
                "radicado": radicado or None,
                "factura": factura or None,
                "corte": corte or None,
                "invoice_count": invoice_count,
                "nit_eps": nit_eps or None,
                "valor_radicado": valor or None,
                "year": year,
                "month": month,
                "status": status,
                "observations": observations,
                "path": new_path,
                "storage_path": new_path,
                "stored_filename": Path(new_path).name,
            },
        )
        sb_audit(user, "update_support", "support", support_id, payload, self.client_address[0])
        self.json_response({"item": support_public(updated)})

    def supabase_delete_support(self, user: dict[str, Any], support_id: int) -> None:
        row = sb_find_by_id("supports", support_id)
        if not row:
            return self.error_json(404, "Soporte no encontrado")
        sb_update_by_id("supports", support_id, {"status": "eliminado"})
        sb_audit(user, "delete_support", "support", support_id, {"filename": row.get("original_filename")}, self.client_address[0])
        self.json_response({"ok": True})

    def supabase_serve_support_file(self, user: dict[str, Any], support_id: int, inline: bool) -> None:
        row = sb_find_by_id("supports", support_id)
        if not row or row.get("status") == "eliminado":
            return self.error_json(404, "Soporte no encontrado")
        storage_path = supabase_path(row.get("storage_path") or row.get("path"))
        payload = SupabaseClient().download_object(storage_path)
        if not inline:
            sb_audit(user, "download_pdf", "support", support_id, {"filename": row.get("original_filename")}, self.client_address[0])
        disposition = "inline" if inline else "attachment"
        filename = quote(row.get("original_filename") or "soporte.pdf")
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{filename}")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def supabase_download_zip(self, user: dict[str, Any], query: dict[str, list[str]]) -> None:
        self.require_permission(user, "download")
        rows = sb_sort_supports(sb_filtered_supports(query))
        if not rows:
            return self.error_json(404, "No hay soportes para descargar con esos filtros")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            zip_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for row in rows:
                    storage_path = supabase_path(row.get("storage_path") or row.get("path"))
                    pdf_payload = SupabaseClient().download_object(storage_path)
                    year = row.get("year") or "Sin año"
                    month = f"{int(row['month']):02d}-{MONTH_NAMES[int(row['month'])]}" if row.get("month") else "Sin mes"
                    eps_name = slugify(row.get("eps_name") or "Sin EPS")
                    arcname = f"{year}/{month}/{eps_name}/{row.get('original_filename') or Path(storage_path).name}"
                    zf.writestr(arcname, pdf_payload)
            sb_audit(user, "download_zip", "support", None, {"count": len(rows), "filters": {key: value[0] for key, value in query.items()}}, self.client_address[0])
            payload = zip_path.read_bytes()
        finally:
            zip_path.unlink(missing_ok=True)
        filename = f"soportes_eps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f"attachment; filename={filename}")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def supabase_list_eps(self) -> None:
        supports = sb_support_rows()
        items = []
        for eps in sb_all("eps"):
            eps_id = eps.get("id")
            item = dict(eps)
            item["support_count"] = sum(1 for row in supports if row.get("eps_id") == eps_id or row.get("eps_name") == eps.get("name"))
            items.append(item)
        items.sort(key=lambda row: (-(int(row.get("active") or 0)), str(row.get("name") or "")))
        self.json_response({"items": items})

    def supabase_create_eps(self, user: dict[str, Any]) -> None:
        payload = self.read_json()
        row = SupabaseClient().rest_insert(
            "eps",
            {
                "name": payload.get("name"),
                "nit": payload.get("nit"),
                "code": payload.get("code"),
                "color": payload.get("color") or "#1769e0",
                "logo_url": payload.get("logo_url"),
                "aliases": payload.get("aliases") or "",
                "active": 1 if payload.get("active", True) else 0,
                "created_at": now_iso(),
            },
        )
        sb_audit(user, "create_eps", "eps", row.get("id"), payload, self.client_address[0])
        self.json_response({"ok": True})

    def supabase_update_eps(self, user: dict[str, Any], eps_id: int) -> None:
        payload = self.read_json()
        sb_update_by_id(
            "eps",
            eps_id,
            {
                "name": payload.get("name"),
                "nit": payload.get("nit"),
                "code": payload.get("code"),
                "color": payload.get("color") or "#1769e0",
                "logo_url": payload.get("logo_url"),
                "aliases": payload.get("aliases") or "",
                "active": 1 if payload.get("active", True) else 0,
            },
        )
        sb_audit(user, "update_eps", "eps", eps_id, payload, self.client_address[0])
        self.json_response({"ok": True})

    def supabase_delete_eps(self, user: dict[str, Any], eps_id: int) -> None:
        SupabaseClient().rest_delete("eps", {"id": f"eq.{eps_id}"})
        sb_audit(user, "delete_eps", "eps", eps_id, None, self.client_address[0])
        self.json_response({"ok": True})

    def supabase_list_users(self) -> None:
        rows = sb_all("app_users")
        rows.sort(key=lambda row: (-(int(row.get("active") or 0)), str(row.get("name") or "")))
        safe = [{key: value for key, value in row.items() if key not in {"password_hash", "email"}} for row in rows]
        self.json_response({"items": safe})

    def supabase_create_user(self, user: dict[str, Any]) -> None:
        payload = self.read_json()
        name = (payload.get("name") or "").strip()
        password = payload.get("password") or ""
        if not name:
            return self.error_json(400, "El nombre de usuario es obligatorio")
        if not password:
            return self.error_json(400, "La contraseña es obligatoria")
        existing_users = sb_all("app_users")
        if any(normalize_text(row.get("name") or "") == normalize_text(name) for row in existing_users):
            return self.error_json(409, "Ya existe un usuario con ese nombre")
        existing_emails = {str(row.get("email") or "").strip().lower() for row in existing_users if row.get("email")}
        row = SupabaseClient().rest_insert(
            "app_users",
            {
                "name": name,
                "email": technical_user_email(name, existing_emails),
                "password_hash": hash_password(password),
                "role": payload.get("role") or "Consulta",
                "active": 1 if payload.get("active", True) else 0,
                "created_at": now_iso(),
            },
        )
        sb_audit(user, "create_user", "user", row.get("id"), {"usuario": name}, self.client_address[0])
        self.json_response({"ok": True})

    def supabase_update_user(self, user: dict[str, Any], target_id: int) -> None:
        payload = self.read_json()
        current = sb_find_by_id("app_users", target_id)
        if not current:
            return self.error_json(404, "Usuario no encontrado")
        name = (payload.get("name") or "").strip()
        if not name:
            return self.error_json(400, "El nombre de usuario es obligatorio")
        for row in sb_all("app_users"):
            if int(row.get("id") or 0) != target_id and normalize_text(row.get("name") or "") == normalize_text(name):
                return self.error_json(409, "Ya existe un usuario con ese nombre")
        values = {
            "name": name,
            "email": current.get("email") or technical_user_email(name),
            "role": payload.get("role"),
            "active": 1 if payload.get("active", True) else 0,
        }
        if payload.get("password"):
            values["password_hash"] = hash_password(payload["password"])
        sb_update_by_id("app_users", target_id, values)
        sb_audit(user, "update_user", "user", target_id, {"usuario": name}, self.client_address[0])
        self.json_response({"ok": True})

    def supabase_deactivate_user(self, user: dict[str, Any], target_id: int) -> None:
        sb_update_by_id("app_users", target_id, {"active": 0})
        sb_audit(user, "deactivate_user", "user", target_id, None, self.client_address[0])
        self.json_response({"ok": True})

    def supabase_reports(self) -> None:
        rows = sb_support_rows()
        audit_rows = sb_all("audit_logs")
        by_year_counts: dict[str, int] = {}
        for row in rows:
            label = str(row.get("year") or "Sin año")
            by_year_counts[label] = by_year_counts.get(label, 0) + 1
        by_year = [{"label": label, "total": total} for label, total in sorted(by_year_counts.items(), reverse=True)]
        self.json_response(
            {
                "by_eps": sb_group_counts(rows, "eps_name"),
                "by_user": sb_group_counts(rows, "uploaded_by_name"),
                "by_year": by_year,
                "pending": sum(1 for row in rows if row.get("status") == "pendiente_revision"),
                "duplicates": sum(1 for row in audit_rows if row.get("action") == "duplicate_pdf"),
            }
        )

    def supabase_cortes(self, query: dict[str, list[str]]) -> None:
        today = datetime.now()
        year = int((query.get("year") or [str(today.year)])[0] or today.year)
        month = int((query.get("month") or [str(today.month)])[0] or today.month)
        ranges = corte_ranges(year, month)
        rows = [row for row in sb_support_rows() if int(row.get("year") or 0) == year and int(row.get("month") or 0) == month]
        items = []
        for corte_item in ranges:
            corte_id = corte_item["id"]
            grouped: dict[str, dict[str, Any]] = {}
            for row in rows:
                if str(row.get("corte") or "") != corte_id:
                    continue
                eps = row.get("eps_name") or "Sin EPS"
                grouped.setdefault(eps, {"label": eps, "support_total": 0, "invoice_total": 0})
                grouped[eps]["support_total"] += 1
                grouped[eps]["invoice_total"] += int(row.get("invoice_count") or 0)
            eps_rows = sorted(grouped.values(), key=lambda item: (-item["invoice_total"], item["label"]))
            items.append(
                {
                    "id": corte_id,
                    "label": corte_item["label"],
                    "detail": corte_item["detail"],
                    "support_total": sum(item["support_total"] for item in eps_rows),
                    "invoice_total": sum(item["invoice_total"] for item in eps_rows),
                    "eps": eps_rows,
                }
            )
        self.json_response(
            {
                "cycle": {
                    "year": year,
                    "month": month,
                    "month_name": MONTH_NAMES[month],
                    "label": f"{MONTH_NAMES[month]} {year}",
                    "start": ranges[0]["start"],
                    "end": ranges[-1]["end"],
                },
                "items": items,
            }
        )

    def supabase_settings(self) -> None:
        self.json_response({"settings": {row["key"]: row["value"] for row in sb_all("settings")}})

    def supabase_update_settings(self, user: dict[str, Any]) -> None:
        payload = self.read_json()
        rows = [{"key": key, "value": str(payload[key])} for key in ["system_name", "company_name", "primary_color", "page_size"] if key in payload]
        if rows:
            SupabaseClient().rest_upsert("settings", rows, "key")
        sb_audit(user, "update_settings", "settings", None, payload, self.client_address[0])
        self.json_response({"ok": True})

    def dashboard(self, query: dict[str, list[str]]) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_dashboard(query)
        where, params = parse_filters(query)
        today = datetime.now().date().isoformat()
        month_start = datetime.now().replace(day=1).date().isoformat()
        with db() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM supports WHERE {where}", params).fetchone()[0]
            eps_total = conn.execute("SELECT COUNT(*) FROM eps WHERE active = 1").fetchone()[0]
            pending = conn.execute(
                f"SELECT COUNT(*) FROM supports WHERE {where} AND status = 'pendiente_revision'",
                params,
            ).fetchone()[0]
            today_count = conn.execute(
                "SELECT COUNT(*) FROM supports WHERE status != 'eliminado' AND date(uploaded_at) = ?",
                (today,),
            ).fetchone()[0]
            month_count = conn.execute(
                "SELECT COUNT(*) FROM supports WHERE status != 'eliminado' AND date(uploaded_at) >= ?",
                (month_start,),
            ).fetchone()[0]
            downloads = conn.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action IN ('download_pdf','download_zip')"
            ).fetchone()[0]
            by_eps = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT COALESCE(eps_name, 'Sin EPS') AS label, COUNT(*) AS total
                    FROM supports
                    WHERE {where}
                    GROUP BY COALESCE(eps_name, 'Sin EPS')
                    ORDER BY total DESC
                    LIMIT 8
                    """,
                    params,
                )
            ]
            by_month = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT year, month, COUNT(*) AS total
                    FROM supports
                    WHERE status != 'eliminado' AND year IS NOT NULL AND month IS NOT NULL
                    GROUP BY year, month
                    ORDER BY year DESC, month DESC
                    LIMIT 12
                    """
                )
            ]
            recent = [
                support_public(row)
                for row in conn.execute(
                    """
                    SELECT * FROM supports
                    WHERE status != 'eliminado'
                    ORDER BY uploaded_at DESC
                    LIMIT 8
                    """
                )
            ]
            years = [row["year"] for row in conn.execute("SELECT DISTINCT year FROM supports WHERE year IS NOT NULL ORDER BY year DESC")]
            users = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT uploaded_by_name AS name, COUNT(*) AS total
                    FROM supports
                    WHERE status != 'eliminado'
                    GROUP BY uploaded_by_name
                    ORDER BY total DESC
                    LIMIT 5
                    """
                )
            ]
        self.json_response(
            {
                "stats": {
                    "total_supports": total,
                    "eps_total": eps_total,
                    "today_count": today_count,
                    "month_count": month_count,
                    "downloads": downloads,
                    "pending": pending,
                },
                "by_eps": by_eps,
                "by_month": by_month,
                "recent": recent,
                "years": years,
                "users": users,
            }
        )

    def list_supports(self, query: dict[str, list[str]]) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_list_supports(query)
        where, params = parse_filters(query)
        page = max(1, int((query.get("page") or ["1"])[0] or "1"))
        limit = min(100, max(5, int((query.get("limit") or ["10"])[0] or "10")))
        offset = (page - 1) * limit
        with db() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM supports WHERE {where}", params).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT * FROM supports
                WHERE {where}
                ORDER BY COALESCE(radication_date, uploaded_at) DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        self.json_response({"items": [support_public(row) for row in rows], "total": total, "page": page, "limit": limit})

    def get_support(self, support_id: int) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_get_support(support_id)
        with db() as conn:
            row = conn.execute("SELECT * FROM supports WHERE id = ?", (support_id,)).fetchone()
        if not row:
            return self.error_json(404, "Soporte no encontrado")
        self.json_response({"item": support_public(row)})

    def upload_supports(self, user: dict[str, Any]) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_upload_supports(user)
        self.require_permission(user, "upload")
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return self.error_json(400, "Se esperaba multipart/form-data")

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        file_items = form["files"] if "files" in form else []
        if not isinstance(file_items, list):
            file_items = [file_items]

        results = []
        with db() as conn:
            for item in file_items:
                if not getattr(item, "filename", None):
                    continue
                original = Path(item.filename).name
                if not original.lower().endswith(".pdf"):
                    results.append({"filename": original, "status": "rechazado", "message": "Solo se permiten archivos PDF."})
                    continue
                content = item.file.read()
                if len(content) > MAX_UPLOAD_BYTES:
                    results.append({"filename": original, "status": "rechazado", "message": "El PDF supera el límite de 25 MB."})
                    continue

                sha = support_upload_fingerprint(content)
                temp_path = STORAGE_DIR / "pendientes" / f"{uuid.uuid4().hex}_{slugify(original)}"
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path.write_bytes(content)
                metadata = extract_metadata(temp_path, conn)
                require_manual_cycle(metadata)

                eps_row = get_or_create_eps(conn, metadata["eps_name"], metadata.get("nit_eps")) if metadata["eps_name"] else None
                if eps_row:
                    metadata["eps_id"] = eps_row["id"]
                    metadata["eps_name"] = eps_row["name"]

                final_path = classify_path(metadata, original, metadata.get("radicado"))
                if final_path != temp_path:
                    shutil.move(str(temp_path), str(final_path))

                year = month = None

                cursor = conn.execute(
                    """
                    INSERT INTO supports (
                        original_filename, stored_filename, path, eps_id, eps_name, radication_date,
                        radicado, factura, corte, invoice_count, invoice_numbers, nit_eps, valor_radicado, year, month, uploaded_at,
                        uploaded_by, uploaded_by_name, size_bytes, sha256, status, observations, extracted_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        original,
                        final_path.name,
                        str(final_path.relative_to(BASE_DIR)),
                        metadata.get("eps_id"),
                        metadata.get("eps_name") or None,
                        metadata.get("radication_date") or None,
                        metadata.get("radicado") or None,
                        metadata.get("factura") or None,
                        metadata.get("corte") or None,
                        metadata.get("invoice_count") or 0,
                        metadata.get("invoice_numbers") or None,
                        metadata.get("nit_eps") or None,
                        metadata.get("valor_radicado") or None,
                        year,
                        month,
                        now_iso(),
                        user["id"],
                        user["name"],
                        len(content),
                        sha,
                        metadata["status"],
                        "",
                        metadata["extracted_text"],
                    ),
                )
                support_id = cursor.lastrowid
                audit(
                    conn,
                    user,
                    "upload_pdf",
                    "support",
                    support_id,
                    {"filename": original, "status": metadata["status"], "missing": metadata["missing"]},
                    self.client_address[0],
                )
                row = conn.execute("SELECT * FROM supports WHERE id = ?", (support_id,)).fetchone()
                results.append(
                    {
                        "filename": original,
                        "status": metadata["status"],
                        "message": "Datos extraídos correctamente."
                        if metadata["status"] == "guardado"
                        else "Faltan datos para revisión.",
                        "missing": metadata["missing"],
                        "item": support_public(row),
                    }
            )
            conn.commit()
        sync_supabase_after_write(upload_files=True)
        self.json_response({"results": results})

    def find_duplicate(self, conn: sqlite3.Connection, filename: str, sha: str, radicado: str | None) -> dict[str, Any] | None:
        checks = [
            ("hash", "sha256 = ?", sha),
            ("nombre de archivo", "lower(original_filename) = lower(?)", filename),
        ]
        if radicado:
            checks.insert(1, ("número de radicado", "lower(radicado) = lower(?)", radicado))
        for reason, clause, value in checks:
            row = conn.execute(
                f"SELECT id, original_filename, eps_name, radicado, uploaded_at FROM supports WHERE status != 'eliminado' AND {clause} LIMIT 1",
                (value,),
            ).fetchone()
            if row:
                data = dict(row)
                data["reason"] = reason
                return data
        return None

    def update_support(self, user: dict[str, Any], support_id: int) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_update_support(user, support_id)
        payload = self.read_json()
        with db() as conn:
            row = conn.execute("SELECT * FROM supports WHERE id = ?", (support_id,)).fetchone()
            if not row:
                return self.error_json(404, "Soporte no encontrado")
            eps_name = (payload.get("eps_name") or "").strip()
            radication_date = (payload.get("radication_date") or "").strip()
            radicado = (payload.get("radicado") or "").strip()
            factura = (payload.get("factura") or "").strip()
            corte = (payload.get("corte") or "").strip()
            invoice_count_raw = (payload.get("invoice_count") or "").strip()
            nit_eps = (payload.get("nit_eps") or "").strip()
            valor = (payload.get("valor_radicado") or "").strip()
            observations = (payload.get("observations") or "").strip()

            if corte and corte not in CORTE_LABELS:
                return self.error_json(400, "El corte debe ser 1, 2 o 3")
            try:
                invoice_count = max(0, int(invoice_count_raw or row["invoice_count"] or 0))
                year, month = parse_support_cycle_fields(payload)
            except ValueError:
                return self.error_json(400, "La cantidad de facturas debe ser numérica")

            if not eps_name or not radication_date or not corte or not year or not month:
                status = "pendiente_revision"
            else:
                status = "guardado"

            if radication_date:
                try:
                    datetime.strptime(radication_date, "%Y-%m-%d")
                except ValueError:
                    return self.error_json(400, "La fecha de radicación no es válida")
            else:
                year = month = None

            eps_row = get_or_create_eps(conn, eps_name, nit_eps) if eps_name else None
            current_path = (BASE_DIR / row["path"]).resolve()
            new_metadata = {"eps_name": eps_name, "radication_date": radication_date}
            new_path = classify_path(new_metadata, row["original_filename"], radicado or row["radicado"], current_path)
            if current_path.exists() and current_path != new_path.resolve():
                shutil.move(str(current_path), str(new_path))
            else:
                new_path = current_path

            conn.execute(
                """
                UPDATE supports
                SET eps_id = ?, eps_name = ?, radication_date = ?, radicado = ?, factura = ?,
                    corte = ?, invoice_count = ?, nit_eps = ?, valor_radicado = ?, year = ?, month = ?, status = ?,
                    observations = ?, path = ?, stored_filename = ?
                WHERE id = ?
                """,
                (
                    eps_row["id"] if eps_row else None,
                    eps_row["name"] if eps_row else None,
                    radication_date or None,
                    radicado or None,
                    factura or None,
                    corte or None,
                    invoice_count,
                    nit_eps or None,
                    valor or None,
                    year,
                    month,
                    status,
                    observations,
                    str(new_path.relative_to(BASE_DIR)),
                    new_path.name,
                    support_id,
                ),
            )
            audit(conn, user, "update_support", "support", support_id, payload, self.client_address[0])
            conn.commit()
            updated = conn.execute("SELECT * FROM supports WHERE id = ?", (support_id,)).fetchone()
        sync_supabase_after_write(upload_files=True)
        self.json_response({"item": support_public(updated)})

    def delete_support(self, user: dict[str, Any], support_id: int) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_delete_support(user, support_id)
        with db() as conn:
            row = conn.execute("SELECT * FROM supports WHERE id = ?", (support_id,)).fetchone()
            if not row:
                return self.error_json(404, "Soporte no encontrado")
            conn.execute("UPDATE supports SET status = 'eliminado' WHERE id = ?", (support_id,))
            audit(conn, user, "delete_support", "support", support_id, {"filename": row["original_filename"]}, self.client_address[0])
            conn.commit()
        sync_supabase_after_write(upload_files=False)
        self.json_response({"ok": True})

    def serve_support_file(self, user: dict[str, Any], support_id: int, inline: bool) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_serve_support_file(user, support_id, inline)
        with db() as conn:
            row = conn.execute("SELECT * FROM supports WHERE id = ? AND status != 'eliminado'", (support_id,)).fetchone()
            if not row:
                return self.error_json(404, "Soporte no encontrado")
            path = ensure_support_file_from_supabase(row)
            if not path.exists():
                return self.error_json(404, "Archivo físico no encontrado")
            if not inline:
                audit(
                    conn,
                    user,
                    "download_pdf",
                    "support",
                    support_id,
                    {"filename": row["original_filename"]},
                    self.client_address[0],
                )
                conn.commit()
                sync_supabase_after_write(upload_files=False)
        payload = path.read_bytes()
        disposition = "inline" if inline else "attachment"
        filename = quote(row["original_filename"])
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{filename}")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def download_zip(self, user: dict[str, Any], query: dict[str, list[str]]) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_download_zip(user, query)
        self.require_permission(user, "download")
        where, params = parse_filters(query)
        with db() as conn:
            rows = conn.execute(
                f"SELECT * FROM supports WHERE {where} ORDER BY year DESC, month DESC, eps_name, original_filename",
                params,
            ).fetchall()
            if not rows:
                return self.error_json(404, "No hay soportes para descargar con esos filtros")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                zip_path = Path(tmp.name)
            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for row in rows:
                        path = ensure_support_file_from_supabase(row)
                        if not path.exists():
                            continue
                        year = row["year"] or "Sin año"
                        month = f"{int(row['month']):02d}-{MONTH_NAMES[int(row['month'])]}" if row["month"] else "Sin mes"
                        eps_name = slugify(row["eps_name"] or "Sin EPS")
                        arcname = f"{year}/{month}/{eps_name}/{row['original_filename']}"
                        zf.write(path, arcname)
                audit(
                    conn,
                    user,
                    "download_zip",
                    "support",
                    None,
                    {"count": len(rows), "filters": {key: value[0] for key, value in query.items()}},
                    self.client_address[0],
                )
                conn.commit()
                sync_supabase_after_write(upload_files=False)
                payload = zip_path.read_bytes()
            finally:
                zip_path.unlink(missing_ok=True)
        filename = f"soportes_eps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f"attachment; filename={filename}")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def list_eps(self) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_list_eps()
        with db() as conn:
            rows = conn.execute(
                """
                SELECT e.*, COUNT(s.id) AS support_count
                FROM eps e
                LEFT JOIN supports s ON s.eps_id = e.id AND s.status != 'eliminado'
                GROUP BY e.id
                ORDER BY e.active DESC, e.name
                """
            ).fetchall()
        self.json_response({"items": [dict(row) for row in rows]})

    def create_eps(self, user: dict[str, Any]) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_create_eps(user)
        payload = self.read_json()
        with db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO eps (name, nit, code, color, logo_url, aliases, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("name"),
                    payload.get("nit"),
                    payload.get("code"),
                    payload.get("color") or "#1769e0",
                    payload.get("logo_url"),
                    payload.get("aliases") or "",
                    1 if payload.get("active", True) else 0,
                    now_iso(),
                ),
            )
            audit(conn, user, "create_eps", "eps", cursor.lastrowid, payload, self.client_address[0])
            conn.commit()
        sync_supabase_after_write(upload_files=False)
        self.json_response({"ok": True})

    def update_eps(self, user: dict[str, Any], eps_id: int) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_update_eps(user, eps_id)
        payload = self.read_json()
        with db() as conn:
            conn.execute(
                """
                UPDATE eps
                SET name = ?, nit = ?, code = ?, color = ?, logo_url = ?, aliases = ?, active = ?
                WHERE id = ?
                """,
                (
                    payload.get("name"),
                    payload.get("nit"),
                    payload.get("code"),
                    payload.get("color") or "#1769e0",
                    payload.get("logo_url"),
                    payload.get("aliases") or "",
                    1 if payload.get("active", True) else 0,
                    eps_id,
                ),
            )
            audit(conn, user, "update_eps", "eps", eps_id, payload, self.client_address[0])
            conn.commit()
        sync_supabase_after_write(upload_files=False)
        self.json_response({"ok": True})

    def delete_eps(self, user: dict[str, Any], eps_id: int) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_delete_eps(user, eps_id)
        with db() as conn:
            conn.execute("UPDATE eps SET active = 0 WHERE id = ?", (eps_id,))
            audit(conn, user, "delete_eps", "eps", eps_id, None, self.client_address[0])
            conn.commit()
        sync_supabase_after_write(upload_files=False)
        self.json_response({"ok": True})

    def list_users(self) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_list_users()
        with db() as conn:
            rows = conn.execute(
                "SELECT id, name, role, active, created_at FROM users ORDER BY active DESC, name"
            ).fetchall()
        self.json_response({"items": [dict(row) for row in rows]})

    def create_user(self, user: dict[str, Any]) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_create_user(user)
        payload = self.read_json()
        name = (payload.get("name") or "").strip()
        password = payload.get("password") or ""
        if not name:
            return self.error_json(400, "El nombre de usuario es obligatorio")
        if not password:
            return self.error_json(400, "La contraseña es obligatoria")
        with db() as conn:
            if conn.execute("SELECT id FROM users WHERE lower(name) = lower(?)", (name,)).fetchone():
                return self.error_json(409, "Ya existe un usuario con ese nombre")
            existing_emails = {row["email"].lower() for row in conn.execute("SELECT email FROM users").fetchall()}
            cursor = conn.execute(
                """
                INSERT INTO users (name, email, password_hash, role, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    technical_user_email(name, existing_emails),
                    hash_password(password),
                    payload.get("role") or "Consulta",
                    1 if payload.get("active", True) else 0,
                    now_iso(),
                ),
            )
            audit(conn, user, "create_user", "user", cursor.lastrowid, {"usuario": name}, self.client_address[0])
            conn.commit()
        sync_supabase_after_write(upload_files=False)
        self.json_response({"ok": True})

    def update_user(self, user: dict[str, Any], target_id: int) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_update_user(user, target_id)
        payload = self.read_json()
        name = (payload.get("name") or "").strip()
        if not name:
            return self.error_json(400, "El nombre de usuario es obligatorio")
        with db() as conn:
            current = conn.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
            if not current:
                return self.error_json(404, "Usuario no encontrado")
            duplicate = conn.execute("SELECT id FROM users WHERE lower(name) = lower(?) AND id <> ?", (name, target_id)).fetchone()
            if duplicate:
                return self.error_json(409, "Ya existe un usuario con ese nombre")
            if payload.get("password"):
                conn.execute(
                    """
                    UPDATE users SET name = ?, email = ?, role = ?, active = ?, password_hash = ?
                    WHERE id = ?
                    """,
                    (
                        name,
                        current["email"],
                        payload.get("role"),
                        1 if payload.get("active", True) else 0,
                        hash_password(payload["password"]),
                        target_id,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE users SET name = ?, email = ?, role = ?, active = ? WHERE id = ?",
                    (
                        name,
                        current["email"],
                        payload.get("role"),
                        1 if payload.get("active", True) else 0,
                        target_id,
                    ),
                )
            audit(conn, user, "update_user", "user", target_id, {"usuario": name}, self.client_address[0])
            conn.commit()
        sync_supabase_after_write(upload_files=False)
        self.json_response({"ok": True})

    def deactivate_user(self, user: dict[str, Any], target_id: int) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_deactivate_user(user, target_id)
        with db() as conn:
            conn.execute("UPDATE users SET active = 0 WHERE id = ?", (target_id,))
            audit(conn, user, "deactivate_user", "user", target_id, None, self.client_address[0])
            conn.commit()
        sync_supabase_after_write(upload_files=False)
        self.json_response({"ok": True})

    def reports(self) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_reports()
        with db() as conn:
            by_eps = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT COALESCE(eps_name, 'Sin EPS') AS label, COUNT(*) AS total
                    FROM supports WHERE status != 'eliminado'
                    GROUP BY COALESCE(eps_name, 'Sin EPS') ORDER BY total DESC
                    """
                )
            ]
            by_user = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT uploaded_by_name AS label, COUNT(*) AS total
                    FROM supports WHERE status != 'eliminado'
                    GROUP BY uploaded_by_name ORDER BY total DESC
                    """
                )
            ]
            by_year = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT COALESCE(year, 'Sin año') AS label, COUNT(*) AS total
                    FROM supports WHERE status != 'eliminado'
                    GROUP BY year ORDER BY year DESC
                    """
                )
            ]
            pending = conn.execute(
                "SELECT COUNT(*) FROM supports WHERE status = 'pendiente_revision'"
            ).fetchone()[0]
            duplicates = conn.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action = 'duplicate_pdf'"
            ).fetchone()[0]
        self.json_response({"by_eps": by_eps, "by_user": by_user, "by_year": by_year, "pending": pending, "duplicates": duplicates})

    def cortes(self, query: dict[str, list[str]]) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_cortes(query)
        today = datetime.now()
        year = int((query.get("year") or [str(today.year)])[0] or today.year)
        month = int((query.get("month") or [str(today.month)])[0] or today.month)
        ranges = corte_ranges(year, month)
        with db() as conn:
            items = []
            for corte_item in ranges:
                corte_id = corte_item["id"]
                eps_rows = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT
                            COALESCE(eps_name, 'Sin EPS') AS label,
                            COUNT(*) AS support_total,
                            COALESCE(SUM(invoice_count), 0) AS invoice_total
                        FROM supports
                        WHERE status != 'eliminado'
                          AND year = ?
                          AND month = ?
                          AND corte = ?
                        GROUP BY COALESCE(eps_name, 'Sin EPS')
                        ORDER BY invoice_total DESC, label
                        """,
                        (year, month, corte_id),
                    )
                ]
                invoice_total = sum(row["invoice_total"] for row in eps_rows)
                support_total = sum(row["support_total"] for row in eps_rows)
                items.append(
                    {
                        "id": corte_id,
                        "label": corte_item["label"],
                        "detail": corte_item["detail"],
                        "support_total": support_total,
                        "invoice_total": invoice_total,
                        "eps": eps_rows,
                    }
                )
        cycle = {
            "year": year,
            "month": month,
            "month_name": MONTH_NAMES[month],
            "label": f"{MONTH_NAMES[month]} {year}",
            "start": ranges[0]["start"],
            "end": ranges[-1]["end"],
        }
        self.json_response({"cycle": cycle, "items": items})

    def settings(self) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_settings()
        with db() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        self.json_response({"settings": {row["key"]: row["value"] for row in rows}})

    def update_settings(self, user: dict[str, Any]) -> None:
        if USE_SUPABASE_ONLY:
            return self.supabase_update_settings(user)
        payload = self.read_json()
        with db() as conn:
            for key in ["system_name", "company_name", "primary_color", "page_size"]:
                if key in payload:
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(payload[key])))
            audit(conn, user, "update_settings", "settings", None, payload, self.client_address[0])
            conn.commit()
        sync_supabase_after_write(upload_files=False)
        self.json_response({"ok": True})

    def supabase_status(self) -> None:
        self.json_response(
            {
                "enabled": supabase_enabled(),
                "backend": DATA_BACKEND,
                "sqlite_active": not USE_SUPABASE_ONLY,
                "url": SUPABASE_URL if SUPABASE_URL else "",
                "bucket": SUPABASE_BUCKET,
                "has_publishable_key": bool(SUPABASE_PUBLISHABLE_KEY),
                "has_secret_key": bool(SUPABASE_SERVICE_KEY),
                "message": supabase_config_message(),
                "sync_on_write": SUPABASE_SYNC_ON_WRITE,
                "pull_on_start": SUPABASE_PULL_ON_START,
                "last_sync": SUPABASE_LAST_SYNC,
            }
        )

    def supabase_sync(self) -> None:
        global SUPABASE_LAST_SYNC
        try:
            if USE_SUPABASE_ONLY:
                sb_seed_defaults()
                stats = {
                    "enabled": supabase_enabled(),
                    "ok": True,
                    "backend": DATA_BACKEND,
                    "app_users": len(sb_all("app_users")),
                    "eps": len(sb_all("eps")),
                    "settings": len(sb_all("settings")),
                    "supports": len(sb_all("supports")),
                    "audit_logs": len(sb_all("audit_logs")),
                    "message": "Supabase es la base de datos activa",
                }
                SUPABASE_LAST_SYNC = stats
                return self.json_response({"ok": True, "synced": stats})
            restored = restore_from_supabase(download_files=False) if supabase_enabled() else None
            synced = sync_all_to_supabase(upload_files=True)
            SUPABASE_LAST_SYNC = synced
            self.json_response({"ok": True, "restored": restored, "synced": synced})
        except Exception as exc:
            SUPABASE_LAST_SYNC = {"enabled": supabase_enabled(), "ok": False, "message": str(exc)}
            self.error_json(500, str(exc))


def run(port: int = 8765) -> None:
    global SUPABASE_LAST_SYNC
    if USE_SUPABASE_ONLY:
        if not supabase_enabled():
            raise RuntimeError(supabase_config_message())
        sb_seed_defaults()
        SUPABASE_LAST_SYNC = {
            "enabled": True,
            "ok": True,
            "backend": DATA_BACKEND,
            "message": "Supabase es la base de datos activa",
        }
    else:
        init_db()
    if supabase_enabled() and SUPABASE_PULL_ON_START:
        try:
            if not USE_SUPABASE_ONLY:
                restored = restore_from_supabase(download_files=False)
                synced = sync_all_to_supabase(upload_files=False)
                SUPABASE_LAST_SYNC = {"ok": True, "restored": restored, "synced": synced}
        except Exception as exc:
            SUPABASE_LAST_SYNC = {"enabled": True, "ok": False, "message": str(exc)}
            print(f"[supabase] {exc}", file=sys.stderr)
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"Soportes EPS disponible en http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8765))
    run(port)
