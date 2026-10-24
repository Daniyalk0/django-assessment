from unittest.mock import patch

from django.test import TestCase

from .models import FailedEmail
from .tasks import allow_email_send, send_email_task, redis_client
import time
from celery.contrib.testing.worker import start_worker
from config.celery import app as celery_app


class EmailQueueTests(TestCase):

    
    def test_500_jobs_are_processed(self):
        with patch(
            "orders.tasks.allow_email_send",
            return_value=True,
        ), patch("orders.tasks.send_mail") as mock_send_mail:
            results = [
                send_email_task.apply(
                    args=(
                        f"user{i}@example.com",
                        "Test subject",
                        "Test message",
                    ),
                    throw=False,
                )
                for i in range(500)
            ]

        self.assertEqual(len(results), 500)
        self.assertTrue(all(result.successful() for result in results))
        self.assertEqual(mock_send_mail.call_count, 500)


    def test_rate_limiter_allows_at_most_200_attempts(self):
        key = f"email_rate_limit:{int(time.time() // 60)}"
        redis_client.delete(key)

        try:
            results = [allow_email_send() for _ in range(205)]

            self.assertEqual(sum(results), 200)
            self.assertEqual(len(results) - sum(results), 5)
        finally:
            redis_client.delete(key)

    def test_failed_email_is_retried(self):
        with patch(
            "orders.tasks.allow_email_send",
            return_value=True,
        ), patch(
            "orders.tasks.send_mail",
            side_effect=[RuntimeError("Temporary failure"), 1],
        ) as mock_send_mail:
            result = send_email_task.apply(
                args=(
                    "retry@example.com",
                    "Retry test",
                    "Test retry",
                ),
                throw=False,
            )

        self.assertTrue(result.successful())
        self.assertEqual(mock_send_mail.call_count, 2)
        self.assertEqual(FailedEmail.objects.count(), 0)
