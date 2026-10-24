# Django Systems Engineering Assessment

A Django project demonstrating ORM performance optimization, asynchronous email processing with Celery and Redis, and architecture trade-offs.

## Features

- **Order Summary API:** Uses Django ORM `select_related()` to avoid N+1 queries when retrieving customers for orders.
- **Query Profiling:** Integrates Django Silk to inspect SQL queries and measure performance.
- **Async Email Queue:** Uses Celery with Redis as the broker.
- **Rate Limiting:** Uses an atomic Redis Lua script with a fixed-window counter, allowing up to 200 attempts per minute window.
- **Retries and Failure Records:** Retries failed email attempts with exponential backoff and jitter. Permanently failed attempts are recorded in the `FailedEmail` database table.
- **Automated Tests:** Covers 500 task executions, Redis rate limiting, and retry behavior.

## Requirements

- Python 3.13 or a compatible version
- Docker Desktop with Docker Compose
- Git

## Setup

### 1. Create and activate a virtual environment

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

Install all project dependencies from the root directory:

```powershell
pip install -r requirements.txt
```

### 3. Start Redis

```powershell
docker compose up -d redis
docker compose exec redis redis-cli ping
```

The expected response is `PONG`.

### 4. Apply database migrations

```powershell
python manage.py migrate
```

### 5. Start Django

In the first terminal:

```powershell
python manage.py runserver
```

### 6. Start the Celery worker

Activate the virtual environment in a second terminal, navigate to the project root, and run:

```powershell
celery -A config worker --loglevel=info --pool=solo
```

The `solo` pool is suitable for local development on Windows.

## API Endpoint

```text
GET /api/orders/summary/
```

The endpoint returns order IDs, customer names, and order totals. Django Silk can be used to inspect query counts and execution timings during development.

## Testing

Run the automated tests:

```powershell
python manage.py test orders
```

The tests cover task execution, the Redis rate limiter, and retry behavior.

## Email Behavior

The current development email configuration uses a console-style backend. Emails are printed in the worker output rather than delivered to real recipients. A production deployment should configure a real email provider and secure its credentials.

## Architecture Notes

See [DESIGN.md](DESIGN.md) for the queue architecture, technology trade-offs, rate-limiter design, Redis failure behavior, and worker-crash considerations.

See [ANSWERS.md](ANSWERS.md) for the incident investigation and written architecture review.

## Limitations

- The limiter uses fixed one-minute windows, not a rolling 60-second window.
- Redis must be available for rate-limit checks; the task retries limiter errors rather than intentionally bypassing the limit.
- Celery worker crash recovery depends on acknowledgement settings and broker behavior. Tasks may be redelivered, so production email delivery should account for duplicate attempts.
