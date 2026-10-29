# Whop owner authorization

This extends the existing project. Public posting remains disabled:
`REWARDS_LIVE_PUBLISHING=false`. No campaign is joined or paid service activated.

The OAuth broker is deployed on the owner's verified Cloudflare Workers Free
account. Its exact callback is:

```text
https://content-rewards-whop.content-rewards-dc8a4aba9226.workers.dev/oauth/callback
```

[Public HTTPS verification passed](https://github.com/ahyadzyoud-cyber/content-rewards-automation-/actions/runs/40865214345),
including database/key health and clean invalid-callback redirects.

The live grant is not yet authorized. Configure the owner-controlled Whop app and
Cloudflare secrets following [current owner steps](next-actions.md). The general
deployment instructions below are retained for maintenance, not a request to
create another service or repeat the completed deployment.

## Permission requested

The authorization request contains only **`bounty:basic:read`**. It adds no
OpenID, email, profile, submission, advertising, funding or payout permission.
It does not restrict the grant to a Whop business account.

The scope discrepancy was resolved before requesting consent on 2026-10-29.
Whop's live [OAuth discovery metadata](https://api.whop.com/.well-known/openid-configuration)
returned HTTP 200 with issuer `https://api.whop.com` and advertised
`bounty:basic:read` in `scopes_supported`. Neither `bounty` nor `bounty:basic`
appears in that advertised list. This agrees with the required permission in
[Whop's List Bounties reference](https://docs.whop.com/api-reference/beta/bounties/list-bounties.md).
The previous `bounty:basic` request was corrected to this explicitly read-only
permission; the service never adds write, submission or payout scopes. A live
grant and successful listing still require separate verification.

A dedicated minimal app avoids reusing a grant that previously accumulated
broader permissions. Existing grants can be reviewed or revoked in
[Whop Authorized apps](https://whop.com/dashboard/settings/authorized-apps).

## Deploy the callback before registering it

The exact first prerequisite is an owner-authorized Cloudflare account on
**Workers Free**, with its `workers.dev` subdomain selected in the account's
Workers dashboard. In **My Profile → API Tokens → Create Token → Create Custom
Token**, restrict the token to that account and grant only:

* Account Settings: Read.
* Workers Scripts: Edit.
* D1: Edit.
* Billing: Read, for the helper's read-only subscription/free-plan check.

Do not add billing write or purchase permissions. Set `CLOUDFLARE_API_TOKEN`
using this existing environment's secure secret configuration, restricted to
`api.cloudflare.com`; do not paste it into chat. `CLOUDFLARE_ACCOUNT_ID` is a
nonsecret optional setting when the token exposes exactly one account; set it
explicitly if more than one account is visible.

The prepared deploy helper first performs a read-only free-plan preflight:

```sh
.venv/bin/python scripts/deploy_whop.py --preflight
```

After a successful free-plan check it can deploy the prepared component:

```sh
.venv/bin/python scripts/deploy_whop.py --apply
```

The helper does not activate Workers Paid, purchase a subscription or add payment
information. It refuses an unverified or paid-plan account. Free-tier exhaustion
must stop execution rather than upgrade the account. The deployment's actual
confirmed callback is then registered in Whop; `WHOP_CLIENT_ID` can be set after
registration and the same helper rerun without rebuilding this project.
See [the cloud broker](../cloud/whop/) for operation details.

The published free quotas are 100,000 Worker requests per day, 5 million D1
rows read per day, 100,000 D1 rows written per day, and 5 GB total D1 storage.
Cloudflare's D1 FAQ states that Free-plan quota exhaustion returns errors; it
does not automatically upgrade the plan. Check account-wide usage, since
limits can be shared with other projects.

The deployed worker's actual HTTPS origin is `PUBLIC_ORIGIN`. The exact callback
is that origin followed by `/oauth/callback`. Do not register this document's
placeholder hostname, a localhost address, or a guessed `workers.dev` hostname.
Use the deployment's confirmed URL. The worker checks an exact HTTPS origin;
OAuth redirect matching does not permit an added trailing slash or query string.

The deploy helper generates and uploads the initial encryption key without
printing it or saving it in a local file; later deployments preserve that key.
Set or replace the owner password and separate machine credential directly in
**Cloudflare → Workers & Pages → the deployed Worker → Settings → Variables
and Secrets**, using secret fields. Save their owner-managed copies in a
password manager; they are never entered in chat.

Keep these values only in the hosting platform's secure configuration:

| Setting | Purpose |
| --- | --- |
| `OWNER_PASSWORD` | Long random owner login password; at least 32 characters. |
| `WHOP_BROKER_API_TOKEN` | Long random server-to-server broker credential; at least 32 characters. |
| `TOKEN_ENCRYPTION_KEY` | 32 random bytes, encoded as 43-character unpadded base64url; encrypts persistent credentials. |

Keep the encryption key stable across deployments. Replacing it without a
controlled migration makes previously encrypted credentials unreadable. Never
put these values in a repository, chat, issue, build log or workflow artifact.
Use platform secret fields; the deploy helper never asks you to paste credentials into its command arguments. Nonsecret
`WHOP_CLIENT_ID`, confirmed `PUBLIC_ORIGIN` and
`REWARDS_LIVE_PUBLISHING=false` belong in normal configuration.

## Register the Whop app and authorize

After the deployment reports a verified HTTPS URL:

1. Open the [Whop Developer Dashboard](https://whop.com/dashboard/developer).
   Select the dedicated app for this project, or create a dedicated OAuth app
   if none exists. Do not purchase anything or configure a paid product.
2. In the app's **OAuth** section, register the deployment's **exact**
   `https://ACTUAL_WORKER_HOST/oauth/callback` URI. Replace the example hostname
   with the confirmed real host. Under **View available scopes**, select only
   `bounty:basic:read`. If the app does not offer that exact permission, stop and
   verify app eligibility with Whop; do not select a broader permission.
3. Set the app's nonsecret client ID (`app_...`) as `WHOP_CLIENT_ID` through the
   deployment configuration. The documented PKCE exchange does not require
   copying an app client secret into this project.
4. Open the deployed site's HTTPS root and sign in using its securely configured
   owner password. Select **Authorize Whop**. The broker creates a short-lived,
   browser-bound, single-use state and PKCE S256 transaction before redirecting
   to Whop.
5. Sign in to Whop as the actual Jordan-resident creator, review the requested
   permission, and approve it if correct. Whop returns directly to the registered
   callback. Do not copy the callback URL, authorization code, access token or
   refresh token anywhere.
6. Wait for the broker's sanitized success or blocking message. A successful
   callback stores tokens server-side; it does not display them to the browser.
   Authorization and the first real listing still need live verification.

The broker uses `POST https://api.whop.com/oauth/token` with PKCE, refreshes
before access-token expiry, and persists each rotated refresh token. It must
serialize refresh attempts and stop after an uncertain rotation rather than
retrying an already-used token. Tests verify implementation behavior with
fixtures; only a real grant can verify Whop's actual response and renewal.

`WHOP_ACCESS_TOKEN` remains an optional legacy credential; it is not part of the
owner authorization process and should not be manually copied after consent.

## What happens after authorization

The official read-only listing requests open clipping and `ugc_content` bounties
with `country=JO`. That country is creator residence. Results remain fixed
rewards per approved submission, with their original currency, quoted net reward,
remaining slots, pending submissions, and provider terms preserved. They are not
converted to CPM campaigns.

CPM-based **Content Rewards** remains a separate discovery lane. Its official
guide describes per-1,000-view payments, but the researched public documentation
does not establish that the fixed-reward Bounties API lists those campaigns.
Use an explicitly approved API/feed/export or provider permission for that lane;
never scrape restricted creator pages or invent a CPM rate from a fixed prize.

Opportunity reviews must list weaknesses first and score verified evidence out
of 10. A country match and a rate are insufficient. Until new-account acceptance,
owner payout/KYC eligibility, active budget/slots, approved source material and
rights, target-platform requirements, and automation permission are verified,
the opportunity remains blocked. No real opportunity or first video was
approved by this implementation work.

Whop's public payout guide lists Jordan, but the owner still completes any KYC
and chooses an available payout method directly inside Whop. Passwords, identity
documents and bank/payment details never belong in this chat.

## Official references checked 2026-10-29

* [Live OAuth discovery metadata](https://api.whop.com/.well-known/openid-configuration)
* [OAuth 2.1 and PKCE](https://docs.whop.com/developer/guides/oauth.md)
* [Permissions](https://docs.whop.com/developer/guides/permissions.md)
* [Permission Catalog](https://docs.whop.com/api-reference/beta/api-keys/list-the-permission-catalog.md)
* [List OAuth Grants](https://docs.whop.com/api-reference/beta/users/list-oauth-grants.md)
* [List Bounties](https://docs.whop.com/api-reference/beta/bounties/list-bounties.md)
* [Troubleshooting, including invalid/insufficient scope](https://docs.whop.com/developer/troubleshooting.md)
* [Jordan and other supported payout countries](https://docs.whop.com/manage-your-business/manage-payouts/set-up-payouts.md)
* [Content Rewards](https://docs.whop.com/memberships-and-access/third-party-apps/content-rewards.md)
* [Workers pricing, official source](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers/platform/pricing.mdx)
* [D1 pricing, official source](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/d1/platform/pricing.mdx)
* [D1 free quotas, official source](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/partials/workers/d1-pricing.mdx)
* [D1 free quota exhaustion behavior, official source](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/partials/d1/faq-pricing.mdx)
