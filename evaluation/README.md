# Measured cache experiment

This is a repeatable pip-cache experiment, not an assertion that caching always
improves whole-pipeline time. No benchmark results are shipped with the code.

## Enable and run

1. Update the existing deployiq-monitoring CloudFormation stack with the latest
   infrastructure/monitoring-stack.json. Preserve ALL existing parameters. This
   updates the analyzer to import successful benchmark artifacts and the read API
   to return benchmark details. No additional IAM permissions or secrets are needed.
2. After UPDATE_COMPLETE, commit and push the changed files (evaluation/, backend/,
   frontend/, infrastructure/, .github/workflows/, README.md, and .gitignore).
3. Wait for DeployIQ CI and DeployIQ Dashboard to pass. The latter publishes the
   new benchmark detail panel to CloudFront.
4. In Actions, choose DeployIQ Cache Benchmark > Run workflow > main.
5. Wait for success. Its GitHub run summary contains the measured comparison and
   every raw timing. Download the cache-benchmark-RUN_ID-ATTEMPT artifact if needed.
6. Refresh the hosted dashboard. Select this benchmark run. The detail panel shows
   medians, the cold fill, the warm-cache change, and the eight raw samples.

## Method

- One GitHub-hosted ubuntu-latest runner with Python 3.12.
- Four rounds, each with no-cache and cached installation. Variant order alternates.
- Each sample uses a NEW virtual environment; this prevents a false speedup from
  packages already being installed. The pip cache directory is isolated from the
  runner's default cache and from setup-python caching.
- Dependencies, including transitives, are pinned in requirements-benchmark.txt.
- Baseline uses --no-cache-dir for all four measurements.
- Cached round 1 starts with an empty cache; rounds 2–4 reuse that cache.
- Only the pip-install subprocess is timed with a monotonic clock. Virtualenv
  creation, pip check, and the app-import check are outside the timed section.
- Every installed environment must have the same resolved dependencies, pass
  pip check, and successfully import the real sample app.
- Compare the median of FOUR baseline samples against THREE warm-cache samples.
  The one cold-fill sample is reported separately and excluded from that comparison.
- Change (%) = (baseline median - warm median) / baseline median * 100.
  Negative results are shown as slower, never silently converted into a speedup.

This measures reuse of a local pip download cache. It does NOT measure GitHub's
remote cache upload/download overhead, total job time, deployment time, or changes
to production reliability. Network variation and shared-runner effects remain;
small differences should not be described as statistically established wins.
Repeat the whole workflow for more independent evidence and keep all reports.
For slides, report sample counts and variability, not only a percentage.

## How data reaches the dashboard

The completed workflow event inserts its usual run row in DynamoDB. A stream
filter also sends successful runs named DeployIQ Cache Benchmark to the worker.
The worker downloads ONLY the artifact for that exact run attempt, validates
repository/commit/run identity and sample shape, recomputes the medians, then
stores a benchmark map on the run. It does not invoke Bedrock or consume the AI
call allowance. Existing signed webhook validation, Cognito login, and API
repository restrictions still apply.

GitHub Actions read-only permission already covers artifact downloads. The
artifact ZIP and JSON sizes are bounded; downloads do not forward the GitHub token
to the signed download host. Reports expire in GitHub after 14 days; the validated
measurements in DynamoDB persist until removed with your monitoring data.

A normal successful run is NOT an experiment and is not fetched or measured.
The dashboard contains no invented duration or improvement numbers.

## Troubleshooting

- New workflow missing: confirm it was committed and pushed to main.
- Only an ordinary run row appears: update the stack before running the experiment.
  Existing duplicate webhook redelivery does not trigger another INSERT.
- benchmark_status failed: read benchmark_error_code. Check token expiration and
  Actions read access if GitHub reports 401/403; check artifact retention for 404.
- Artifact delivery can be delayed. The stream retries are bounded. After fixing
  a failure, rerun the benchmark or manually invoke the worker with the existing
  row key, as described in infrastructure/ANALYSIS_SETUP.md.
- Bedrock's current zero quota does not prevent benchmark import.

Local unit checks do not install packages or generate performance claims:

```bash
python -m unittest discover -s evaluation/tests -v
```
