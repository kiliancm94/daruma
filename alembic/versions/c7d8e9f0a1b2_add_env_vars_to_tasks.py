"""add env_vars to tasks

Revision ID: c7d8e9f0a1b2
Revises: b623e165a31e
Create Date: 2026-04-06 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b623e165a31e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable env_vars column to tasks table."""
    op.add_column("tasks", sa.Column("env_vars", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove env_vars column from tasks table."""
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("env_vars")
