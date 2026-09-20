# SplitPay Frontend Upgrade

The frontend has been refreshed without changing the backend API contracts.

## What changed
- Reworked the global navigation into a compact fintech-style header with responsive mobile navigation.
- Rebuilt the dashboard around net position, money owed/owed-to-me, group exposure, recent transactions, and reliability signals.
- Added visible product trust cues for exact Decimal arithmetic, idempotent payment handling, Redis/PostgreSQL fallback, signed webhooks, and the repository's automated test suite.
- Refreshed Groups with a stronger create-group flow and responsive group cards.
- Refreshed Transactions with search, summary counters, responsive mobile rows, and clearer transaction IDs/statuses.
- Added a cleaner page shell, typography hierarchy, spacing, surfaces, shadows, and responsive behavior.
- No new frontend dependencies were introduced.

## Verification
Backend tests live in `backend/app/tests`; frontend tests in `frontend/src/__tests__` (`npm test`).

A production Vite build could not be completed in the packaging environment because the uploaded repository did not contain a complete installed dependency tree and package installation timed out. Source files were updated in-place and the existing lockfile/package manifest were left unchanged.


## Editorial redesign + theme system (September 2026)

The frontend now uses a reference-inspired editorial fintech visual system:
- warm paper/cream light theme with deep navy ink and muted blue accents
- full dark mode with persistent localStorage preference
- theme toggle available in authenticated navigation and login/register screens
- serif editorial headings, pill labels, soft borders, grain/grid texture, glass surfaces and restrained motion
- responsive layouts preserved across dashboard, groups, group details, expenses, settlements, transactions, transaction details and profile
- existing API/business logic was intentionally preserved

Run with:
```bash
cd frontend
npm install
npm run dev
```

For the complete stack:
```bash
docker compose up --build
```
