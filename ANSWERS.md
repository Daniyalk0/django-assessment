# Task 1: Diagnose a Broken System

### Root Cause
The endpoint had an N+1 query problem. Accessing `order.customer.name` inside a loop caused Django to execute an additional query for each order's customer.

### Fix
Replaced:

```python
Order.objects.all()
```

with:

```python
Order.objects.select_related("customer")
```

`select_related()` uses a SQL JOIN to fetch orders and their related customers in one query, reducing database round trips without changing the API response.

### Profiler Evidence

Measured using Django Silk on `GET /api/orders/summary/`:

| Metric | Before | After |
|---|---:|---:|
| SQL queries | 201 | 1 |
| SQL query time | 66 ms | 1 ms |
| Total response time | 562 ms | 64 ms |

### Investigation Log
1. Reproduced the slow endpoint with 200 orders.
2. Inspected SQL queries using Django Silk.
3. Identified repeated customer queries inside the loop.
4. Applied `select_related("customer")`.
5. Verified the reduced query count and response time while preserving the response data.


# Task 2: Asynchronous Email Queue

## Implementation
- **Celery + Redis:** Celery processes email jobs asynchronously, while Redis acts as the message broker and stores rate-limit counters.
- **Rate limiting:** An atomic Redis `INCR` counter allows up to 200 attempts per minute. The counter expires after 70 seconds.
- **Retries:** Failed email attempts use exponential backoff, jitter, a maximum delay of 300 seconds, and up to five retries.
- **Dead-letter handling:** After retries are exhausted, failure details are saved in the `FailedEmail` database table.

## Verification
- Successfully processed a test email task using Celery.
- Simulated an email failure and observed Celery schedule a retry.
- Queued 500 jobs; a status snapshot showed 400 `SUCCESS` and 100 `RETRY`. These counts are a snapshot, not proof that all jobs completed.
- Tested the rate limiter directly: 205 attempts resulted in 200 allowed and 5 blocked.

## SIGKILL
`SIGKILL` immediately terminates a process and cannot be caught by Python. A worker killed during execution may interrupt a task. Late acknowledgement and worker-loss redelivery settings can help recover interrupted tasks, but may cause duplicate execution, so tasks should be idempotent.



# Task 3: Written Architecture Review

## Question A — Django Admin Performance

### 1. Excessive related-object queries (N+1 problem)

Django admin may execute additional queries for every row when `list_display` includes fields accessed through foreign keys or many-to-many relationships. For example, displaying `order.customer.name` for 100 rows can trigger repeated customer queries.

**Fix:** Configure `list_select_related = ("customer",)` on the `ModelAdmin` to fetch foreign-key relationships through SQL joins. For many-to-many relationships, use `prefetch_related()` through a customized `get_queryset()` method. This reduces query count, although joining or prefetching large related datasets can increase memory usage and query complexity.

### 2. Loading too many records and expensive fields

Rendering thousands of rows, large text fields, or complex calculated columns can consume substantial database, memory, and template-rendering time. An indexed primary key does not prevent these costs.

**Fix:** Set `show_full_result_count = False` to avoid the additional full-table count used by the admin changelist, and configure `list_per_page` to a reasonable value such as 50 or 100. Use `list_display` to show only necessary fields and `list_display_links` to keep navigation practical. For expensive derived values, avoid per-row database queries and consider database-side annotations where appropriate. Smaller pages improve responsiveness but require more navigation.

### 3. Expensive filtering, sorting, and counting

Admin filters and ordering may use unindexed columns or complex joins. On a table with 500,000+ records, filtering or sorting can cause full-table scans, while exact counts may be costly even when the primary key is indexed.

**Fix:** Inspect SQL using Django Debug Toolbar or Silk and examine the database's `EXPLAIN` plan. Add targeted `Meta.indexes` or `db_index=True` indexes for frequently filtered or ordered fields, based on actual query patterns. Customize `ModelAdmin.get_queryset()` and `get_ordering()` to avoid unnecessary joins and expensive ordering. Additional indexes speed up reads but consume storage and add overhead to inserts and updates.

## Question B — Pagination Trade-offs

### Offset-based versus cursor-based pagination

**Offset-based pagination** retrieves a page using SQL `LIMIT` and `OFFSET`. Django REST Framework supports this through `LimitOffsetPagination` and `PageNumberPagination`.

Its main advantage is simplicity: clients can jump directly to a particular page, and page numbers are easy to display. However, at scale, large offsets become expensive because the database may scan or traverse many rows and discard those preceding the requested page. An index can help, but it does not eliminate the cost of skipping large numbers of rows.

Offset pagination also behaves poorly when records change between requests. If a new record is inserted near the beginning, records may shift between pages, causing duplicates or skipped results. Deletions can cause similar inconsistencies.

**Cursor-based pagination** uses a position in an ordered dataset rather than a numeric offset. Django REST Framework provides `CursorPagination`, which works best with a stable, indexed ordering field, such as a creation timestamp combined with a unique identifier.

Cursor pagination is generally more efficient for deep pagination because the database can seek from the cursor using an indexed ordering condition instead of skipping thousands of rows. It also reduces duplicates and omissions caused by insertions before the current position, although it does not provide a completely frozen snapshot: updates to ordering fields and deletions can still affect results.

The trade-off is reduced navigation flexibility. Clients generally cannot jump directly to page 500 or reliably calculate a total page count. Cursor pagination also requires deterministic ordering and careful cursor handling.

**My choice:** For a mobile app with infinite scrolling, I would choose cursor pagination because predictable performance and smooth sequential navigation matter more than jumping to arbitrary pages. For a small administrative dataset where users need page numbers, direct page access, and conventional navigation, I would choose offset-based pagination, provided query performance remains acceptable.