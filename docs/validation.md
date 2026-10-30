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


## Whop authorization redirect correction — 2026-10-29

The production owner session was active and a recent OAuth start state was
still bound to that session. Read-only D1 metadata confirmed this without
printing session hashes, encrypted payloads, state or CSRF values. This shows
the reported action passed Origin, session and CSRF validation and persisted
its PKCE transaction. The configured public origin and database binding matched
this existing deployment; health returned HTTP200 and publishing remained false.

Using the configured public app ID, an isolated anonymous request with synthetic
state/PKCE verified the actual provider chain without consent or code exchange:

```text
https://api.whop.com/oauth/authorize  → 302
https://whop.com/oauth/authorize      → 307
https://whop.com/login                → 200
```

Only statuses, origins and paths were logged, never full redirect queries.
The owner-page CSP permitted `self` and `api.whop.com`, but omitted `whop.com`.
Real Chromium154 reproduced the exact symptom: POST `/oauth/start` returned303
and its state was stored, then Chrome raised a `form-action` policy violation
and stayed on the owner page before contacting the provider frontend. The old
browser fixture returned200 at the first API hop, so it had missed that chain.
[MDN documents Chrome's redirect enforcement](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/form-action).

The fix adds only the verified `https://whop.com` frontend to `form-action`.
There is no wildcard or general HTTPS allowance. Exact Origin checks,
session-bound CSRF, one-use state, PKCE S256, read-only scope, secure cookies,
callback validation and no-referrer redirects remain intact.

All27 affected Worker tests and all6 real Chromium tests passed. The updated
browser fixtures intercept every redirect hop before network: API302,
frontend307 and login200. They verify that owner cookies stay on the owner
origin and no owner-page referrer reaches any provider hop. Regressions prove
both the old-policy failure and rejection of an unrelated provider redirect,
alongside the existing null/foreign-Origin and tampered-CSRF cases. No test
performed real consent or exposed production credentials.

Deployment used a code-only upload to the existing Free Worker. It preserved
all secret bindings and exact existing public variables/D1 binding and sent no
schema or database-record mutation. No credentials or encryption keys were
replaced. The first immediate edge read still showed the previous deployment;
a later verified read returnedHTTP200 with the corrected exact three-target
policy and `Referrer-Policy: same-origin`. No new environment Publish action is
required. Reopen the owner homepage to fetch its new CSP before retrying
**Authorize Whop discovery**; do not merely resubmit the old form document.


## Completed-consent callback expiry correction — 2026-10-29

The reported failure occurred before token exchange. Production D1 remained
`empty`, credential version/generation remained zero, and no pending state
remained. Read-only Cloudflare analytics showed all invocations successful with
zero errors and zero outbound subrequests. The last pre-return owner activity
was followed by approximately 26 minutes at Whop; scheduled cleanup ran between
that activity and the return. With the old 10-minute PKCE-state TTL, even the
latest possible transaction had expired before cleanup and could not pass the
callback lookup. No token request was attempted, so changing token formatting,
client secrets or cookie SameSite policy would not address this failure.

Official Whop documentation and issuer metadata were checked again: the query
`code`/`state` callback and JSON PKCE token exchange remain correct. Real
Chromium tests confirmed that both cross-site GET returns and provider
POST→303→GET returns send the existing SameSite=Lax owner cookie correctly.

The transaction now has a bounded 30-minute lifetime, matching the existing
owner-session window. Only an already-authenticated, exact-Origin and
CSRF-validated `/oauth/start` action refreshes that same session cookie and its
server expiry. Session extension and state insertion are conditional atomic D1
writes; revocation races cannot recreate a logged-out session. The browser
cookie remains the same value with Secure/HttpOnly/SameSite=Lax and Max-Age1800.
No long-lived credentials, provider scopes or keys were changed.

Callbacks still require matching browser-bound, unexpired, single-use state.
Expired/missing-owner, unavailable request, provider denial and token-exchange
failure now redirect to fixed whitelisted result paths with safe messages.
Codes, state, provider bodies and credentials never enter those paths or pages;
no-referrer and no-store remain enforced. Unknown reason paths and unexpected
query parameters are rejected. There is no new database table or schema change.

Targeted verification passed33 Worker tests and10 real Chromium tests. New
regressions cover a 25-minute-old login followed by26 minutes of provider
verification, scheduled cleanup midway, one JSON code exchange and encrypted
credential persistence. They also cover legacy 10-minute expiry reproduction,
31-minute expiry, missing/wrong state, revoked sessions, wrong CSRF, replay
without a second exchange, preservation of already-ready ciphertext, and safe
failure pages. Browser provider requests and token responses are isolated
fixtures; no real account consent or code exchange is claimed by these tests.

The existing Free Worker received a code-only update. Before/after checks
preserved D1 binding, secret binding names, exact public-variable hash and all
Cloudflare secrets. No secret update, schema change or database-record mutation
was sent during deployment. Existing expired records had already been removed
by the normal scheduled cleanup; no expired code or PKCE transaction was
resurrected. Owner authorization must start a fresh transaction after deployment.
Publishing remains false and no paid service was activated.


## Whop token exchange runtime correction — 2026-10-29

The new real callback reached its credential claim and ended
`reauthorization_required` with no encrypted credential payload. The generic
result page had hidden the outbound request failure. Official Whop documents
were checked again: JSON PKCE exchange, a flat access/refresh-token response,
Bearer token type and numeric expiry are correct. Anonymous official Retrieve
App inspection confirmed the configured app is already a **public** OAuth
client and its registered redirect URI exactly matches this Worker. Its empty
installation permission list is not the requested OAuth action scope;
`bounty:basic:read` remains the single initial OAuth permission. No client
secret or app-settings change is required.

The confirmed failure was `redirect: "error"` in the Worker fetch options.
Cloudflare Workers does not implement that mode: it throws a TypeError before
sending HTTP. This is explicit in the
[official Workers Request documentation](https://developers.cloudflare.com/workers/runtime-apis/request/)
and [workerd's Request implementation](https://github.com/cloudflare/workerd/blob/main/src/workerd/api/http.c%2B%2B).

A temporary, existing-Bearer-protected runtime probe used hard-coded Whop
endpoints, the public app identifier, and newly generated **nonexistent** test
codes/verifiers. It read no credential/session records and wrote no D1 data.
Only stage, status, known OAuth error enums and field-presence flags were
returned; bodies, descriptions, code/state/token values, request URLs and app
identifiers were never logged or returned. In the actual deployed runtime:

| Request mode | Result |
| --- | --- |
| error | Request-stage exception, no HTTP response; classified unsupported redirect mode |
| manual | Whop HTTP400 JSON invalid_grant, as expected for the nonexistent test code |

Both default and descriptive User-Agent variants had the same outcome. This
ruled out the app's Public mode, JSON serialization, callback registration and
client identity as the reported transport blocker. No real code, token or
refresh grant was retried. The temporary diagnostic endpoint was removed after
confirmation.

Token exchange/refresh and fixed-bounty GET requests now use the supported
`manual` redirect mode. Existing non-2xx rejection remains unchanged, so 3xx
responses do not forward codes or bearer credentials. The Node mocks previously
accepted an option that actual workerd rejects; all injected HTTP fakes now
enforce the supported runtime contract and specifically require manual mode.

Targeted checks passed36 core cases and4 affected Chromium callback cases.
New cases reject every relevant 3xx token/bounty redirect without forwarding,
persisting redirected credentials or replaying codes, and reject refresh
redirects after one claimed attempt. Existing delayed-consent, replay,
PKCE/state, encrypted persistence, cookie, CSRF and Origin protections remain.
Unrelated local Python suites, rendering and builds were not repeated.

The existing Free Worker received a code-only update. Secret bindings, D1
binding, exact public-variable hash, compatibility date and compatibility flags
were preserved. No secret update, database mutation, schema change, public
client-mode change, additional compatibility flag or paid activation was sent.
Publishing remains false. A fresh owner authorization is required to issue a
new code after this deployed fix; no setup changes are required.


## Authorized global discovery and private owner review

After the owner completed consent, the existing broker returned authenticated
HTTP 200 status: authorization ready, the exact read-only bounty scope usable,
five durably persisted refresh rotations, two private discovery snapshots and a
successful scheduled renewal check. The latest scheduled renewal was at 23:30
Asia/Amman on 2026-10-29. Complete fresh clipping and UGC listings returned two
real open fixed-reward opportunities admitting Jordan residents. No raw
account-visible record, advertiser identity or private brief is committed here.
The official country filter includes worldwide offers admitting that residence;
removing it is not necessary for global discovery.

A read-only dry run assessed the real observations and prepared an ignored,
private review packet. Neither opportunity passed the payout, rights,
new-account and workflow-permission gates. Their mandatory livestream steps
cannot be represented as unattended compliance. No approved campaign footage
was downloaded, no real video could be prepared, and no job, provider submission,
publication, earnings or payout record was created. Whop's payout guide lists
Jordan but actual owner KYC and an available method remain unverified. Its
conditional $10 withdrawal minimum is separate from campaign ranking: smaller
rewards remain queued. Content Rewards CPM access remains separate; no permitted
Vyro integration or other verified campaign is invented from marketing pages.

The existing free Worker now serves a private owner opportunities page using
only encrypted, current-authorization-generation scheduled snapshots. Its
provider briefs are escaped; timestamps, incomplete/stale observations and
verification weaknesses are explicit. Missing/expired owner sessions redirect
to the existing sign-in page without private content. Four focused regression
cases passed, including XSS, secret/metadata exclusion, no provider requests or
DB writes, old-generation exclusion, and retention of small rewards.

The production code-only update passed the Workers Free preflight and verified
that runtime settings, public variables, private bindings and schedules were
unchanged. The helper sent no secret values, D1 query, schema migration,
subdomain change or schedule write. Live HTTPS health returned 200, publication
false, and the private page returned a clean no-store/no-referrer sign-in
redirect. Existing authorization and the five rotations remained intact after
upload. The private broker also successfully decrypted both existing scheduled
snapshots after upload; required owner-cap fields parsed against the real
records without exporting credentials or key material. Owner-authenticated
rendering is tested with isolated encrypted fixtures; no real owner password or
session was obtained to impersonate a login.

Optional fixed-bounty economic scenarios now require separate fresh reviews of
cost, time and acceptance probability. Missing values remain unknown, estimates
are not earnings, and a separate economic rank does not remove blocked, small or
negative-scenario offers from the evidence queue. Instagram's official account
quota is read before container creation and again after processing; unknown or
exhausted capacity prevents publication, and approval/rights checks run after
the final new network await. Personal winner-cap checks additionally reject
unknown or exhausted owner allowances despite available global slots, without inferring this owner's
pending proofs from global counts. These changes passed 118 Whop
reader/ranking/workflow and 147 Instagram/adapter targeted cases. The source-only
code-update path passed 42 mocked deployment cases. Actual social consent, quota and token
renewal remain unverified without owner authorization.


## Mandatory full-brief publication compliance

On 2026-10-30, fresh authenticated clipping/UGC discovery was fully paginated.
It still returned only the two known fixed bounties. The documented anonymous
Retrieve Bounty operation returned HTTP 200 for both known IDs; descriptions
matched the authenticated listings. Private, complete requirement inventories
were retained with the official text/hash. Both offers were temporarily deferred
for unattended execution, preserving the research queue. Their mandatory live
participation, rights and platform/submission gaps prevented preparation of a
fully compliant real video. No provider-recommended paid feature was activated.
No social account is authorized; publication remains false.

Publication approval and the actual publishing path now both enforce a full
reviewed brief, explicit coverage of all mandatory categories, measured media
and required metadata, and fresh individual manual proofs bound to the exact
video/metadata/campaign/account. Legacy records without that evidence remain
readable but cannot pass. Optional entries and post-publication placement cannot
stand in for critical pre-publication requirements. Future view thresholds and
submission proofs remain pending, not passed or required before the first post.
The staged file is rechecked before a provider write and again after Instagram
processing. Atomic approval/review changes preserve concurrent upload claims.

Preparation applies supported reviewed duration and literal metadata constraints,
defers unsupported or failed renders and moves to the next candidate, retaining
smaller offers. An actual FFmpeg regression verifies that a MOV renamed .mp4 is
still measured as MOV. Unknown content, rights and human participation are not
inferred from those mechanical checks or a successful upload.

Validation passed: full Python suite693 cases, including the real media probes,
new compliance unit/workflow/selection regressions and previous adapters, OAuth,
concurrency and persistence tests. Ruff and diff checks passed. The existing
Whop callback/credentials, D1 data, keys, cloud settings and schedules were not
changed; there is no need for another environment Publish or callback redeploy.
The Python application code is updated through the existing source checkout and
GitHub. No live publication, campaign submission, confirmed reward or payout
occurred, and no first real video is represented as ready for approval.
