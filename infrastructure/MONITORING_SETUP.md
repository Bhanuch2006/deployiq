# Deploy the monitoring backend

This stack creates an HTTPS webhook endpoint, Python Lambda, a DynamoDB table,
and seven-day CloudWatch logs. It does not modify EC2 or its IAM roles.
There is no dashboard or AI analysis yet. The endpoint only accepts registered,
signed repository events; there is no public API for reading stored data.

## Create the stack

1. Generate a random webhook secret locally: `openssl rand -hex 32`.
   Keep it in your password manager. Do not paste it into chat or commit it.
2. In CloudFormation, us-east-1, choose Create stack > With new resources (standard).
3. Choose an existing template > Upload a template file. Upload
   `infrastructure/monitoring-stack.json` from this repository.
4. Name the stack `deployiq-monitoring`. Enter the random WebhookSecret.
   Leave AllowedRepository and AllowedRepositoryId at their defaults.
5. Keep other options at defaults, acknowledge IAM resource creation, and create.
6. Wait for CREATE_COMPLETE. Copy WebhookUrl from the Outputs tab.

The template masks the secret parameter with NoEcho. Lambda stores it encrypted
at rest in its environment; AWS admins with configuration access can retrieve it.
The generated template contains a reference to the parameter, never its value.

## Connect GitHub

In Bhanuch2006/deployiq > Settings > Webhooks > Add webhook:

- Payload URL: WebhookUrl from CloudFormation (including /webhooks/github).
- Content type: application/json.
- Secret: the same random secret used in the stack.
- SSL verification: enabled.
- Events: Let me select individual events. Uncheck Pushes; select Workflow runs.
- Active: checked.

The initial ping should receive 200 and a pong response. A workflow run already
completed before webhook registration is not imported automatically. In Actions,
run DeployIQ CI manually on main, or push a real commit. Completed events are
stored; requested/in_progress events are acknowledged and ignored.

## Verify real ingestion

1. In webhook Recent deliveries, inspect workflow_run/completed: expect HTTP 200,
   with Run stored. Inspect redelivery: expect Run already stored and one record.
2. In DynamoDB > Tables > deployiq-monitoring-runs > Explore table items, inspect
   repository, run_id, run_attempt, conclusion, head_sha, and received_at.
3. Re-running a workflow produces a distinct attempt record.

GitHub does not automatically redeliver all failed webhook deliveries. If an event
fails (including 429 throttling or 503 storage failure), use Redeliver after fixing
it. A future durable queue and reconciliation job will improve recovery.
No duration is inferred from updated_at: it is not guaranteed to be the exact
completion time. Job timings will be fetched separately for measured analytics.

## Development

```bash
python -m pip install -r backend/requirements-dev.txt
python -m unittest discover -s backend/tests -v
python infrastructure/scripts/build_monitoring_template.py
```

Regenerate and commit the template whenever handler.py changes; CI checks this.
To update AWS, update the same CloudFormation stack with the regenerated template
and retain the existing secret parameter. Changes are not auto-deployed by CI yet.

## Cleanup

Delete the GitHub webhook, then delete the deployiq-monitoring stack. This removes
the run table and its data, Lambda, API, role, and log group. Export data first if
needed. EC2 and ECR are separate resources and are not removed by this stack.
