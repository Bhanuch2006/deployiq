"""Read-only dashboard API. API Gateway validates Cognito JWTs before invocation."""
import base64
from decimal import Decimal
import json
import logging
import os
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_table = None
SUMMARY_FIELDS = ["run_key", "repository", "run_id", "run_attempt", "name", "conclusion", "head_sha", "head_branch", "html_url", "received_at", "created_at", "run_started_at", "updated_at", "analysis_status", "analysis_source"]
DETAIL_FIELDS = SUMMARY_FIELDS + ["diagnosis", "sanitized_log_excerpt", "fix_verification", "analysis_completed_at", "analysis_error_code", "ai_error_code", "model_id", "token_usage", "benchmark", "benchmark_status", "benchmark_error_code"]


def table():
    global _table
    if _table is None:
        import boto3
        from botocore.config import Config
        _table = boto3.resource("dynamodb", config=Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 2})).Table(os.environ["RUNS_TABLE"])
    return _table


def json_number(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError("Unsupported JSON value")


def response(code, body):
    return {"statusCode": code, "headers": {"content-type": "application/json", "cache-control": "no-store"}, "body": json.dumps(body, default=json_number)}


def select(item, fields):
    return {key: item[key] for key in fields if key in item}


def encode_cursor(key):
    return base64.urlsafe_b64encode(json.dumps(key, default=json_number).encode()).decode()


def decode_cursor(value, repository):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Invalid cursor")
    try:
        key = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
    except Exception:
        raise ValueError("Invalid cursor") from None
    if not isinstance(key, dict) or set(key) != {"run_key", "repository", "received_at"}:
        raise ValueError("Invalid cursor")
    if key["repository"] != repository or not all(isinstance(v, str) and len(v) <= 512 for v in key.values()):
        raise ValueError("Invalid cursor")
    if not key["run_key"].startswith(repository + "#"):
        raise ValueError("Invalid cursor")
    return key


def handler(event, context):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    # Defense in depth: no anonymous reads even if Lambda is invoked without the gateway.
    if not claims.get("sub") or claims.get("token_use") != "id":
        return response(401, {"message": "Sign in to access pipeline history"})
    repository = os.environ["ALLOWED_REPOSITORY"]
    try:
        if event.get("routeKey") == "GET /runs":
            query = event.get("queryStringParameters") or {}
            try:
                limit = int(query.get("limit", "25"))
            except (ValueError, TypeError):
                raise ValueError("Limit must be between 1 and 50") from None
            if not 1 <= limit <= 50:
                raise ValueError("Limit must be between 1 and 50")
            options = {"IndexName": "RepositoryReceivedIndex", "KeyConditionExpression": "repository = :repo", "ExpressionAttributeValues": {":repo": repository}, "ScanIndexForward": False, "Limit": limit}
            if query.get("cursor"):
                options["ExclusiveStartKey"] = decode_cursor(query["cursor"], repository)
            result = table().query(**options)
            return response(200, {"repository": repository, "runs": [select(item, SUMMARY_FIELDS) for item in result.get("Items", [])], "next_cursor": encode_cursor(result["LastEvaluatedKey"]) if result.get("LastEvaluatedKey") else None})
        if event.get("routeKey") == "GET /runs/{runId}/attempts/{attempt}":
            params = event.get("pathParameters") or {}
            run_id = params.get("runId", "")
            attempt = params.get("attempt", "")
            if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id) or not re.fullmatch(r"[1-9][0-9]{0,5}", attempt):
                raise ValueError("Invalid run identity")
            item = table().get_item(Key={"run_key": f"{repository}#{run_id}#{attempt}"}, ConsistentRead=True).get("Item")
            if not item or item.get("repository") != repository or str(item.get("repository_id")) != os.environ["ALLOWED_REPOSITORY_ID"]:
                return response(404, {"message": "Run not found"})
            return response(200, {"run": select(item, DETAIL_FIELDS)})
        return response(404, {"message": "Route not found"})
    except ValueError as error:
        return response(400, {"message": str(error)})
    except Exception:
        logger.error("Dashboard read failed")
        return response(503, {"message": "Pipeline history is temporarily unavailable. Try again shortly."})
