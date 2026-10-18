from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import logging
import re
import ipaddress
import hmac
import asyncio
import csv
import io
import uuid
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import bcrypt
import jwt
import httpx
from bson import ObjectId
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError, DuplicateKeyError, OperationFailure
from pydantic import BaseModel, Field

from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout,
    CheckoutSessionRequest,
)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Stripe (BYOK via emergentintegrations)
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY") or "sk_test_emergent"
CANCELLATION_FEE_EUR = float(os.environ.get("CANCELLATION_FEE_EUR", "69.99"))

# Telegram notifications (payment confirmations)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

app = FastAPI()
api_router = APIRouter(prefix="/api")

JWT_ALGORITHM = "HS256"
MAX_FAILED = 10
LOCKOUT_MINUTES = 15


# ---------- helpers ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(sub_id: str, kind: str, role: str) -> str:
    payload = {
        "sub": sub_id,
        "kind": kind,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(sub_id: str, kind: str) -> str:
    payload = {
        "sub": sub_id,
        "kind": kind,
        "exp": datetime.now(timezone.utc) + timedelta(days=14),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, access: str, refresh: str):
    response.set_cookie(key="access_token", value=access, httponly=True, secure=True,
                        samesite="none", max_age=12 * 3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh, httponly=True, secure=True,
                        samesite="none", max_age=14 * 24 * 3600, path="/")


def mask_iban_from_last4(last4: str) -> str:
    s = (last4 or "").strip()
    if not s:
        return ""
    return "FR76 •••• •••• •••• •••• " + s[-4:]


# ---------- emoji handling ----------
# Broad emoji / pictograph / symbol ranges. Used to (a) clean stored values so
# clients never see emojis and (b) detect the leading emoji marker of a line.
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002300-\U000023FF"
    "\U00002B00-\U00002BFF"
    "\U00002190-\U000021FF"
    "\U0000FE00-\U0000FE0F"
    "\U0001F1E6-\U0001F1FF"
    "\U0000200D"
    "\U000020E3"
    "\U00002122\U000000A9\U000000AE"
    "]+",
    flags=re.UNICODE,
)


def strip_emojis(s: str) -> str:
    """Remove every emoji / pictograph then collapse whitespace."""
    if not s:
        return ""
    cleaned = _EMOJI_PATTERN.sub(" ", s)
    return re.sub(r"\s+", " ", cleaned).strip()


# Map of specific emoji codepoints to the profile field they represent in the
# "vertical block" import format (one field per line, each prefixed by an emoji).
_EMOJI_FIELD = {
    # person / holder name
    "\U0001F464": "name", "\U0001F465": "name", "\U0001F9D1": "name",
    "\U0001F468": "name", "\U0001F469": "name", "\U0001F9D3": "name",
    # email
    "\U0001F4E7": "email", "\U00002709": "email", "\U0001F4E8": "email",
    "\U0001F4E9": "email", "\U0001F4E5": "email", "\U0001F4E4": "email",
    # phone
    "\U0001F4F1": "phone", "\U0000260E": "phone", "\U0001F4DE": "phone",
    "\U0001F4F2": "phone",
    # home / street address
    "\U0001F3E0": "address", "\U0001F3E1": "address", "\U0001F3E2": "address",
    "\U0001F4CD": "address", "\U0001F6E3": "address", "\U0001F3D8": "address",
    # mailbox -> postal code + city
    "\U0001F4EE": "postal", "\U0001F4EB": "postal", "\U0001F4EA": "postal",
    "\U0001F4EC": "postal", "\U0001F4ED": "postal", "\U0001F3E4": "postal",
    # calendar / cake -> birth year
    "\U0001F4C5": "birth", "\U0001F4C6": "birth", "\U0001F5D3": "birth",
    "\U0001F382": "birth", "\U0001F389": "birth",
    # bank name
    "\U0001F3E6": "bank", "\U0001F3DB": "bank", "\U0001F4B0": "bank",
    "\U0001F3E7": "bank", "\U0001F3E5": "bank",
    # IBAN / bank card
    "\U0001F4B3": "iban", "\U0001F4B6": "iban", "\U0001F4B5": "iban",
    "\U0001F4B4": "iban", "\U0001F9FE": "iban",
}


def _leading_emoji_field(line: str):
    """Return (field_or_None, rest_without_emojis) for a block line."""
    stripped = line.lstrip()
    field = None
    for ch in stripped:
        if ch in _EMOJI_FIELD:
            field = _EMOJI_FIELD[ch]
            break
        if _EMOJI_PATTERN.match(ch) or ch in " \t":
            continue
        break
    return field, strip_emojis(line)


def _derive_iban_last4(raw: str) -> str:
    """Accept either an IBAN or a 4-digit code. Returns the last 4 digits, or '' if invalid.
    Raises HTTPException if a non-empty value cannot yield a 4-digit result."""
    s = re.sub(r"\s", "", (raw or ""))
    if not s:
        return ""
    digits_only = re.sub(r"\D", "", s)
    if len(s) >= 15:  # looks like a full IBAN
        if not digits_only or len(digits_only) < 4:
            raise HTTPException(status_code=400, detail="IBAN invalide.")
        return digits_only[-4:]
    if re.fullmatch(r"\d{4}", s):
        return s
    raise HTTPException(
        status_code=400,
        detail="Fournissez un IBAN complet ou exactement les 4 derniers chiffres.",
    )


def _normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


def _normalize_phone(raw: str) -> str:
    s = re.sub(r"[^\d+]", "", (raw or "").strip())
    # If starts with + keep, else strip leading zeros only if length > 10 — keep as-is otherwise
    return s


def _looks_like_email(s: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", (s or "").strip()))


def _looks_like_phone(s: str) -> bool:
    digits = re.sub(r"\D", "", s or "")
    return len(digits) >= 8


def _validate_last4(raw: str) -> str:
    """Legacy helper used by direct admin CRUD endpoints: accepts 4 digits or empty."""
    return _derive_iban_last4(raw)


# BIC: 4 letters (bank code) + 2 letters (country) + 2 alnum + optional 3 alnum (branch)
_BIC_RE = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")

# Mapping of BIC bank code (first 4 letters) → human bank name.
# Covers the main French retail banks + a few neo-banks.
_BIC_PREFIX_TO_BANK = {
    "BNPA": "BNP Paribas",
    "SOGE": "Société Générale",
    "AGRI": "Crédit Agricole",
    "CRLY": "LCL",
    "CMCI": "Crédit Mutuel",
    "CMBR": "Crédit Mutuel de Bretagne",
    "CMCM": "Crédit Mutuel",
    "CMCY": "Crédit Mutuel",
    "CCBP": "Banque Populaire",
    "BRED": "BRED Banque Populaire",
    "CEPA": "Caisse d'Épargne",
    "CEFR": "Caisse d'Épargne",
    "PSST": "La Banque Postale",
    "BPCE": "BPCE",
    "BOUS": "Boursorama Banque",
    "FTNO": "Fortuneo",
    "HELA": "Hello Bank",
    "MONA": "Monabanq",
    "REVO": "Revolut",
    "N26": "N26",
    "NTSB": "N26",
    "MFBA": "Ma French Bank",
    "ORAN": "Orange Bank",
    "QNTO": "Qonto",
    "WISE": "Wise",
    "SMCT": "LCL",
    "HSBC": "HSBC",
    "ING": "ING",
    "INGB": "ING",
    "BQBE": "Banque de Bretagne",
    "CMMC": "Crédit Mutuel Massif Central",
    "CIC": "CIC",
    "CMBF": "Crédit Mutuel",
    "SMCB": "Société Marseillaise de Crédit",
}


def _bank_name_from_bic(bic: str) -> str:
    """Return the bank display name derived from the first 4 letters of a valid BIC."""
    s = _normalize_bic(bic)
    if not _looks_like_bic(s):
        return ""
    prefix = s[:4]
    return _BIC_PREFIX_TO_BANK.get(prefix, "")


# Known French / common European banks for heuristic bank-name detection in imports
_KNOWN_BANKS = {
    "bnp paribas": "BNP Paribas",
    "bnp": "BNP Paribas",
    "credit agricole": "Crédit Agricole",
    "crédit agricole": "Crédit Agricole",
    "ca": "Crédit Agricole",
    "lcl": "LCL",
    "societe generale": "Société Générale",
    "société générale": "Société Générale",
    "sg": "Société Générale",
    "la banque postale": "La Banque Postale",
    "banque postale": "La Banque Postale",
    "caisse d'epargne": "Caisse d'Épargne",
    "caisse d'épargne": "Caisse d'Épargne",
    "caisse epargne": "Caisse d'Épargne",
    "credit mutuel": "Crédit Mutuel",
    "crédit mutuel": "Crédit Mutuel",
    "cic": "CIC",
    "hsbc": "HSBC",
    "ing": "ING",
    "boursorama": "Boursorama Banque",
    "fortuneo": "Fortuneo",
    "hello bank": "Hello Bank",
    "monabanq": "Monabanq",
    "revolut": "Revolut",
    "n26": "N26",
    "bpce": "BPCE",
    "bred": "BRED Banque Populaire",
    "banque populaire": "Banque Populaire",
    "orange bank": "Orange Bank",
    "ma french bank": "Ma French Bank",
}


def _looks_like_bic(s: str) -> bool:
    return bool(_BIC_RE.match((s or "").strip().upper()))


def _normalize_bic(raw: str) -> str:
    return (raw or "").strip().upper()


def _match_bank_name(text: str) -> Optional[str]:
    low = (text or "").strip().lower()
    if not low:
        return None
    # Direct exact
    if low in _KNOWN_BANKS:
        return _KNOWN_BANKS[low]
    # Substring match (longest first)
    best = None
    for key, val in sorted(_KNOWN_BANKS.items(), key=lambda kv: -len(kv[0])):
        if key in low:
            best = val
            break
    return best


async def public_user(entity: dict) -> dict:
    """Build the public representation for either an admin user or a customer profile."""
    kind = entity.get("kind", "user")
    if kind == "profile":
        iban_full = (entity.get("iban", "") or "").replace(" ", "").upper()
        return {
            "id": str(entity["_id"]),
            "email": entity.get("email", ""),
            "phone": entity.get("phone", ""),
            "name": strip_emojis(entity.get("name", "")) or "Non renseigné",
            "iban": iban_full,
            "iban_masked": mask_iban_from_last4(entity.get("iban_last4", "")),
            "has_iban": bool(iban_full or entity.get("iban_last4")),
            "bic": entity.get("bic", ""),
            "bank_name": strip_emojis(entity.get("bank_name", "")),
            "address": strip_emojis(entity.get("address", "")),
            "postal_code": entity.get("postal_code", ""),
            "city": strip_emojis(entity.get("city", "")),
            "birth_year": entity.get("birth_year", ""),
            "role": "user",
            "kind": "profile",
        }
    # admin user
    return {
        "id": str(entity["_id"]),
        "email": entity.get("email", ""),
        "phone": "",
        "name": entity.get("name", "Admin"),
        "iban_masked": "",
        "has_iban": False,
        "bic": "",
        "bank_name": "",
        "role": entity.get("role", "admin"),
        "kind": "user",
    }


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Type de jeton invalide")
        kind = payload.get("kind", "user")
        sub = payload["sub"]
        if kind == "profile":
            doc = await db.customer_profiles.find_one({"_id": ObjectId(sub)})
            if not doc:
                raise HTTPException(status_code=401, detail="Profil introuvable")
            doc["kind"] = "profile"
            return doc
        else:
            doc = await db.users.find_one({"_id": ObjectId(sub)})
            if not doc:
                raise HTTPException(status_code=401, detail="Utilisateur introuvable")
            doc["kind"] = "user"
            return doc
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Jeton invalide")


async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if user.get("kind") != "user" or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    return user


# ---------- models ----------
class LoginInput(BaseModel):
    email: str
    password: str


class CancelInput(BaseModel):
    reason: str
    feedback: Optional[str] = ""


class ProfileAdminInput(BaseModel):
    email: Optional[str] = ""
    phone: Optional[str] = ""
    name: str = Field("", max_length=200)
    iban: Optional[str] = Field("", max_length=40)
    iban_last4: Optional[str] = ""
    bic: Optional[str] = ""
    bank_name: Optional[str] = Field("", max_length=120)
    address: Optional[str] = Field("", max_length=300)
    postal_code: Optional[str] = Field("", max_length=20)
    city: Optional[str] = Field("", max_length=120)
    birth_year: Optional[str] = Field("", max_length=10)


class ProfileImportInput(BaseModel):
    text: str = Field(..., min_length=1)


# ---------- brute force ----------
async def check_lockout(identifier: str):
    rec = await db.login_attempts.find_one({"identifier": identifier})
    if rec and rec.get("count", 0) >= MAX_FAILED:
        last = rec.get("last_attempt")
        if last:
            if isinstance(last, str):
                last = datetime.fromisoformat(last)
            if datetime.now(timezone.utc) - last < timedelta(minutes=LOCKOUT_MINUTES):
                raise HTTPException(status_code=429,
                                    detail="Trop de tentatives. Réessayez dans quelques minutes.")


async def record_failure(identifier: str):
    await db.login_attempts.update_one(
        {"identifier": identifier},
        {"$inc": {"count": 1}, "$set": {"last_attempt": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def clear_failures(identifier: str):
    await db.login_attempts.delete_one({"identifier": identifier})


# ---------- routes: auth ----------
@api_router.get("/")
async def root():
    return {"message": "Bouygues clone API"}


@api_router.post("/auth/login")
async def login(payload: LoginInput, request: Request, response: Response):
    raw = (payload.email or "").strip()
    if not raw or not payload.password:
        raise HTTPException(status_code=400, detail="Identifiant et mot de passe obligatoires.")

    ip = request.client.host if request.client else "unknown"
    identifier_key = f"{ip}:{raw.lower()}"
    await check_lockout(identifier_key)

    admin_email = _normalize_email(os.environ.get("ADMIN_EMAIL", ""))
    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    normalized_email = _normalize_email(raw) if "@" in raw else ""
    normalized_phone = _normalize_phone(raw) if "@" not in raw else ""

    # --- Admin path: strict password ---
    if admin_email and normalized_email == admin_email:
        admin_doc = await db.users.find_one({"email": admin_email})
        if not admin_doc or not verify_password(payload.password, admin_doc["password_hash"]):
            await record_failure(identifier_key)
            raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect.")
        await clear_failures(identifier_key)
        admin_doc["kind"] = "user"
        access = create_access_token(str(admin_doc["_id"]), "user", "admin")
        refresh = create_refresh_token(str(admin_doc["_id"]), "user")
        set_auth_cookies(response, access, refresh)
        return {"message": "Connexion réussie", "user": await public_user(admin_doc)}

    # --- Customer profile path: any password accepted if identifier is authorized ---
    query = {"$or": []}
    if normalized_email:
        query["$or"].append({"email": normalized_email})
    if normalized_phone:
        query["$or"].append({"phone": normalized_phone})
    if not query["$or"]:
        await record_failure(identifier_key)
        raise HTTPException(status_code=401, detail="Identifiant non autorisé.")

    profile = await db.customer_profiles.find_one(query)
    if not profile:
        await record_failure(identifier_key)
        raise HTTPException(status_code=401, detail="Identifiant non autorisé.")

    await clear_failures(identifier_key)
    profile["kind"] = "profile"
    access = create_access_token(str(profile["_id"]), "profile", "user")
    refresh = create_refresh_token(str(profile["_id"]), "profile")
    set_auth_cookies(response, access, refresh)
    return {"message": "Connexion réussie", "user": await public_user(profile)}


@api_router.post("/auth/logout")
async def logout(response: Response, _: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Déconnecté"}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": await public_user(user)}


@api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Aucun jeton de rafraîchissement")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Type de jeton invalide")
        kind = payload.get("kind", "user")
        sub = payload["sub"]
        role = "user"
        if kind == "user":
            doc = await db.users.find_one({"_id": ObjectId(sub)})
            if not doc:
                raise HTTPException(status_code=401, detail="Utilisateur introuvable")
            role = doc.get("role", "user")
        else:
            doc = await db.customer_profiles.find_one({"_id": ObjectId(sub)})
            if not doc:
                raise HTTPException(status_code=401, detail="Profil introuvable")
        access = create_access_token(sub, kind, role)
        response.set_cookie(key="access_token", value=access, httponly=True, secure=True,
                            samesite="none", max_age=12 * 3600, path="/")
        return {"message": "Jeton rafraîchi"}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Jeton invalide")


# ---------- routes: subscription ----------
@api_router.get("/subscription/canal")
async def canal_status(user: dict = Depends(get_current_user)):
    rec = await db.cancellations.find_one({"user_id": str(user["_id"]), "service": "canal"})
    return {
        "service": "CANAL+",
        "offer": "CANAL+ Ciné Séries",
        "price": "69,99 €/mois",
        "status": "cancellation_requested" if rec else "active",
        "cancellation": {
            "reason": rec.get("reason"),
            "requested_at": rec.get("created_at"),
            "effective_date": rec.get("effective_date"),
        } if rec else None,
    }


@api_router.post("/subscription/canal/cancel")
async def canal_cancel(payload: CancelInput, user: dict = Depends(get_current_user)):
    existing = await db.cancellations.find_one({"user_id": str(user["_id"]), "service": "canal"})
    if existing:
        raise HTTPException(status_code=400, detail="Une demande de résiliation est déjà en cours.")
    now = datetime.now(timezone.utc)
    effective = now + timedelta(days=30)
    await db.cancellations.insert_one({
        "user_id": str(user["_id"]),
        "email": user.get("email", ""),
        "phone": user.get("phone", ""),
        "service": "canal",
        "reason": payload.reason,
        "feedback": payload.feedback or "",
        "status": "pending",
        "created_at": now.isoformat(),
        "effective_date": effective.strftime("%d/%m/%Y"),
    })
    return {
        "message": "Votre demande de résiliation a bien été enregistrée.",
        "effective_date": effective.strftime("%d/%m/%Y"),
    }


@api_router.post("/subscription/canal/cancel/undo")
async def canal_undo(user: dict = Depends(get_current_user)):
    rec = await db.cancellations.find_one({"user_id": str(user["_id"]), "service": "canal"})
    if not rec:
        raise HTTPException(status_code=400, detail="Aucune résiliation en cours.")
    eff = rec.get("effective_date")
    try:
        eff_dt = datetime.strptime(eff, "%d/%m/%Y").replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > eff_dt:
            raise HTTPException(
                status_code=400,
                detail="La résiliation est déjà effective et ne peut plus être annulée.",
            )
    except ValueError:
        pass
    await db.cancellations.delete_one({"_id": rec["_id"]})
    return {"message": "Votre résiliation a été annulée. Votre abonnement reste actif."}


@api_router.get("/prelevements")
async def list_prelevements(user: dict = Depends(get_current_user)):
    docs = await db.prelevements.find({"user_id": str(user["_id"])}).sort("date", -1).to_list(200)
    items = [{"date": d["date"], "amount": d["amount"], "label": d.get("label", "")} for d in docs]
    return {
        "prelevements": items,
        "latest": items[0]["date"] if items else None,
        "count": len(items),
        "amount": 69.99,
    }


# ---------- admin: customer profiles ----------
def _profile_to_public(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "email": doc.get("email", ""),
        "phone": doc.get("phone", ""),
        "name": doc.get("name", ""),
        "iban": doc.get("iban", ""),
        "iban_last4": doc.get("iban_last4", ""),
        "bic": doc.get("bic", ""),
        "bank_name": doc.get("bank_name", ""),
        "address": doc.get("address", ""),
        "postal_code": doc.get("postal_code", ""),
        "city": doc.get("city", ""),
        "birth_year": doc.get("birth_year", ""),
        "updated_at": doc.get("updated_at", ""),
    }


async def _check_profile_uniqueness(email: str, phone: str, exclude_id: Optional[ObjectId] = None):
    conflicts = []
    if email:
        q = {"email": email}
        if exclude_id:
            q["_id"] = {"$ne": exclude_id}
        if await db.customer_profiles.find_one(q):
            conflicts.append(f"email {email}")
    if phone:
        q = {"phone": phone}
        if exclude_id:
            q["_id"] = {"$ne": exclude_id}
        if await db.customer_profiles.find_one(q):
            conflicts.append(f"téléphone {phone}")
    if conflicts:
        raise HTTPException(
            status_code=400,
            detail=f"Un profil existe déjà avec cet(te) : {', '.join(conflicts)}.",
        )


@api_router.get("/admin/profiles")
async def admin_list_profiles(
    skip: int = 0,
    limit: int = 50,
    q: str = "",
    _: dict = Depends(get_admin_user),
):
    skip = max(0, int(skip))
    limit = max(1, min(int(limit), 500))
    query = {}
    q = (q or "").strip()
    if q:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        query = {"$or": [
            {"email": rx}, {"phone": rx}, {"name": rx},
            {"city": rx}, {"postal_code": rx},
        ]}
        total = await db.customer_profiles.count_documents(query)
    else:
        total = await db.customer_profiles.estimated_document_count()
    docs = (
        await db.customer_profiles.find(query)
        .sort("_id", 1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    return {
        "profiles": [_profile_to_public(d) for d in docs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@api_router.post("/admin/profiles")
async def admin_create_profile(payload: ProfileAdminInput, _: dict = Depends(get_admin_user)):
    email = _normalize_email(payload.email or "")
    phone = _normalize_phone(payload.phone or "")
    name = (payload.name or "").strip()
    iban_full = _extract_full_iban(payload.iban or "") or re.sub(r"\s", "", (payload.iban or "")).upper()
    last4 = _validate_last4(payload.iban_last4 or "") or (iban_full[-4:] if iban_full else "")
    bic = _normalize_bic(payload.bic or "")
    if bic and not _looks_like_bic(bic):
        raise HTTPException(status_code=400, detail="BIC invalide (8 ou 11 caractères).")
    bank_name = (payload.bank_name or "").strip()
    if not bank_name and bic:
        bank_name = _bank_name_from_bic(bic)
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Email ou téléphone obligatoire.")
    if email and not _looks_like_email(email):
        raise HTTPException(status_code=400, detail="Email invalide.")
    await _check_profile_uniqueness(email, phone)
    doc = {
        "email": email,
        "phone": phone,
        "name": strip_emojis(name),
        "iban": iban_full,
        "iban_last4": last4,
        "bic": bic,
        "bank_name": strip_emojis(bank_name),
        "address": strip_emojis(payload.address or ""),
        "postal_code": strip_emojis(payload.postal_code or ""),
        "city": strip_emojis(payload.city or ""),
        "birth_year": strip_emojis(payload.birth_year or ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.customer_profiles.insert_one(doc)
    doc["_id"] = res.inserted_id
    return {"profile": _profile_to_public(doc)}


@api_router.put("/admin/profiles/{profile_id}")
async def admin_update_profile(
    profile_id: str,
    payload: ProfileAdminInput,
    _: dict = Depends(get_admin_user),
):
    try:
        oid = ObjectId(profile_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiant de profil invalide.")
    email = _normalize_email(payload.email or "")
    phone = _normalize_phone(payload.phone or "")
    name = (payload.name or "").strip()
    iban_full = _extract_full_iban(payload.iban or "") or re.sub(r"\s", "", (payload.iban or "")).upper()
    last4 = _validate_last4(payload.iban_last4 or "") or (iban_full[-4:] if iban_full else "")
    bic = _normalize_bic(payload.bic or "")
    if bic and not _looks_like_bic(bic):
        raise HTTPException(status_code=400, detail="BIC invalide (8 ou 11 caractères).")
    bank_name = (payload.bank_name or "").strip()
    if not bank_name and bic:
        bank_name = _bank_name_from_bic(bic)
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Email ou téléphone obligatoire.")
    if email and not _looks_like_email(email):
        raise HTTPException(status_code=400, detail="Email invalide.")
    await _check_profile_uniqueness(email, phone, exclude_id=oid)
    updates = {
        "email": email,
        "phone": phone,
        "name": strip_emojis(name),
        "iban": iban_full,
        "iban_last4": last4,
        "bic": bic,
        "bank_name": strip_emojis(bank_name),
        "address": strip_emojis(payload.address or ""),
        "postal_code": strip_emojis(payload.postal_code or ""),
        "city": strip_emojis(payload.city or ""),
        "birth_year": strip_emojis(payload.birth_year or ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.customer_profiles.update_one({"_id": oid}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profil introuvable.")
    doc = await db.customer_profiles.find_one({"_id": oid})
    return {"profile": _profile_to_public(doc)}


@api_router.delete("/admin/profiles/all")
async def admin_delete_all_profiles(_: dict = Depends(get_admin_user)):
    result = await db.customer_profiles.delete_many({})
    return {"message": "Base vidée.", "deleted": result.deleted_count}


@api_router.delete("/admin/profiles/{profile_id}")
async def admin_delete_profile(profile_id: str, _: dict = Depends(get_admin_user)):
    try:
        oid = ObjectId(profile_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiant de profil invalide.")
    result = await db.customer_profiles.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Profil introuvable.")
    return {"message": "Profil supprimé."}


class DeleteBulkInput(BaseModel):
    ids: List[str] = []


class DeleteRangeInput(BaseModel):
    start: int
    end: int


@api_router.post("/admin/profiles/delete-bulk")
async def admin_delete_bulk(payload: DeleteBulkInput, _: dict = Depends(get_admin_user)):
    oids = []
    for i in payload.ids:
        try:
            oids.append(ObjectId(i))
        except Exception:
            continue
    if not oids:
        raise HTTPException(status_code=400, detail="Aucun identifiant valide fourni.")
    result = await db.customer_profiles.delete_many({"_id": {"$in": oids}})
    return {"message": "Profils supprimés.", "deleted": result.deleted_count}


@api_router.post("/admin/profiles/delete-range")
async def admin_delete_range(payload: DeleteRangeInput, _: dict = Depends(get_admin_user)):
    """Delete profiles by 1-based position in the default (_id ascending) order,
    i.e. the row numbers shown in the admin table — inclusive bounds."""
    start = max(1, int(payload.start))
    end = int(payload.end)
    if end < start:
        raise HTTPException(status_code=400, detail="Plage invalide (fin < début).")
    skip = start - 1
    count = end - start + 1
    cursor = db.customer_profiles.find({}, {"_id": 1}).sort("_id", 1).skip(skip).limit(count)
    ids = [d["_id"] async for d in cursor]
    if not ids:
        return {"message": "Aucun profil dans cette plage.", "deleted": 0}
    result = await db.customer_profiles.delete_many({"_id": {"$in": ids}})
    return {"message": "Plage supprimée.", "deleted": result.deleted_count}


# ---------- bulk import ----------
_HEADER_KEYS = {
    "email": {"email", "e-mail", "mail", "adresse", "adresseemail", "courriel"},
    "phone": {"phone", "tel", "telephone", "téléphone", "mobile", "numero", "numéro"},
    "name": {"name", "nom", "prenom", "prénom", "nom prénom", "nomprénom", "titulaire",
             "fullname", "full_name"},
    "iban_last4": {"iban", "iban_last4", "iban4", "last4", "4chiffres", "chiffres"},
}

_HAS_ALNUM = re.compile(r"[0-9A-Za-zÀ-ÿ@]")
_EMAIL_RE = re.compile(r"[^@\s,;|\t]+@[^@\s,;|\t]+\.[^@\s,;|\t]+")
_IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2}(?:[\s]?[A-Z0-9]{2,4}){4,8})\b", re.IGNORECASE)
_FULL_IBAN_RE = re.compile(r"[A-Za-z]{2}\d{2}[A-Za-z0-9 ]{10,40}")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_POSTAL_CITY_RE = re.compile(r"^\s*(\d{5})\s+(.+)$")
_NA_VALUES = {"n/a", "na", "n.a", "-", "--", "néant", "neant", "aucun",
              "none", "null", "vide", "x", "."}


def _is_na(text: str) -> bool:
    return (text or "").strip().lower() in _NA_VALUES


def _extract_full_iban(text: str) -> str:
    """Return the full IBAN (uppercase, no spaces) if a valid one is present."""
    if not text:
        return ""
    m = _FULL_IBAN_RE.search(text)
    if not m:
        return ""
    compact = re.sub(r"\s", "", m.group(0)).upper()
    if 15 <= len(compact) <= 34 and re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", compact):
        return compact
    return ""


def _classify_header(h):
    key = re.sub(r"[\s_\-]", "", (h or "").strip().lower())
    for field, aliases in _HEADER_KEYS.items():
        norm = {re.sub(r"[\s_\-]", "", a) for a in aliases}
        if key in norm:
            return field
    return None


def _empty_record():
    return {"email": "", "phone": "", "name": "", "iban": "", "iban_last4": "", "bic": "",
            "bank_name": "", "address": "", "postal_code": "", "city": "", "birth_year": ""}


def _norm_birth_year(text):
    m = _YEAR_RE.search(text or "")
    return m.group(0) if m else ""


def _is_phone_token(text):
    t = (text or "").strip()
    if not t or re.search(r"[A-Za-z]", t):
        return False
    digits = re.sub(r"\D", "", t)
    return 8 <= len(digits) <= 15 and bool(re.fullmatch(r"[\d\s.+()\-]+", t))


def _assign_block_line(rec, field, rest):
    """STRICT field assignment: each line goes to exactly ONE field. The emoji marker
    is authoritative; content heuristics are only a fallback for unmarked lines and
    NEVER merge two different pieces of information into the same field."""
    rest = (rest or "").strip()
    if not rest:
        return
    low = rest.lower()
    na = _is_na(rest)

    # 1) Explicit emoji marker -> dedicated field only.
    if field == "name":
        if not rec["name"] and not na:
            rec["name"] = rest
        return
    if field == "email":
        if not na and _looks_like_email(rest):
            rec["email"] = _normalize_email(rest)
        return
    if field == "phone":
        if not na:
            rec["phone"] = _normalize_phone(rest)
        return
    if field == "address":
        if not na and not rec["address"]:
            rec["address"] = rest
        return
    if field == "postal":
        mpc = _POSTAL_CITY_RE.match(rest)
        if mpc:
            rec["postal_code"] = mpc.group(1)
            rec["city"] = mpc.group(2).strip()
        elif not na:
            rec["city"] = rest
        return
    if field == "birth":
        y = _norm_birth_year(rest)
        if y:
            rec["birth_year"] = y
        return
    if field == "bank":
        if not na and not rec["bank_name"]:
            rec["bank_name"] = rest
        return
    if field == "iban":
        iban = _extract_full_iban(rest)
        if iban:
            rec["iban"] = iban
            rec["iban_last4"] = iban[-4:]
        return

    # 2) Unmarked line -> conservative, isolated heuristics.
    if na:
        return
    if _looks_like_email(rest):
        if not rec["email"]:
            rec["email"] = _normalize_email(rest)
        return
    iban = _extract_full_iban(rest)
    if iban:
        rec["iban"] = iban
        rec["iban_last4"] = iban[-4:]
        return
    if "né" in low or "nee" in low or "naiss" in low:
        y = _norm_birth_year(rest)
        if y:
            rec["birth_year"] = y
            return
    mpc = _POSTAL_CITY_RE.match(rest)
    if mpc:
        rec["postal_code"] = mpc.group(1)
        rec["city"] = mpc.group(2).strip()
        return
    if _is_phone_token(rest):
        if not rec["phone"]:
            rec["phone"] = _normalize_phone(rest)
        return
    if re.match(r"^\d{1,5}\s+\S", rest) and not rec["address"]:
        rec["address"] = rest
        return
    y = _norm_birth_year(rest)
    if y and len(re.sub(r"\D", "", rest)) == 4:
        rec["birth_year"] = y
        return
    bank = _match_bank_name(rest)
    if bank and not rec["bank_name"]:
        rec["bank_name"] = bank
        return
    # Last resort: only the holder name, otherwise DROP (never pollute another field).
    if not rec["name"]:
        rec["name"] = rest


def _is_block_header(ln):
    return bool(re.search(r"#\s*\d+", ln)) and not re.search(r"[A-Za-zÀ-ÿ@]", ln)


def _looks_like_block_format(lines):
    non_empty = [ln for ln in lines if ln.strip()]
    if not non_empty:
        return False
    if any(_is_block_header(ln) for ln in non_empty[:80]):
        return True
    marked = 0
    for ln in non_empty[:60]:
        field, _ = _leading_emoji_field(ln)
        if field:
            marked += 1
    return marked >= max(2, int(0.3 * min(len(non_empty), 60)))


def _parse_blocks(text):
    """Vertical/block format: records separated by '#N' headers or blank lines,
    each field on its own line (optionally prefixed by an emoji)."""
    raw_lines = (text or "").splitlines()
    has_hash = any(_is_block_header(ln) for ln in raw_lines)
    records = []
    current = None

    def flush():
        nonlocal current
        if current and (current["email"] or current["phone"]):
            records.append(current)
        current = None

    for ln in raw_lines:
        if _is_block_header(ln):
            flush()
            current = _empty_record()
            continue
        if not ln.strip():
            if not has_hash:
                flush()
            continue
        if not _HAS_ALNUM.search(strip_emojis(ln)):
            continue  # decorative separator line
        if current is None:
            current = _empty_record()
        field, rest = _leading_emoji_field(ln)
        _assign_block_line(current, field, rest)
    flush()
    return records


# ----- horizontal (one line = one record) fallback parser -----
def _split_line(line):
    for d in [";", "\t", "|", ","]:
        if d in line:
            return [p.strip() for p in line.split(d) if p.strip()]
    return [p for p in re.split(r"\s{2,}|\s+", line) if p]


def _parse_tokens_heuristic(tokens):
    out = _empty_record()
    leftover = []
    for raw in tokens:
        t = strip_emojis(raw.strip().strip('"').strip("'"))
        if not t:
            continue
        if not out["email"] and _looks_like_email(t):
            out["email"] = _normalize_email(t)
            continue
        if not out["iban_last4"]:
            iban = _extract_full_iban(t)
            if iban:
                out["iban"] = iban
                out["iban_last4"] = iban[-4:]
                continue
            if re.fullmatch(r"\d{4}", t):
                out["iban_last4"] = t
                continue
        if not out["bic"] and _looks_like_bic(t):
            out["bic"] = _normalize_bic(t)
            continue
        if not out["phone"] and _is_phone_token(t):
            out["phone"] = _normalize_phone(t)
            continue
        leftover.append(t)
    leftover_text = " ".join(leftover).strip()
    bank = _match_bank_name(leftover_text)
    if bank and not out["bank_name"]:
        out["bank_name"] = bank
        low = leftover_text.lower()
        if bank.lower() in low:
            start = low.index(bank.lower())
            leftover_text = (leftover_text[:start] + leftover_text[start + len(bank):]).strip()
    out["name"] = re.sub(r"\s+", " ", leftover_text).strip()
    return out


def _parse_horizontal(text):
    rows = []
    lines = [ln for ln in (text or "").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return rows
    first_tokens = _split_line(lines[0])
    skip_header = any(_classify_header(tok) for tok in first_tokens)
    start_idx = 1 if skip_header else 0
    for line in lines[start_idx:]:
        email = ""
        iban_full = ""
        remaining = line
        m = _EMAIL_RE.search(remaining)
        if m:
            email = _normalize_email(m.group(0))
            remaining = (remaining[: m.start()] + " " + remaining[m.end():]).strip()
        m = _IBAN_RE.search(remaining)
        if m:
            iban_full = _extract_full_iban(m.group(1))
            if iban_full:
                remaining = (remaining[: m.start()] + " " + remaining[m.end():]).strip()
        tokens = _split_line(remaining) if remaining.strip() else []
        row = _parse_tokens_heuristic(tokens)
        row["email"] = email or row["email"]
        if iban_full:
            row["iban"] = iban_full
            row["iban_last4"] = iban_full[-4:]
        if row.get("email") or row.get("phone"):
            rows.append(row)
    return rows


def parse_import_text(text):
    """Accept ANY format: the vertical emoji/block format OR the horizontal
    (one line per record) format. Merge records sharing an email or phone."""
    lines = (text or "").splitlines()
    if _looks_like_block_format(lines):
        rows = _parse_blocks(text)
    else:
        rows = _parse_horizontal(text)

    # Merge repeated identities while keeping ambiguous email/phone collisions
    # as explicit skipped rows instead of silently combining two profiles.
    records = []
    by_email = {}
    by_phone = {}
    conflicts = []

    for r in rows:
        row = dict(r)
        email = _normalize_email(row.get("email", ""))
        phone = _normalize_phone(row.get("phone", ""))
        row["email"], row["phone"] = email, phone
        if not email and not phone:
            continue

        email_index = by_email.get(email) if email else None
        phone_index = by_phone.get(phone) if phone else None
        if email_index is not None and phone_index is not None and email_index != phone_index:
            row["_import_conflict"] = True
            conflicts.append(row)
            continue
        if (phone_index is not None and email_index is None and email and
                records[phone_index].get("email") and records[phone_index]["email"] != email):
            row["_import_conflict"] = True
            conflicts.append(row)
            continue

        index = email_index if email_index is not None else phone_index
        if index is None:
            index = len(records)
            records.append(row)
            old_email, old_phone = email, phone
        else:
            target = records[index]
            old_email, old_phone = target.get("email", ""), target.get("phone", "")
            for field, value in row.items():
                if value and field != "_import_conflict":
                    target[field] = value

        # A repeated email may contain an updated phone. Remove the old alias
        # so later rows are matched only to the identity now being retained.
        for aliases, old_value, new_value in (
            (by_email, old_email, email),
            (by_phone, old_phone, phone),
        ):
            if old_value and new_value and old_value != new_value and aliases.get(old_value) == index:
                aliases.pop(old_value, None)

        if email:
            by_email[email] = index
        if phone:
            by_phone[phone] = index

    return records + conflicts


# ---------- import jobs (background, large-volume safe) ----------
IMPORT_JOBS = {}
_IMPORT_BATCH = 1000


def _new_job():
    job_id = uuid.uuid4().hex
    IMPORT_JOBS[job_id] = {
        "job_id": job_id, "status": "parsing", "total": 0,
        "processed": 0, "created": 0, "updated": 0, "duplicates": 0, "errors": 0,
        "error_samples": [], "message": "",
    }
    return job_id


async def _flush_batch(job, batch):
    if not batch:
        return

    emails = sorted({item["email"] for item in batch if item["email"]})
    phones = sorted({item["phone"] for item in batch if item["phone"]})
    clauses = []
    if emails:
        clauses.append({"email": {"$in": emails}})
    if phones:
        clauses.append({"phone": {"$in": phones}})

    by_email, by_phone = {}, {}
    if clauses:
        cursor = db.customer_profiles.find(
            {"$or": clauses}, {"_id": 1, "email": 1, "phone": 1}
        )
        async for profile in cursor:
            if profile.get("email"):
                by_email.setdefault(profile["email"], []).append(profile)
            if profile.get("phone"):
                by_phone.setdefault(profile["phone"], []).append(profile)

    operations, operation_rows = [], []
    for item in batch:
        email, phone, doc = item["email"], item["phone"], item["doc"]
        email_matches = by_email.get(email, [])
        phone_matches = by_phone.get(phone, [])
        email_ids = {p["_id"] for p in email_matches}
        phone_ids = {p["_id"] for p in phone_matches}

        if email_matches and phone_matches:
            common_ids = email_ids & phone_ids
            if not common_ids:
                job["duplicates"] += 1
                if len(job["error_samples"]) < 20:
                    job["error_samples"].append({
                        "error": "Ligne ignorée : l’email et le téléphone appartiennent à deux profils différents."
                    })
                continue
            matched_id = next(iter(common_ids))
            existing = next(p for p in email_matches + phone_matches if p["_id"] == matched_id)
        elif email_matches:
            existing = email_matches[0]
        elif phone_matches:
            existing = phone_matches[0]
            if (email and existing.get("email") and
                    existing["email"] != email):
                job["duplicates"] += 1
                if len(job["error_samples"]) < 20:
                    job["error_samples"].append({
                        "error": "Ligne ignorée : ce téléphone est déjà rattaché à un autre email."
                    })
                continue
        else:
            existing = None

        if existing:
            updates = {key: value for key, value in doc.items() if value not in (None, "")}
            operations.append(UpdateOne({"_id": existing["_id"]}, {"$set": updates}))
        else:
            identity = {"email": email} if email else {"phone": phone}
            operations.append(UpdateOne(identity, {"$set": doc}, upsert=True))
        operation_rows.append(item)

    try:
        if operations:
            result = await db.customer_profiles.bulk_write(operations, ordered=False)
            job["created"] += result.upserted_count or 0
            job["updated"] += result.matched_count or 0
    except BulkWriteError as bwe:
        details = bwe.details or {}
        job["created"] += details.get("nUpserted", 0)
        job["updated"] += details.get("nMatched", 0)
        for error in details.get("writeErrors", []):
            index = error.get("index", -1)
            item = operation_rows[index] if 0 <= index < len(operation_rows) else None
            if error.get("code") == 11000 and item:
                # Another import may have inserted this identity after preflight.
                email, phone = item["email"], item["phone"]
                found_by_email = await db.customer_profiles.find_one({"email": email}) if email else None
                found_by_phone = await db.customer_profiles.find_one({"phone": phone}) if phone else None
                if (found_by_email and found_by_phone and
                        found_by_email["_id"] != found_by_phone["_id"]):
                    job["duplicates"] += 1
                    message = "Ligne ignorée : l’email et le téléphone appartiennent à deux profils différents."
                elif (found_by_phone and not found_by_email and email and
                      found_by_phone.get("email") and found_by_phone["email"] != email):
                    job["duplicates"] += 1
                    message = "Ligne ignorée : ce téléphone est déjà rattaché à un autre email."
                else:
                    winner = found_by_email or found_by_phone
                    if winner:
                        try:
                            updates = {
                                key: value for key, value in item["doc"].items()
                                if value not in (None, "")
                            }
                            await db.customer_profiles.update_one(
                                {"_id": winner["_id"]}, {"$set": updates}
                            )
                            job["updated"] += 1
                            continue
                        except DuplicateKeyError:
                            pass
                    job["duplicates"] += 1
                    message = "Ligne ignorée : cet email ou téléphone est déjà associé à un autre profil."
                if len(job["error_samples"]) < 20:
                    job["error_samples"].append({"error": message})
            else:
                job["errors"] += 1
                if len(job["error_samples"]) < 20:
                    job["error_samples"].append({
                        "error": (error.get("errmsg", "Erreur d’écriture") or "")[:160]
                    })
    finally:
        job["processed"] += len(batch)


async def _run_import_job(job_id, text):
    job = IMPORT_JOBS[job_id]
    try:
        parsed = await asyncio.to_thread(parse_import_text, text)
        if not parsed:
            job["status"] = "error"
            job["message"] = ("Aucune ligne exploitable détectée "
                              "(il faut au moins un email ou un téléphone).")
            return
        job["total"] = len(parsed)
        job["status"] = "running"
        batch = []
        for row in parsed:
            email = row.get("email", "")
            phone = row.get("phone", "")
            if row.get("_import_conflict"):
                job["duplicates"] += 1
                job["processed"] += 1
                if len(job["error_samples"]) < 20:
                    job["error_samples"].append({
                        "error": "Ligne ignorée : email ou téléphone déjà rattaché à un autre profil du fichier."
                    })
                continue
            if email and not _looks_like_email(email):
                job["errors"] += 1
                job["processed"] += 1
                if len(job["error_samples"]) < 20:
                    job["error_samples"].append({"error": f"Email invalide : {email}"})
                continue
            bic = (row.get("bic", "") or "").upper()
            bank_name = row.get("bank_name", "")
            if bic and not bank_name:
                bank_name = _bank_name_from_bic(bic)
            doc = {
                "email": email,
                "phone": phone,
                "name": strip_emojis(row.get("name", "")),
                "iban": strip_emojis(row.get("iban", "")).replace(" ", "").upper(),
                "iban_last4": row.get("iban_last4", ""),
                "bic": bic if _looks_like_bic(bic) else "",
                "bank_name": strip_emojis(bank_name),
                "address": strip_emojis(row.get("address", "")),
                "postal_code": row.get("postal_code", ""),
                "city": strip_emojis(row.get("city", "")),
                "birth_year": row.get("birth_year", ""),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            batch.append({"email": email, "phone": phone, "doc": doc})
            if len(batch) >= _IMPORT_BATCH:
                await _flush_batch(job, batch)
                batch = []
                await asyncio.sleep(0)
        if batch:
            await _flush_batch(job, batch)
        job["status"] = "done"
    except Exception as e:
        logger.exception("Import job failed")
        job["status"] = "error"
        job["message"] = str(e)


async def _start_import(text):
    if not text.strip():
        raise HTTPException(status_code=400, detail="Fichier vide ou texte manquant.")
    job_id = _new_job()
    asyncio.create_task(_run_import_job(job_id, text))
    return {"job_id": job_id}


@api_router.post("/admin/profiles/import")
async def admin_import_profiles(
    payload: Optional[ProfileImportInput] = None,
    _: dict = Depends(get_admin_user),
):
    text = (payload.text if payload else "") or ""
    return await _start_import(text)


@api_router.post("/admin/profiles/import-file")
async def admin_import_profiles_file(
    file: UploadFile = File(...),
    _: dict = Depends(get_admin_user),
):
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Impossible de décoder le fichier.")
    return await _start_import(text)


@api_router.get("/admin/profiles/import-status/{job_id}")
async def admin_import_status(job_id: str, _: dict = Depends(get_admin_user)):
    job = IMPORT_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Tâche d'import introuvable.")
    return job


# ---------- streaming export (large-volume safe) ----------
_EXPORT_EMOJI = {
    "name": "\U0001F464", "email": "\U0001F4E7", "phone": "\U0001F4F1",
    "address": "\U0001F3E0", "postal": "\U0001F4EE", "bank": "\U0001F3E6",
    "iban": "\U0001F4B3", "birth": "\U0001F4C5",
}


@api_router.get("/admin/profiles/export")
async def admin_export_profiles(format: str = "csv", _: dict = Depends(get_admin_user)):
    fmt = (format or "csv").lower()
    cursor = db.customer_profiles.find({}).sort("_id", 1).batch_size(1000)
    seen = set()

    def _dedup_key(d):
        if d.get("email"):
            return "e:" + d["email"]
        if d.get("phone"):
            return "p:" + d["phone"]
        return None

    if fmt == "txt":
        async def gen_txt():
            n = 0
            async for d in cursor:
                key = _dedup_key(d)
                if key is not None:
                    if key in seen:
                        continue
                    seen.add(key)
                n += 1
                e = _EXPORT_EMOJI
                lines = [f"── #{n} ──"]
                if d.get("name"):
                    lines.append(f"{e['name']} {d['name']}")
                lines.append(f"{e['email']} {d.get('email') or 'N/A'}")
                if d.get("phone"):
                    lines.append(f"{e['phone']} {d['phone']}")
                if d.get("address"):
                    lines.append(f"{e['address']} {d['address']}")
                if d.get("postal_code") or d.get("city"):
                    lines.append(f"{e['postal']} {d.get('postal_code', '')} {d.get('city', '')}".strip())
                if d.get("bank_name"):
                    lines.append(f"{e['bank']} {d['bank_name']}")
                if d.get("iban"):
                    lines.append(f"{e['iban']} {d['iban']}")
                if d.get("birth_year"):
                    lines.append(f"{e['birth']} Né(e) en {d['birth_year']}")
                yield "\n".join(lines) + "\n\n"
        headers = {"Content-Disposition": "attachment; filename=profils.txt"}
        return StreamingResponse(gen_txt(), media_type="text/plain; charset=utf-8", headers=headers)

    cols = ["name", "email", "phone", "address", "postal_code", "city",
            "bank_name", "iban", "birth_year", "iban_last4", "bic"]

    async def gen_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        async for d in cursor:
            key = _dedup_key(d)
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            writer.writerow([d.get(c, "") for c in cols])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    headers = {"Content-Disposition": "attachment; filename=profils.csv"}
    return StreamingResponse(gen_csv(), media_type="text/csv; charset=utf-8", headers=headers)

# ---------- cron ----------
def _check_cron_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    if not token or not secret or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _run_prelevements(day_iso: str):
    profiles = await db.customer_profiles.find({}).to_list(10000)
    for p in profiles:
        exists = await db.prelevements.find_one({"user_id": str(p["_id"]), "date": day_iso})
        if not exists:
            await db.prelevements.insert_one({
                "user_id": str(p["_id"]),
                "amount": 69.99,
                "label": "CANAL+ Ciné Séries",
                "date": day_iso,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })


@api_router.post("/cron/prelevements")
async def cron_prelevements(request: Request):
    _check_cron_auth(request)
    day_iso = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d")
    asyncio.create_task(_run_prelevements(day_iso))
    return {"status": "accepted"}


# ---------- Stripe payments (Flow B — BYOK via emergentintegrations) ----------
class CheckoutRequest(BaseModel):
    origin_url: str
    reason: Optional[str] = ""
    feedback: Optional[str] = ""


def _get_stripe_client(request: Request) -> StripeCheckout:
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    return StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)


async def _send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Telegram not configured; skipping notification.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as hc:
            r = await hc.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            if r.status_code != 200:
                logger.warning("Telegram sendMessage failed: %s %s", r.status_code, r.text[:200])
    except Exception:
        logger.exception("Telegram notification error")


async def _notify_payment_paid(record: dict):
    name = email = phone = ""
    try:
        prof = await db.customer_profiles.find_one({"_id": ObjectId(record.get("user_id", ""))})
    except Exception:
        prof = None
    if prof:
        name = strip_emojis(prof.get("name", ""))
        email = prof.get("email", "")
        phone = prof.get("phone", "")
    amount = float(record.get("amount", CANCELLATION_FEE_EUR) or 0)
    purpose = record.get("purpose", "")
    label = "Frais de résiliation" if purpose == "cancellation_fee" else (purpose or "—")
    msg = (
        "\u2705 <b>Paiement confirmé</b>\n"
        f"\U0001F4B6 Montant : <b>{amount:.2f} €</b>\n"
        f"\U0001F464 Client : {name or '—'}\n"
        f"\U0001F4E7 {email or '—'}\n"
        f"\U0001F4F1 {phone or '—'}\n"
        f"\U0001F9FE Objet : {label}"
    )
    await _send_telegram(msg)


@api_router.post("/payments/checkout")
async def create_checkout(
    req: CheckoutRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    checkout = _get_stripe_client(request)
    success_url = f"{req.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{req.origin_url}/payment/cancel"
    try:
        session = await checkout.create_checkout_session(
            CheckoutSessionRequest(
                amount=float(CANCELLATION_FEE_EUR),
                currency="eur",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": str(user["_id"]),
                    "purpose": "cancellation_fee",
                    "reason": (req.reason or "")[:120],
                    "feedback": (req.feedback or "")[:300],
                },
            )
        )
    except Exception:
        logger.exception("Stripe checkout failed")
        raise HTTPException(502, "Erreur Stripe. Réessayez plus tard.")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "user_id": str(user["_id"]),
        "purpose": "cancellation_fee",
        "amount": float(CANCELLATION_FEE_EUR),
        "currency": "eur",
        "status": "initiated",
        "payment_status": "pending",
        "reason": req.reason or "",
        "feedback": req.feedback or "",
        "created_at": now_iso,
        "updated_at": now_iso,
    })
    return {"checkout_url": session.url, "session_id": session.session_id}


async def _finalize_cancellation_from_metadata(user_id: str, reason: str, feedback: str):
    existing = await db.cancellations.find_one({"user_id": user_id, "service": "canal"})
    if existing:
        return
    now = datetime.now(timezone.utc)
    effective = now + timedelta(days=30)
    await db.cancellations.insert_one({
        "user_id": user_id,
        "service": "canal",
        "reason": reason or "",
        "feedback": feedback or "",
        "status": "pending",
        "paid": True,
        "created_at": now.isoformat(),
        "effective_date": effective.strftime("%d/%m/%Y"),
    })


@api_router.get("/payments/status/{session_id}")
async def payment_status(session_id: str, request: Request):
    record = await db.payment_transactions.find_one({"session_id": session_id})
    if not record:
        raise HTTPException(404, "Transaction introuvable.")
    if record.get("payment_status") != "paid":
        checkout = _get_stripe_client(request)
        try:
            s = await checkout.get_checkout_status(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                now_iso = datetime.now(timezone.utc).isoformat()
                upd = await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {
                        "status": "completed",
                        "payment_status": "paid",
                        "updated_at": now_iso,
                    }},
                )
                record = await db.payment_transactions.find_one({"session_id": session_id})
                if record and record.get("purpose") == "cancellation_fee":
                    await _finalize_cancellation_from_metadata(
                        record["user_id"], record.get("reason", ""), record.get("feedback", "")
                    )
                if upd.modified_count == 1 and record:
                    await _notify_payment_paid(record)
        except Exception:
            pass
    return {
        "session_id": record["session_id"],
        "status": record["status"],
        "payment_status": record["payment_status"],
        "purpose": record.get("purpose", ""),
    }


@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    checkout = _get_stripe_client(request)
    try:
        event = await checkout.handle_webhook(body, sig)
    except Exception:
        logger.exception("Stripe webhook verification failed")
        raise HTTPException(400, "Webhook invalide.")

    session_id = event.session_id
    payment_status_val = (event.payment_status or "").lower()
    now_iso = datetime.now(timezone.utc).isoformat()

    record = await db.payment_transactions.find_one({"session_id": session_id})
    if not record:
        return {"status": "ignored"}

    if payment_status_val == "paid":
        upd = await db.payment_transactions.update_one(
            {"session_id": session_id, "payment_status": {"$ne": "paid"}},
            {"$set": {
                "status": "completed",
                "payment_status": "paid",
                "updated_at": now_iso,
            }},
        )
        if record.get("purpose") == "cancellation_fee":
            await _finalize_cancellation_from_metadata(
                record["user_id"], record.get("reason", ""), record.get("feedback", "")
            )
        if upd.modified_count == 1:
            fresh = await db.payment_transactions.find_one({"session_id": session_id})
            await _notify_payment_paid(fresh or record)
    elif payment_status_val in {"failed", "canceled", "expired"}:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {
                "status": payment_status_val,
                "payment_status": payment_status_val,
                "updated_at": now_iso,
            }},
        )
    return {"status": "ok"}



# ---------- app wiring ----------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origin_regex=r"https?://(localhost(:\d+)?|.*\.emergentagent\.com|.*\.preview\.emergentagent\.com|.*\.emergent\.host)",
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------- serve the built frontend (for single-service deploys e.g. Railway) ----------
# Inert on Emergent (the build directory does not exist there; the frontend is served
# by its own dev server and the ingress only routes /api/* to the backend).
FRONTEND_BUILD = Path(__file__).parent.parent / "frontend" / "build"
if FRONTEND_BUILD.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_BUILD / "static")),
        name="static-assets",
    )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Never intercept API routes.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = FRONTEND_BUILD / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_BUILD / "index.html"))


@app.on_event("startup")
async def startup():
    # Ensure indexes
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    # customer_profiles: partial unique indexes so empty/missing values don't collide
    for field in ("email", "phone"):
        try:
            await db.customer_profiles.create_index(
                field, unique=True, partialFilterExpression={field: {"$gt": ""}}
            )
        except DuplicateKeyError:
            # Keep the service online on legacy data; the importer checks for
            # identity conflicts itself and reports them as skipped rows.
            logger.warning(
                "Unique %s index was not created: duplicate customer profile values exist.",
                field,
            )
        except OperationFailure as exc:
            # A pre-existing index with incompatible options must not prevent
            # Railway from starting; only index-specific conflicts are ignored.
            if exc.code not in (85, 86):
                raise
            logger.warning(
                "Unique %s index was not changed because an incompatible index exists.",
                field,
            )
    # Drop legacy index if it exists
    try:
        await db.customer_profiles.drop_index("identifier_1")
    except Exception:
        pass

    # Ensure the configured administrator exists without deleting other users.
    admin_email = _normalize_email(os.environ.get("ADMIN_EMAIL", ""))
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if admin_email and admin_password:
        existing = await db.users.find_one({"email": admin_email})
        if existing is None:
            await db.users.insert_one({
                "email": admin_email,
                "password_hash": hash_password(admin_password),
                "name": "Administrateur",
                "role": "admin",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            # Always keep password in sync with env + force role=admin
            await db.users.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "password_hash": hash_password(admin_password),
                    "role": "admin",
                }},
            )

    # Clear old password reset tokens collection (no longer used)
    try:
        await db.password_reset_tokens.drop()
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
