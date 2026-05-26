import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


app = FastAPI()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
DB_FILE = Path("/tmp/licenses.json")


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


def load_db():
    if not DB_FILE.exists():
        return {"licenses": {}}

    try:
        with DB_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"licenses": {}}


def save_db(db):
    with DB_FILE.open("w", encoding="utf-8") as f:
        json.dump(db, f, indent=4)


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


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "license api running",
        "admin_secret_configured": bool(ADMIN_SECRET),
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

    plan, expires_at = get_expiration(data.duration)
    db = load_db()

    license_key = make_license_key()

    while license_key in db["licenses"]:
        license_key = make_license_key()

    created_at = now_utc()

    db["licenses"][license_key] = {
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

    save_db(db)

    return {
        "ok": True,
        "license_key": license_key,
        "plan": plan,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@app.post("/verify-license")
def verify_license(data: VerifyLicenseRequest):
    db = load_db()
    license_data = db["licenses"].get(data.license_key)

    if not license_data:
        return {"valid": False, "reason": "invalid"}

    if license_data["status"] != "active":
        return {"valid": False, "reason": license_data["status"]}

    expires_at = license_data.get("expires_at")

    if expires_at:
        expires_dt = datetime.fromisoformat(expires_at)

        if now_utc() > expires_dt:
            license_data["status"] = "expired"
            save_db(db)
            return {"valid": False, "reason": "expired"}

    saved_hwid = license_data.get("hwid")

    if saved_hwid is None and data.hwid:
        license_data["hwid"] = data.hwid

    elif saved_hwid and data.hwid and saved_hwid != data.hwid:
        return {"valid": False, "reason": "hwid_mismatch"}

    license_data["last_seen_at"] = now_utc().isoformat()
    save_db(db)

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

    db = load_db()
    license_data = db["licenses"].get(data.license_key)

    if not license_data:
        raise HTTPException(status_code=404, detail="License not found")

    license_data["status"] = "revoked"
    save_db(db)

    return {"ok": True, "status": "revoked"}


@app.get("/admin/list-licenses")
def list_licenses(x_admin_secret: Optional[str] = Header(default=None)):
    require_admin(x_admin_secret)
    return load_db()import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional


app = FastAPI()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
DB_FILE = Path("/tmp/licenses.json")


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


def load_db():
    if not DB_FILE.exists():
        return {"licenses": {}}

    try:
        with DB_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"licenses": {}}


def save_db(db):
    with DB_FILE.open("w", encoding="utf-8") as f:
        json.dump(db, f, indent=4)


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


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "license api running",
        "admin_secret_configured": bool(ADMIN_SECRET),
    }


@app.get("/health")
def health():
    return {
        "ok": True
    }


@app.post("/admin/create-license")
def create_license(data: CreateLicenseRequest, x_admin_secret: Optional[str] = Header(default=None)):
    require_admin(x_admin_secret)

    plan, expires_at = get_expiration(data.duration)
    db = load_db()

    license_key = make_license_key()

    while license_key in db["licenses"]:
        license_key = make_license_key()

    created_at = now_utc()

    db["licenses"][license_key] = {
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

    save_db(db)

    return {
        "ok": True,
        "license_key": license_key,
        "plan": plan,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@app.post("/verify-license")
def verify_license(data: VerifyLicenseRequest):
    db = load_db()
    license_data = db["licenses"].get(data.license_key)

    if not license_data:
        return {
            "valid": False,
            "reason": "invalid"
        }

    if license_data["status"] != "active":
        return {
            "valid": False,
            "reason": license_data["status"]
        }

    expires_at = license_data.get("expires_at")

    if expires_at:
        expires_dt = datetime.fromisoformat(expires_at)

        if now_utc() > expires_dt:
            license_data["status"] = "expired"
            save_db(db)

            return {
                "valid": False,
                "reason": "expired"
            }

    saved_hwid = license_data.get("hwid")

    if saved_hwid is None and data.hwid:
        license_data["hwid"] = data.hwid

    elif saved_hwid and data.hwid and saved_hwid != data.hwid:
        return {
            "valid": False,
            "reason": "hwid_mismatch"
        }

    license_data["last_seen_at"] = now_utc().isoformat()
    save_db(db)

    return {
        "valid": True,
        "reason": "ok",
        "plan": license_data["plan"],
        "expires_at": license_data["expires_at"],
        "discord_id": license_data["discord_id"],
    }


@app.post("/admin/revoke-license")
def revoke_license(data: RevokeLicenseRequest, x_admin_secret: Optional[str] = Header(default=None)):
    require_admin(x_admin_secret)

    db = load_db()
    license_data = db["licenses"].get(data.license_key)

    if not license_data:
        raise HTTPException(status_code=404, detail="License not found")

    license_data["status"] = "revoked"
    save_db(db)

    return {
        "ok": True,
        "status": "revoked"
    }


@app.get("/admin/list-licenses")
def list_licenses(x_admin_secret: Optional[str] = Header(default=None)):
    require_admin(x_admin_secret)
    return load_db()import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


app = FastAPI()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
DB_FILE = Path("licenses.json")


class CreateLicenseRequest(BaseModel):
    duration: str
    discord_id: str | None = None
    note: str | None = None


class VerifyLicenseRequest(BaseModel):
    license_key: str
    discord_id: str | None = None
    hwid: str | None = None


class RevokeLicenseRequest(BaseModel):
    license_key: str


def now_utc():
    return datetime.now(timezone.utc)


def load_db():
    if not DB_FILE.exists():
        return {"licenses": {}}

    try:
        with DB_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"licenses": {}}


def save_db(db):
    with DB_FILE.open("w", encoding="utf-8") as f:
        json.dump(db, f, indent=4)


def require_admin(x_admin_secret: str | None):
    if not ADMIN_SECRET:
        raise HTTPException(status_code=500, detail="ADMIN_SECRET not configured")

    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Invalid admin secret")


def make_license_key():
    return "7DYQ-" + secrets.token_urlsafe(32).replace("-", "").replace("_", "")[:32].upper()


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


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "license api running"
    }


@app.get("/health")
def health():
    return {
        "ok": True
    }


@app.post("/admin/create-license")
def create_license(
    data: CreateLicenseRequest,
    x_admin_secret: str | None = Header(default=None),
):
    require_admin(x_admin_secret)

    plan, expires_at = get_expiration(data.duration)

    db = load_db()

    license_key = make_license_key()

    while license_key in db["licenses"]:
        license_key = make_license_key()

    created_at = now_utc()

    db["licenses"][license_key] = {
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

    save_db(db)

    return {
        "ok": True,
        "license_key": license_key,
        "plan": plan,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@app.post("/verify-license")
def verify_license(data: VerifyLicenseRequest):
    db = load_db()
    license_data = db["licenses"].get(data.license_key)

    if not license_data:
        return {
            "valid": False,
            "reason": "invalid"
        }

    if license_data["status"] != "active":
        return {
            "valid": False,
            "reason": license_data["status"]
        }

    expires_at = license_data.get("expires_at")

    if expires_at:
        expires_dt = datetime.fromisoformat(expires_at)

        if now_utc() > expires_dt:
            license_data["status"] = "expired"
            save_db(db)

            return {
                "valid": False,
                "reason": "expired"
            }

    saved_hwid = license_data.get("hwid")

    if saved_hwid is None and data.hwid:
        license_data["hwid"] = data.hwid

    elif saved_hwid and data.hwid and saved_hwid != data.hwid:
        return {
            "valid": False,
            "reason": "hwid_mismatch"
        }

    license_data["last_seen_at"] = now_utc().isoformat()
    save_db(db)

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
    x_admin_secret: str | None = Header(default=None),
):
    require_admin(x_admin_secret)

    db = load_db()
    license_data = db["licenses"].get(data.license_key)

    if not license_data:
        raise HTTPException(status_code=404, detail="License not found")

    license_data["status"] = "revoked"
    save_db(db)

    return {
        "ok": True,
        "status": "revoked"
    }


@app.get("/admin/list-licenses")
def list_licenses(x_admin_secret: str | None = Header(default=None)):
    require_admin(x_admin_secret)
    return load_db()from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "license api running"
    }


@app.get("/health")
def health():
    return {
        "ok": True
    }
