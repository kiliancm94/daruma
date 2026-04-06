"""add output_format and output_destination to tasks

Revision ID: a1b2c3d4e5f6
Revises: 2af01557bde3
Create Date: 2026-04-03 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "2af01557bde3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("output_format", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("output_destination", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("output_destination")
        batch_op.drop_column("output_format")
