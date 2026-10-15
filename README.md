# DeployIQ

AI-assisted DevOps pipeline monitoring and optimization on AWS.

## Milestone 1: sample application and CI

Implemented: FastAPI sample service, health endpoint, release-version endpoint,
pytest checks, non-root Docker image, and GitHub Actions tests plus container smoke check.
The dashboard, AWS resources, GitHub ingestion, and AI analyzer are future milestones.
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
using GitHub OIDC and DeployIQGitHubECRRole. It does not start an AWS server yet.
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
