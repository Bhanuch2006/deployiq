# DeployIQ dashboard setup

The React dashboard reads the existing monitoring table through authenticated,
read-only API routes. The frontend remains part of this GitHub/AWS project; no
separate Sites hosting or external database is created. It runs locally for this
milestone; publishing the static build to AWS is a later step.

## 1. Update the same CloudFormation stack

Upload the regenerated infrastructure/monitoring-stack.json through
CloudFormation > deployiq-monitoring > Update stack > Make a direct update >
Replace current template. Preserve all existing parameters, including the previous
WebhookSecret and GitHubTokenSecretArn. Keep DashboardOrigin at
`http://127.0.0.1:5173`. Review that the table is modified, not replaced. Submit
with IAM acknowledgement and wait for UPDATE_COMPLETE.

This adds Cognito (a private team user pool and public app client), an HTTP API JWT
authorizer, a read-only Lambda, and a repository/time index on the existing table.
The index backfills existing runs. It excludes QUOTA rows because they do not have
a repository attribute. Reads of the index are eventually consistent.
It does not change the webhook URL or deploy the frontend to a public website.

Copy DashboardApiUrl, DashboardClientId, and DashboardUserPoolId from Outputs.
These values are public identifiers, not credentials. Leave the Secrets Manager
GitHub token and WebhookSecret private.

## 2. Create your team login

Cognito > User pools > find the pool from DashboardUserPoolId > Users > Create user.
Use a username, for example `mahesh`. Choose not to send an invitation if the
console offers that option. Set a temporary password meeting the policy:
12+ characters, uppercase, lowercase, a number, and a symbol. Keep it private.
The pool does not require an email address or phone number. Do not mark an email
as verified unless you have actually verified it.

The dashboard handles the first-sign-in NEW_PASSWORD_REQUIRED challenge. You will
choose a permanent password there. The dashboard has no public signup or browser-based password reset; admins manage accounts.

All admin-created users in this pool share read access to this one team's registered
repository. This is a single-team prototype, not per-user multi-tenant isolation.
The Lambda role cannot write records or read the GitHub token secret.

## 3. Run locally

In a laptop terminal:

```bash
cd /home/mahesh/Documents/Codex/2026-10-16/j/outputs/deployiq/frontend
npm ci
npm run dev
```

Open exactly `http://127.0.0.1:5173` (the configured CORS origin).
Under Connection settings, enter DashboardApiUrl and DashboardClientId, then Save
connection. These non-secret identifiers are stored locally for convenience.
Sign in using the username and temporary password you created, and set your new
password when asked.

Alternatively copy frontend/.env.example to frontend/.env.local and set
VITE_API_BASE_URL and VITE_COGNITO_CLIENT_ID, then restart Vite. Never put a password,
webhook secret, AWS access key, or GitHub token in any VITE_ variable: they are
compiled into browser assets. AWS region is us-east-1 for this implementation.

## 4. Verify the experience

- The list contains your real runs, most recent first, with pagination.
- Selecting a run loads its details, evidence, suggested fix, and sanitized excerpt.
- The current Bedrock quota problem appears as a Rules result, not AI success.
- Refresh reloads list data and selected details. It is not an automatic live feed.
- Search and Passed/Failed filters operate on loaded runs; Load older runs fetches
  another page. Metrics are explicitly limited to loaded history.
- Success rate is successful / (successful + failed + timed-out). Cancelled and
  skipped runs are excluded. No build-duration improvements are invented.
- Sign out clears the in-memory session. A page reload also requires sign-in.
- Calling GET /runs without a Cognito ID token returns 401 through API Gateway.

Tokens are held in memory, not localStorage or URLs. Cognito validates credentials;
API Gateway checks token signature, issuer, audience, and expiry. The read Lambda
also requires an ID-token claim and scopes queries to the configured repository.
Local logout does not invalidate an already issued JWT on the server; tokens expire
after 30 minutes. Each run's log excerpt is potentially sensitive and is only
returned by the authenticated detail route.

## Troubleshooting

- Login fails: check the exact client ID and pool, username, password, and whether
  the temporary password has expired. The app client must have no client secret.
- CORS error: use 127.0.0.1:5173 exactly, not localhost:5173. If hosting later, update
  DashboardOrigin to that HTTPS origin via CloudFormation.
- 503 while the index is being built: wait for stack completion and refresh.
- Empty history: verify this is the same API stack/repository and inspect DynamoDB.
- Sign-in credentials are never required to build the static frontend.

## Build and push

```bash
cd /home/mahesh/Documents/Codex/2026-10-16/j/outputs/deployiq
git add frontend/ backend/ infrastructure/ .github/workflows/ci.yml README.md
git commit -m "Add authenticated pipeline dashboard"
git push
```

CI runs frontend unit tests and a production build as well as existing backend
and sample app checks. It still deploys only the sample app automatically.
CloudFormation updates and dashboard publication are separate steps for now.

`npm run build` in frontend/ produces dist/ for later static hosting. No mock runs
or fake analytics are included in the production dashboard.
