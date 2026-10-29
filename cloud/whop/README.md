# Owner Whop authorization and unattended renewal

This component adds a private Whop authorization service to the existing project.
It uses a Cloudflare Worker for an HTTPS callback and D1 for encrypted, durable
OAuth state and rotating credentials. It does not publish social content, submit
bounties, move money, or convert fixed bounties into CPM campaigns.
`REWARDS_LIVE_PUBLISHING=false` remains required.

The service is prepared for deployment; a source file, local test, or published
Codex development environment does not establish a reachable production callback.
The actual callback exists only after deployment to the owner's Cloudflare account
and verification of that exact HTTPS address.

Current deployment: `https://content-rewards-whop.content-rewards-dc8a4aba9226.workers.dev`.
The private D1 binding, stable encryption secret and 30-minute renewal cron are
installed on the verified Free account. Owner app registration/login/consent
remain pending. `/health` checks database/key health without revealing them.
The optional manual [HTTPS verification workflow](../../.github/workflows/whop-health.yml)
uses a standard public GitHub runner and no secrets, cache or artifacts.
Follow [current owner steps](../../docs/next-actions.md); do not create another
Worker or replace the encryption key.


## The first owner action

In the official Cloudflare dashboard, use an existing account on **Workers Free**
and ensure that its `workers.dev` subdomain is selected. Create an account-scoped
Cloudflare API token with **Account Settings: Read**, **Workers Scripts: Edit**,
**D1: Edit**, and **Billing: Read**. Restrict it to that one account. Enter the token
only in the existing Codex environment's secure `CLOUDFLARE_API_TOKEN` field for
`api.cloudflare.com`, then save/apply the environment settings. Do not send the
token in chat. Billing read permission is used to verify that deployment does not
activate or rely on a paid plan; the helper has no billing-write operation.

If no Cloudflare account exists yet, the first action is to create and verify a
**Free** account, without upgrading or adding a paid Worker plan. These deployment
steps reuse the existing GitHub repository and Codex environment.

## Deployment after the owner authorizes Cloudflare

The project supplies an official Cloudflare API deployment helper. It operates
from the current cloud machine, so a local computer does not need to stay on:

```sh
.venv/bin/python scripts/deploy_whop.py --preflight
.venv/bin/python scripts/deploy_whop.py --apply
```

The first command is read-only. The second may create the project's free Worker
and private D1 database only after the plan check succeeds; it never activates a
paid plan. If the token can see multiple accounts, set the public
`CLOUDFLARE_ACCOUNT_ID` for the intended Free account before running the helper.
An existing `workers.dev` namespace is required; select it in the owner's
dashboard if the preflight identifies that prerequisite.

The helper initializes the schema and uploads the Worker, generates its initial
server-side encryption and machine credentials without printing or saving their
values locally, and preserves those secrets during redeployments. Its output
includes the **actual** HTTPS origin and callback URI. An initial deployment may
be inactive until the public Whop client ID and owner password are configured.
Do not perform OAuth consent until all required settings are present.

Use the exact callback URI in the Whop application's OAuth settings as described
below. Set the application's public client ID as `WHOP_CLIENT_ID` in the cloud
configuration and rerun the helper to deploy the configured client. In the
Cloudflare dashboard, select the deployed Worker > **Settings** > **Variables
and Secrets** > **Add**, choose type **Secret**, and configure `OWNER_PASSWORD`.
Use a password manager's generated random password of at least 32 characters.
Select **Deploy** to apply secret changes.

The helper's generated broker credential is not exposed. To connect the Python
reader, choose a separate generated `WHOP_BROKER_API_TOKEN`, save it as a
Cloudflare Worker **Secret**, and enter that same value only in the existing
Codex environment's secure machine-credential field scoped to this Worker's
actual hostname. Configure its public broker base URL separately. The agent can
prepare the hostname-scoped requirement after the actual deployment address is
known. Neither the Whop access token nor refresh token is configured in Python.

The checked-in Wrangler file contains an explicit placeholder for the
account-owned D1 identifier. Do not use that placeholder as a real identifier or
run a blind Wrangler deployment against it. The API helper discovers or creates
the actual named database and binds its verified ID directly during deployment.
It keeps only nonsensitive deployment identifiers locally. For a later
Git-connected Cloudflare build, first replace the placeholder with the verified
public database ID so redeployment reuses the existing credential database.

## What the owner configures

| Setting | Kind | Purpose |
| --- | --- | --- |
| `WHOP_CLIENT_ID` | Public identifier | The owner's Whop OAuth application |
| `PUBLIC_ORIGIN` | Public HTTPS origin | The actual production `workers.dev` origin, without a trailing slash |
| `OWNER_PASSWORD` | Cloudflare Secret | A password-manager-generated random owner password, at least 32 characters |
| `WHOP_BROKER_API_TOKEN` | Cloudflare Secret | A separate password-manager-generated random machine credential, at least 32 characters |
| `TOKEN_ENCRYPTION_KEY` | Cloudflare Secret | Exactly 32 cryptographically random bytes, unpadded base64url encoded (43 characters) |
| `DB` | D1 binding | The private database initialized from this folder's schema |

Owner-provided secrets are entered only in secure provider configuration. The deployment helper generates the initial server-side key and machine secret without displaying them. Whop access
and refresh tokens are received automatically at the callback, encrypted by the
Worker, and stored in D1; they are never copied into chat, source, GitHub branches,
workflow artifacts, or the public observation checkpoint. The encryption key must
remain unchanged across ordinary deployments so existing credentials can be read.
Replacing it requires reauthorization unless an explicit migration is performed.

## Whop application and consent

1. In the official [Whop Developer Dashboard](https://whop.com/dashboard/developer),
   select or create the owner-controlled application and open **OAuth**.
2. Register the **exact deployed** redirect URI:
   `https://YOUR-ACTUAL-WORKER.YOUR-ACTUAL-SUBDOMAIN.workers.dev/oauth/callback`.
   Replace both placeholders with the verified production address. Never register
   a guessed hostname, a preview-version URL, or the Codex development machine.
3. Configure that application's public client ID as `WHOP_CLIENT_ID` and the
   actual origin as `PUBLIC_ORIGIN`. A Whop client secret is not requested by
   the documented PKCE token exchange and is not collected by this service.
4. Open the deployed Worker homepage in your own browser. Sign in using the
   owner password configured in Cloudflare, then use the authorization form.
5. On Whop's own consent screen, confirm that the requested scope is exactly
   **`bounty:basic:read`**. The Worker uses PKCE S256, an expiring single-use state,
   and browser-bound owner authorization. It requests no identity, submission,
   payout, or write scopes.
6. Whop redirects your browser to the registered callback. The service exchanges
   the code directly with Whop and persists the encrypted token set. The owner
   status screen reports authorization state without displaying any credential.
   Do not copy callback URLs or authorization codes to chat or issue comments.

### Verified read-only scope

The initial permission is **`bounty:basic:read`**. Whop's live
[OAuth discovery metadata](https://api.whop.com/.well-known/openid-configuration),
retrieved with HTTP 200 on 2026-10-29, advertises that exact scope. It advertises
neither `bounty` nor `bounty:basic`. The official **List Bounties** contract
requires the same `bounty:basic:read` action. This corrects the earlier
`bounty:basic` request before any real consent is requested.

Use a dedicated app with only this read permission so a previously accumulated
broader grant is not reused. If Whop rejects consent or listing, the service
reports the failure and stops without adding permissions. The initial
application does not call `/userinfo` and does not require `openid`.

## Private discovery interface

The existing Python discovery reader can call the deployed service's
`GET /api/bounties` using the machine credential in the `Authorization` header.
Tokens issued by Whop are not returned to that reader. Only official read-only
Whop bounty requests are forwarded, restricted to open clipping or UGC work and
creator residency `JO`; pagination is bounded. Authentication, refresh, or scope
failures stop the read instead of switching to scraping or returning invented
results. The service and Python reader keep the Whop fixed-reward model separate
from the project's verified CPM `Campaign` records.

A creator-country match alone does not verify acceptance of a new social
account, payout onboarding, campaign materials, reuse rights, automation
permission, deadline, competition, or campaign budget availability. Those facts
need current, attributable evidence before a candidate is selectable.

## Operation and recovery

Owner HTML form pages use `Referrer-Policy: same-origin`. Native Chromium form
POSTs inherit the document policy; `no-referrer` makes their `Origin` header
`null` even when posting to this same service. This page policy preserves the
exact origin check without exposing referrers to other origins. Missing, null
and foreign origins remain rejected; session-bound CSRF checks remain required.
OAuth callbacks, redirects and other responses retain `no-referrer` so callback
codes and state cannot become referrers. See the
[Fetch standard](https://fetch.spec.whatwg.org/#append-a-request-origin-header).

The deployed cron runs every 30 minutes and renews an authorized token before
expiry. D1 persists successful refresh-token rotations across Worker instances
and deployments. A database claim admits only one refresh operation for the
current token generation. The replacement refresh token is committed before it
can be used by later requests. An uncertain request or interrupted rotation
requires owner reauthorization; an old refresh token is never blindly replayed.
This conservative recovery prevents reuse of a consumed rotating token but can
require owner attention after a network failure or crash during renewal.

The credential database is private. Keep Worker request observability and
invocation logging disabled as configured; OAuth callback query strings contain
short-lived authorization codes. Do not enable request logging, Logpush, tail
logging, or custom console output for the callback. D1 backups contain encrypted
credentials; database recovery must not resurrect an already consumed refresh
token and resume it. After restoring an older credential snapshot, reauthorize.

Production verification still requires the actual owner deployment and consent,
a successful official bounty read, a later automatic refresh with persisted new
token generation, and a successful cron invocation. Local tests cannot establish
those account-dependent facts. Until those pass, the business is not live.

## Free-plan limits

Official Cloudflare documentation currently provides Workers Free with 100,000
requests per day and 10 ms CPU per invocation. D1 Free includes 5 million rows
read per day, 100,000 rows written per day, and 5 GB account storage, with a 500 MB
maximum per database. A private owner service should use a small fraction of
those limits, but that expectation does not replace production CPU validation.
Exceeded free limits cause errors; do not upgrade automatically. Existing
account-wide usage from other projects counts toward these limits.

This deployment needs only a Worker, D1, and a cron trigger. It does not activate
paid plans, custom domains, R2, Queues, containers, or paid observability.

## Validation

Run the component's focused tests with:

```sh
cd cloud/whop
npm test
```

This uses Node's built-in test runner. No live OAuth grant or public publishing
is performed by the test suite.

## Official references

- [Whop live OAuth discovery metadata](https://api.whop.com/.well-known/openid-configuration)
- [Whop OAuth PKCE guide](https://docs.whop.com/developer/guides/oauth.md)
- [Whop List Bounties contract](https://docs.whop.com/api-reference/beta/bounties/list-bounties.md)
- [Workers pricing and free limits](https://developers.cloudflare.com/workers/platform/pricing/)
- [Workers platform limits](https://developers.cloudflare.com/workers/platform/limits/)
- [D1 pricing and free-limit behavior](https://developers.cloudflare.com/d1/platform/pricing/)
- [D1 storage and query limits](https://developers.cloudflare.com/d1/platform/limits/)
- [Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/)
- [Workers Logs and invocation logging](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)

Cloudflare's developer website was blocked by this development environment's
current egress policy during review. The same official documentation source was
read successfully from the public
[`cloudflare/cloudflare-docs` repository](https://github.com/cloudflare/cloudflare-docs/tree/production/src/content/docs),
including its D1 pricing and free-limit FAQ partials. This verifies documentation;
it does not verify an owner's Cloudflare plan or production deployment.


For non-browser health/private API clients on `workers.dev`, identify this
application as `ContentRewardsAutomation/0.1`. Cloudflare's managed Browser
Integrity Check rejects some library-default identities, including Python
urllib, with error1010. The private reader and public verification workflow now
use this descriptive identity as prescribed by
[Cloudflare](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/).
The actual [HTTPS check passed](https://github.com/ahyadzyoud-cyber/content-rewards-automation-/actions/runs/40865214345);
it does not imply owner OAuth or production token renewal has passed.


The owner-form browser regressions run separately from the fast SQLite suite:

```sh
cd cloud/whop
npm ci --ignore-scripts --no-audit --no-fund
npx playwright install --with-deps chromium
npm run test:browser
```

With a prepared Chromium installation, set `CHROMIUM_EXECUTABLE_PATH` to that
binary instead of downloading another browser. Tests use isolated SQLite and
synthetic credentials, intercept all network traffic, and never authorize Whop
or touch production D1. CI uses the locked Playwright development dependency.
