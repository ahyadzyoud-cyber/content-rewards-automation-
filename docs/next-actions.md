# Owner participation required after publication

The existing cloud environment has been published. Its new active version and
live network access were verified. `REWARDS_LIVE_PUBLISHING` is configured and
remains disabled. The old proxy-blocked instructions are superseded; no new
environment, project rebuild or repeat of earlier local test suites is needed.

## Whop creator consent

A real official clipping/UGC bounty discovery adapter is available:

```bash
rewards discover-whop --country JO --goal clipping
```

It needs an owner-authorized **user OAuth** grant with `bounty:basic:read`, not
an account API key with different visibility. Use an existing trusted Whop app
and registered callback/PKCE flow, following the exact official dashboard steps
in [live Whop findings](live-whop-findings.md). No credentials, callback codes or
passwords belong in chat. If no trusted OAuth client/callback exists yet, that
account-owned app registration and secure token-store path must be established
before creator consent; the repository does not pretend to provide one.

The new API host `api.whop.com` was discovered in the now-accessible official
docs. A narrowly scoped network addition and **optional personal**
`WHOP_ACCESS_TOKEN` requirement were saved to the existing environment draft.
Review/save that addition with the eventual secure credential configuration,
then publish the updated environment. Existing published site access already
works; this addition is specifically for the authenticated API host. No prior
required social credential declarations were reintroduced.

Whop's public payout guide explicitly includes Jordan, but the owner must still
complete identity/payout onboarding and verify the actual method shown in the
account. The bounty country filter is creator residency. New-account acceptance,
material rights and campaign-specific requirements still need actual evidence.
Bounties pay fixed rewards and are not silently ranked as CPM Content Rewards.

Whop access tokens last one hour and refresh tokens rotate; a trusted callback
and secure durable renewal store are still needed for unattended discovery.
A short-lived personal access token enables a read-only live test only.

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
