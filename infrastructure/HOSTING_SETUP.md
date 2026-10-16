# Publish the dashboard on AWS

This extends the EXISTING deployiq-monitoring stack with a private S3 bucket,
CloudFront distribution, origin access control, cache/security policies, and a
GitHub publishing role. The UI is publicly downloadable; Cognito sign-in and the
JWT-protected API continue to protect all pipeline data and log excerpts.
No custom domain, certificate purchase, or dedicated server is needed for hosting.
S3 storage/requests and CloudFront usage can consume AWS credits.

## 1. Update the existing stack

In CloudFormation, us-east-1, update deployiq-monitoring using
infrastructure/monitoring-stack.json. Preserve EVERY existing parameter value,
including WebhookSecret, GitHubTokenSecretArn, repository registration, and
DashboardOrigin. Keep DashboardOrigin at http://127.0.0.1:5173 for local development.
The generated API CORS configuration now also allows the exact CloudFront origin.

Review changes, acknowledge IAM creation, and submit. Do not delete/recreate the
stack. Wait for UPDATE_COMPLETE; CloudFront creation may take several minutes.
Until frontend files are published, its URL can show AccessDenied. Do not make the
bucket public or enable S3 static website hosting to fix this.

New Outputs:

- DashboardUrl: HTTPS address to share with your faculty.
- DashboardBucketName: private origin bucket.
- DashboardDistributionId: CloudFront distribution.
- DashboardPublishRoleArn: role restricted to this repository's main branch.

Existing DashboardApiUrl and DashboardClientId remain unchanged.

## 2. Add GitHub repository variables

Repository > Settings > Secrets and variables > Actions > Variables >
New repository variable. Use Variables, not Secrets; these are public identifiers.

| Variable name | CloudFormation output |
| --- | --- |
| DASHBOARD_BUCKET_NAME | DashboardBucketName |
| DASHBOARD_DISTRIBUTION_ID | DashboardDistributionId |
| DASHBOARD_PUBLISH_ROLE_ARN | DashboardPublishRoleArn |
| DASHBOARD_API_URL | DashboardApiUrl |
| DASHBOARD_CLIENT_ID | DashboardClientId |

Do not add root access keys or the GitHub log-reader token. The publish role uses
the existing GitHub OIDC provider and can only list/upload this bucket and create
invalidations on this distribution. It cannot read DynamoDB or Secrets Manager.

## 3. Push and publish

From the project root:

```bash
git add frontend/ infrastructure/ .github/workflows/ backend/ README.md
git commit -m "Host the authenticated dashboard on S3 and CloudFront"
git push
```

The separate DeployIQ Dashboard workflow tests/builds React, authenticates to AWS,
uploads hashed assets, uploads index.html last, then requests cache invalidation.
It runs for main frontend/publish-workflow changes and can be run manually. It is
skipped until DASHBOARD_BUCKET_NAME exists; if you configured variables after the
push, use Actions > DeployIQ Dashboard > Run workflow > main.

The usual DeployIQ CI workflow continues to test/deploy the sample app separately.
The publishing job builds connection values from the repository variables; it
never depends on your laptop's ignored .env.local.

## 4. Verify the hosted version

Wait for the publishing job to succeed, then open DashboardUrl from Outputs.
CloudFront invalidation is asynchronous; allow a short propagation period and
refresh if the previous page is still visible. Sign in with your EXISTING Cognito
username and permanent password. Your old user and records are retained.

Check that real workflow runs load and failure details display. Test in a private
browser window: pipeline data must require sign-in. You can stop your laptop's
Vite server; it is not involved in hosting. The sample application remains on EC2.

The bucket's direct S3 object URL should deny anonymous reads. CloudFront's domain
is allowed to fetch through origin access control. HTTPS, CSP, content-type sniffing
protection, frame restrictions, and a referrer policy are configured at CloudFront.
The frontend uses the root path; there are currently no deep-linked SPA routes.

## Updating and recovery

- Future pushes changing frontend/ on main publish automatically.
- New hashed assets have a one-year immutable cache lifetime. index.html requires
  revalidation. Root and index.html are invalidated on publication.
- Old assets are not deleted during deployment because existing tabs may still
  reference them. Storage should be reviewed periodically; do not blindly expire
  current assets by age because a release may remain current for a long time.
- If upload fails, inspect the workflow. Old index.html stays active when asset
  upload fails. A later index upload or invalidation error requires a retry; the
  workflow does not claim atomic rollback of the website release.
- Missing configuration: ensure all five repository variables are set exactly.
- 403 before first upload: publish the files; keep S3 private.
- Login works but reads fail: verify DASHBOARD_API_URL, client ID, and the exact
  CloudFront domain in API CORS. Run a new publish after correcting variables.

## Cleanup

Delete/disable the CloudFront resources through CloudFormation when done. The S3
bucket has Retain policies, so deleting the stack intentionally leaves its files
and bucket for recovery. Empty and delete that retained bucket separately when
no longer needed. The entire monitoring stack also includes your DynamoDB data
and Cognito users: deleting that stack removes them. Export required data first.
