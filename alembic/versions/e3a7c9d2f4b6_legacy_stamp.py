"""legacy stamped baseline

Revision ID: e3a7c9d2f4b6
Revises:
Create Date: 2026-05-21 08:30:00

Existing installer builds stamped databases with this revision before the
version file existed in source control. Keep it as a no-op anchor so Alembic can
resolve those installations and upgrade them to the managed baseline.
"""

revision = "e3a7c9d2f4b6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
