-- =====================================================================
-- SplitPay Database Schema (PostgreSQL)
-- Money is ALWAYS stored as NUMERIC(12,2) — never FLOAT/DOUBLE.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------
-- USERS
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(120)  NOT NULL,
    email           VARCHAR(255)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255)  NOT NULL,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users(email);

-- ---------------------------------------------------------------------
-- GROUPS
-- ---------------------------------------------------------------------
CREATE TABLE groups (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(150)  NOT NULL,
    created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_groups_created_by ON groups(created_by);

-- ---------------------------------------------------------------------
-- GROUP MEMBERS (composite PK — a user is in a group at most once)
-- ---------------------------------------------------------------------
CREATE TABLE group_members (
    group_id        UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, user_id)
);

CREATE INDEX idx_group_members_user ON group_members(user_id);

-- ---------------------------------------------------------------------
-- EXPENSES
-- ---------------------------------------------------------------------
CREATE TABLE expenses (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    group_id        UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    description     VARCHAR(255) NOT NULL,
    total_amount    NUMERIC(12,2) NOT NULL CHECK (total_amount > 0),
    split_type      VARCHAR(20) NOT NULL CHECK (split_type IN ('EQUAL','PERCENTAGE','EXACT')),
    paid_by         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_expenses_group ON expenses(group_id);
CREATE INDEX idx_expenses_paid_by ON expenses(paid_by);
CREATE INDEX idx_expenses_group_created_at ON expenses(group_id, created_at DESC);

-- ---------------------------------------------------------------------
-- EXPENSE SPLITS (one row per participant per expense)
-- ---------------------------------------------------------------------
CREATE TABLE expense_splits (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    expense_id      UUID NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id)    ON DELETE RESTRICT,
    amount          NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    percentage      NUMERIC(5,2) CHECK (percentage >= 0 AND percentage <= 100),
    UNIQUE (expense_id, user_id)
);

CREATE INDEX idx_expense_splits_expense ON expense_splits(expense_id);
CREATE INDEX idx_expense_splits_user ON expense_splits(user_id);

-- ---------------------------------------------------------------------
-- SETTLEMENTS (simplified debts computed by the SettlementService)
-- ---------------------------------------------------------------------
CREATE TABLE settlements (
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

CREATE INDEX idx_settlements_group ON settlements(group_id);
CREATE INDEX idx_settlements_from_user ON settlements(from_user);
CREATE INDEX idx_settlements_to_user ON settlements(to_user);
CREATE INDEX idx_settlements_status ON settlements(status);

-- ---------------------------------------------------------------------
-- PAYMENTS (one settlement can have multiple payment attempts;
-- idempotency_key prevents duplicate order creation)
-- ---------------------------------------------------------------------
CREATE TABLE payments (
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
    -- Idempotency is enforced per-user at the API layer (key sent by client),
    -- but must be globally unique at the DB layer to prevent race conditions.
    UNIQUE (idempotency_key)
);

CREATE INDEX idx_payments_settlement ON payments(settlement_id);
CREATE INDEX idx_payments_status ON payments(status);
CREATE UNIQUE INDEX idx_payments_gateway_order_id ON payments(gateway_order_id) WHERE gateway_order_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- WEBHOOK EVENTS LOG (dedupe delivery, audit trail)
-- ---------------------------------------------------------------------
CREATE TABLE webhook_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_event_id  VARCHAR(150) NOT NULL UNIQUE,
    payment_id      UUID REFERENCES payments(id) ON DELETE SET NULL,
    raw_payload     JSONB NOT NULL,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_webhook_events_payment ON webhook_events(payment_id);
