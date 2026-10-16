"""Accept signed GitHub workflow_run events and persist completed attempts."""
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
MAX_BODY_BYTES = 1024 * 1024
_table = None


def response(status, message):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"message": message}),
    }


def table():
    global _table
    if _table is None:
        import boto3
        from botocore.config import Config
        _table = boto3.resource(
            "dynamodb", config=Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 2})
        ).Table(os.environ["RUNS_TABLE"])
    return _table


def store_run(item):
    from botocore.exceptions import ClientError
    try:
        table().put_item(Item=item, ConditionExpression="attribute_not_exists(run_key)")
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return True


def handler(event, context):
    headers = {key.lower(): value for key, value in (event.get("headers") or {}).items()}
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        logger.error("Webhook secret is not configured")
        return response(503, "Webhook unavailable")
    try:
        body = event.get("body") or ""
        if not isinstance(body, str) or len(body) > 2 * MAX_BODY_BYTES:
            return response(413, "Payload too large")
        raw = base64.b64decode(body, validate=True) if event.get("isBase64Encoded") else body.encode("utf-8")
    except (ValueError, binascii.Error, UnicodeError):
        return response(400, "Invalid body encoding")
    if len(raw) > MAX_BODY_BYTES:
        return response(413, "Payload too large")
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    supplied = headers.get("x-hub-signature-256", "")
    if not isinstance(supplied, str) or not hmac.compare_digest(expected.encode(), supplied.encode("utf-8")):
        return response(401, "Invalid signature")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        return response(400, "Invalid JSON")
    if not isinstance(payload, dict):
        return response(400, "Expected a JSON object")
    repository = payload.get("repository")
    repository = repository if isinstance(repository, dict) else {}
    if repository.get("full_name") != os.environ.get("ALLOWED_REPOSITORY"):
        return response(403, "Repository not registered")
    # Bind registration to its numeric ID as well as its display name.
    if str(repository.get("id")) != os.environ.get("ALLOWED_REPOSITORY_ID"):
        return response(403, "Repository identity does not match")
    event_type = headers.get("x-github-event", "")
    if event_type == "ping":
        return response(200, "pong")
    if event_type != "workflow_run" or payload.get("action") != "completed":
        return response(200, "Event ignored")
    run = payload.get("workflow_run")
    if not isinstance(run, dict):
        return response(400, "Missing workflow run")
    run_id = run.get("id")
    attempt = run.get("run_attempt", 1)
    if type(run_id) is not int or run_id <= 0 or type(attempt) is not int or attempt <= 0:
        return response(400, "Invalid run identity")
    if run.get("status") != "completed" or not isinstance(run.get("conclusion"), str):
        return response(400, "Expected a completed run with a conclusion")
    delivery = headers.get("x-github-delivery", "")
    if not delivery or len(delivery) > 128:
        return response(400, "Missing or invalid delivery ID")
    # Explicit field allowlist: never persist the whole webhook or credentials.
    fields = ["name", "head_branch", "head_sha", "html_url", "event", "conclusion", "status", "created_at", "run_started_at", "updated_at"]
    item = {
        "run_key": f"{repository['full_name']}#{run_id}#{attempt}",
        "repository": repository["full_name"],
        "repository_id": repository["id"],
        "run_id": run_id,
        "run_attempt": attempt,
        "delivery_id": delivery,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    for field in fields:
        value = run.get(field)
        if value is not None:
            if not isinstance(value, str) or len(value) > 2048:
                return response(400, "Invalid run field")
            item[field] = value
    try:
        created = store_run(item)
    except Exception:
        # Do not log request bodies, signatures, or the webhook secret.
        logger.exception("Unable to store workflow result")
        return response(503, "Storage temporarily unavailable; redeliver this event")
    logger.info("Workflow result processed: run=%s attempt=%s created=%s", run_id, attempt, created)
    return response(200, "Run stored" if created else "Run already stored")
