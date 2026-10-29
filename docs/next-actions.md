# Owner participation required after publication

The existing cloud environment has been published. Its new active version and
live network access were verified. `REWARDS_LIVE_PUBLISHING` is configured and
remains disabled. The old proxy-blocked instructions are superseded; no new
environment, project rebuild or repeat of earlier local test suites is needed.

## Whop app registration and consent are the current priority

Cloudflare authorization now works. The existing account passed the free-plan
check (no account subscriptions), its missing free `workers.dev` namespace was
initialized, and this project's single Worker/private D1 service was deployed.
The generated encryption key and broker credential were retained across the
health-check update. The 30-minute renewal cron is installed; no real Whop grant
or production renewal has been verified yet.

The exact deployed callback to register is:

```text
https://content-rewards-whop.content-rewards-dc8a4aba9226.workers.dev/oauth/callback
```

**Next owner action:** open the [Whop Developer Dashboard](https://whop.com/dashboard/developer),
create/select this project's dedicated OAuth app, and register that exact callback.
Under **View available scopes**, enable only **`bounty:basic:read`**. The live
issuer's discovery metadata and List Bounties contract agree on that read-only
scope; neither `bounty` nor `bounty:basic` is advertised. Earlier basic-only
instructions have been superseded by this verified provider evidence.

Then complete these account-owned settings:

1. In Cloudflare **Workers & Pages → content-rewards-whop → Settings → Variables
   and Secrets**, set `WHOP_CLIENT_ID` to the app's public ID (normal text).
2. Set `OWNER_PASSWORD` as a Secret using a password-manager-generated random
   password of at least 32 characters. Keep it in your password manager.
3. Replace `WHOP_BROKER_API_TOKEN` with a separate generated random Secret of
   at least 32 characters. Enter that same machine credential only in this
   environment's secure `WHOP_BROKER_API_TOKEN` field, scoped to the exact Worker
   hostname. Do not change `TOKEN_ENCRYPTION_KEY` or the private D1 binding.
4. Deploy those Cloudflare setting changes. Review/save/**Publish** the pending
   existing-environment update containing the newly discovered exact Worker
   host, its nonsecret `WHOP_BROKER_URL`, and the optional machine credential.
   The address could only be added after real deployment. No new environment
   is needed. Leave `WHOP_ACCESS_TOKEN` empty and optional and keep
   `REWARDS_LIVE_PUBLISHING=false`.
5. Open the [owner authorization site](https://content-rewards-whop.content-rewards-dc8a4aba9226.workers.dev/),
   sign in with the owner password, choose **Authorize Whop discovery**, review
   the single `bounty:basic:read` permission on Whop, and consent as the actual
   Jordan-resident creator. The callback receives and encrypts credentials
   automatically; no callback URL/code, password or token is pasted into chat.

The agent can then verify the real account-visible clipping and UGC bounty
responses, persisted renewal and private cron results. Fixed rewards remain
separate from CPM Content Rewards. Weakness-first rankings still require dated
new-account, payout/KYC, rights/materials, platform, deadline and automation
permission evidence; no API grant establishes those campaign-specific facts.
See [Whop authorization](whop-authorization.md) and [the deployed broker](../cloud/whop/README.md).

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
