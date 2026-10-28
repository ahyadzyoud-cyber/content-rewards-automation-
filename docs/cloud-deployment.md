# Cloud execution without the owner's computer

The existing Docker worker is suitable for an already authorized persistent
host. No hosting plan, paid subscription or cloud account has been activated.
The repository also includes a **GitHub Actions observation dry run with a
default-disabled recurring job**, which runs on GitHub's cloud runner while the
owner's computer is off after its execution gates have been satisfied.
It is not an authorized publishing deployment or proof that the business is live.

## Implemented cloud dry run

Workflow: `.github/workflows/cloud-worker.yml` (Actions display name
**Cloud observation dry run**).

The job installs frozen dependencies, restores the exact prior observation
artifact, optionally reads a provider-approved public no-cost normalized JSON
feed, computes explained rankings, and saves public observations and a report.
It has no YouTube, Instagram, Whop or Vyro account tokens and never invokes
publication, video generation, campaign submission, payout or the general
schedule runner. Missing campaign access is reported `blocked_no_permitted_feed`,
not counted as successful provider discovery. Public feed assertions cannot
verify their own Jordan eligibility, material rights or account acceptance.

GitHub's free standard-runner eligibility and available account quota have not
been verified from this environment. Standard runners for public repositories
and limited private-repository allowances have different billing rules. Before
dispatching, verify the repository's visibility, account Actions allowance and
spending controls directly in GitHub. The dispatch requires an explicit
`confirm_free_usage` attestation. A six-hour UTC cron declaration is present, but
its job condition requires **both** repository variables
`REWARDS_ENABLE_SCHEDULED_DRY_RUN=true` and
`REWARDS_FREE_USAGE_CONFIRMED=true`. Neither is created by setup. The job is
skipped before runner allocation while either is absent or false. Pushing this
workflow therefore does not activate recurring work or a paid service. The
usage check must include artifact storage/retention as well as runner minutes.

Once free usage is confirmed, an authorized operator can run:

```bash
gh workflow run cloud-worker.yml --ref main -f confirm_free_usage=true -f initialize_state=true
```

The first run intentionally has no campaign feed. It should produce a valid
empty state and a report with blocked campaign discovery, with publication
disabled. This validates cloud execution and persistence only. Subsequent runs
must omit `initialize_state` so state is restored rather than reset:

```bash
gh workflow run cloud-worker.yml --ref main -f confirm_free_usage=true
```

The runner uses its built-in short-lived `GITHUB_TOKEN`/`GH_TOKEN` for read-only
Actions metadata and artifact retrieval. No personal access token needs to be
committed, placed in a workflow input or sent in chat. Live platform credentials
are intentionally not bound to this workflow.

## Adding real permitted discovery

Only after a provider supplies an official/public normalized JSON feed and
confirms permitted automated use, no cost and public redistribution, dispatch
with `public_feed_url` and
`confirm_permitted_public_no_cost_feed=true`. Do not paste a credential-bearing
URL. The feed and campaign source URLs must be HTTPS without user information,
query secrets, fragments or private hosts. The existing runtime DNS/egress guards
and payload limits also apply. At most five feeds and 1000 observations are
supported in a run. Whop Content Rewards and Vyro have no invented default URL.

Only public, unverified observations and no-cost public feed configurations are
persisted. Private eligibility/payment evidence text, material paths, job records, account IDs,
approval digests, views/earnings ledgers and environment variables are never
exported. Artifacts inherit GitHub repository access; do not use this workflow
for private campaign terms or account data. Their visibility must be checked
before supplying any information beyond an approved public source.

## Persistence and failure behavior

The immutable artifact `rewards-dry-run-state-v1` contains one `state.json`
envelope with a schema version, sequence, provenance and SHA-256 integrity
checksum. A separate report artifact explicitly says `production_verified=false`
and `live_publishing=false`. The checksum detects corruption; GitHub run/artifact
access controls supply provenance, not a secret signing key.

Runs on the same branch use one concurrency group and do not cancel a running
job. Restoration selects the newest prior completed cloud-worker run whose
observation job executed on the same branch. Runs skipped by disabled execution
gates are ignored only after their workflow/job metadata establishes that no
observation job executed. A cancelled or failed executed run is never ignored.
The selected run must have succeeded and contain the exact expected artifact.
A failed prior run, missing/expired artifact, malformed state, unexpected files
or bad checksum stops the new job. It never silently initializes an empty ledger
or falls back to an older snapshot. Initialization is accepted only when no
prior completed executed cloud-worker run exists.

State artifacts request 90-day retention; reports request 30 days. Repository or
organization policy may shorten retention. This is an observation checkpoint,
not production durability. Monitor retention, download backups of permitted
public state and keep a successful cadence. After expiry, explicitly recover
the verified checkpoint; never reset state merely to make a job pass.

For a deliberate recovery after investigating a failed run, an authorized
operator may supply `previous_run_id` for a known successful cloud-worker run on
the same branch. The helper validates that run and still requires its artifact.
It never downloads unrelated CI artifacts. If no verified checkpoint remains,
resolve the loss before reinitializing. No publish deduplication ledger is
handled by this dry-run workflow, so it must not be extended to live posting
without a durable write-ahead state store and reconciliation design.

## Preparing a recurring free schedule

After free-runner eligibility, available quota and artifact storage are
verified, complete the explicit first initialization dispatch and one successful
state-restoring dispatch. Then set both non-secret repository variables
`REWARDS_FREE_USAGE_CONFIRMED=true` and
`REWARDS_ENABLE_SCHEDULED_DRY_RUN=true`. Neither variable has been enabled here.
Set either to `false` to stop scheduled execution without deleting state.
Scheduled events cannot initialize state, so they fail closed until a successful
initial dispatch exists.

The existing cron, `17 */6 * * *`, means four observation runs per day in UTC
(03:17, 09:17, 15:17 and 21:17
in Asia/Amman). GitHub schedules can be delayed and inactive public repositories
may have schedules disabled; it is not a real-time always-on worker. Default
branch requirements still apply. Keep `REWARDS_LIVE_PUBLISHING=false`; scheduling
this job does not remove any account, eligibility or publication prerequisites.

Live production still needs verified campaign API/feed access, account-owner
OAuth and renewal, actual Jordan eligibility/payout verification, approved
materials and first-publication review, verified platform contracts and
tracking, persistent media and a production ledger with crash-safe publishing
reconciliation. Use the existing Docker deployment guide for an authorized
persistent host; do not call the business live until those operations have been
verified in that production environment.
