# DeployIQ

AI-assisted DevOps pipeline monitoring and optimization on AWS.

## Milestone 1: sample application and CI

Implemented: FastAPI sample service, health endpoint, release-version endpoint,
pytest checks, non-root Docker image, and GitHub Actions tests plus container smoke check.
The sample app deploys to EC2. Signed GitHub run ingestion is implemented in
backend/webhooks/handler.py, with a deployable CloudFormation stack.
Failure-analysis code and stack resources are implemented; see the setup guide
to enable them in AWS. The React dashboard and authenticated read API are implemented; deployment
and login setup are described below.
No AWS resources are created by this starter.

### Run locally (Linux)

Python 3.12 is the CI and container target; Python 3.12 or newer is suitable for local setup.

```bash
cd sample-app
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
uvicorn app:app --reload
```

Open http://127.0.0.1:8000/health and http://127.0.0.1:8000/docs.
Stop the server with Ctrl+C.

### Run with Docker

From the repository root, with a running Docker daemon accessible to your user:

```bash
docker build -t deployiq-sample ./sample-app
docker run --rm -p 127.0.0.1:8000:8000 -e APP_VERSION=demo-001 deployiq-sample
```

### Publish to GitHub

Create an empty repository named `deployiq` on GitHub, then run from this folder:

```bash
git init
git add .
git commit -m "Initialize DeployIQ sample application and CI"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/deployiq.git
git push -u origin main
```

Replace YOUR_USERNAME. Check the repository's Actions tab for DeployIQ CI.
It tests the application, builds the container, and checks its health endpoint.
On main pushes or manual main runs, it also uploads the tested image to private ECR
using GitHub OIDC and DeployIQGitHubECRRole. It then deploys that exact image to the existing EC2 demo server through Systems Manager.
Attach infrastructure/github-deploy-policy.json to DeployIQGitHubECRRole before pushing.
Deployment first checks a candidate on localhost:8001, then replaces the port-80
container, with a brief interruption. A failed replacement attempts to restore the
previous container and fails CI. The SSM runner reports remote success or failure.
Concurrent workflow runs do not cancel an active deployment. Server-side locking
also prevents overlapping container replacements. The instance must be running and
online in Systems Manager. It is currently i-0e4717493127d0d23 in us-east-1.
Each image tag includes the commit SHA, run ID, and attempt, so reruns work with
immutable ECR tags. Pull requests and other branches do not upload images.

The required role trust policy is in infrastructure/github-trust-policy.json.
It restricts access to this repository and main branch using their numeric IDs.

## Team modules

| Folder | Responsibility |
| --- | --- |
| infrastructure/ and .github/workflows/ | Member 1: AWS, Docker, CI/CD |
| ai-engine/ | Member 2: log diagnosis and optimization |
| backend/ | Member 3: APIs, GitHub events, queue, storage |
| frontend/ | Member 4: dashboard and analytics |
| evaluation/ | Shared: measured before/after results |

## Next milestones

1. Push this starter and confirm both CI jobs pass.
2. Confirm the AWS account expiration date, region, credits, and service access.
3. Add infrastructure as code and secure GitHub OIDC deployment.
4. Ingest signed GitHub workflow events, persist runs, and queue analysis.
5. Add failure diagnosis, authentication, dashboard, and measured optimization.

Keep credentials out of Git. The planning target is $60 total AWS spend;
alerts are not spending caps. No real performance improvements have been measured yet.

## Monitoring backend

See [monitoring setup](infrastructure/MONITORING_SETUP.md) to deploy
`infrastructure/monitoring-stack.json` through CloudFormation. This creates
API Gateway → signature-verifying Lambda → DynamoDB. Completed workflow
attempts are stored once, with repository name and numeric ID checks.
The infrastructure is prepared locally and must be deployed separately.

## Failure analysis

Follow [analysis setup](infrastructure/ANALYSIS_SETUP.md) to configure the
read-only GitHub token and update the existing monitoring stack. DynamoDB Streams
triggers failed-run analysis asynchronously. Bedrock diagnoses must quote actual
log evidence; a rules fallback is labeled explicitly. AI is capped at 10 attempts
per UTC day, and fixes remain unverified until a human checks a new CI run.
The manual DeployIQ Diagnosis Demo workflow provides a repeatable failure/fix.

## Dashboard

The React frontend in frontend/ shows real run history and failure details.
Follow [dashboard setup](infrastructure/DASHBOARD_SETUP.md) to update the monitoring
stack, create a Cognito team login, and run the interface locally. Its read-only
API requires a verified ID token; public signup is disabled. All invited team
users share this one repository. AWS hosting resources and a separate dashboard publishing workflow are prepared;
follow the hosting setup guide to enable them.

## AWS dashboard hosting

Follow [hosting setup](infrastructure/HOSTING_SETUP.md) to update the existing
stack with private S3 and CloudFront HTTPS delivery. Set the five GitHub repository
variables from stack Outputs, then run DeployIQ Dashboard. Main-branch frontend
changes publish automatically. Authentication and pipeline data stay on the
existing Cognito/API/Lambda/DynamoDB backend.
