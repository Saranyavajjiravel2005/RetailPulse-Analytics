"""add data quality tables

Revision ID: b7f8a9023456
Revises: a09e3c7b8b5e
Create Date: 2026-10-29 07:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7f8a9023456'
down_revision: Union[str, None] = 'a09e3c7b8b5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dataqualityissuetype = postgresql.ENUM(
        'SALE_EXCEEDS_STOCK', 'INVENTORY_INCONSISTENT_WITH_MOVEMENTS',
        'SALE_INACTIVE_OR_MISSING_PRODUCT', 'SALE_INVALID_CUSTOMER',
        'DUPLICATE_OR_INVALID_PRODUCT_SKU', 'MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO',
        'STOCK_MOVEMENT_INCONSISTENT', 'REPORT_TOTAL_MISMATCH', 'OTHER',
        name='dataqualityissuetype',
        create_type=False,
    )
    dataqualityissuetype.create(op.get_bind(), checkfirst=True)

    dataqualityseverity = postgresql.ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='dataqualityseverity', create_type=False)
    dataqualityseverity.create(op.get_bind(), checkfirst=True)

    dataqualityissuestatus = postgresql.ENUM('OPEN', 'INVESTIGATING', 'RESOLVED', 'IGNORED', name='dataqualityissuestatus', create_type=False)
    dataqualityissuestatus.create(op.get_bind(), checkfirst=True)

    reconciliationstatus = postgresql.ENUM('RUNNING', 'COMPLETED', 'COMPLETED_WITH_ISSUES', 'FAILED', name='reconciliationstatus', create_type=False)
    reconciliationstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'reconciliation_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('execution_id', sa.String(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('triggered_by', sa.UUID(), nullable=True),
        sa.Column('triggered_by_name', sa.String(), nullable=True),
        sa.Column('records_checked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('issues_detected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('issues_resolved', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_checks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', postgresql.ENUM('RUNNING', 'COMPLETED', 'COMPLETED_WITH_ISSUES', 'FAILED', name='reconciliationstatus', create_type=False), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('summary', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['triggered_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('execution_id')
    )
    op.create_index(op.f('ix_reconciliation_runs_company_id'), 'reconciliation_runs', ['company_id'], unique=False)
    op.create_index(op.f('ix_reconciliation_runs_execution_id'), 'reconciliation_runs', ['execution_id'], unique=True)
    op.create_index(op.f('ix_reconciliation_runs_started_at'), 'reconciliation_runs', ['started_at'], unique=False)

    op.create_table(
        'data_quality_issues',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('issue_type', postgresql.ENUM('SALE_EXCEEDS_STOCK', 'INVENTORY_INCONSISTENT_WITH_MOVEMENTS', 'SALE_INACTIVE_OR_MISSING_PRODUCT', 'SALE_INVALID_CUSTOMER', 'DUPLICATE_OR_INVALID_PRODUCT_SKU', 'MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO', 'STOCK_MOVEMENT_INCONSISTENT', 'REPORT_TOTAL_MISMATCH', 'OTHER', name='dataqualityissuetype', create_type=False), nullable=False),
        sa.Column('severity', postgresql.ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='dataqualityseverity', create_type=False), nullable=False),
        sa.Column('affected_module', sa.String(), nullable=False),
        sa.Column('affected_record_id', sa.String(), nullable=True),
        sa.Column('affected_record_type', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('status', postgresql.ENUM('OPEN', 'INVESTIGATING', 'RESOLVED', 'IGNORED', name='dataqualityissuestatus', create_type=False), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=True),
        sa.Column('detected_by_run_id', sa.UUID(), nullable=True),
        sa.Column('resolved_by', sa.UUID(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('previous_status', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['detected_by_run_id'], ['reconciliation_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_data_quality_issues_company_id'), 'data_quality_issues', ['company_id'], unique=False)
    op.create_index(op.f('ix_data_quality_issues_issue_type'), 'data_quality_issues', ['issue_type'], unique=False)
    op.create_index(op.f('ix_data_quality_issues_severity'), 'data_quality_issues', ['severity'], unique=False)
    op.create_index(op.f('ix_data_quality_issues_affected_module'), 'data_quality_issues', ['affected_module'], unique=False)
    op.create_index(op.f('ix_data_quality_issues_status'), 'data_quality_issues', ['status'], unique=False)
    op.create_index(op.f('ix_data_quality_issues_detected_at'), 'data_quality_issues', ['detected_at'], unique=False)

    op.create_table(
        'data_quality_issue_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('issue_id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('previous_status', sa.String(), nullable=True),
        sa.Column('new_status', sa.String(), nullable=False),
        sa.Column('changed_by', sa.UUID(), nullable=True),
        sa.Column('changed_by_name', sa.String(), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('changed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['issue_id'], ['data_quality_issues.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_data_quality_issue_history_issue_id'), 'data_quality_issue_history', ['issue_id'], unique=False)
    op.create_index(op.f('ix_data_quality_issue_history_company_id'), 'data_quality_issue_history', ['company_id'], unique=False)
    op.create_index(op.f('ix_data_quality_issue_history_changed_at'), 'data_quality_issue_history', ['changed_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_data_quality_issue_history_changed_at'), table_name='data_quality_issue_history')
    op.drop_index(op.f('ix_data_quality_issue_history_company_id'), table_name='data_quality_issue_history')
    op.drop_index(op.f('ix_data_quality_issue_history_issue_id'), table_name='data_quality_issue_history')
    op.drop_table('data_quality_issue_history')
    op.drop_index(op.f('ix_data_quality_issues_detected_at'), table_name='data_quality_issues')
    op.drop_index(op.f('ix_data_quality_issues_status'), table_name='data_quality_issues')
    op.drop_index(op.f('ix_data_quality_issues_affected_module'), table_name='data_quality_issues')
    op.drop_index(op.f('ix_data_quality_issues_severity'), table_name='data_quality_issues')
    op.drop_index(op.f('ix_data_quality_issues_issue_type'), table_name='data_quality_issues')
    op.drop_index(op.f('ix_data_quality_issues_company_id'), table_name='data_quality_issues')
    op.drop_table('data_quality_issues')
    op.drop_index(op.f('ix_reconciliation_runs_started_at'), table_name='reconciliation_runs')
    op.drop_index(op.f('ix_reconciliation_runs_execution_id'), table_name='reconciliation_runs')
    op.drop_index(op.f('ix_reconciliation_runs_company_id'), table_name='reconciliation_runs')
    op.drop_table('reconciliation_runs')
    op.execute('DROP TYPE IF EXISTS reconciliationstatus')
    op.execute('DROP TYPE IF EXISTS dataqualityissuestatus')
    op.execute('DROP TYPE IF EXISTS dataqualityseverity')
    op.execute('DROP TYPE IF EXISTS dataqualityissuetype')
