"""Create KISAN X farm and decision report tables.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "farms",
        sa.Column("farm_id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("region", sa.String(length=160), nullable=True),
        sa.Column("season", sa.String(length=100), nullable=True),
        sa.Column("area_value", sa.Float(), nullable=True),
        sa.Column("area_unit", sa.String(length=20), nullable=False),
        sa.Column("crop_history", sa.JSON(), nullable=False),
        sa.Column("irrigation", sa.String(length=100), nullable=True),
        sa.Column("soil_fields", sa.JSON(), nullable=False),
        sa.Column("priorities", sa.JSON(), nullable=False),
        sa.Column("geometry_geojson", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "decision_reports",
        sa.Column("report_id", sa.String(length=36), primary_key=True),
        sa.Column("farm_id", sa.String(length=36), sa.ForeignKey("farms.farm_id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_type", sa.String(length=40), nullable=False),
        sa.Column("rulebook_version", sa.String(length=80), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("decision_reports")
    op.drop_table("farms")
