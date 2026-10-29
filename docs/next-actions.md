# Owner participation required after publication

The existing cloud environment has been published. Its new active version and
live network access were verified. `REWARDS_LIVE_PUBLISHING` is configured and
remains disabled. The old proxy-blocked instructions are superseded; no new
environment, project rebuild or repeat of earlier local test suites is needed.

## Whop authorization is the current priority

The existing source now includes a complete owner-operated PKCE callback,
encrypted private D1 credential storage, durable single-flight refresh-token
rotation, and unattended renewal/discovery. These are tested components, not an
already deployed Whop grant. The request uses exactly **`bounty:basic`**.

**Next owner action:** use an existing **Cloudflare Workers Free** account,
select its `workers.dev` namespace, and create an account-scoped API token with
**Account Settings Read**, **Workers Scripts Edit**, **D1 Edit**, and
**Billing Read**. Enter it only as the optional personal
`CLOUDFLARE_API_TOKEN` in this environment's secure settings, scoped to
`api.cloudflare.com`. Review/save the pending domain and startup changes and
**Publish the updated existing environment**. Keep `WHOP_ACCESS_TOKEN` empty
and optional and `REWARDS_LIVE_PUBLISHING=false`.

The agent can then perform the read-only free-plan preflight and deploy this
project's single private Worker/D1 service. No paid upgrade, another Codex
environment, or project rebuild is needed. The deployment will return the real
HTTPS callback to register in Whop. There is no callback address to register yet.

Follow [Whop authorization](whop-authorization.md) for the exact subsequent
owner steps: register that callback, configure the nonsecret client ID, set the
owner password securely, and complete consent inside Whop. No token, password,
callback URL or code is pasted into chat. The separate machine credential is
configured securely only after the actual broker hostname exists.

After consent, the worker checks renewal every 30 minutes and reads clipping
and UGC bounties for Jordan when its private snapshots are missing or six hours
old. Delayed cron delivery uses persisted due times. A new grant invalidates old
account observations and renewal evidence. Uncertain refresh writes stop for
reauthorization instead of replaying a consumed refresh token.

`rewards discover-whop --country JO --goal both` retrieves fixed rewards through
the private broker and reports weaknesses before scores. Unknown new-account
acceptance, owner payout/KYC, approved materials, rights, platforms, deadlines
or automation permission blocks selection. CPM Content Rewards remains a
separate lane requiring an approved source; fixed rewards never become CPM.

The public List Bounties contract separately names `bounty:basic:read`; the
implemented consent request stays `bounty:basic` as instructed. If Whop rejects
that exact scope, stop for provider clarification rather than adding permissions.

## Social account consent

Authorize the actual YouTube channel for upload, readonly and offline access,
then place its Google client ID, client secret, refresh token and channel ID in
secure environment settings. See [account authorization](account-authorization.md).

For Instagram, use the Meta app's **Instagram > API setup with Instagram
business login > Generate token** flow for the target professional account.
Configure `INSTAGRAM_ACCESS_TOKEN`, its professional `user_id` as
`INSTAGRAM_ACCOUNT_ID`, and the app-supported `INSTAGRAM_API_VERSION`.
Current official examples use `v26.0`; the chosen app and grants must still be
verified. See [current Meta instructions](instagram-authorization-current.md).
The corrected identity probe uses `/me` and distinguishes professional `user_id`
from app-scoped `id`. Secure renewal and approved immutable media hosting remain
operational prerequisites for continuous Instagram use.

## Vyro account and automation permission

Real public listings are documented in [live Vyro findings](live-vyro-findings.md).
The displayed-rate research shortlist begins with Total Drama Roblox offers at
$2.50 per 1,000 views, then Joy 101 at $2.00. No candidate is verified suitable
for a new Jordan-based creator: actual briefs, budget, account admission,
payout access and material rights remain unknown. Three public listings are
locked for new posts and must not be treated as open opportunities.

Vyro's terms prohibit unauthorized automated collection, and its content rules
also mention automated posting in prohibited spam promotion. Obtain a
provider-approved API/feed/export and confirmation that this specific workflow
and official social API scheduling are allowed. Complete creator/social linking
and actual Jordan payout verification inside the official account. A public
marketing rate or a personal social API grant is not permission from Vyro.

## Cloud operation and first video

The free observer reuses the existing worker on standard public GitHub runners
and persists only public observations in a small separate Git branch. It needs
no paid artifact storage, repository-variable permission, social tokens, or
computer left on. See [free observer](free-cloud-observer.md) for execution
proof and scheduling limits. It correctly reports blocked discovery until a
permitted source is configured, and it never publishes or handles a private
financial ledger.

Once account/provider permissions, real eligible terms and approved footage
exist, the agent can prepare the first actual video and its preflight packet.
Only then is owner publication approval requested. Until that review,
`REWARDS_LIVE_PUBLISHING=false` and `business_live=false` remain correct.
