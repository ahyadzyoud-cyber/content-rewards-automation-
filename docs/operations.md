# Operations

Run commands from the repository root with `uv run --frozen rewards ...`.
State is in `.data/rewards.sqlite`, media in `.data/media`; both are ignored by Git.
Back up the database using SQLite's backup API, and retain media, before changing hosts.
Do not treat the development snapshot as a production backup or an always-on host.

## Accounts and evidence required before live use

1. Verify Whop Content Rewards and Vyro account access, actual campaign terms,
   Jordan creator eligibility, new-account acceptance, allowed platforms,
   material/editing rights and current remaining budget. Verify supported Jordan
   payouts and complete platform identity/payout verification directly with each
   provider. This project never requests payout credentials in chat.
2. Obtain a documented official campaign API, permitted export or feed from each
   provider. No private-page scraper, session-cookie automation or guessed API is
   provided. Add the permitted no-cost feed's exact host to environment network
   settings. A feed is not sufficient evidence of country eligibility by itself.
3. Authorize the actual YouTube channel through Google OAuth with upload and
   readonly scopes. Configure `YOUTUBE_ACCESS_TOKEN` and `YOUTUBE_CHANNEL_ID` in
   secure settings. Verify channel eligibility, quota, audience defaults,
   policy compliance and any API project audit/public-upload restriction.
4. For Instagram, authorize an eligible professional account using Instagram
   Login. Configure `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID` and a
   currently verified `INSTAGRAM_API_VERSION`. Verify app review/access levels
   and publishing/insights permissions. Personal accounts are not accepted.
5. Instagram needs externally reachable immutable video hosting already approved
   by the owner. Configure `INSTAGRAM_IMMUTABLE_MEDIA_HOST` only after verifying
   its immutability policy, HTTPS, permissions and cost. No host is provisioned.
   Serve each reviewed video as `https://HOST/PATH/SHA256.mp4` with `video/mp4`;
   the basename must be the rendered file's actual SHA-256. URLs with credential
   query strings are rejected. The worker downloads and verifies exact bytes
   immediately before creating the container. A mutable host cannot provide the
   required guarantee and must not be configured.
6. Review the first video and publication metadata yourself, including rights,
   disclosures, required hashtags, audience classification and campaign rules.
   Run the explicit approval command only after that review. Set
   `REWARDS_LIVE_PUBLISHING=true` only when ready for authorized external writes.

Do not send tokens in chat. The environment draft declares the two API token
requirements and non-secret account/version/hosting settings. Token values are
entered securely. Existing bindings should be reused. Short-lived access tokens
must be renewed; refresh and initial OAuth consent are not automated yet.

## Import and prepare

```bash
uv run --frozen rewards import-campaigns /path/to/authorized-campaigns.json
uv run --frozen rewards rank --platform youtube
uv run --frozen rewards prepare --platform youtube
```

`prepare` renders a draft from the best selectable campaign with existing local
approved footage. An atomic reservation creates at most one automatic candidate
per campaign/platform, including concurrent workers. One worker per database is
usually sufficient. If rendering fails, inspect and resume that job rather than
creating a duplicate automatic candidate.
To supply specific metadata instead:

```bash
uv run --frozen rewards plan CAMPAIGN_ID --platform youtube --source /path/to/approved.mp4 --title "Reviewed headline" --caption "Reviewed description and disclosures"
uv run --frozen rewards render JOB_ID --duration 30
uv run --frozen rewards list job
```

Rendering preserves the source with portrait letterboxing, adds the headline,
and produces H264/AAC MP4 up to 60 seconds. It does not invent campaign claims,
produce original AI footage or guarantee that a minimal edit qualifies for a
specific campaign. Source authorization and output format are checked; actual
campaign-specific creative requirements remain part of review. Existing output
files are not overwritten. To revise a draft, create a new job.

For an explicitly confirmed permitted no-cost normalized JSON feed:

```bash
uv run --frozen rewards add-feed provider-feed https://APPROVED_HOST/campaigns.json --confirm-permitted-no-cost
uv run --frozen rewards discover
```

The URL is supplied by the provider; this command is not a known Whop/Vyro API.
Only public HTTPS destinations on the configured host are used; no redirects,
URL credentials, private addresses or query secrets. New/updated feed records
are unverified and require evidence review. Importing a changed campaign also
invalidates existing publication approvals. A refresh conservatively clears
feed verification even when content is unchanged.

## Explicit publication review

For YouTube, set the authorized channel ID before approval:

```bash
uv run --frozen rewards approve JOB_ID --reason "Owner reviewed video, target, disclosures, rights and campaign requirements"
uv run --frozen rewards publish JOB_ID
```

For Instagram, host the exact reviewed file under its hash first:

```bash
uv run --frozen rewards approve JOB_ID --video-url https://APPROVED_IMMUTABLE_HOST/media/SHA256.mp4 --reason "Owner reviewed this exact hosted video and campaign requirements"
uv run --frozen rewards publish JOB_ID
```

These commands are documented for the owner; setup never executes a real
approval or publication. Approvals bind the exact media bytes, title, caption,
hosting URL, campaign evidence and account ID. Changing any requires a new
review. The service rechecks current evidence and account identity. YouTube
uploads use public visibility only after these gates; unaudited projects may
still have provider restrictions. A returned video ID confirms acceptance,
not policy approval, public processing completion, or campaign eligibility.

The HTTP API deliberately has no approval route. Business endpoints require a
strong bearer token; only `/health` is unauthenticated. Keep it on loopback or
behind authenticated HTTPS. Never put credentials in request URLs.

## Tracking

```bash
uv run --frozen rewards metrics JOB_ID
uv run --frozen rewards list metrics
uv run --frozen rewards record-submission JOB_ID --status submitted --evidence-url https://PROVIDER/submission/ID
uv run --frozen rewards record-submission JOB_ID --status approved --evidence-url https://PROVIDER/approval/ID --earnings-usd 12.50
uv run --frozen rewards list submission
```

Use `paid` only with actual payment evidence. The ledger labels these entries
`operator_recorded`. It does not submit claims to a provider or independently
verify payouts. Metrics and status snapshots are retained as events; the current
submission record represents the latest observed status. Views, eligible views,
approved reward amounts and cash received are different quantities. No earnings
are estimated from views.

## Recurring worker

`init` and `worker` register hourly ranking idempotently. Add supported work as
its prerequisites become available:

```bash
uv run --frozen rewards schedule discover-hourly --action discover --interval 3600
uv run --frozen rewards schedule prepare-youtube --action prepare --platform youtube --interval 3600
uv run --frozen rewards schedule prepare-instagram --action prepare --platform instagram --interval 3600
uv run --frozen rewards schedule publish-reviewed-job --action publish --job-id JOB_ID --interval 300
uv run --frozen rewards schedule observe-job --action metrics --job-id JOB_ID --interval 3600
uv run --frozen rewards schedules
uv run --frozen rewards worker --once
uv run --frozen rewards worker
```

No publication schedule can create its own approval. A successfully published
job cannot publish twice. Cancel its publication schedule after success:
`uv run --frozen rewards cancel-schedule publish-reviewed-job`.
Schedule IDs are idempotent; to change interval/payload, cancel and recreate.
The worker persists timestamps and claims one due task at a time, with a
30-minute lease and a 15-minute async operation timeout. Blocked tasks are
recorded and do not stop other schedules. After restoring a cloud snapshot,
restart the processes; schedules and files survive, processes do not.

## Uncertain publication recovery

The job changes to `publishing` before its first external write. A timeout,
provider failure or malformed success may leave a real post on the account.
The job then remains `needs_reconciliation`; a process crash can leave
`publishing`. Neither state automatically retries. Inspect the target account
and provider IDs before any further attempt. Preserve the database and request
a reconciliation change tied to the verified outcome; do not delete the job,
reset state or create a replacement merely to retry. Automated reconciliation
is not implemented, deliberately avoiding duplicate posts.

## Cloud hosting

The repository includes Docker deployment configuration. The image build,
non-root offline video demo, Compose API/worker startup and worker restart with
persistent state passed in this onboarding environment. This is a development
deployment check, not a deployment to an always-on business host. On an existing
owner-approved host with Docker Compose and persistent disk:

```bash
cp .env.example .env
# Fill the ignored .env securely. Keep REWARDS_LIVE_PUBLISHING=false initially.
docker compose up --build -d
docker compose exec worker rewards init
docker compose exec worker rewards status
docker compose logs --tail=50 worker
```

In the Codex environment, the Docker build additionally needed the existing
proxy hostname mapping and trusted CA bundle. The tested helper reproduces that
supported configuration without printing proxy credentials or disabling TLS:

```bash
uv run --frozen python scripts/build_container.py
docker compose up --no-build -d
```

The helper uses the existing `SSL_CERT_FILE` or system CA bundle as a temporary
BuildKit certificate mount. It does not copy that bundle into the final image.
If a deployed runtime also uses an organization proxy, configure its legitimate
proxy resolution and CA trust separately before live API checks. Never bypass
TLS, package signatures or artifact integrity checks to make installation pass.

Both services share the named data volume. Import source footage into that
volume before importing absolute material paths (`/app/.data/...`) used in
containers. The API binds the host loopback interface. One worker is sufficient.
No provider was selected or activated: free quotas, credit-card requirements,
resource limits and persistent storage must be confirmed for an actual host.
No always-on free-tier guarantee is made. Do not activate anything paid without
the owner's explicit approval. CI runs tests only; it never publishes content.
