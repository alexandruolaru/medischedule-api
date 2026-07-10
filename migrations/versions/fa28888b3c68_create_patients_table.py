"""create patients table

Revision ID: fa28888b3c68
Revises: 
Create Date: 2026-07-10 12:00:16.109636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa28888b3c68'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_patients_id"),
        "patients",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_patients_email"),
        "patients",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_patients_email"),
        table_name="patients",
    )

    op.drop_index(
        op.f("ix_patients_id"),
        table_name="patients",
    )

    op.drop_table("patients")