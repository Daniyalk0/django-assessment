import time

import redis
from celery import shared_task
from celery.exceptions import Retry
from django.conf import settings
from django.core.mail import send_mail

from .models import FailedEmail

redis_client = redis.Redis.from_url(
    settings.CELERY_BROKER_URL,
    decode_responses=True,
)


RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], 70)
end
return count
"""


def allow_email_send():
    current_minute = int(time.time() // 60)
    key = f"email_rate_limit:{current_minute}"

    count = redis_client.eval(RATE_LIMIT_SCRIPT, 1, key)

    return count <= 200


@shared_task(
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_email_task(self, recipient, subject, message):
    # Rate-limit excess jobs without treating them as email failures.
    try:
        if not allow_email_send():
            raise self.retry(countdown=60)
    except Retry:
        raise
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        FailedEmail.objects.create(
            recipient=recipient,
            subject=subject,
            message=message,
            error=f"Rate limiter error: {exc}",
        )
        raise

    # Attempt delivery and retry temporary sending failures.
    try:
        send_mail(
            subject,
            message,
            None,
            [recipient],
            fail_silently=False,
        )
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        FailedEmail.objects.create(
            recipient=recipient,
            subject=subject,
            message=message,
            error=str(exc),
        )
        raise
