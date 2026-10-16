# Enable failure analysis

The sample application's EC2 deployment stays separate. The monitoring table now
feeds an analyzer via DynamoDB Streams. Only INSERTs whose conclusion is failure
or timed_out reach the analyzer. This avoids doing AI work inside the webhook.
The analyzer fetches failed-job logs for the exact run attempt, redacts common
secret patterns, selects a bounded excerpt, and calls Amazon Nova Micro through
Bedrock Converse in us-east-1. Exact evidence quotes are validated locally.
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

## 2. Verify Bedrock access

In Amazon Bedrock, us-east-1, try Amazon Nova Micro in the text/chat playground.
The model ID used is amazon.nova-micro-v1:0. This is an inference API, not a
provisioned model or a dedicated endpoint. Account/model restrictions may prevent
inference; do not change account plans silently to resolve them. The worker
records access errors and clearly labels a rules fallback instead of claiming AI.

## 3. Update the existing stack

Regenerated template: infrastructure/monitoring-stack.json.

CloudFormation > deployiq-monitoring > Update stack > Make a direct update >
Replace current template > Upload this file. Keep the existing stack name and
repository parameters. Retain the existing WebhookSecret value (use previous
value). Enter the Secret ARN in the new GitHubTokenSecretArn parameter.
Continue with defaults, acknowledge IAM changes, and submit.
Wait for UPDATE_COMPLETE. Do not delete or recreate the stack: the existing run
history and webhook URL are retained. Review the changes: the table is modified
to enable a stream, not replaced. The new role may only read the selected token,
update this table, invoke Nova Micro, write its own logs, and report failed events.

It adds a worker Lambda, stream mapping, seven-day logs, and an encrypted SQS
failure queue (14-day retention). DynamoDB Streams is the trigger; SQS here holds
failure notifications after retry/age limits, rather than normal analysis jobs.
The stream mapping starts at LATEST, so generate a NEW failed workflow afterward.
Redelivering a stored webhook does not insert another row or trigger analysis.

## 4. Push the code and run the demo

Push backend/, infrastructure/, .github/workflows/, and README.md. The normal CI
checks the backend and deploys the sample app only if all tests pass.

In GitHub Actions select DeployIQ Diagnosis Demo > Run workflow > main.
Leave install_dependency unchecked. This intentionally fails an import of requests
inside an isolated virtual environment. It does not deploy or break the EC2 app.

After the workflow finishes, inspect its row in deployiq-monitoring-runs:

- analysis_status: completed.
- analysis_source: bedrock for real AI, or rules for deterministic fallback.
- diagnosis: root_cause, evidence, suggested_fix, verification_steps.
- fix_verification: not_verified (the model never verifies its own fix).
- sanitized_log_excerpt and model_id; token_usage if Bedrock succeeded.
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
- AccessDeniedException in ai_error_code: review Bedrock model/account access and
  invocation policy. Rules are not an AI result.
- A failed analysis has analysis_error_code. Examine the analyzer's CloudWatch
  log group for sanitized error codes. Full raw logs and tokens are not logged.

The analyzer uses an atomic daily counter (UTC) in the same table: QUOTA#YYYY-MM-DD.
It allows at most 10 Bedrock attempts per day, across retries. Quota rows are not
pipeline runs. Input is at most 12,000 characters and output at most 700 tokens.
A completed analysis is cached. Bedrock failures/invalid output produce a labeled
rules result; they are not automatically regenerated later. To retry one manually,
remove its analysis_status in DynamoDB, then invoke the analyzer in Lambda Test
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

The existing GitHub webhook secret and GitHub log-reader token serve different
purposes. Keep both private. The Secrets Manager secret is external to the stack;
it must be deleted separately during cleanup. Deleting the stack removes analysis
resources and run history, but leaves the EC2/ECR resources intact.
