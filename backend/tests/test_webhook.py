import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhooks import handler as webhook

SECRET = "test-only-secret-never-use-in-aws"


class WebhookTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "WEBHOOK_SECRET": SECRET,
            "ALLOWED_REPOSITORY": "Bhanuch2006/deployiq",
            "ALLOWED_REPOSITORY_ID": "1421278672",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.payload = {
            "action": "completed",
            "repository": {"full_name": "Bhanuch2006/deployiq", "id": 1421278672},
            "workflow_run": {"id": 123, "run_attempt": 1, "status": "completed", "conclusion": "failure", "head_sha": "abc", "name": "DeployIQ CI"},
        }

    def event(self, payload=None, event_type="workflow_run", encoded=False):
        raw = json.dumps(payload if payload is not None else self.payload, ensure_ascii=False).encode()
        signature = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        return {"headers": {"X-Hub-Signature-256": signature, "X-GitHub-Event": event_type, "X-GitHub-Delivery": "test-delivery"}, "body": base64.b64encode(raw).decode() if encoded else raw.decode(), "isBase64Encoded": encoded}

    def test_signed_result_is_stored_without_extra_fields(self):
        self.payload["workflow_run"]["unwanted_secret"] = "do-not-store"
        with patch.object(webhook, "store_run", return_value=True) as store:
            result = webhook.handler(self.event(), None)
        self.assertEqual(result["statusCode"], 200)
        item = store.call_args.args[0]
        self.assertEqual(item["run_key"], "Bhanuch2006/deployiq#123#1")
        self.assertEqual(item["conclusion"], "failure")
        self.assertNotIn("unwanted_secret", item)

    def test_tampered_body_is_rejected_before_storage(self):
        event = self.event()
        event["body"] += " "
        with patch.object(webhook, "store_run") as store:
            self.assertEqual(webhook.handler(event, None)["statusCode"], 401)
            store.assert_not_called()

    def test_unsigned_request_is_rejected(self):
        event = self.event()
        event["headers"].pop("X-Hub-Signature-256")
        self.assertEqual(webhook.handler(event, None)["statusCode"], 401)

    def test_unicode_base64_signature_is_verified(self):
        self.payload["workflow_run"]["name"] = "Build café"
        with patch.object(webhook, "store_run", return_value=True):
            self.assertEqual(webhook.handler(self.event(encoded=True), None)["statusCode"], 200)

    def test_other_repository_is_rejected(self):
        self.payload["repository"]["full_name"] = "someone/other"
        self.assertEqual(webhook.handler(self.event(), None)["statusCode"], 403)

    def test_reused_name_with_different_id_is_rejected(self):
        self.payload["repository"]["id"] = 999
        self.assertEqual(webhook.handler(self.event(), None)["statusCode"], 403)

    def test_ping_does_not_store_a_run(self):
        with patch.object(webhook, "store_run") as store:
            self.assertEqual(webhook.handler(self.event(event_type="ping"), None)["statusCode"], 200)
            store.assert_not_called()

    def test_in_progress_run_is_ignored(self):
        self.payload["action"] = "in_progress"
        with patch.object(webhook, "store_run") as store:
            self.assertEqual(webhook.handler(self.event(), None)["statusCode"], 200)
            store.assert_not_called()

    def test_retry_gets_separate_run_key(self):
        self.payload["workflow_run"]["run_attempt"] = 2
        with patch.object(webhook, "store_run", return_value=True) as store:
            webhook.handler(self.event(), None)
        self.assertTrue(store.call_args.args[0]["run_key"].endswith("#123#2"))

    def test_duplicate_is_acknowledged(self):
        with patch.object(webhook, "store_run", return_value=False):
            result = webhook.handler(self.event(), None)
        self.assertEqual(result["statusCode"], 200)
        self.assertIn("already stored", result["body"])

    def test_conditional_write_handles_duplicate(self):
        with patch.object(webhook, "table") as table:
            table.return_value.put_item.side_effect = ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
            self.assertFalse(webhook.store_run({"run_key": "repo#123#1"}))
            self.assertEqual(table.return_value.put_item.call_args.kwargs["ConditionExpression"], "attribute_not_exists(run_key)")

    def test_storage_failure_returns_retryable_response(self):
        with patch.object(webhook, "store_run", side_effect=RuntimeError("offline")), self.assertLogs(webhook.logger, level="ERROR"):
            self.assertEqual(webhook.handler(self.event(), None)["statusCode"], 503)

    def test_malformed_run_is_rejected(self):
        self.payload["workflow_run"]["id"] = True
        self.assertEqual(webhook.handler(self.event(), None)["statusCode"], 400)

    def test_invalid_base64_is_rejected(self):
        event = self.event(encoded=True)
        event["body"] = "!not-base64!"
        self.assertEqual(webhook.handler(event, None)["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
