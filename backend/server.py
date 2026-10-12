from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import logging
import re
import ipaddress
import secrets
import hmac
import asyncio
from zoneinfo import ZoneInfo
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
import httpx
from bson import ObjectId
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

JWT_ALGORITHM = "HS256"
MAX_FAILED = 5
LOCKOUT_MINUTES = 15

# ---------- email (Emergent managed Resend) ----------
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ["EMERGENT_EMAIL_KEY"]
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str) -> Optional[str]:
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    if EMAIL_REPLY_TO:
        payload["contact_email"] = EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=30) as http_client:
            resp = await http_client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        try:
            code = e.response.json().get("code", "")
        except ValueError:
            code = ""
        if code in ("insufficient_credits", "integration_disabled", "daily_limit_reached"):
            logger.warning(f"Email paused: {code} ({e.response.status_code})")
            raise HTTPException(status_code=503, detail="Email is temporarily unavailable")
        logger.error(f"Email send failed: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=502, detail="Failed to send email")
    except Exception as e:
        logger.error(f"Email send error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email")


def build_reset_email_html(reset_url: str) -> str:
    return (
        '<table role="presentation" width="100%" style="background:#eef3f7;padding:24px">'
        '<tr><td align="center">'
        '<table role="presentation" width="480" style="background:#ffffff;border-radius:16px;'
        'font-family:Arial,Helvetica,sans-serif">'
        '<tr><td style="padding:32px 32px 8px">'
        f'<p style="font-size:20px;font-weight:bold;color:#164194;margin:0">{escape(EMAIL_FROM_NAME)}</p>'
        '</td></tr>'
        '<tr><td style="padding:8px 32px">'
        '<h1 style="font-size:22px;color:#17334d;margin:0 0 12px">Réinitialisation de votre mot de passe</h1>'
        '<p style="font-size:15px;color:#5a6b7a;line-height:1.6;margin:0 0 20px">'
        'Vous avez demandé à réinitialiser votre mot de passe. Cliquez sur le bouton '
        'ci-dessous pour en choisir un nouveau. Ce lien expire dans 1 heure.</p>'
        f'<p style="margin:0 0 24px"><a href="{escape(reset_url)}" '
        'style="background:#c4521f;color:#ffffff;text-decoration:none;font-weight:bold;'
        'padding:14px 28px;border-radius:999px;display:inline-block;font-size:15px">'
        'Choisir un nouveau mot de passe</a></p>'
        '<p style="font-size:13px;color:#8a98a6;line-height:1.5;margin:0">'
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail. "
        'Nous ne vous demanderons jamais votre mot de passe par e-mail.</p>'
        '</td></tr>'
        '<tr><td style="padding:24px 32px;border-top:1px solid #eef3f7">'
        f'<p style="font-size:12px;color:#8a98a6;margin:0">Envoyé par {escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table></td></tr></table>'
    )


def build_welcome_email_html() -> str:
    login_url = f"{FRONTEND_URL}/"
    return (
        '<table role="presentation" width="100%" style="background:#eef3f7;padding:24px">'
        '<tr><td align="center">'
        '<table role="presentation" width="480" style="background:#ffffff;border-radius:16px;'
        'font-family:Arial,Helvetica,sans-serif">'
        '<tr><td style="padding:32px 32px 8px">'
        f'<p style="font-size:20px;font-weight:bold;color:#164194;margin:0">{escape(EMAIL_FROM_NAME)}</p>'
        '</td></tr>'
        '<tr><td style="padding:8px 32px">'
        '<h1 style="font-size:22px;color:#17334d;margin:0 0 12px">Bienvenue sur votre espace client</h1>'
        '<p style="font-size:15px;color:#5a6b7a;line-height:1.6;margin:0 0 20px">'
        'Votre compte a bien été créé. Vous pouvez dès maintenant vous connecter pour gérer '
        'vos offres, vos factures et vos abonnements.</p>'
        f'<p style="margin:0 0 24px"><a href="{escape(login_url)}" '
        'style="background:#c4521f;color:#ffffff;text-decoration:none;font-weight:bold;'
        'padding:14px 28px;border-radius:999px;display:inline-block;font-size:15px">'
        'Accéder à mon espace client</a></p>'
        '<p style="font-size:13px;color:#8a98a6;line-height:1.5;margin:0">'
        'Nous ne vous demanderons jamais votre mot de passe par e-mail.</p>'
        '</td></tr>'
        '<tr><td style="padding:24px 32px;border-top:1px solid #eef3f7">'
        f'<p style="font-size:12px;color:#8a98a6;margin:0">Envoyé par {escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table></td></tr></table>'
    )


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


def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=15), "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id,
               "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, access: str, refresh: str):
    response.set_cookie(key="access_token", value=access, httponly=True, secure=True,
                        samesite="none", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")


def mask_iban(iban: str) -> str:
    if not iban:
        return ""
    s = iban.replace(" ", "")
    if len(s) <= 4:
        return "•••• " + s
    return "•••• •••• •••• " + s[-4:]


def mask_iban_from_last4(last4: str) -> str:
    s = (last4 or "").strip()
    if not s:
        return ""
    return "•••• •••• •••• " + s[-4:]


async def public_user(user: dict) -> dict:
    # Admin-managed overlay: lookup by email (lowercased); fall back to user record.
    email = (user.get("email") or "").strip().lower()
    profile = None
    if email:
        profile = await db.customer_profiles.find_one({"identifier": email})
    # Also allow a phone-based identifier later if the user stored one.
    phone = (user.get("phone") or "").strip()
    if not profile and phone:
        profile = await db.customer_profiles.find_one({"identifier": phone})

    name_from_profile = (profile or {}).get("name", "").strip()
    iban_last4 = ((profile or {}).get("iban_last4") or "").strip()

    display_name = name_from_profile or (
        " ".join([user.get("prenom", ""), user.get("nom", "")]).strip()
        or user.get("name", "")
    )
    iban_masked = (
        mask_iban_from_last4(iban_last4)
        if iban_last4
        else mask_iban(user.get("iban", ""))
    )
    has_iban = bool(iban_last4) or bool(user.get("iban"))

    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": display_name,
        "nom": user.get("nom", ""),
        "prenom": user.get("prenom", ""),
        "iban_masked": iban_masked,
        "has_iban": has_iban,
        "role": user.get("role", "user"),
        "managed_by_admin": bool(profile),
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
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="Utilisateur introuvable")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Jeton invalide")


# ---------- models ----------
class RegisterInput(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    name: Optional[str] = ""


class LoginInput(BaseModel):
    email: str
    password: str


class ForgotPasswordInput(BaseModel):
    email: str


class ResetPasswordInput(BaseModel):
    token: str
    password: str = Field(..., min_length=6)


class CancelInput(BaseModel):
    reason: str
    feedback: Optional[str] = ""


class ProfileInput(BaseModel):
    nom: Optional[str] = ""
    prenom: Optional[str] = ""
    iban: Optional[str] = ""


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


# ---------- routes ----------
@api_router.get("/")
async def root():
    return {"message": "Bouygues clone API"}


@api_router.post("/auth/register")
async def register(payload: RegisterInput, response: Response):
    email = payload.email.strip().lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Un compte existe déjà avec cet identifiant.")
    doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name or "",
        "role": "user",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    access = create_access_token(str(result.inserted_id), email)
    refresh = create_refresh_token(str(result.inserted_id))
    set_auth_cookies(response, access, refresh)
    if "@" in email:
        try:
            await send_email(
                to=email,
                subject="Bienvenue sur votre espace client",
                html=build_welcome_email_html(),
            )
        except HTTPException as e:
            logger.warning(f"Welcome email not delivered: {e.detail}")
    return {"message": "Compte créé avec succès", "user": await public_user(doc)}


@api_router.post("/auth/login")
async def login(payload: LoginInput, request: Request, response: Response):
    email = payload.email.strip().lower()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    await check_lockout(identifier)

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await record_failure(identifier)
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect.")

    await clear_failures(identifier)
    access = create_access_token(str(user["_id"]), email)
    refresh = create_refresh_token(str(user["_id"]))
    set_auth_cookies(response, access, refresh)
    return {"message": "Connexion réussie", "user": await public_user(user)}


@api_router.post("/auth/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
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
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="Utilisateur introuvable")
        access = create_access_token(str(user["_id"]), user["email"])
        response.set_cookie(key="access_token", value=access, httponly=True, secure=True,
                            samesite="none", max_age=900, path="/")
        return {"message": "Jeton rafraîchi"}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Jeton invalide")


@api_router.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordInput):
    email = payload.email.strip().lower()
    user = await db.users.find_one({"email": email})
    # Always return success to avoid user enumeration
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "email": email,
            "token": token,
            "used": False,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        })
        reset_url = f"{FRONTEND_URL}/reset-password?token={token}"
        logger.info(f"Password reset link: {reset_url}")
        try:
            await send_email(
                to=email,
                subject=f"Réinitialisation de votre mot de passe — {EMAIL_FROM_NAME}",
                html=build_reset_email_html(reset_url),
            )
        except HTTPException as e:
            # Do not leak email delivery state to the caller; log for the owner.
            logger.warning(f"Reset email not delivered: {e.detail}")
    return {"message": "Si un compte existe, un lien de réinitialisation a été envoyé."}


@api_router.post("/auth/reset-password")
async def reset_password(payload: ResetPasswordInput):
    rec = await db.password_reset_tokens.find_one({"token": payload.token})
    if not rec or rec.get("used"):
        raise HTTPException(status_code=400, detail="Lien invalide ou déjà utilisé.")
    expires = rec.get("expires_at")
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and datetime.now(timezone.utc) > expires:
        raise HTTPException(status_code=400, detail="Ce lien a expiré. Veuillez refaire une demande.")
    await db.users.update_one(
        {"email": rec["email"]},
        {"$set": {"password_hash": hash_password(payload.password)}},
    )
    await db.password_reset_tokens.update_one(
        {"_id": rec["_id"]}, {"$set": {"used": True}}
    )
    return {"message": "Votre mot de passe a été réinitialisé avec succès."}


@api_router.get("/subscription/canal")
async def canal_status(user: dict = Depends(get_current_user)):
    rec = await db.cancellations.find_one({"user_id": str(user["_id"]), "service": "canal"})
    return {
        "service": "CANAL+",
        "offer": "CANAL+ Ciné Séries",
        "price": "69,99 €/mois",
        "since": "12 mars 2023",
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
        "email": user["email"],
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


@api_router.put("/profile")
async def update_profile(payload: ProfileInput, user: dict = Depends(get_current_user)):
    updates = {}
    if payload.nom is not None:
        updates["nom"] = payload.nom.strip()
    if payload.prenom is not None:
        updates["prenom"] = payload.prenom.strip()
    if payload.iban is not None:
        updates["iban"] = payload.iban.replace(" ", "").upper()
    if updates:
        await db.users.update_one({"_id": user["_id"]}, {"$set": updates})
    u = await db.users.find_one({"_id": user["_id"]})
    return {"user": await public_user(u)}


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


def _check_cron_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    if not token or not secret or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _run_prelevements(day_iso: str):
    users = await db.users.find({}).to_list(10000)
    for u in users:
        exists = await db.prelevements.find_one({"user_id": str(u["_id"]), "date": day_iso})
        if not exists:
            await db.prelevements.insert_one({
                "user_id": str(u["_id"]),
                "amount": 69.99,
                "label": "CANAL+ Ciné Séries",
                "date": day_iso,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })


@api_router.post("/cron/prelevements")
async def cron_prelevements(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _check_cron_auth(request)
    day_iso = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d")
    asyncio.create_task(_run_prelevements(day_iso))
    return {"status": "accepted"}


# ---------- admin: customer profiles mapping ----------
class ProfileAdminInput(BaseModel):
    identifier: str = Field(..., min_length=3)
    name: str = Field("", max_length=120)
    iban_last4: str = Field("", max_length=4)


async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    return user


def _normalize_identifier(raw: str) -> str:
    s = (raw or "").strip()
    if "@" in s:
        return s.lower()
    # phone: keep digits and + only
    return re.sub(r"[^\d+]", "", s)


def _validate_last4(raw: str) -> str:
    s = re.sub(r"\D", "", raw or "")
    if s and len(s) != 4:
        raise HTTPException(
            status_code=400,
            detail="Les 4 derniers chiffres de l'IBAN doivent contenir exactement 4 chiffres.",
        )
    return s


def _profile_to_public(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "identifier": doc.get("identifier", ""),
        "name": doc.get("name", ""),
        "iban_last4": doc.get("iban_last4", ""),
        "updated_at": doc.get("updated_at", ""),
    }


@api_router.get("/admin/profiles")
async def admin_list_profiles(_: dict = Depends(get_admin_user)):
    docs = await db.customer_profiles.find({}).sort("identifier", 1).to_list(2000)
    return {"profiles": [_profile_to_public(d) for d in docs]}


@api_router.post("/admin/profiles")
async def admin_create_profile(payload: ProfileAdminInput, _: dict = Depends(get_admin_user)):
    identifier = _normalize_identifier(payload.identifier)
    if not identifier:
        raise HTTPException(status_code=400, detail="Identifiant invalide.")
    last4 = _validate_last4(payload.iban_last4)
    existing = await db.customer_profiles.find_one({"identifier": identifier})
    if existing:
        raise HTTPException(status_code=400, detail="Un profil existe déjà avec cet identifiant.")
    doc = {
        "identifier": identifier,
        "name": (payload.name or "").strip(),
        "iban_last4": last4,
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
    identifier = _normalize_identifier(payload.identifier)
    if not identifier:
        raise HTTPException(status_code=400, detail="Identifiant invalide.")
    last4 = _validate_last4(payload.iban_last4)
    clash = await db.customer_profiles.find_one(
        {"identifier": identifier, "_id": {"$ne": oid}}
    )
    if clash:
        raise HTTPException(status_code=400, detail="Un autre profil utilise déjà cet identifiant.")
    updates = {
        "identifier": identifier,
        "name": (payload.name or "").strip(),
        "iban_last4": last4,
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


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000"),
                   "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier")
    await db.customer_profiles.create_index("identifier", unique=True)
    # seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email},
                                  {"$set": {"password_hash": hash_password(admin_password)}})


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
