import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


app = FastAPI()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

TABLE_URL = f"{SUPABASE_URL}/rest/v1/licenses"


class CreateLicenseRequest(BaseModel):
    duration: str
    discord_id: Optional[str] = None
    note: Optional[str] = None


class VerifyLicenseRequest(BaseModel):
    license_key: str
    discord_id: Optional[str] = None
    hwid: Optional[str] = None


class RevokeLicenseRequest(BaseModel):
    license_key: str


def now_utc():
    return datetime.now(timezone.utc)


def supabase_headers(prefer=None):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def require_config():
    if not SUPABASE_URL:
        raise HTTPException(status_code=500, detail="SUPABASE_URL not configured")

    if not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_KEY not configured")


def require_admin(x_admin_secret):
    if not ADMIN_SECRET:
        raise HTTPException(status_code=500, detail="ADMIN_SECRET not configured")

    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Invalid admin secret")


def make_license_key():
    raw = secrets.token_urlsafe(32)
    clean = raw.replace("-", "").replace("_", "").upper()
    return "7DYQ-" + clean[:32]


def get_expiration(duration):
    duration = duration.lower().strip()
    now = now_utc()

    if duration in ["1d", "1day", "1_day", "day"]:
        return "1_day", now + timedelta(days=1)

    if duration in ["7d", "1w", "1week", "1_week", "week"]:
        return "1_week", now + timedelta(days=7)

    if duration in ["30d", "1m", "1month", "1_month", "month"]:
        return "1_month", now + timedelta(days=30)

    if duration in ["lifetime", "life", "lt"]:
        return "lifetime", None

    raise HTTPException(status_code=400, detail="Invalid duration")


def get_license(license_key):
    require_config()

    response = requests.get(
        TABLE_URL,
        headers=supabase_headers(),
        params={
            "license_key": f"eq.{license_key}",
            "select": "*",
            "limit": "1",
        },
        timeout=30,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "supabase_get_failed",
                "status": response.status_code,
                "body": response.text,
            },
        )

    rows = response.json()

    if not rows:
        return None

    return rows[0]


def insert_license(row):
    require_config()

    response = requests.post(
        TABLE_URL,
        headers=supabase_headers(prefer="return=representation"),
        json=row,
        timeout=30,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "supabase_insert_failed",
                "status": response.status_code,
                "body": response.text,
            },
        )

    return response.json()[0]


def update_license(license_key, patch):
    require_config()

    response = requests.patch(
        TABLE_URL,
        headers=supabase_headers(prefer="return=representation"),
        params={
            "license_key": f"eq.{license_key}",
        },
        json=patch,
        timeout=30,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "supabase_update_failed",
                "status": response.status_code,
                "body": response.text,
            },
        )

    rows = response.json()

    if not rows:
        return None

    return rows[0]


def list_all_licenses():
    require_config()

    response = requests.get(
        TABLE_URL,
        headers=supabase_headers(),
        params={
            "select": "*",
            "order": "created_at.desc",
        },
        timeout=30,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "supabase_list_failed",
                "status": response.status_code,
                "body": response.text,
            },
        )

    return response.json()


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "license api running",
        "admin_secret_configured": bool(ADMIN_SECRET),
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_SERVICE_KEY),
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/admin/create-license")
def create_license(
    data: CreateLicenseRequest,
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)
    require_config()

    plan, expires_at = get_expiration(data.duration)

    license_key = make_license_key()

    while get_license(license_key) is not None:
        license_key = make_license_key()

    created_at = now_utc()

    row = {
        "license_key": license_key,
        "plan": plan,
        "status": "active",
        "discord_id": data.discord_id,
        "note": data.note,
        "hwid": None,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "last_seen_at": None,
    }

    inserted = insert_license(row)

    return {
        "ok": True,
        "license_key": inserted["license_key"],
        "plan": inserted["plan"],
        "expires_at": inserted["expires_at"],
    }


@app.post("/verify-license")
def verify_license(data: VerifyLicenseRequest):
    require_config()

    license_data = get_license(data.license_key)

    if not license_data:
        return {"valid": False, "reason": "invalid"}

    if license_data["status"] != "active":
        return {"valid": False, "reason": license_data["status"]}

    expires_at = license_data.get("expires_at")

    if expires_at:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

        if now_utc() > expires_dt:
            update_license(data.license_key, {"status": "expired"})
            return {"valid": False, "reason": "expired"}

    saved_hwid = license_data.get("hwid")

    if saved_hwid is None and data.hwid:
        license_data = update_license(
            data.license_key,
            {
                "hwid": data.hwid,
                "last_seen_at": now_utc().isoformat(),
            },
        )

    elif saved_hwid and data.hwid and saved_hwid != data.hwid:
        return {"valid": False, "reason": "hwid_mismatch"}

    else:
        license_data = update_license(
            data.license_key,
            {
                "last_seen_at": now_utc().isoformat(),
            },
        )

    return {
        "valid": True,
        "reason": "ok",
        "plan": license_data["plan"],
        "expires_at": license_data["expires_at"],
        "discord_id": license_data["discord_id"],
    }


@app.post("/admin/revoke-license")
def revoke_license(
    data: RevokeLicenseRequest,
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)
    require_config()

    license_data = get_license(data.license_key)

    if not license_data:
        raise HTTPException(status_code=404, detail="License not found")

    update_license(data.license_key, {"status": "revoked"})

    return {"ok": True, "status": "revoked"}


@app.get("/admin/list-licenses")
def list_licenses(x_admin_secret: Optional[str] = Header(default=None)):
    require_admin(x_admin_secret)
    require_config()

    rows = list_all_licenses()

    return {
        "licenses": {
            row["license_key"]: row for row in rows
        }
    }
