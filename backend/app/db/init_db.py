import json

from sqlalchemy import select

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (  # noqa: F401 - imports register metadata
    ActiveSubscription, DecisionReport, Farm, OwnerPaymentConfig, PaymentClaim, SubscriptionTier,
)

DEFAULT_TIERS = [
    ("FREE", "Farmer Free", 0, 36500, "#74847e", [
        "Farm profiles and rotation comparisons", "NASA POWER historical climate context", "Essential workspace access",
    ]),
    ("KISAN_PRO", "KISAN-X Pro", 99, 30, "#2f7655", [
        "Pilot subscription; confirm included features with the owner before paying",
    ]),
    ("FPO_COOPERATIVE", "FPO / Institutional", 499, 30, "#477d9d", [
        "Pilot subscription; confirm included features with the owner before paying",
    ]),
]


def seed_payment_defaults() -> None:
    with SessionLocal() as db:
        if db.get(OwnerPaymentConfig, 1) is None:
            db.add(OwnerPaymentConfig(id=1))
        if db.scalar(select(SubscriptionTier.id).limit(1)) is None:
            db.add_all([
                SubscriptionTier(tier_code=code, name=name, price_inr=price, duration_days=days,
                                 badge_color=color, features_json=json.dumps(features), is_active=True)
                for code, name, price, days, color, features in DEFAULT_TIERS
            ])
        db.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    seed_payment_defaults()
