from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class OwnerPaymentConfig(Base):
    __tablename__ = "owner_payment_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_owner_payment_config_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    upi_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    payee_name: Mapped[str] = mapped_column(String(60), default="KISAN-X", nullable=False)
    qr_image_path: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, default=utc_epoch, nullable=False)


class SubscriptionTier(Base):
    __tablename__ = "subscription_tiers"
    __table_args__ = (CheckConstraint("price_inr >= 0", name="ck_tier_nonnegative_price"),
                      CheckConstraint("duration_days > 0", name="ck_tier_positive_duration"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tier_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    price_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    badge_color: Mapped[str] = mapped_column(String(16), default="#74847e", nullable=False)
    features_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PaymentClaim(Base):
    __tablename__ = "payment_claims"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_payment_claim_status"),
        Index("idx_claims_phone_created", "farmer_phone", "created_at"),
        Index("idx_claims_utr_open", "utr_number", unique=True,
              sqlite_where=text("status IN ('PENDING','APPROVED')"),
              postgresql_where=text("status IN ('PENDING','APPROVED')")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farmer_name: Mapped[str] = mapped_column(String(80), nullable=False)
    farmer_phone: Mapped[str] = mapped_column(String(10), nullable=False)
    tier_code: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    utr_number: Mapped[str] = mapped_column(String(22), nullable=False)
    screenshot_path: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="PENDING", nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, default=utc_epoch, nullable=False)
    verified_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ActiveSubscription(Base):
    __tablename__ = "active_subscriptions"

    farmer_phone: Mapped[str] = mapped_column(String(10), primary_key=True)
    farmer_name: Mapped[str] = mapped_column(String(80), nullable=False)
    tier_code: Mapped[str] = mapped_column(String(40), nullable=False)
    activated_at: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
