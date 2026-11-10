"""enhance import bulk processing

Revision ID: c1f2a3b4c5d6
Revises: b7f8a9023456
Create Date: 2026-11-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f2a3b4c5d6'
down_revision: Union[str, None] = 'b7f8a9023456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add skipped_records column to import_history if not present
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    history_cols = [c['name'] for c in inspector.get_columns('import_history')]
    if 'skipped_records' not in history_cols:
        op.add_column('import_history', sa.Column('skipped_records', sa.Integer(), nullable=False, server_default='0'))

    # Add error_type column to import_errors if not present
    errors_cols = [c['name'] for c in inspector.get_columns('import_errors')]
    if 'error_type' not in errors_cols:
        op.add_column('import_errors', sa.Column('error_type', sa.String(), nullable=True, server_default='VALIDATION_ERROR'))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    history_cols = [c['name'] for c in inspector.get_columns('import_history')]
    if 'skipped_records' in history_cols:
        op.drop_column('import_history', 'skipped_records')

    errors_cols = [c['name'] for c in inspector.get_columns('import_errors')]
    if 'error_type' in errors_cols:
        op.drop_column('import_errors', 'error_type')
