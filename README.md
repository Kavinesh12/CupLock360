# CUPLOCK 360°

Scaffolding rental, inventory and financial control platform for Cuplock rental operations.

| Folder | What | Stack |
| --- | --- | --- |
| `api/` | REST API, every business rule | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL |
| `web/` | Owner, office, accounts and stores web app | React, Vite, TypeScript, Ant Design, TanStack Query |
| `app/` | Android field app | Ionic React, Capacitor |

## Run locally

Requirements: Python 3.12+, Node 22, PostgreSQL 16.

```bash
# 1. API
cd api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # edit DB URL if needed
alembic upgrade head
python -m app.seed              # permissions, 12 roles, owner account
uvicorn app.main:app --reload   # http://localhost:8000/docs

# 2. Web (new terminal)
cd web && npm install && npm run dev      # http://localhost:5173

# 3. Mobile app in the browser (new terminal)
cd app && npm install && npm run dev      # http://localhost:8100
```

Default owner login: `owner` / `Owner@12345` (change via `CUPLOCK_OWNER_*` before seeding).

**OTP in development.** With `CUPLOCK_OTP_DELIVERY=console`, OTPs are kept in a dev-only outbox (never logged).
On the web login screen click **Dev: show OTP**, or open `http://localhost:8000/api/v1/dev/otp-outbox`.
This endpoint exists only when `CUPLOCK_ENV=dev`. Set `CUPLOCK_OTP_DELIVERY=email` plus the SMTP settings to send real
OTPs until SMS DLT registration is approved.

### Docker

```bash
docker compose up --build       # web + API on http://localhost:8080
```

### Android APK

```bash
cd app
echo "VITE_API_URL=https://your-api-host" > .env
npm run android:sync
npm run android:open            # build / sign in Android Studio
```

## Tests

```bash
cd api && pytest -q             # needs a `cuplock_test` Postgres database
```

## Security model (Day 1)

- Passwords hashed with Argon2id.
- Login is password **then** OTP. Access tokens last 15 minutes; refresh tokens are single-use and rotate.
  Reusing a spent refresh token revokes the whole session.
- OTPs: 6 digits, 5-minute expiry, single use, 3 attempts, 5 per 15 minutes per user, stored only as an HMAC,
  bound to a purpose and optional transaction reference (used for approvals from Day 4).
- Permissions are checked on every API call. Users can be limited to branches/warehouses/sites/clients and
  given an approval limit in ₹.
- Deactivating a user, changing their roles, scopes or password signs them out everywhere immediately.
- Audit log is append-only (database trigger) and hash-chained; `GET /api/v1/audit/verify` detects tampering.

## Modules so far

| Day | Module | Web | Android |
| --- | --- | --- | --- |
| 1 | Login with OTP, users, roles, branches, audit trail | ✓ | login |
| 2 | Clients (GSTIN, credit profile), projects, sites | ✓ | |
| 2 | Item master, rate cards (project > client > standard) | ✓ | |
| 2 | Leads, follow-ups, convert lead to client | ✓ | ✓ |
| 3 | Stock ledger by status and location, opening stock from Excel, transfers, status changes, write-offs, stock checks | ✓ | stock lookup |

### Stock rules

- Every change is a movement (OPN, TRS, TRR, STC, WOF, CHK) with signed ledger lines. The ledger is append-only (database trigger) and balances can never go negative.
- Opening stock is loaded once per warehouse from the Excel template, with a preview before saving. After any other movement in that warehouse it is closed; use a stock check instead.
- Transfers: sent stock is *in transit*. On receipt, good pieces become available and damaged pieces become damaged at the destination; any shortfall is marked *missing* at the sending warehouse.
- Stock check counts available stock. Short pieces go to *missing*; extra pieces come back from *missing* first.
- Write-offs (damaged or missing only), stock checks and opening stock need `stock.adjust` (owner, GM, branch manager).

## Roles

The 12 roles from the client deck are seeded: Business Owner, General Manager, Branch Manager, Sales / CRM
Executive, Site Manager, Storekeeper, Dispatch & Logistics, Accounts Manager, Accounts Executive, Auditor,
Client Portal User, System Administrator. Permissions per role live in `api/app/core/rbac.py` and can be
edited on the Roles screen.
