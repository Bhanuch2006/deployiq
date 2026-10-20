# Enable failure analysis

The sample application's EC2 deployment stays separate. The monitoring table now
feeds an analyzer via DynamoDB Streams. Failure/timed_out INSERTs reach diagnosis; successful DeployIQ Cache Benchmark
INSERTs reach the separate artifact importer. This avoids doing AI work inside the webhook.
The analyzer fetches failed-job logs for the exact run attempt, redacts common
secret patterns, selects a bounded excerpt, and calls Groq over HTTPS using openai/gpt-oss-120b.
The rest of the pipeline stays on AWS in us-east-1. Exact evidence quotes are validated locally.
No code fixes or shell commands are executed by the model.

## 1. Create a narrowly scoped GitHub token

GitHub > profile Settings > Developer settings > Personal access tokens >
Fine-grained tokens > Generate new token.

- Name: DeployIQ log reader.
- Resource owner: Bhanuch2006.
- Expiration: 30 days (or a suitable short date through the demo).
- Repository access: Only select repositories > deployiq.
- Repository permissions: Actions > Read-only. Metadata read is automatic.
- Do not grant code write or administration access.

Do not paste this token into chat, code, a workflow, or the CloudFormation template.
In AWS Secrets Manager, us-east-1, Store a new secret > Other type of secret >
Plaintext. Replace the entire editor contents with JUST the token (no JSON,
quotes, key name, or whitespace). Use the default encryption key. Name it
`deployiq/github-actions-token`. Leave automatic rotation off for this prototype.
Store it and copy its Secret ARN. The ARN is safe to provide for configuration.
Secrets Manager storage/API usage may consume credits.

## 2. Create the Groq secret

Verify a short prompt works with openai/gpt-oss-120b in the
[Groq console](https://console.groq.com/), then create a Groq API key.
Never paste it into chat, repository files, frontend variables, or workflow logs.

In AWS Secrets Manager, **us-east-1**:

1. Store a new secret > Other type of secret > Plaintext.
2. Replace the entire editor with ONLY the Groq API key, beginning with `gsk_`.
   Do not use a JSON object, quotes, or a key/value pair.
3. Keep the default `aws/secretsmanager` encryption key.
4. Name it `deployiq/groq-api-key`, leave rotation off, and store it.
5. Copy its **Secret ARN**, not its secret value.

The secret is external to CloudFormation. Storage/API usage may consume AWS
credits. The analyzer role receives GetSecretValue permission for exactly the
GitHub and Groq secret ARNs; the dashboard cannot read either secret.
Use the default encryption key for this guide; custom KMS keys need a separate,
scoped decrypt grant.

Sanitized log excerpts leave AWS and are processed by Groq. Redaction remains
best-effort. Use only the team's demo repository and review the provider's
[data controls](https://console.groq.com/docs/your-data).
Groq account limits still apply; the app additionally limits calls to ten per UTC
day. See [Groq limits](https://console.groq.com/docs/rate-limits).

## 3. Update the existing stack

Regenerated template: infrastructure/monitoring-stack.json.

CloudFormation > deployiq-monitoring > Update stack > Make a direct update >
Replace current template > Upload this file. Keep the existing stack name and
repository parameters. Retain the existing WebhookSecret value (use previous
value). Keep GitHubTokenSecretArn at its existing value. Set the new
**GroqApiKeySecretArn** parameter to the Groq secret ARN (never the API key).
Continue with defaults, acknowledge IAM changes, and submit.
Wait for UPDATE_COMPLETE. Do not delete or recreate the stack: the existing run
history and webhook URL are retained. Review the changes: the table is modified
to enable a stream, not replaced. The analyzer role may read the two selected secrets,
update this table, write its own logs, and report failed events. Bedrock invocation
permission is removed. The Lambda uses AI_PROVIDER=groq and
GROQ_MODEL_ID=openai/gpt-oss-120b, and needs outbound HTTPS access. The supplied
non-VPC Lambda configuration already provides internet access.

It adds a worker Lambda, stream mapping, seven-day logs, and an encrypted SQS
failure queue (14-day retention). DynamoDB Streams is the trigger; SQS here holds
failure notifications after retry/age limits, rather than normal analysis jobs.
The stream mapping starts at LATEST, so generate a NEW failed workflow afterward.
Redelivering a stored webhook does not insert another row or trigger analysis.

## 4. Push the code and run the demo

Push backend/, frontend/, infrastructure/, and README.md. The dashboard
publishing workflow must succeed so the hosted UI can label new results Groq AI. The normal CI
checks the backend and deploys the sample app only if all tests pass.

In GitHub Actions select DeployIQ Diagnosis Demo > Run workflow > main.
Leave install_dependency unchecked. This intentionally fails an import of requests
inside an isolated virtual environment. It does not deploy or break the EC2 app.

After the workflow finishes, inspect its row in deployiq-monitoring-runs:

- analysis_status: completed.
- analysis_source: groq for real AI, or rules for deterministic fallback.
  Historical bedrock records keep their original source label.
- diagnosis: root_cause, evidence, suggested_fix, verification_steps.
- fix_verification: not_verified (the model never verifies its own fix).
- sanitized_log_excerpt and model_id; token_usage if Groq succeeded.
- ai_error_code explains why a fallback was used.

Run the demo again with install_dependency checked. The job installs requests
before importing it, so it should pass. This is a controlled demonstration, not
a performance benchmark. Its successful run is stored without calling AI.

## Troubleshooting and limits

- github_http_401/403: check token expiration, repository scope, Actions read, and
  that Secrets Manager plaintext is ONLY the token.
- github_http_404: confirm exact repository/job, token permissions, log retention.
- failed_job_logs_not_available: logs may be delayed or removed. Stream delivery
  retries twice; failures are reported to the SQS failure destination.
- groq_http_401: verify the Groq API key is valid and active.
- groq_http_403: check Groq account/model access.
- groq_http_429: Groq rate or daily limit; check its console limits before retrying.
- groq_http_400: check model availability and supported request settings.
- groq_secret_invalid_plaintext: store ONLY the key, not JSON or quotes.
- groq_connection_failed: check outbound HTTPS access and provider availability.
- model_response_incomplete / invalid_model_response / model_evidence_not_in_logs:
  output was rejected; a Rules fallback is expected and never labeled AI.
- AccessDeniedException: check the analyzer's permission to read the exact secret
  ARNs (and that both secrets are in us-east-1).
- A failed analysis has analysis_error_code. Examine the analyzer's CloudWatch
  log group for sanitized error codes. Full raw logs and tokens are not logged.

The analyzer uses an atomic daily counter (UTC) in the same table: QUOTA#YYYY-MM-DD.
It allows at most 10 AI attempts per day, across retries. Quota rows are not
pipeline runs. Input is at most 12,000 characters and Groq completion budget at most 2,048 tokens (including reasoning).
Responses are bounded to 64 KiB, with a 30-second HTTP timeout and no automatic
provider retries; stored diagnosis fields remain length-limited.
A completed analysis is cached. Groq failures/invalid output produce a labeled
rules result; they are not automatically regenerated later. To retry one manually,
remove its analysis_status in DynamoDB (and analysis_lock_until only if an old
lease remains after a stopped invocation), then invoke the analyzer in Lambda Test
with the run key and this event (replace the example key):

```json
{"Records":[{"eventName":"INSERT","dynamodb":{"Keys":{"run_key":{"S":"Bhanuch2006/deployiq#RUN_ID#ATTEMPT"}}}}]}
```

Redaction is best-effort, not a guarantee of detecting arbitrary secrets. Only
connect the team's demo repository and avoid deliberately printing credentials.
The analyzer examines at most 300 job metadata entries, downloads up to the first
1 MiB per job for up to 3 failed jobs, and truncates selected log context. Large
logs and long run histories may need a later ingestion implementation.
Evidence quotes establish that the text appeared in the logs; the proposed cause
and fix still require human review and a new passing run.

DynamoDB Streams retries have bounded retention; the SQS destination is an alert
and recovery aid, not a permanent log archive or automatic replay mechanism.
If failure notification arrives, use its run/event information and the retained
DynamoDB row to invoke the analyzer manually after correcting the issue.

The GitHub webhook secret, GitHub log-reader token, and Groq API key serve
different purposes. Keep all private. Both Secrets Manager secrets are external
to the stack and must be deleted separately during cleanup; revoke the Groq key
in Groq as well. Deleting the stack removes analysis
resources and run history, but leaves the EC2/ECR resources intact.


## Verify the migration

After UPDATE_COMPLETE and a successful dashboard publication, run a NEW Diagnosis
Demo with install_dependency unchecked. Refresh the dashboard after completion.
Expect **Groq AI**, exact evidence, and a suggested fix still marked unverified.
In DynamoDB expect analysis_source=groq, model_id=openai/gpt-oss-120b,
analysis_status=completed, and an empty ai_error_code.
Existing cached Rules results do not regenerate automatically. Use a new run for
the first end-to-end check; only reset a historical result if needed afterward.
The successful benchmark importer is unaffected by the provider switch.

Local tests mock provider responses; a real deployed request is required to
verify the key, account limits, model response, and outbound connectivity together.
