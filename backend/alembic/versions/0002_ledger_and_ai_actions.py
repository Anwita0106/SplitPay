"""Settlement ledger fields, expense edit tracking, and AI action drafts.

Revision ID: 0002_ledger_ai
Revises: 0001_baseline
Create Date: 2026-09-20

Purely additive and data-preserving:
  * settlements.method           existing rows -> 'UPI' (they all came from the payment flow)
  * settlements.recorded_by      NULL for existing rows
  * settlements.idempotency_key  NULL for existing rows (partial unique index)
  * expenses.updated_at          backfilled from created_at
  * ai_actions                   new table (server-side AI drafts / audit trail)

Behavioural note (intentional): from this revision on, COMPLETED settlements
are netted into group balances. Balances for groups that already contain
completed settlements will therefore drop to the true outstanding amount.
"""
from alembic import op

revision = "0002_ledger_ai"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE settlements ADD COLUMN IF NOT EXISTS method VARCHAR(20) NOT NULL DEFAULT 'UPI'")
    op.execute(
        "ALTER TABLE settlements ADD COLUMN IF NOT EXISTS recorded_by UUID "
        "REFERENCES users(id) ON DELETE RESTRICT"
    )
    op.execute("ALTER TABLE settlements ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(120)")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'settlements_method_check') THEN
                ALTER TABLE settlements
                    ADD CONSTRAINT settlements_method_check CHECK (method IN ('UPI','MANUAL'));
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_settlements_idempotency_key "
        "ON settlements(idempotency_key) WHERE idempotency_key IS NOT NULL"
    )

    op.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    # Existing expenses have never been edited: their "last updated" is their creation time.
    op.execute("UPDATE expenses SET updated_at = created_at")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_actions (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            group_id     UUID REFERENCES groups(id) ON DELETE SET NULL,
            kind         VARCHAR(20) NOT NULL CHECK (kind IN ('EXPENSE','SETTLEMENT')),
            status       VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                             CHECK (status IN ('PENDING','CONFIRMED','CANCELLED','EXPIRED','FAILED')),
            payload      JSONB NOT NULL,
            result_id    UUID,
            error        TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at   TIMESTAMPTZ NOT NULL,
            resolved_at  TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_actions_user_created ON ai_actions(user_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_actions_group ON ai_actions(group_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_actions_status ON ai_actions(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_actions")
    op.execute("DROP INDEX IF EXISTS idx_settlements_idempotency_key")
    op.execute("ALTER TABLE settlements DROP CONSTRAINT IF EXISTS settlements_method_check")
    op.execute("ALTER TABLE settlements DROP COLUMN IF EXISTS idempotency_key")
    op.execute("ALTER TABLE settlements DROP COLUMN IF EXISTS recorded_by")
    op.execute("ALTER TABLE settlements DROP COLUMN IF EXISTS method")
    op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS updated_at")
