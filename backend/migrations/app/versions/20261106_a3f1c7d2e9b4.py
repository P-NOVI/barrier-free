"""제보 리뷰 테이블

Revision ID: a3f1c7d2e9b4
Revises: 87aeb223281d
Create Date: 2026-11-06 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f1c7d2e9b4"
down_revision: str | Sequence[str] | None = "87aeb223281d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", "user_id"),
    )
    with op.batch_alter_table("report_reviews", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_report_reviews_report_id"), ["report_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_report_reviews_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("report_reviews", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_report_reviews_user_id"))
        batch_op.drop_index(batch_op.f("ix_report_reviews_report_id"))

    op.drop_table("report_reviews")
