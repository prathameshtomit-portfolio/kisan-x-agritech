"""Direct UPI checkout and owner-verified payment claims. No payment gateway is used."""
from __future__ import annotations

import hmac
import json
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.payments import ActiveSubscription, OwnerPaymentConfig, PaymentClaim, SubscriptionTier

router = APIRouter(tags=["direct UPI payments"])
DATA_DIR = Path(__file__).resolve().parents[4] / "data"
QR_DIR = DATA_DIR / "payment_uploads" / "qr"
PROOF_DIR = DATA_DIR / "payment_uploads" / "proofs"
QR_DIR.mkdir(parents=True, exist_ok=True)
PROOF_DIR.mkdir(parents=True, exist_ok=True)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PENDING_PER_PHONE = 3
PIN_MAX_FAILS = 5
PIN_LOCK_SECONDS = 300
UPI_ID_RE = re.compile(r"^[A-Za-z0-9._-]{2,64}@[A-Za-z][A-Za-z0-9]{1,31}$")
UTR_RE = re.compile(r"^[A-Z0-9]{10,22}$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")
_pin_failures: dict[str, list[float]] = {}


class PaymentStatusInput(BaseModel):
    farmer_phone: str = Field(min_length=10, max_length=16)
    utr_number: str = Field(min_length=10, max_length=22)


class TierUpdate(BaseModel):
    tier_code: str = Field(min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=60)
    price_inr: int | None = Field(default=None, ge=0, le=100000)
    features: list[str] | None = Field(default=None, max_length=12)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Plan name cannot be blank.")
        return value.strip() if value is not None else None


class VerifyInput(BaseModel):
    claim_id: int = Field(gt=0)
    decision: str = Field(pattern="^(APPROVE|REJECT)$")


def owner_guard(request: Request, x_owner_pin: str | None = Header(default=None, alias="X-Owner-Pin"),
                x_owner_email: str | None = Header(default=None, alias="X-Owner-Email")) -> None:
    expected = settings.owner_pin
    if len(expected) < 6:
        raise HTTPException(status_code=503, detail="Owner payment setup is incomplete. Configure KISANX_OWNER_PIN (6+ characters) in the private service environment.")
    client = request.client.host if request.client else "unknown"
    now = time.time()
    recent = [stamp for stamp in _pin_failures.get(client, []) if now - stamp < PIN_LOCK_SECONDS]
    if len(recent) >= PIN_MAX_FAILS:
        raise HTTPException(status_code=429, detail="Too many incorrect PIN attempts. Try again in a few minutes.")
    expected_email = settings.owner_email.strip().casefold()
    supplied_email = (x_owner_email or "").strip().casefold()
    email_ok = bool(supplied_email) and hmac.compare_digest(supplied_email.encode(), expected_email.encode())
    if not email_ok or not x_owner_pin or not hmac.compare_digest(x_owner_pin.encode(), expected.encode()):
        recent.append(now)
        if len(_pin_failures) > 1000:
            _pin_failures.clear()
        _pin_failures[client] = recent
        raise HTTPException(status_code=401, detail="Owner email or PIN is invalid.")
    _pin_failures.pop(client, None)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not PHONE_RE.fullmatch(digits):
        raise HTTPException(status_code=422, detail="Enter a valid 10-digit Indian mobile number.")
    return digits


def image_extension(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


async def read_image(upload: UploadFile | None, label: str) -> tuple[bytes, str] | None:
    if upload is None or not upload.filename:
        return None
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if not data:
        return None
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"{label} is larger than 5 MB.")
    extension = image_extension(data)
    if extension is None:
        raise HTTPException(status_code=415, detail=f"{label} must be a PNG, JPEG or WebP image.")
    return data, extension


def file_in(directory: Path, stored_name: str) -> Path | None:
    if not stored_name:
        return None
    candidate = directory / Path(stored_name).name
    return candidate if candidate.is_file() else None


def tier_payload(tier: SubscriptionTier) -> dict:
    try:
        features = json.loads(tier.features_json or "[]")
    except json.JSONDecodeError:
        features = []
    return {"tier_code": tier.tier_code, "name": tier.name, "price_inr": tier.price_inr,
            "duration_days": tier.duration_days, "badge_color": tier.badge_color,
            "features": features, "is_active": tier.is_active}


def claim_payload(claim: PaymentClaim, owner: bool) -> dict:
    result = {"id": claim.id, "tier_code": claim.tier_code, "amount_inr": claim.amount_inr,
              "status": claim.status, "created_at": claim.created_at, "verified_at": claim.verified_at}
    if owner:
        result.update({"farmer_name": claim.farmer_name, "farmer_phone": claim.farmer_phone,
                       "utr_number": claim.utr_number, "has_proof": bool(claim.screenshot_path)})
    return result


def ensure_owner_config(db: Session) -> OwnerPaymentConfig:
    config = db.get(OwnerPaymentConfig, 1)
    if config is None:
        config = OwnerPaymentConfig(id=1)
        db.add(config)
        db.flush()
    return config


@router.get("/pay/public-config")
def public_config(db: Session = Depends(get_db)) -> dict:
    config = ensure_owner_config(db)
    tiers = db.scalars(select(SubscriptionTier).where(SubscriptionTier.is_active.is_(True)).order_by(SubscriptionTier.price_inr, SubscriptionTier.id)).all()
    qr_ready = file_in(QR_DIR, config.qr_image_path) is not None
    claims_enabled = settings.enable_public_payment_claims
    return {"payments_ready": claims_enabled and bool(config.upi_id), "payment_claims_enabled": claims_enabled,
            "upi_id": config.upi_id if claims_enabled else "", "payee_name": config.payee_name if claims_enabled else "",
            "qr_image_url": f"/api/v1/pay/qr?v={config.updated_at}" if claims_enabled and qr_ready else None,
            "tiers": [tier_payload(tier) for tier in tiers]}


@router.get("/pay/qr")
def qr_image(db: Session = Depends(get_db)) -> FileResponse:
    if not settings.enable_public_payment_claims:
        raise HTTPException(status_code=404, detail="Payment QR is not available on this demo deployment.")
    config = ensure_owner_config(db)
    path = file_in(QR_DIR, config.qr_image_path)
    if path is None:
        raise HTTPException(status_code=404, detail="No QR code has been uploaded yet.")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.post("/pay/submit-claim")
async def submit_claim(
    farmer_name: str = Form(...), farmer_phone: str = Form(...), tier_code: str = Form(...),
    utr_number: str = Form(...), screenshot: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if not settings.enable_public_payment_claims:
        raise HTTPException(status_code=503, detail="Payment claims are disabled on this demo deployment.")
    name = farmer_name.strip()
    if not 2 <= len(name) <= 80:
        raise HTTPException(status_code=422, detail="Enter your name (2–80 characters).")
    phone = normalize_phone(farmer_phone)
    utr = re.sub(r"\s+", "", utr_number).upper()
    if not UTR_RE.fullmatch(utr):
        raise HTTPException(status_code=422, detail="UTR / UPI reference should be 10–22 letters or digits.")
    image = await read_image(screenshot, "Screenshot")
    stored_name = f"{uuid.uuid4().hex}{image[1]}" if image else ""
    if image:
        (PROOF_DIR / stored_name).write_bytes(image[0])
    try:
        tier = db.scalar(select(SubscriptionTier).where(SubscriptionTier.tier_code == tier_code, SubscriptionTier.is_active.is_(True)))
        if tier is None or tier.price_inr <= 0:
            raise HTTPException(status_code=400, detail="Choose an available paid plan.")
        pending = db.scalar(select(func.count()).select_from(PaymentClaim).where(PaymentClaim.farmer_phone == phone, PaymentClaim.status == "PENDING")) or 0
        if pending >= MAX_PENDING_PER_PHONE:
            raise HTTPException(status_code=429, detail="You already have payment proofs waiting for verification. Please wait for the owner to review them.")
        claim = PaymentClaim(farmer_name=name, farmer_phone=phone, tier_code=tier_code,
                             amount_inr=tier.price_inr, utr_number=utr, screenshot_path=stored_name,
                             status="PENDING", created_at=int(time.time()))
        db.add(claim)
        db.commit()
        db.refresh(claim)
        return {"ok": True, "claim_id": claim.id, "status": claim.status}
    except IntegrityError as exc:
        db.rollback()
        if stored_name:
            (PROOF_DIR / stored_name).unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="This UTR has already been submitted.") from exc
    except Exception:
        db.rollback()
        if stored_name:
            (PROOF_DIR / stored_name).unlink(missing_ok=True)
        raise


@router.post("/pay/status")
def payment_status(payload: PaymentStatusInput, db: Session = Depends(get_db)) -> dict:
    if not settings.enable_public_payment_claims:
        raise HTTPException(status_code=503, detail="Payment status is disabled on this demo deployment.")
    phone = normalize_phone(payload.farmer_phone)
    utr = re.sub(r"\s+", "", payload.utr_number).upper()
    if not UTR_RE.fullmatch(utr):
        raise HTTPException(status_code=422, detail="Enter the UPI reference / UTR from your payment receipt.")
    claim = db.scalar(select(PaymentClaim).where(
        PaymentClaim.farmer_phone == phone, PaymentClaim.utr_number == utr
    ))
    return {"claim": claim_payload(claim, owner=False) if claim else None}


@router.get("/owner/dashboard", dependencies=[Depends(owner_guard)])
def owner_dashboard(db: Session = Depends(get_db)) -> dict:
    now = int(time.time())
    total = db.scalar(select(func.coalesce(func.sum(PaymentClaim.amount_inr), 0)).where(PaymentClaim.status == "APPROVED")) or 0
    pending = db.scalar(select(func.count()).select_from(PaymentClaim).where(PaymentClaim.status == "PENDING")) or 0
    active = db.scalar(select(func.count()).select_from(ActiveSubscription).where(ActiveSubscription.expires_at > now)) or 0
    claims = db.scalars(select(PaymentClaim).order_by(PaymentClaim.created_at.desc(), PaymentClaim.id.desc()).limit(200)).all()
    config = ensure_owner_config(db)
    tiers = db.scalars(select(SubscriptionTier).order_by(SubscriptionTier.price_inr, SubscriptionTier.id)).all()
    qr_ready = file_in(QR_DIR, config.qr_image_path) is not None
    return {"total_revenue_inr": total, "pending_count": pending, "active_paid_farmers": active,
            "claims": [claim_payload(claim, owner=True) for claim in claims],
            "settings": {"upi_id": config.upi_id, "payee_name": config.payee_name,
                         "qr_image_url": f"/api/v1/pay/qr?v={config.updated_at}" if qr_ready else None},
            "tiers": [tier_payload(tier) for tier in tiers]}


@router.post("/owner/verify-claim", dependencies=[Depends(owner_guard)])
def verify_claim(payload: VerifyInput, db: Session = Depends(get_db)) -> dict:
    claim = db.get(PaymentClaim, payload.claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found.")
    now = int(time.time())
    status = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
    changed = db.execute(update(PaymentClaim).where(PaymentClaim.id == payload.claim_id, PaymentClaim.status == "PENDING")
                         .values(status=status, verified_at=now)).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Claim is already {claim.status}.")
    if status == "APPROVED":
        tier = db.scalar(select(SubscriptionTier).where(SubscriptionTier.tier_code == claim.tier_code))
        days = tier.duration_days if tier else 30
        existing = db.get(ActiveSubscription, claim.farmer_phone)
        start = existing.expires_at if existing and existing.tier_code == claim.tier_code and existing.expires_at > now else now
        if existing is None:
            existing = ActiveSubscription(farmer_phone=claim.farmer_phone, farmer_name=claim.farmer_name,
                                          tier_code=claim.tier_code, activated_at=now, expires_at=start + days * 86400)
            db.add(existing)
        else:
            existing.farmer_name = claim.farmer_name
            existing.tier_code = claim.tier_code
            existing.activated_at = now
            existing.expires_at = start + days * 86400
    db.commit()
    return {"ok": True, "claim_id": payload.claim_id, "status": status}


@router.get("/owner/claims/{claim_id}/proof", dependencies=[Depends(owner_guard)])
def claim_proof(claim_id: int, db: Session = Depends(get_db)) -> FileResponse:
    claim = db.get(PaymentClaim, claim_id)
    path = file_in(PROOF_DIR, claim.screenshot_path) if claim else None
    if path is None:
        raise HTTPException(status_code=404, detail="No proof image for this claim.")
    return FileResponse(path, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/owner/update-settings", dependencies=[Depends(owner_guard)])
async def update_settings(
    upi_id: str | None = Form(default=None), payee_name: str | None = Form(default=None),
    qr_image: UploadFile | None = File(default=None), tier_updates_json: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict:
    new_upi = upi_id.strip() if upi_id is not None else None
    if new_upi and not UPI_ID_RE.fullmatch(new_upi):
        raise HTTPException(status_code=422, detail="UPI ID looks invalid. It should look like name@bank.")
    new_payee = payee_name.strip() if payee_name is not None else None
    if new_payee is not None and not 1 <= len(new_payee) <= 60:
        raise HTTPException(status_code=422, detail="Payee name must be 1–60 characters.")
    try:
        updates = [TierUpdate.model_validate(item) for item in json.loads(tier_updates_json)] if tier_updates_json else []
    except (ValueError, TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="Plan details are invalid. Check names, prices and features.") from exc
    for item in updates:
        if item.tier_code == "FREE" and item.price_inr not in (None, 0):
            raise HTTPException(status_code=422, detail="The Free plan must stay at ₹0.")
        if item.tier_code == "FREE" and item.is_active is False:
            raise HTTPException(status_code=422, detail="The Free plan must remain available.")
    image = await read_image(qr_image, "QR image")
    new_qr_name = f"qr_{uuid.uuid4().hex}{image[1]}" if image else ""
    if image:
        (QR_DIR / new_qr_name).write_bytes(image[0])
    config = ensure_owner_config(db)
    previous_qr = config.qr_image_path if new_qr_name else ""
    try:
        if new_upi is not None:
            config.upi_id = new_upi
        if new_payee is not None:
            config.payee_name = new_payee
        if new_qr_name:
            config.qr_image_path = new_qr_name
        config.updated_at = int(time.time())
        for item in updates:
            tier = db.scalar(select(SubscriptionTier).where(SubscriptionTier.tier_code == item.tier_code))
            if tier is None:
                raise HTTPException(status_code=404, detail=f"Unknown plan {item.tier_code}.")
            if item.name is not None:
                tier.name = item.name.strip()
            if item.price_inr is not None:
                tier.price_inr = item.price_inr
            if item.features is not None:
                tier.features_json = json.dumps([value.strip()[:120] for value in item.features if value and value.strip()][:12])
            if item.is_active is not None:
                tier.is_active = item.is_active
        db.commit()
    except Exception:
        db.rollback()
        if new_qr_name:
            (QR_DIR / new_qr_name).unlink(missing_ok=True)
        raise
    if previous_qr:
        (QR_DIR / Path(previous_qr).name).unlink(missing_ok=True)
    return {"ok": True}
