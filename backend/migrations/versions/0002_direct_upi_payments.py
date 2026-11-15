"""Add owner-managed direct UPI payments.

Revision ID: 0002_direct_upi_payments
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_direct_upi_payments"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "owner_payment_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("upi_id", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("payee_name", sa.String(length=60), nullable=False, server_default="KISAN-X"),
        sa.Column("qr_image_path", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("updated_at", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("id = 1", name="ck_owner_payment_config_singleton"),
    )
    op.create_table(
        "subscription_tiers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tier_code", sa.String(length=40), nullable=False, unique=True),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("price_inr", sa.Integer(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("badge_color", sa.String(length=16), nullable=False, server_default="#74847e"),
        sa.Column("features_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("price_inr >= 0", name="ck_tier_nonnegative_price"),
        sa.CheckConstraint("duration_days > 0", name="ck_tier_positive_duration"),
    )
    op.create_table(
        "payment_claims",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("farmer_name", sa.String(length=80), nullable=False),
        sa.Column("farmer_phone", sa.String(length=10), nullable=False),
        sa.Column("tier_code", sa.String(length=40), nullable=False),
        sa.Column("amount_inr", sa.Integer(), nullable=False),
        sa.Column("utr_number", sa.String(length=22), nullable=False),
        sa.Column("screenshot_path", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_payment_claim_status"),
    )
    op.create_index("idx_claims_phone_created", "payment_claims", ["farmer_phone", "created_at"])
    op.create_index(
        "idx_claims_utr_open", "payment_claims", ["utr_number"], unique=True,
        sqlite_where=sa.text("status IN ('PENDING','APPROVED')"),
        postgresql_where=sa.text("status IN ('PENDING','APPROVED')"),
    )
    op.create_table(
        "active_subscriptions",
        sa.Column("farmer_phone", sa.String(length=10), primary_key=True),
        sa.Column("farmer_name", sa.String(length=80), nullable=False),
        sa.Column("tier_code", sa.String(length=40), nullable=False),
        sa.Column("activated_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("active_subscriptions")
    op.drop_index("idx_claims_utr_open", table_name="payment_claims")
    op.drop_index("idx_claims_phone_created", table_name="payment_claims")
    op.drop_table("payment_claims")
    op.drop_table("subscription_tiers")
    op.drop_table("owner_payment_config")
