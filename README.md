# DawitAppachMotor

A modular digital lottery platform for Telegram customers and a private web administration dashboard.

## Stage 1 status

The backend foundation is initialized:

- FastAPI application and health endpoint
- SQLAlchemy/PostgreSQL configuration
- Alembic migration environment
- Core database models
- Docker Compose PostgreSQL and backend services
- Environment variable template

## Stage 2 status

Lottery management and number availability are implemented:

- Create, list, retrieve, and update lotteries
- Generate tickets transactionally with leading-zero number formatting
- Paginate, search, and filter lottery numbers
- Prevent range changes while tickets are reserved or sold
- Limit generated lottery ranges to 1,000,000 tickets
- Validate lottery status and configurable ticket values

### Lottery API

- `POST /lotteries`
- `GET /lotteries`
- `GET /lotteries/{lottery_id}`
- `PATCH /lotteries/{lottery_id}`
- `GET /lotteries/{lottery_id}/tickets?page=1&page_size=50&status=AVAILABLE&search=003`

## Stage 3 status

Transactional reservation management is implemented:

- Customer and lottery row locking during reservation creation
- Ticket row locking for atomic availability checks
- Customer allocation limits across reserved and sold tickets
- PostgreSQL-backed duplicate ticket prevention
- Full reservation rollback if any requested number is unavailable
- Ethiopian phone number normalization
- Amharic-capable Unicode customer names
- Idempotent reservation expiration and ticket release
- Automated payment record creation for each reservation

### Reservation API

- `POST /reservations`
- `POST /reservations/expire`

## Stage 4 status

The Telegram customer bot interface is implemented:

- Persistent customer menu
- Telegram user ID customer identification
- Active lottery selection
- Paginated number browsing
- Number search
- Multiple selection and review
- Amharic and English name input
- Ethiopian phone number collection
- Explicit reservation confirmation
- Reservation and purchased-number views
- Public masking of sold-number phone numbers
- Reservation unavailable and allocation-limit messages

Start the bot in Docker by setting `TELEGRAM_BOT_TOKEN` in `.env`, then run:

```powershell
docker compose up -d --build bot
```

## Stage 5 status

Private payment screenshot submission is implemented:

- JPEG, PNG, and WebP validation
- 10 MB attachment limit
- Secure per-reservation storage keys
- Screenshot association with customer, reservation, and payment
- `PAYMENT_SUBMITTED` status updates
- Reservation expiration validation
- Telegram photo upload handling
- Telegram image-document upload handling

### Payment API

- `POST /payments/reservations/{reservation_reference}/screenshots`

## Stage 6 status

Secure owner authentication and the initial admin dashboard are implemented:

- Argon2 password hashing
- HTTP-only, SameSite session cookies
- 12-hour signed sessions
- Login rate limiting
- Protected administrator API dependencies
- Owner account setup command
- Live dashboard overview totals
- Responsive Next.js login and dashboard interface

Provision or update the owner account:

```powershell
docker compose exec backend python -m app.commands.setup_admin --username owner --password "a-long-secure-password"
```

Open the dashboard at `http://localhost:3000`.

## Stage 7 status

Manual payment verification is implemented:

- Submitted-payment review queue
- Private screenshot preview for authenticated administrators
- Atomic payment approval
- Duplicate approval prevention
- Explicit confirmation for expired reservation approval
- Reservation ticket consistency validation
- Atomic ticket transition to SOLD
- Payment rejection with mandatory reason
- Reserved-number release after rejection
- Customer Telegram notification attempts
- Audit log entries for approval and rejection

### Payment review API

- `GET /admin/payments/pending`
- `POST /admin/payments/{payment_id}/approve`
- `POST /admin/payments/{payment_id}/reject`
- `GET /admin/payments/{payment_id}/attachment`

## Stage 8 status

Customer activity tracking and Telegram broadcasts are implemented:

- Searchable, newest-first activity log API
- Customer and activity-type filtering support
- Bot-start and payment audit activity records
- Broadcast creation for all customers or selected customer IDs
- Broadcast delivery records
- Controlled synchronous worker processing
- Permanent failure tracking
- Broadcast history with sent, failed, and pending counts

### Activity and broadcast API

- `GET /admin/activities`
- `GET /admin/broadcasts/customers`
- `POST /admin/broadcasts`
- `POST /admin/broadcasts/{broadcast_id}/process`
- `GET /admin/broadcasts`

## Stage 9 status

Customer management, Unicode search, sales reports, and automated expiration are implemented:

- Paginated customer directory
- Search by Amharic or English name, phone, or Telegram username
- Name and recent activity sorting
- Purchased, reservation, payment, and activity history per customer
- Confirmed revenue reporting from approved payments only
- Lottery-level sold, reserved, and available totals
- Persistent 5-minute reservation expiration worker
- Idempotent database expiration processing

### Customer and report API

- `GET /admin/customers`
- `GET /admin/customers/{customer_id}`
- `GET /admin/reports`

## Stage 10 deployment status

Production deployment support is included:

- Docker and Docker Compose images for PostgreSQL, backend, bot, frontend, and expiration worker
- Environment-based secrets and configuration
- Alembic migrations before backend startup
- Persistent PostgreSQL and payment-attachment volumes
- Health checks for backend and database
- Database backup and restore PowerShell scripts
- HTTPS deployment guidance
- Logging and monitoring guidance

## Production deployment

1. Provision a VPS with Docker Engine and Docker Compose.
2. Copy `.env.example` to `.env` and replace every development secret.
3. Set a strong PostgreSQL password and matching `DATABASE_URL`.
4. Set `PUBLIC_APP_URL` and `BACKEND_CORS_ORIGINS` to the real HTTPS frontend origin.
5. Set `TELEGRAM_BOT_TOKEN` and provision the owner account.
6. Configure a reverse proxy such as Caddy or Nginx for TLS and forward:
   - `/` to the frontend on port `3000`
   - `/api` or direct `/admin`, `/lotteries`, `/payments`, `/reservations`, `/health` routes to port `8000`
7. Start the stack:

```powershell
docker compose up -d --build
```

HTTPS should terminate at the reverse proxy. The administrator session cookie will be marked Secure when `PUBLIC_APP_URL` starts with `https://`.

## Database backup and restore

Create a backup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
```

Restore a custom-format backup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1 -BackupFile .\backups\dawit-lottery-YYYYMMDD-HHmmss.sql
```

Test restore procedures regularly and keep encrypted off-host copies of both PostgreSQL backups and the `attachment_data` volume.

## Operations

- Review container logs with `docker compose logs --tail=200`.
- Monitor PostgreSQL and backend health through Docker health checks.
- Back up `/var/lib/postgresql/data` through `pg_dump`, not by copying live database files.
- Back up the `attachment_data` volume separately.
- Protect `.env`, Telegram tokens, session secrets, database credentials, and payment attachments.
- Run migrations automatically through the backend startup command.

## Local development

1. Copy `backend/.env.example` to `.env` if running locally.
2. Start PostgreSQL and the backend:

   ```powershell
   docker compose up --build
   ```

3. Open `http://localhost:8000/health`.
4. Open FastAPI documentation at `http://localhost:8000/docs`.

## Backend setup without Docker

```powershell
cd backend
python -m pip install -r requirements.txt
$env:DATABASE_URL="postgresql+psycopg://lottery:lottery@localhost:5432/dawit_lottery"
uvicorn app.main:app --reload
```
