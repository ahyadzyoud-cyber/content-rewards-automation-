# Validation record

Validated on 2026-10-28 in the actual cloud environment.

* GitHub `main` resolved to `f8911ed1605c8356cc869177e029276097cd9de4`
  (`Create README.md`). The existing checkout was initialized from that commit;
  project implementation changes are present locally for review.
* Python 3.12.14, uv 0.12.23, FFmpeg 7.1.5 and ffprobe were available natively.
  Frozen dependency installation and repeated initialization passed.
* `bash scripts/install.sh`: lint passed; **155 tests passed**. One upstream
  Starlette TestClient deprecation warning was emitted; no tests failed or were
  skipped. Coverage includes scoring/evidence gates, real media conversion,
  HTTP transports, authenticated API, publishing approvals, concurrent claims,
  atomic candidate reservation, scheduler persistence and isolated CLI workflow.
* `uv build`: source distribution and wheel built successfully.
* `uv run --frozen python scripts/demo.py`: synthetic import, ranking, best
  candidate selection, real portrait rendering, separate-process persistence
  and scheduling passed. Live publication was blocked as expected. The temporary
  fixture was removed and never entered the real ledger.
* `bash scripts/start.sh`: actual loopback HTTP health/authenticated status,
  unauthorized rejection, unverified campaign import/ranking and stop/restart
  persistence passed against a temporary database. Temporary bearer credentials
  were generated in memory and never logged or saved.
* Docker image built successfully from the pinned official Python base using
  frozen runtime dependencies and a non-editable package install. The environment
  required existing proxy DNS mapping and its trusted CA bundle mounted during
  build. TLS and Debian package signature verification remained enabled. The
  helper `scripts/build_container.py` reproduced the successful build.
* The synthetic video demo also passed inside the non-root Docker image with
  networking disabled. This verified FFmpeg 5.1 compatibility in the image.
* Docker Compose configuration validation, API health, fail-closed missing
  authentication, worker execution and restart persistence passed. The isolated
  smoke project's containers and generated volume were removed after validation.
* `git diff --check` passed. Generated dependencies, state, media, caches,
  logs and build outputs are ignored. The original README was expanded under
  the owner's explicit project-initialization instruction.

The saved environment draft contains the native install script, service startup
instructions, required network domains, two API access-token requirements, and
account/version/hosting/admin settings. Draft saving does not publish a snapshot,
apply network changes to the current instance or supply credentials.

Not executed: real account authorization, real campaign API discovery, live
YouTube/Instagram publication/insights, campaign submission or payout, OAuth
refresh, and production deployment. Whop Content Rewards and `vyro.com` official
campaign APIs remain unconfirmed. See `integrations.md` for source evidence and
observed network blocks. No restricted scraping, paid service activation, real
publication or earnings claim occurred.

## Continuation validation

The initial 39-file implementation was committed and pushed to GitHub `main` as
`f80a5a7`. The continuation preserves that project and adds credential lifecycle,
readiness/preflight and scheduled cloud observation capabilities.

* **275 tests passed**, with no failed or skipped tests, after the continuation.
  Lint, source/wheel builds, and the isolated real-FFmpeg CLI demo passed.
* Google refresh tests cover expiry, concurrent refresh, token invalidation,
  PKCE/state consent and sanitized failures. A mocked integrated account-check,
  approved upload and metrics sequence reused one renewed token without storing
  credentials. These are protocol tests, not a live Google authorization claim.
* Real HTTP startup verified authenticated readiness reporting and blocked
  account checks with missing credentials. The report correctly returned zero
  real campaigns and `business_live=false`.
* The updated Docker image rebuilt successfully and passed its offline non-root
  synthetic video demo. Native and container checks remain development evidence.
* The cloud helper executed two successive local observation runs, restoring its
  validated checkpoint between them and reaching sequence two. Without a
  permitted feed it reported `blocked_no_permitted_feed`, with no publication
  and `production_verified=false`. Artifact metadata/history failure cases and
  skipped-job handling were tested with a fake GitHub API.
* The six-hour GitHub cron is implemented behind two repository-variable gates.
  Setup did not enable those variables or dispatch a remote cloud job. Repository
  visibility, free allowance, remote CI outcome and production execution could
  not be checked because GitHub API requests remain Forbidden at the proxy.
* Public Whop/Content Rewards/Vyro requests remain blocked. An accessible official
  Whop SDK describes paid ad campaigns, not an applicable creator rewards API.
  No real campaign or Jordan eligibility recommendation was invented.

The draft adds `api.github.com`, `whop.com` and `www.whop.com`, plus secure Google
refresh-token/client-secret requirements and public client-ID metadata. The
settings still need the product's save/publish action to apply; no secret values
were supplied, and no paid activation or real publication was performed.

## Post-publication verification

The environment was published successfully. The active configuration version
changed, there was initially no editable draft, its site/API egress rules were
present, and `REWARDS_LIVE_PUBLISHING` was injected with publishing disabled.
Whop public documentation, Vyro public pages and GitHub's API now respond.
Old proxy failures above are historical rather than the current access state.

Only affected/new checks were run locally: 33 Whop adapter cases, 16 provider
permission/Whop workflow cases, 20 current Meta identity cases and 20 Git-backed
checkpoint cases. No application rebuild or rerun of the old full local suite
was needed. The updated commit's [cloud CI run passed](https://github.com/ahyadzyoud-cyber/content-rewards-automation-/actions/runs/40767631297).

Official Whop docs now establish a user-OAuth clipping-bounty route, separate
from CPM rewards, and general Jordan payout-country support. Public Vyro offers
were recorded as unverified research, with actual rates and unknown budgets.
Both providers' automation restrictions were documented. Provider campaigns
now require explicit automation authorization/evidence, and untrusted feeds
cannot grant it. No record was falsely marked eligible or published.

The public GitHub free-observer workflow was dispatched twice. Runs
40767661130 and 40767922065 succeeded, and the remote checkpoint report reached
sequence 2 with `previous_run_id=40767661130`. No Actions artifacts were created;
the scheduled workflow uses standard public runners and a small public Git
checkpoint. It does not receive social credentials, export the private ledger,
scrape websites, or publish. The first actual cron execution remains pending.

Actual campaign-qualified discovery, social authorization, approved video,
production publishing and earnings remain unverified. The newly documented
`api.whop.com` destination and optional personal Whop grant are staged separately
in the existing environment draft. This does not undo the successful original
publication or make social credentials prerequisites for development setup.


## Whop OAuth continuation — 2026-10-29

Interrupted uncommitted source was inspected and preserved; no environment,
checkout, dependencies or completed features were rebuilt. The new cloud broker
requests exactly `bounty:basic`, uses PKCE S256, browser-bound expiring one-use
state, owner login/CSRF and an exact HTTPS callback. Access/refresh credentials
and private observations use AES-GCM authenticated encryption in D1. The
rotation claim is committed before the consuming request; uncertain failures
cannot replay the previous refresh token.

Focused checks passed without any real credentials:

* 22 Node broker tests use actual SQLite with the production schema/CAS SQL and
  mocked provider HTTP. They cover encryption/purpose/key tampering, state and
  browser binding/replay, clean callback redirects including errors, refresh
  concurrency, persisted rotation/restart and ambiguous writes, permission
  restrictions, private scheduled discovery and generation-bound evidence.
  A production entry-point regression verifies Cloudflare ExecutionContext is
  not misused as the HTTP fetcher. Delayed cron delivery uses persistent due times.
* 68 Whop reader/broker/workflow and existing operator API checks passed; four
  new authenticated Whop API checks passed. Separate fixed-bounty assessment
  tests passed (34). Unknown evidence cannot authorize a CPM campaign or job.
* 25 deployment-helper tests passed, including free-plan rejection, read-only
  preflight, same-project reuse, secret/key/database preservation, uncertain
  upload recovery, private bindings and schedule readback, and additive schema.
* 163 focused social integration/OAuth checks passed for the independent
  YouTube identity/statistic/scope corrections. No social account was connected.
* Ruff and diff whitespace checks passed. The old full local suite, Docker
  build and media demonstration were not rerun; CI now also runs the Node broker
  checks when source changes are pushed.

The deployment preflight currently stops before network access because secure
`CLOUDFLARE_API_TOKEN` is missing. No Worker/D1 resources were created, no callback
URL was claimed live, and no grant, real bounty, CPM campaign or production
renewal was fabricated. The existing environment draft preserves optional
`WHOP_ACCESS_TOKEN`, adds optional personal Cloudflare authorization and
`api.cloudflare.com`, retains `api.whop.com`, and updates startup instructions.
The save requires owner review/save/**Publish** to apply. Publication does not
itself deploy the OAuth broker. Live publishing remains false, and no paid
service or public posting was activated.


The current GitHub observer status was also checked read-only after resumption:
two actual `schedule` runs, 40799543010 and 40834679284, succeeded. The remote
checkpoint reached sequence 4 with the first scheduled run as predecessor.
Scheduled execution/persistence is now verified; permitted discovery remains
blocked with zero campaigns, and live publishing remains false.


The combined source commit `5f898211c4a6e018c332e5dfa54e9c781d2e7561`
passed its configured GitHub Checks workflow
[40856108106](https://github.com/ahyadzyoud-cyber/content-rewards-automation-/actions/runs/40856108106),
including Python tests/lint/build and the added Node broker security suite.
The API confirms success; detailed log download is blocked by the current
network policy, so no additional remote test-count claim is inferred.


## Live free Whop deployment — 2026-10-29

The owner published the updated environment and supplied Cloudflare authorization
securely. The active environment version changed to
`cecfgver_6ae3291577fc81999373cf2ee3f34a69`; no draft was present at the initial
read, and live Cloudflare account/subscription API calls returned HTTP200.
The account had no account subscriptions, confirming default Workers Free.
Its missing `workers.dev` namespace was initialized through the official API,
then the existing project's single `content-rewards-whop` Worker and private D1
database were deployed. The health update reused the same database and secret
bindings. No paid subscription or second Codex environment was created.

The exact callback is:
`https://content-rewards-whop.content-rewards-dc8a4aba9226.workers.dev/oauth/callback`.
Public health checks were added so real D1/encryption-key readiness can be
verified before the owner configures a Whop app or login password. The renewal
cron is installed every 30 minutes; a real grant and automatic renewal remain
unverified.

Whop's live issuer metadata (`api.whop.com/.well-known/openid-configuration`)
resolved the permission question: it advertises `bounty:basic:read`, but neither
`bounty` nor `bounty:basic`. The List Bounties contract agrees. The latest owner
request was to verify the official read permission before consent; broker code,
reader status, documentation and tests now use only that advertised read scope,
without OpenID or write permissions. Earlier exact-basic instructions above are
historical. No actual consent request was made.

Affected local checks passed: 23 broker tests after the scope correction, the
new database/key public health test, 28 Python broker/API/workflow checks, and
two focused client-identity regressions. No dependencies, project image or
media pipeline were rebuilt. Source CI run
[40864488496](https://github.com/ahyadzyoud-cyber/content-rewards-automation-/actions/runs/40864488496)
passed; it includes Python checks/build and the broker suite.

The current cloud environment correctly blocked direct requests to the newly
created Worker hostname because that exact destination did not exist before
deployment. A narrow destination, real `WHOP_BROKER_URL`, optional personal
`WHOP_BROKER_API_TOKEN`, and refreshed startup instructions were saved in a new
draft; the tool confirms **requires_publish=true**. Existing secrets and
optional `WHOP_ACCESS_TOKEN` were preserved.

Public endpoint verification used a standard GitHub-hosted runner on the
confirmed public repository, with no secrets, artifacts or cache. Initial probes
failed with Cloudflare error1010. Official Cloudflare documentation explicitly
identifies default Python urllib identity as a cause on workers.dev and
prescribes a descriptive application User-Agent. Applying
`ContentRewardsAutomation/0.1` resolved the issue; the same identity is now sent
by the private Python broker client. See the
[official diagnosis](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/).

[HTTPS verification run40865214345](https://github.com/ahyadzyoud-cyber/content-rewards-automation-/actions/runs/40865214345)
**passed**. It verified TLS, HTTP200 database/key health, the exact read scope,
live publishing false, and a missing-state callback's clean HTTP303 redirect
with no-store/no-referrer headers. Owner configuration is still incomplete:
WHOP_CLIENT_ID and OWNER_PASSWORD must be configured securely, and the owner
must complete legitimate Whop consent. No real campaign, token rotation,
publication, or earnings is claimed verified by this health check.

The final client-identity source change also passed
[CI run40865213842](https://github.com/ahyadzyoud-cyber/content-rewards-automation-/actions/runs/40865213842)
for commit `8958a6337c49b7860be6999fb549faf3779fccc1`.


## Owner login origin correction — 2026-10-29

The real deployed login page loaded with `Referrer-Policy: no-referrer` and the
configured public origin matched its URL. Chromium154 reproduced the reported
failure with a native form navigation: the browser serialized `Origin` as the
literal `null`, and the Worker correctly rejected it with HTTP403. This behavior
is specified by [Fetch](https://fetch.spec.whatwg.org/#append-a-request-origin-header)
for native POST navigation under that referrer policy.

The fix overrides the policy to `same-origin` only for the two owner HTML
states: login and authenticated forms. `requireOrigin` remains the same strict
comparison, with no missing/null-Origin fallback, Referer trust or Fetch Metadata
exception. Session-bound CSRF verification, secure cookies, CSP and no-store
remain enabled. OAuth callbacks and redirects keep `no-referrer`, protecting
callback codes/state and cross-origin consent navigation.

Safe production browser observations, using an isolated context and a
purposefully invalid synthetic password, were:

| Page policy | Browser POST Origin | Worker result |
| --- | --- | --- |
| Before: no-referrer | null | 403, origin rejected |
| After: same-origin | exact configured HTTPS origin | 401, normal password validation |

No request body, password, Cookie value, full Referer, callback query or token
was logged. Browser request interception exposes no Sec-Fetch headers in this
Chromium setup; missing headers were recorded honestly rather than inferred.
For live browser probes, requests were forwarded with their browser-generated
headers through Playwright's TLS-verifying Node transport using the platform's
provided CA bundle. The Chromium trust store did not accept that CA directly;
certificate verification was never disabled.

The affected Worker suite passed26 tests, including missing/null/foreign-origin
rejection for login, OAuthstart and logout before state mutation. All four real Chromium
regression tests passed, covering the old-policy failure, successful isolated owner
login/secure session/PKCE-start/logout, tampered CSRF, and cross-origin attacks.
All fixture browser traffic is intercepted locally; no real Whop consent or
production account password is used.

The corrected source was uploaded to the existing Free Worker using its
existing deployment helper. The helper was explicitly given the existing
Cloudflare app ID instead of any local override. Before/after checks confirmed
the same D1 binding, secret binding names and hash of public variable values.
No secret-update API request or new secret binding was sent; the existing
TOKEN_ENCRYPTION_KEY, OWNER_PASSWORD and broker secret were retained. Public
health returned HTTP200 with owner configuration complete and live publishing
false. No database or Worker was recreated and no paid service was activated.

Actual successful production owner authentication still requires the owner's
existing password in their browser. Refresh the login page before retrying so
Chrome receives the corrected document policy. No environment configuration
change or additional Codex Publish action is needed for this deployed fix.
