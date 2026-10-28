# Free public cloud observer

## Verified cloud execution

The repository was verified public through GitHub's API. GitHub's
[official billing documentation source](https://github.com/github/docs/blob/main/content/billing/concepts/product-billing/github-actions.md)
confirms that standard hosted runners are free for public repositories and that
logs/job summaries do not consume artifact storage. This workflow allocates no
artifact/cache storage and never selects a larger paid runner.

Two actual runs passed:

* [Initialization: run 40767661130](https://github.com/ahyadzyoud-cyber/content-rewards-automation-/actions/runs/40767661130)
  created sequence 1 on `rewards-observation-state`.
* [Restoration: run 40767922065](https://github.com/ahyadzyoud-cyber/content-rewards-automation-/actions/runs/40767922065)
  restored that checkpoint and saved sequence 2 with the first run as predecessor.

The inspected report says `blocked_no_permitted_feed`, `live_publishing=false`
and `production_verified=false`. GitHub reports zero workflow artifacts.
The recurring event is configured; its next scheduled execution has not yet
been observed. These completed runs were explicitly dispatched cloud checks.

The existing project includes an observation workflow that runs on GitHub while
the owner's computer is off. `.github/workflows/free-observer.yml` uses a
standard `ubuntu-latest` runner only while the repository is public. The public
repository/free-standard-runner condition must remain true; the job skips before
runner allocation if the repository becomes private. No paid plan, larger
runner, artifact storage or Actions cache is configured.

The workflow persists its small public checkpoint in the separate Git branch
`rewards-observation-state`. It never switches the source checkout, rewrites
`main`, creates a worktree or reads the private SQLite ledger. Its two files are
`state.json` and `report.json`, with a combined maximum of 128 KiB per checkpoint.
Only public unverified campaign observations and explicitly permitted public
no-cost JSON feed settings are allowed. Credentials, account identities, payout
records, earnings, video files, local material paths and publication approvals
do not belong on this branch. Git history accumulates public checkpoints and is
subject to ordinary repository size limits; it is not a private secret store.

## First initialization and verification

After this workflow is committed to the public default branch:

```bash
gh workflow run free-observer.yml --ref main -f initialize_state=true
```

Initialization is accepted only when `git ls-remote --exit-code` positively
reports the checkpoint branch absent. Permission/network failures are not
interpreted as absence. If a checkpoint already exists, initialization stops
rather than resetting it. Verify that first run succeeds and inspect the branch
before a second ordinary run:

```bash
gh workflow run free-observer.yml --ref main
```

The second run restores the exact remote tip, validates the state envelope,
producer metadata, report and tree, and writes its next sequence with the old
commit as parent. The commit trailer `GitHub-Run-ID` identifies its producer;
the next report's `previous_run_id` names that prior run. A normal non-force Git
push fails on concurrent checkpoint changes. A failed push never resets or
overwrites another successful checkpoint. The workflow's concurrency group
serializes normal scheduled/dispatch execution.

The built-in workflow token has only `contents: write` permission. Checkout's
supported Git authentication is reused; the script does not extract the token
or call repository-variable, billing or artifact APIs. If repository rules block
the checkpoint push, grant the workflow the narrowly required repository write
access through its legitimate settings. Do not supply a password or token in
chat, force a push or disable branch protections merely to make the run pass.

## Recurrence

The cron `17 */6 * * *` schedules four runs per day at **03:17, 09:17, 15:17 and
21:17 in Asia/Amman**. GitHub schedules run from the default branch, can be
delayed or dropped during high load, and may be disabled for inactive public
repositories. This is scheduled observation, not a continuously running server
or guaranteed real-time scheduler.

No artifact retention or paid artifact storage is required. Git history keeps
the public checkpoints; do not put private business data in it. Missing,
corrupt, oversized, unrecognized or conflicting checkpoint state stops a run.
Scheduled runs never initialize missing state silently. Preserve/recover a
verified checkpoint rather than deleting the branch to bypass a failure.

## Discovery and live limits

Without a provider-approved feed, the report correctly says
`blocked_no_permitted_feed`. A successful empty observation run demonstrates
cloud execution and checkpoint persistence, not real provider discovery.

A public feed can be added only through a dispatch with `public_feed_url` and
`confirm_permitted_public_no_cost_feed=true`. That attestation covers automated
access, free use and public redistribution. It must be an authorized normalized
JSON source; neither this workflow nor its helper scrapes Whop or Vyro webpages,
guesses private APIs, logs into creator accounts or bypasses restrictions.

Every report has `live_publishing=false` and `production_verified=false`.
This workflow does not invoke publishing, rendering, earnings collection or the
general application schedule runner and receives no social-account credentials.
Current campaign rights/Jordan eligibility, account authorization, payout setup,
permitted API automation, approved footage and first-video review remain
separate prerequisites for a live business. The separate Docker worker remains
the production-host preparation path once those prerequisites and persistent
private state are available.
