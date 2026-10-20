import copy
import io
import json
import os
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import worker
from botocore.exceptions import ClientError

LOG = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'requests'"
QUOTE = "ModuleNotFoundError: No module named 'requests'"
DIAGNOSIS = {"root_cause": "The requests import failed.", "evidence": [QUOTE], "suggested_fix": "Check dependencies and install requests in the environment.", "verification_steps": "Rerun the failing job."}


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ALLOWED_REPOSITORY": "Bhanuch2006/deployiq", "ALLOWED_REPOSITORY_ID": "1421278672", "GITHUB_TOKEN_SECRET_ARN": "test-secret", "AI_PROVIDER": "bedrock"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.table = MagicMock()
        self.table.get_item.return_value = {"Item": {"run_key": "repo#123#1", "repository": "Bhanuch2006/deployiq", "repository_id": 1421278672, "run_id": 123, "run_attempt": 1, "conclusion": "failure"}}
        self.record = {"eventName": "INSERT", "dynamodb": {"Keys": {"run_key": {"S": "repo#123#1"}}}}
        self.secrets = MagicMock()
        self.secrets.get_secret_value.return_value = {"SecretString": "github_pat_fakevalue"}
        self.bedrock = MagicMock()
        self.bedrock.converse.return_value = {"stopReason": "end_turn", "output": {"message": {"content": [{"text": json.dumps(DIAGNOSIS)}]}}, "usage": {"inputTokens": 100, "outputTokens": 50}}

    def analyze(self, quota=True):
        with patch.object(worker, "failed_logs", return_value=LOG), patch.object(worker, "daily_slot", return_value=quota):
            worker.analyze_record(self.record, self.table, self.secrets, self.bedrock)
        return self.table.update_item.call_args.kwargs["ExpressionAttributeValues"]

    def test_success_persists_verified_evidence_and_ai_source(self):
        values = self.analyze()
        self.assertEqual(values[":source"], "bedrock")
        self.assertEqual(values[":diagnosis"]["evidence"], [QUOTE])
        self.assertEqual(values[":verification"], "not_verified")
        self.assertEqual(values[":usage"]["inputTokens"], 100)

    def test_hallucinated_evidence_is_rejected(self):
        output = copy.deepcopy(DIAGNOSIS)
        output["evidence"] = ["An error that never occurred"]
        self.bedrock.converse.return_value["output"]["message"]["content"] = [{"text": json.dumps(output)}]
        values = self.analyze()
        self.assertEqual(values[":source"], "rules")
        self.assertEqual(values[":error"], "model_evidence_not_in_logs")

    def test_bedrock_access_error_is_labeled_rules(self):
        self.bedrock.converse.side_effect = ClientError({"Error": {"Code": "AccessDeniedException"}}, "Converse")
        values = self.analyze()
        self.assertEqual(values[":source"], "rules")
        self.assertEqual(values[":error"], "AccessDeniedException")

    def test_quota_exhaustion_never_calls_bedrock(self):
        values = self.analyze(quota=False)
        self.bedrock.converse.assert_not_called()
        self.assertEqual(values[":error"], "daily_ai_limit_reached")

    def test_completed_analysis_is_not_billed_twice(self):
        self.table.get_item.return_value["Item"]["analysis_status"] = "completed"
        worker.analyze_record(self.record, self.table, self.secrets, self.bedrock)
        self.table.update_item.assert_not_called()
        self.secrets.get_secret_value.assert_not_called()
        self.bedrock.converse.assert_not_called()

    def test_successful_run_is_not_analyzed(self):
        self.table.get_item.return_value["Item"]["conclusion"] = "success"
        worker.analyze_record(self.record, self.table, self.secrets, self.bedrock)
        self.table.update_item.assert_not_called()

    def test_log_download_failure_remains_retryable(self):
        with patch.object(worker, "failed_logs", side_effect=worker.SafeFailure("github_http_403")):
            with self.assertRaisesRegex(worker.SafeFailure, "github_http_403"):
                worker.analyze_record(self.record, self.table, self.secrets, self.bedrock)
        self.assertEqual(self.table.update_item.call_args.kwargs["ExpressionAttributeValues"][":status"], "failed")
        self.bedrock.converse.assert_not_called()

    def test_daily_quota_uses_atomic_condition(self):
        self.assertTrue(worker.daily_slot(self.table))
        call = self.table.update_item.call_args.kwargs
        self.assertIn("calls < :limit", call["ConditionExpression"])
        self.assertEqual(call["ExpressionAttributeValues"][":limit"], 10)

    def test_daily_quota_rejects_limit(self):
        self.table.update_item.side_effect = ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
        self.assertFalse(worker.daily_slot(self.table))

    def test_secrets_are_redacted(self):
        text = "AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP\nAWS_SECRET_ACCESS_KEY=verysecret\nAuthorization: Bearer abc123\nghp_fakevalue\nCUSTOM_TOKEN='secretvalue'\ngithub_pat_actualtoken"
        cleaned = worker.redact(text, "github_pat_actualtoken")
        for secret in ["AKIAABCDEFGHIJKLMNOP", "verysecret", "abc123", "ghp_fakevalue", "secretvalue", "github_pat_actualtoken"]:
            self.assertNotIn(secret, cleaned)

    def test_private_key_is_redacted(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nprivate data\n-----END RSA PRIVATE KEY-----"
        self.assertNotIn("private data", worker.redact(text))

    def test_excerpt_keeps_error_context(self):
        log = "noise\n" * 5000 + LOG
        selected = worker.excerpt(log)
        self.assertIn(QUOTE, selected)
        self.assertLessEqual(len(selected), worker.MAX_EXCERPT)

    def test_import_name_is_not_assumed_to_be_package_name(self):
        diagnosis = worker.rule_diagnosis(LOG)
        self.assertIn("may differ", diagnosis["suggested_fix"])

    def test_github_token_is_not_forwarded_to_download_host(self):
        redirect = urllib.error.HTTPError("https://api.github.com/test", 302, "redirect", {"Location": "https://logs.example.test/download?sig=redacted"}, io.BytesIO())
        opener = MagicMock()
        opener.open.side_effect = redirect
        downloaded = MagicMock()
        downloaded.read.return_value = LOG.encode()
        with patch.object(worker.urllib.request, "build_opener", return_value=opener), patch.object(worker.urllib.request, "urlopen", return_value=downloaded) as fetch:
            self.assertIn(QUOTE, worker.job_log("Bhanuch2006/deployiq", 123, "private-token"))
        request = fetch.call_args.args[0]
        self.assertNotIn("Authorization", request.headers)

    def test_failed_jobs_are_fetched_for_exact_attempt(self):
        with patch.object(worker, "github_json", return_value={"jobs": [{"id": 42, "conclusion": "failure", "name": "test"}]}) as fetch, patch.object(worker, "job_log", return_value=LOG):
            result = worker.failed_logs("Bhanuch2006/deployiq", 123, 2, "private-token")
        self.assertIn("/attempts/2/jobs", fetch.call_args.args[0])
        self.assertIn(QUOTE, result)


class GroqTests(AnalysisTests):
    def setUp(self):
        super().setUp()
        os.environ["AI_PROVIDER"] = "groq"
        os.environ["GROQ_API_KEY_SECRET_ARN"] = "groq-secret"
        self.addCleanup(lambda: os.environ.pop("GROQ_API_KEY_SECRET_ARN", None))
        self.secrets.get_secret_value.side_effect = lambda **kw: {"SecretString": "gsk_private_test_key" if kw["SecretId"] == "groq-secret" else "github_pat_fakevalue"}
        self.response = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(DIAGNOSIS)}}], "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}
        self.opener = MagicMock()
        self.opener.open.return_value.__enter__.return_value.read.side_effect = lambda limit: json.dumps(self.response).encode()[:limit]
        mock_opener = patch.object(worker.urllib.request, "build_opener", return_value=self.opener)
        mock_opener.start()
        self.addCleanup(mock_opener.stop)

    def test_success_persists_verified_evidence_and_ai_source(self):
        values = self.analyze()
        self.assertEqual(values[":source"], "groq")
        self.assertEqual(values[":model"], "openai/gpt-oss-120b")
        self.assertEqual(values[":diagnosis"]["evidence"], [QUOTE])
        self.assertEqual(values[":usage"], {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150})
        self.assertEqual(values[":verification"], "not_verified")
        self.bedrock.converse.assert_not_called()
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer gsk_private_test_key")
        payload = json.loads(request.data)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("gsk_private_test_key", json.dumps(values))
        self.assertNotIn("github_pat_fakevalue", request.data.decode())

    def test_hallucinated_evidence_is_rejected(self):
        self.response["choices"][0]["message"]["content"] = json.dumps({**DIAGNOSIS, "evidence": ["An error that never occurred"]})
        values = self.analyze()
        self.assertEqual(values[":source"], "rules")
        self.assertEqual(values[":error"], "model_evidence_not_in_logs")

    def test_bedrock_access_error_is_labeled_rules(self):
        # Groq requests never depend on Bedrock permissions.
        self.bedrock.converse.side_effect = ClientError({"Error": {"Code": "AccessDeniedException"}}, "Converse")
        self.assertEqual(self.analyze()[":source"], "groq")

    def test_quota_exhaustion_never_calls_bedrock(self):
        values = self.analyze(quota=False)
        self.opener.open.assert_not_called()
        self.assertEqual(values[":source"], "rules")
        self.assertEqual(values[":error"], "daily_ai_limit_reached")

    def test_rate_limit_is_safe_rules_fallback_without_retry(self):
        self.opener.open.side_effect = urllib.error.HTTPError("https://api.groq.com", 429, "private response", {}, io.BytesIO(b"private response"))
        values = self.analyze()
        self.assertEqual(values[":source"], "rules")
        self.assertEqual(values[":error"], "groq_http_429")
        self.opener.open.assert_called_once()
        self.assertNotIn("private response", json.dumps(values))

    def test_timeout_is_safe_rules_fallback(self):
        self.opener.open.side_effect = TimeoutError("private URL or token")
        self.assertEqual(self.analyze()[":error"], "groq_connection_failed")

    def test_incomplete_model_output_is_not_ai_success(self):
        self.response["choices"][0]["finish_reason"] = "length"
        self.assertEqual(self.analyze()[":error"], "model_response_incomplete")

    def test_oversize_response_is_rejected(self):
        self.opener.open.return_value.__enter__.return_value.read.side_effect = lambda limit: b"x" * limit
        self.assertEqual(self.analyze()[":error"], "groq_response_too_large")

    def test_malformed_response_is_rejected(self):
        self.response = {"choices": []}
        self.assertEqual(self.analyze()[":error"], "invalid_model_response")

    def test_json_secret_is_rejected_before_network(self):
        self.secrets.get_secret_value.side_effect = lambda **kw: {"SecretString": '{"key":"gsk_private"}'}
        self.assertEqual(self.analyze()[":error"], "groq_secret_invalid_plaintext")
        self.opener.open.assert_not_called()

    def test_provider_redirect_is_rejected_without_credentials_forwarding(self):
        # Exercise the real redirect handler separately from the mocked opener.
        request = worker.urllib.request.Request("https://api.groq.com", headers={"Authorization": "Bearer private"})
        self.assertIsNone(worker.NoRedirect().redirect_request(request, None, 302, "redirect", {}, "https://other.example"))
        self.opener.open.side_effect = urllib.error.HTTPError(request.full_url, 302, "redirect", {}, io.BytesIO())
        self.assertEqual(self.analyze()[":error"], "groq_http_302")
        self.opener.open.assert_called_once()

    def test_groq_key_redaction(self):
        self.assertNotIn("gsk_private_test_key", worker.redact("error gsk_private_test_key"))


if __name__ == "__main__":
    unittest.main()
