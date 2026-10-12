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
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import bcrypt
import jwt
from bson import ObjectId
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
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
        return {
            "id": str(entity["_id"]),
            "email": entity.get("email", ""),
            "phone": entity.get("phone", ""),
            "name": entity.get("name", "") or "Non renseigné",
            "iban_masked": mask_iban_from_last4(entity.get("iban_last4", "")),
            "has_iban": bool(entity.get("iban_last4")),
            "bic": entity.get("bic", ""),
            "bank_name": entity.get("bank_name", ""),
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
    name: str = Field("", max_length=120)
    iban_last4: Optional[str] = ""
    bic: Optional[str] = ""
    bank_name: Optional[str] = Field("", max_length=120)


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
        "iban_last4": doc.get("iban_last4", ""),
        "bic": doc.get("bic", ""),
        "bank_name": doc.get("bank_name", ""),
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
async def admin_list_profiles(_: dict = Depends(get_admin_user)):
    docs = await db.customer_profiles.find({}).sort("name", 1).to_list(5000)
    return {"profiles": [_profile_to_public(d) for d in docs]}


@api_router.post("/admin/profiles")
async def admin_create_profile(payload: ProfileAdminInput, _: dict = Depends(get_admin_user)):
    email = _normalize_email(payload.email or "")
    phone = _normalize_phone(payload.phone or "")
    name = (payload.name or "").strip()
    last4 = _validate_last4(payload.iban_last4 or "")
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
        "name": name,
        "iban_last4": last4,
        "bic": bic,
        "bank_name": bank_name,
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
    last4 = _validate_last4(payload.iban_last4 or "")
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
        "name": name,
        "iban_last4": last4,
        "bic": bic,
        "bank_name": bank_name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.customer_profiles.update_one({"_id": oid}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profil introuvable.")
    doc = await db.customer_profiles.find_one({"_id": oid})
    return {"profile": _profile_to_public(doc)}


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


# ---------- bulk import ----------
_HEADER_KEYS = {
    "email": {"email", "e-mail", "mail", "adresse", "adresseemail", "courriel"},
    "phone": {"phone", "tel", "telephone", "téléphone", "mobile", "numero", "numéro"},
    "name": {"name", "nom", "prenom", "prénom", "nom prénom", "nomprénom", "titulaire",
             "fullname", "full_name"},
    "iban_last4": {"iban", "iban_last4", "iban4", "last4", "4chiffres", "chiffres"},
}


def _classify_header(h: str) -> Optional[str]:
    key = re.sub(r"[\s_\-]", "", (h or "").strip().lower())
    for field, aliases in _HEADER_KEYS.items():
        norm = {re.sub(r"[\s_\-]", "", a) for a in aliases}
        if key in norm:
            return field
    return None


def _parse_tokens_heuristic(tokens: List[str]) -> dict:
    """Classify a line's tokens without any header: email / phone / IBAN (full or 4 digits) /
    BIC / known bank name / everything else = name. A full IBAN (≥15 chars, 2 letters + digits)
    is reduced to its last 4 digits."""
    out = {"email": "", "phone": "", "name": "", "iban_last4": "", "bic": "", "bank_name": ""}
    leftover = []
    for raw in tokens:
        t = raw.strip().strip('"').strip("'")
        if not t:
            continue
        if not out["email"] and _looks_like_email(t):
            out["email"] = _normalize_email(t)
            continue
        if not out["iban_last4"]:
            compact = re.sub(r"\s", "", t)
            if re.fullmatch(r"[A-Za-z]{2}\d{2}[A-Za-z0-9]{11,30}", compact):
                digits = re.sub(r"\D", "", compact)
                if len(digits) >= 4:
                    out["iban_last4"] = digits[-4:]
                    continue
            if re.fullmatch(r"\d{4}", t):
                out["iban_last4"] = t
                continue
        if not out["bic"] and _looks_like_bic(t):
            out["bic"] = _normalize_bic(t)
            continue
        if not out["phone"] and _looks_like_phone(t) and not re.search(r"[A-Za-z]", t):
            out["phone"] = _normalize_phone(t)
            continue
        leftover.append(t)
    # Try to detect bank name in the leftover tokens (joined)
    leftover_text = " ".join(leftover).strip()
    bank = _match_bank_name(leftover_text)
    if bank and not out["bank_name"]:
        out["bank_name"] = bank
        # Remove the matched bank name tokens from the leftover for the holder name
        low = leftover_text.lower()
        bank_low = bank.lower()
        if bank_low in low:
            start = low.index(bank_low)
            leftover_text = (leftover_text[:start] + leftover_text[start + len(bank):]).strip()
        else:
            for key in _KNOWN_BANKS:
                if key in low:
                    start = low.index(key)
                    leftover_text = (leftover_text[:start] + leftover_text[start + len(key):]).strip()
                    break
    out["name"] = re.sub(r"\s+", " ", leftover_text).strip()
    return out


_EMAIL_RE = re.compile(r"[^@\s,;|\t]+@[^@\s,;|\t]+\.[^@\s,;|\t]+")
_IBAN_RE = re.compile(
    r"\b([A-Z]{2}\d{2}(?:[\s]?[A-Z0-9]{2,4}){4,8})\b", re.IGNORECASE
)


def _extract_patterns(line: str):
    """Find and strip email + full IBAN from a raw line; return (email, iban_last4, remaining)."""
    email = ""
    iban_last4 = ""
    remaining = line

    m = _EMAIL_RE.search(remaining)
    if m:
        email = _normalize_email(m.group(0))
        remaining = (remaining[: m.start()] + " " + remaining[m.end():]).strip()

    m = _IBAN_RE.search(remaining)
    if m:
        iban_raw = m.group(1)
        digits = re.sub(r"\D", "", iban_raw)
        if len(digits) >= 4:
            iban_last4 = digits[-4:]
            remaining = (remaining[: m.start()] + " " + remaining[m.end():]).strip()

    return email, iban_last4, remaining


def _split_line(line: str) -> List[str]:
    """Split a line using the best delimiter found on this specific line."""
    for d in [";", "\t", "|", ","]:
        if d in line:
            return [p.strip() for p in line.split(d) if p.strip()]
    # Fallback: whitespace splitting (collapses multiple spaces)
    return [p for p in re.split(r"\s{2,}|\s+", line) if p]


def _parse_line_full(line: str) -> dict:
    """Extract email + full IBAN first (preserving spaces inside IBAN), then classify
    the remaining tokens heuristically for phone / 4-digit / BIC / bank name / name."""
    email, iban_last4, remaining = _extract_patterns(line)
    tokens = _split_line(remaining) if remaining.strip() else []
    heuristic = _parse_tokens_heuristic(tokens)
    return {
        "email": email or heuristic["email"],
        "phone": heuristic["phone"],
        "name": heuristic["name"],
        "iban_last4": iban_last4 or heuristic["iban_last4"],
        "bic": heuristic.get("bic", ""),
        "bank_name": heuristic.get("bank_name", ""),
    }


def parse_import_text(text: str) -> List[dict]:
    """Parse any text (CSV / TSV / semicolon / pipe / whitespace) and return a list of profile dicts.
    Headers are detected and skipped if present. Each line is classified heuristically:
    emails are identified by their shape, phones by their digit sequences, 4-digit IBAN tokens by
    their literal form, and remaining tokens become the holder name. Any delimiter is accepted."""
    rows: List[dict] = []
    lines = [ln for ln in (text or "").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return rows

    # Skip header line if its tokens look like known field names.
    first_tokens = _split_line(lines[0])
    skip_header = False
    for tok in first_tokens:
        if _classify_header(tok):
            skip_header = True
            break
    start_idx = 1 if skip_header else 0

    for line in lines[start_idx:]:
        parsed = _parse_line_full(line)
        if parsed.get("email") or parsed.get("phone"):
            rows.append(parsed)
    return rows


async def _bulk_insert_profiles(parsed: List[dict]) -> dict:
    created, updated, errors = 0, 0, []
    for i, row in enumerate(parsed, start=1):
        email = row.get("email", "")
        phone = row.get("phone", "")
        name = row.get("name", "")
        last4 = row.get("iban_last4", "")
        bic = (row.get("bic", "") or "").upper()
        bank_name = row.get("bank_name", "")
        try:
            if email and not _looks_like_email(email):
                raise ValueError("Email invalide.")
            if last4 and (not last4.isdigit() or len(last4) != 4):
                raise ValueError("IBAN doit avoir exactement 4 chiffres.")
            if bic and not _looks_like_bic(bic):
                raise ValueError("BIC invalide.")
            if bic and not bank_name:
                bank_name = _bank_name_from_bic(bic)
            query_or = []
            if email:
                query_or.append({"email": email})
            if phone:
                query_or.append({"phone": phone})
            existing = None
            if query_or:
                existing = await db.customer_profiles.find_one({"$or": query_or})
            update = {
                "email": email,
                "phone": phone,
                "name": name,
                "iban_last4": last4,
                "bic": bic,
                "bank_name": bank_name,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if existing:
                await db.customer_profiles.update_one({"_id": existing["_id"]}, {"$set": update})
                updated += 1
            else:
                await db.customer_profiles.insert_one(update)
                created += 1
        except Exception as e:
            errors.append({"line": i, "data": row, "error": str(e)})
    return {"created": created, "updated": updated, "errors": errors, "total": len(parsed)}


@api_router.post("/admin/profiles/import")
async def admin_import_profiles(
    payload: Optional[ProfileImportInput] = None,
    _: dict = Depends(get_admin_user),
):
    text = (payload.text if payload else "") or ""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Fichier vide ou texte manquant.")
    parsed = parse_import_text(text)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Aucune ligne exploitable détectée (il faut au moins un email ou un téléphone par ligne).",
        )
    result = await _bulk_insert_profiles(parsed)
    return result


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
    if not text.strip():
        raise HTTPException(status_code=400, detail="Fichier vide.")
    parsed = parse_import_text(text)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Aucune ligne exploitable détectée (il faut au moins un email ou un téléphone par ligne).",
        )
    result = await _bulk_insert_profiles(parsed)
    return result


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
                await db.payment_transactions.update_one(
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
        await db.payment_transactions.update_one(
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


@app.on_event("startup")
async def startup():
    # Ensure indexes
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    # customer_profiles: partial unique indexes so empty/missing values don't collide
    await db.customer_profiles.create_index(
        "email", unique=True, partialFilterExpression={"email": {"$gt": ""}}
    )
    await db.customer_profiles.create_index(
        "phone", unique=True, partialFilterExpression={"phone": {"$gt": ""}}
    )
    # Drop legacy index if it exists
    try:
        await db.customer_profiles.drop_index("identifier_1")
    except Exception:
        pass

    # Purge legacy non-admin users (previous auth model)
    admin_email = _normalize_email(os.environ.get("ADMIN_EMAIL", ""))
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if admin_email and admin_password:
        # Delete every user that is NOT the current admin email
        await db.users.delete_many({"email": {"$ne": admin_email}})
        # Also drop any old legacy admin by role but wrong email
        await db.users.delete_many({"role": "admin", "email": {"$ne": admin_email}})

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
