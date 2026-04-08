"""file-backed global skills

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-04-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate task_skills to use skill_name, drop source column from skills."""
    conn = op.get_bind()

    # --- Step 1: Rebuild task_skills with skill_name instead of skill_id ---

    # Create a new task_skills table with skill_name column
    op.create_table(
        "task_skills_new",
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("skill_name", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "skill_name"),
    )

    # Backfill skill_name from skills.name via join on skill_id = skills.id
    conn.execute(
        sa.text(
            "INSERT INTO task_skills_new (task_id, skill_name) "
            "SELECT ts.task_id, s.name "
            "FROM task_skills ts "
            "JOIN skills s ON ts.skill_id = s.id"
        )
    )

    # Drop old table and rename new one
    op.drop_table("task_skills")
    op.rename_table("task_skills_new", "task_skills")

    # --- Step 2: Delete global skills and rebuild skills without source column ---

    # Delete all global skills (they now live on the filesystem)
    conn.execute(sa.text("DELETE FROM skills WHERE source = 'global'"))

    # Recreate skills table without the source column
    op.create_table(
        "skills_new",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Copy remaining (local) skills to the new table
    conn.execute(
        sa.text(
            "INSERT INTO skills_new (id, name, description, content, created_at, updated_at) "
            "SELECT id, name, description, content, created_at, updated_at "
            "FROM skills"
        )
    )

    # Drop old table and rename
    op.drop_table("skills")
    op.rename_table("skills_new", "skills")


def downgrade() -> None:
    """Restore task_skills with skill_id FK and add source column back to skills."""
    conn = op.get_bind()

    # --- Step 1: Rebuild skills with source column ---

    op.create_table(
        "skills_new",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), server_default="local", nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Copy all skills back, setting source to 'local' (global ones were deleted)
    conn.execute(
        sa.text(
            "INSERT INTO skills_new (id, name, description, content, source, created_at, updated_at) "
            "SELECT id, name, description, content, 'local', created_at, updated_at "
            "FROM skills"
        )
    )

    op.drop_table("skills")
    op.rename_table("skills_new", "skills")

    # --- Step 2: Rebuild task_skills with skill_id FK ---

    op.create_table(
        "task_skills_new",
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "skill_id"),
    )

    # Backfill skill_id from skills.id via join on skill_name = skills.name
    # Only rows where the skill still exists in the skills table will be restored
    conn.execute(
        sa.text(
            "INSERT INTO task_skills_new (task_id, skill_id) "
            "SELECT ts.task_id, s.id "
            "FROM task_skills ts "
            "JOIN skills s ON ts.skill_name = s.name"
        )
    )

    op.drop_table("task_skills")
    op.rename_table("task_skills_new", "task_skills")
