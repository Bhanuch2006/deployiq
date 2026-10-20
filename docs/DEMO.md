# DeployIQ faculty demo

Aim for a 6–8 minute walkthrough. Run the workflows once beforehand and keep
completed results open in case live execution takes longer. Never present a
pre-recorded result as a new live result.

## Before presenting

- Sign in to [DeployIQ](https://d27iom2n4u9pw.cloudfront.net/) using the Cognito
  team account. This login is separate from AWS console administration.
- Open GitHub Actions, the dashboard, and the README architecture diagram.
- Confirm the stack is UPDATE_COMPLETE and dashboard publication has passed.
  Confirm the configured GitHub token is still valid and both secrets exist.
- Keep the AWS admin console signed in privately if recovery is needed. Do not
  display secret values, MFA setup screens, or personal credentials.
- Complete both diagnosis-demo variants during rehearsal. Record their run IDs
  and use the **new** failed run, not a historical cached Rules result.
- Keep both measured cache summaries available. If artifacts have expired, use
  retained validated dashboard measurements or saved screenshots and disclose
  their source. Do not invent a fresh measurement.
- Keep unrelated activity low: diagnosis has a ten-attempt UTC daily cap, and
  external model limits may still apply. Do not reset counters to evade limits.

## 1. Explain the problem and architecture — about one minute

Suggested narration:

> A failed CI job often leaves a developer searching through logs. DeployIQ
> collects completed workflow events, extracts failure evidence, and presents an
> AI-assisted explanation with a suggested fix. It also measures one specific
> optimization: pip download-cache reuse.

Show the README diagram. Point out the two delivery paths: the sample service
runs in Docker on EC2, while the dashboard is served by CloudFront from private
S3. The API and authentication stay on AWS; Groq supplies inference.

## 2. Create an intentional failure — about one minute plus workflow time

1. GitHub repository > Actions > **DeployIQ Diagnosis Demo** > Run workflow.
2. Choose `main`. Leave **install_dependency unchecked** and start the run.
3. Open the run. It creates a fresh virtual environment, then imports `requests`
   without installing it. Expect the dependency-check job to fail with:

```text
ModuleNotFoundError: No module named 'requests'
```

Suggested narration:

> This is a controlled failure in a separate workflow. It does not break or
> redeploy our running sample service.

Acceptance: the intended import error appears. A failure caused by permissions,
runner startup, or network setup is not the same demonstration.

## 3. Show the diagnosis — about two minutes

1. Refresh DeployIQ after the failed workflow completes and select its run ID.
2. Show the **Groq AI** source label, likely cause, exact error quote, suggested
   dependency fix, and verification steps.
3. Expand the sanitized excerpt if useful; avoid projecting sensitive logs.
4. Point out **Fix not yet verified for this run**.

Suggested narration:

> The signed webhook stores this completed attempt once. The analyzer reads its
> failed-job logs, redacts common secrets, and sends a bounded excerpt to Groq.
> We validate that the returned evidence actually occurs in that excerpt.
> The result is advice; the model has not executed or verified the fix.

Historical evidence: [run 39475900064](https://github.com/Bhanuch2006/deployiq/actions/runs/39475900064)
was captured in the hosted dashboard with Groq AI and the missing-import quote.
Use it as a disclosed backup if a new request cannot finish during the demo.

Acceptance: a new failed run shows a completed diagnosis with **Groq AI** and
matching evidence. **Rules** is a fallback, not proof that Groq answered.

## 4. Apply the reviewed correction — about one minute plus workflow time

1. Start **DeployIQ Diagnosis Demo** again on `main`.
2. This time enable **install_dependency**.
3. Show the install step and the successful import in GitHub Actions.
4. Refresh DeployIQ and show the new passing run alongside the failed one.

Suggested narration:

> A human reviewed the dependency suggestion. This workflow variant explicitly
> installs requests before the same import check. The successful run is evidence
> that this controlled test now passes; DeployIQ did not autonomously edit code.

Acceptance: the fix-enabled run passes with `Dependency check passed` in its log.
Record the run ID during rehearsal. The original failed run and its unverified
label remain historical; there is no automatic failure-to-fix correlation.

## 5. Show the cache experiment — about one minute

Select a completed **DeployIQ Cache Benchmark** run and show the comparison,
cold fill, and raw samples. Open its GitHub summary if needed.

| Recorded run | Baseline median | Warm median | Cold fill | Warm change |
| --- | --- | --- | --- | --- |
| [38903048448](https://github.com/Bhanuch2006/deployiq/actions/runs/38903048448) | 2.29 s | 1.82 s | 2.42 s | 20.73% faster |
| [38908962867](https://github.com/Bhanuch2006/deployiq/actions/runs/38908962867) | 2.90 s | 2.77 s | 3.58 s | 4.30% faster |

Suggested narration:

> We used a fresh environment for every install and pinned dependencies. Each
> run compares four uncached samples with three warm-cache samples, reporting
> the first cold fill separately. These are installation-time measurements,
> not whole-pipeline or deployment speedups. The different gains demonstrate
> variability; we do not promise a fixed percentage.

Percentages use unrounded data. Both reports should remain visible in the
presentation. A new benchmark is optional; its outcome may be slower or faster.
The importer does not call Groq or consume the AI request allowance.

## If something stalls

| Symptom | Next check / honest demo fallback |
| --- | --- |
| Run not listed | Confirm it completed, refresh, and check the signed webhook's recent delivery status. A duplicate delivery does not insert a new row. |
| Diagnosis pending | Allow asynchronous processing, then inspect analysis_status and analysis_error_code in DynamoDB or sanitized analyzer CloudWatch errors. |
| Rules instead of Groq AI | Inspect ai_error_code. groq_http_401 means key access needs checking; groq_http_429 means provider limits. Use a disclosed recorded Groq result if live inference is unavailable. |
| No benchmark measurements | Inspect benchmark_status / benchmark_error_code. Check successful-run stream filtering and artifact availability; see the experiment guide. |
| Daily AI cap reached | Use a prior result or wait for the UTC-day allowance. Do not describe the fallback as AI. |
| Demo cannot finish live | Show the rehearsed completed runs and explain their date and run IDs. |

Do not delete run history, replace the stack, rotate working secrets, or reset
cached results on stage. Recovery details belong in the
[analysis guide](../infrastructure/ANALYSIS_SETUP.md).

## Questions to be ready for

- **Why Groq?** Bedrock access was blocked by the account's model quotas; the
  inference integration was changed while keeping the AWS processing pipeline.
- **Does AI fix the code?** No. It proposes evidence-backed advice; a human applies
  a correction and checks another run.
- **Is the diagnosis guaranteed correct?** No. Exact-quote checks verify the
  evidence text, not causal correctness.
- **Is everything public?** The dashboard shell has a public HTTPS address; the
  pipeline read API requires a Cognito ID token. The project is one shared team
  workspace, not a multi-tenant service.
- **Did caching speed up deployment by 20%?** No. The recorded 20.73% and 4.30%
  gains apply to warm pip installation only, under the documented experiment.
- **What would you improve next?** More independent benchmark runs, failure/fix
  correlation, broader diagnosis evaluation, and better operational recovery.

## Rehearsal evidence record

Fill this out using real completed runs; keep credentials out of these notes.

| Check | Run ID / observation |
| --- | --- |
| Intentional missing-dependency failure | To record during rehearsal |
| Completed Groq diagnosis with matching quote | To record during rehearsal |
| Fix-enabled passing rerun | To record during rehearsal |
| Cache report and raw samples visible | To record during rehearsal |
| Dashboard and sign-in work on presentation device | To record during rehearsal |
