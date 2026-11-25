"""one lead or customer event counts once

Revision ID: 0002
Revises: 0001

Two identical webhooks at the same moment could both be stored on Postgres, because the check in the route cannot see the other request. A unique index makes the
database refuse the second one. Duplicates that already exist are removed first (the oldest of each is kept), so the index can be made.
"""
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM vp_conversion WHERE id NOT IN (SELECT MIN(id) FROM vp_conversion GROUP BY lead_ref, kind)")
    with op.batch_alter_table('vp_conversion', schema=None) as batch_op:
        batch_op.create_index('uq_vp_conversion_lead_kind', ['lead_ref', 'kind'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('vp_conversion', schema=None) as batch_op:
        batch_op.drop_index('uq_vp_conversion_lead_kind')
