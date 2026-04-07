"""add pipelines

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-04-06 21:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create pipeline tables and add pipeline_run_id FK to runs."""
    op.create_table(
        "pipelines",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("pipeline_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pipeline_id", "step_order", name="uq_pipeline_step_order"),
    )
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("pipeline_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("finished_at", sa.String(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("runs", sa.Column("pipeline_run_id", sa.String(), nullable=True))
    with op.batch_alter_table("runs") as batch_op:
        batch_op.create_foreign_key(
            "fk_runs_pipeline_run_id",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )


def downgrade() -> None:
    """Remove pipeline tables and pipeline_run_id FK from runs."""
    with op.batch_alter_table("runs") as batch_op:
        batch_op.drop_constraint("fk_runs_pipeline_run_id", type_="foreignkey")
        batch_op.drop_column("pipeline_run_id")
    op.drop_table("pipeline_runs")
    op.drop_table("pipeline_steps")
    op.drop_table("pipelines")
