# Alembic migrations

This project intentionally does NOT ship formal Alembic migrations for the
3-day build — `backend/app/db/schema.sql` is the single source of truth,
applied directly via `psql` (see the root README's Setup section) or
automatically by docker-compose on first Postgres startup.

For a real production deployment, this is the first thing to add:
`alembic init alembic`, point `env.py` at
`app.db.base_class.Base.metadata`, and generate an initial migration from
the existing schema with `alembic revision --autogenerate`. See
`docs/SYSTEM_DESIGN.md` → "Bottlenecks & Trade-offs" for the full
rationale on this decision.
