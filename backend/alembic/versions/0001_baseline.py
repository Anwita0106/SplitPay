"""Baseline: the original 8-table schema (formerly applied only via schema.sql).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-20

Every statement is IF NOT EXISTS, so this revision is a harmless no-op on a
database that was already created from the old `schema.sql` (i.e. an existing
user's Docker volume) and builds the full baseline on a brand-new database.
No existing data is read, changed, or deleted.
"""
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_SQL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(120)  NOT NULL,
    email           VARCHAR(255)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255)  NOT NULL,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS groups (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(150)  NOT NULL,
    created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_groups_created_by ON groups(created_by);

CREATE TABLE IF NOT EXISTS group_members (
    group_id        UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id);

CREATE TABLE IF NOT EXISTS expenses (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    group_id        UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    description     VARCHAR(255) NOT NULL,
    total_amount    NUMERIC(12,2) NOT NULL CHECK (total_amount > 0),
    split_type      VARCHAR(20) NOT NULL CHECK (split_type IN ('EQUAL','PERCENTAGE','EXACT')),
    paid_by         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_expenses_group ON expenses(group_id);
CREATE INDEX IF NOT EXISTS idx_expenses_paid_by ON expenses(paid_by);
CREATE INDEX IF NOT EXISTS idx_expenses_group_created_at ON expenses(group_id, created_at DESC);

CREATE TABLE IF NOT EXISTS expense_splits (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    expense_id      UUID NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id)    ON DELETE RESTRICT,
    amount          NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    percentage      NUMERIC(5,2) CHECK (percentage >= 0 AND percentage <= 100),
    UNIQUE (expense_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_expense_splits_expense ON expense_splits(expense_id);
CREATE INDEX IF NOT EXISTS idx_expense_splits_user ON expense_splits(user_id);

CREATE TABLE IF NOT EXISTS settlements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    group_id        UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    from_user       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    to_user         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    amount          NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING','PROCESSING','COMPLETED','CANCELLED')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (from_user <> to_user)
);
CREATE INDEX IF NOT EXISTS idx_settlements_group ON settlements(group_id);
CREATE INDEX IF NOT EXISTS idx_settlements_from_user ON settlements(from_user);
CREATE INDEX IF NOT EXISTS idx_settlements_to_user ON settlements(to_user);
CREATE INDEX IF NOT EXISTS idx_settlements_status ON settlements(status);

CREATE TABLE IF NOT EXISTS payments (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    settlement_id       UUID NOT NULL REFERENCES settlements(id) ON DELETE RESTRICT,
    amount              NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    gateway_order_id    VARCHAR(120),
    gateway_payment_id  VARCHAR(120),
    status              VARCHAR(20) NOT NULL DEFAULT 'CREATED'
                            CHECK (status IN ('CREATED','PENDING','SUCCESS','FAILED','CANCELLED')),
    idempotency_key     VARCHAR(120) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_payments_settlement ON payments(settlement_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_gateway_order_id ON payments(gateway_order_id) WHERE gateway_order_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS webhook_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_event_id  VARCHAR(150) NOT NULL UNIQUE,
    payment_id      UUID REFERENCES payments(id) ON DELETE SET NULL,
    raw_payload     JSONB NOT NULL,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_webhook_events_payment ON webhook_events(payment_id);
"""


def upgrade() -> None:
    op.execute(BASELINE_SQL)


def downgrade() -> None:
    # Deliberately refuses to drop the baseline: that would destroy all user data.
    raise RuntimeError("Refusing to downgrade past the baseline schema (would delete all data).")
