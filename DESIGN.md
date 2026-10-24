# Design Decisions: Asynchronous Email Queue

## 1. Architecture

- **Django** accepts requests and submits email tasks to Celery.
- **Celery** processes email tasks asynchronously, keeping email delivery outside the request-response cycle.
- **Redis** acts as the Celery broker and stores rate-limit counters.
- **PostgreSQL/SQLite via Django ORM** stores records of emails that permanently fail after retries. SQLite is used for local development.
- **Django Silk** profiles SQL queries for the order-summary endpoint.

## 2. Why Celery + Redis?

**Celery + Redis** was chosen because it supports asynchronous task execution, retries, configurable acknowledgements, and multiple workers. Redis is also useful for atomic rate-limit operations.

**Django Q** could provide background task processing with a simpler Django-oriented setup, but Celery offers the task execution and retry controls needed for this assessment.

A **custom queue** would require implementing job persistence, worker coordination, retry scheduling, crash recovery, and concurrency handling. That would increase complexity and maintenance risk without a clear benefit here.

## 3. Rate-Limiting Strategy

The email task uses a **fixed-window counter** with a limit of 200 attempts per minute window. The Redis key includes the current minute, and the counter expires after 70 seconds.

A Lua script performs `INCR` and the initial `EXPIRE` atomically. This prevents concurrent workers from interleaving these operations and leaving the counter without an expiry.

When the count exceeds 200, the task is retried later instead of sending the email immediately. This avoids intentionally exceeding the configured limit.

### Trade-offs

A fixed window is simple and efficient, but it is not a strict rolling 60-second limit. Requests near a minute boundary can allow more than 200 attempts within a rolling 60-second period. A token bucket or sliding-window limiter would provide tighter control but require more complex state management.

## 4. Retry and Failure Handling

Email tasks use Celery retries with exponential backoff, jitter, and a maximum of five retries. Backoff reduces repeated pressure on a failing email service; jitter helps prevent many tasks from retrying simultaneously.

After retries are exhausted, the task records the recipient, subject, message, and error in `FailedEmail` before raising the final exception.

The rate limiter fails closed: if Redis is unavailable, the task does not bypass the limit. It retries the error and records the failure if retries are exhausted.

## 5. Worker Crashes and Delivery Guarantees

`CELERY_TASK_ACKS_LATE = True` acknowledges a task after execution rather than before it. `CELERY_TASK_REJECT_ON_WORKER_LOST = True` asks Celery to requeue a task when its worker process is lost.

These settings help recover interrupted work, but they do not guarantee exactly-once email delivery. A worker could send an email and crash before acknowledging the task, causing the email to be sent again after redelivery. Duplicate delivery is therefore possible; production systems should use idempotency controls where possible.

`SIGKILL` terminates a process immediately and cannot be caught by Python cleanup handlers. Recovery depends on broker acknowledgement behavior and Celery worker configuration.

## 6. Burst Handling and Limitations

The queue separates incoming requests from email delivery, allowing bursts of jobs to wait for workers instead of blocking web requests. The rate limiter controls sending attempts, while Celery manages queued execution and retries.

The current local email backend is for development and writes output to the console; it does not deliver real email. The automated tests verify task execution, rate-limiter behavior, and retry behavior. A separate broker/worker integration test and crash-recovery test would be needed to demonstrate end-to-end queue durability under worker termination.