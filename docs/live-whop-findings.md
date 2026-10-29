# Whop and Content Rewards: verified access findings

## Current authenticated result

After the latest owner consent, production checks confirmed authorization
`ready`, five persistent refresh-token rotations, a successful read-only
`bounty:basic:read` grant, two encrypted discovery snapshots and a successful
scheduled renewal run. Fresh authenticated listing completed every page for
both clipping and UGC and returned two open fixed-reward offers admitting
Jordan residents. The original records and review details remain private;
they are not redistributed into this public repository or observer branch.
The owner can read saved briefs on the existing private
[opportunities page](https://content-rewards-whop.content-rewards-dc8a4aba9226.workers.dev/opportunities).

Neither offer is verified selectable: owner payout/KYC, material rights,
new-account terms and automation permission remain unresolved. The briefs
also contain livestream requirements; those cannot be silently replaced with
automated work. No campaign was joined, no video was published, no payout was
requested and no earnings were claimed. Fixed rewards are not CPM offers.

Global discovery retains `country=JO`: the official list contract explicitly
says worldwide bounties always match the creator-residency filter. This finds
worldwide opportunities while respecting actual residency restrictions, rather
than restricting discovery to Jordan advertisers.

The following sections retain the earlier access research and protocol history.
Their initial no-grant/no-shortlist limitations are superseded by the current
authenticated result above; campaign-specific eligibility remains unverified.

Public contracts rechecked on 2026-10-29 (Asia/Amman).

## Access now works

The public Whop site and documentation return HTTP 200. The old
`https://docs.whop.com/api-reference/introduction` URL redirects to a login page,
but that does **not** mean all current documentation requires authentication.
The official documentation publishes an [LLM index](https://docs.whop.com/llms.txt),
including its current developer and API reference indexes, and linked Markdown
pages are publicly readable.

`https://whop.com/content-rewards/` returned HTTP 200, but its anonymous rendered
content was a Whop community home with no campaign listings. A successful HTTP
response from that path is therefore not evidence of real campaign discovery.

## What Content Rewards officially supports

The [Content Rewards guide](https://docs.whop.com/memberships-and-access/third-party-apps/content-rewards.md)
describes clipping and original UGC campaigns, advertiser-selected social
platforms, campaign budgets, reward rates per 1,000 views, minimum and maximum
payouts, optional flat bonuses, approved footage, and campaign requirements.
It states that advertiser approval precedes view-based creator payment.

Examples in that guide, including named hypothetical campaigns, are examples
of campaign configuration. They are not current funded opportunities and are
not included as real campaign recommendations.

## A documented clipping-bounty API exists

The current [Bounties guide](https://docs.whop.com/developer/bounties/overview.md)
explicitly describes using bounties to run clipping or UGC programs. This is a
real official integration route that can be investigated after owner consent:

* [List Bounties](https://docs.whop.com/api-reference/beta/bounties/list-bounties.md):
  `GET https://api.whop.com/api/v1/bounties`.
* Documented filters include `status=open`, `business_goal_type=clipping` or
  `ugc_content`, and `country=JO`.
* The country filter means countries where workers **reside**, rather than
  the countries of their audience. An empty `allowed_country_codes` list means
  worldwide in this particular API contract.
* The List Bounties reference requires **`bounty:basic:read`**. Whop's live
  [OAuth discovery metadata](https://api.whop.com/.well-known/openid-configuration)
  returned HTTP 200 on 2026-10-29 and advertises that exact scope. It advertises
  neither `bounty` nor `bounty:basic`; no alias is inferred. Initial consent now
  requests only the verified read permission, with no write or identity scope.
  A user OAuth token lists bounties that the user can see and work. An account
  API key represents an account and primarily lists its own bounties; it is not
  equivalent to creator marketplace access.
* [Retrieve Bounty](https://docs.whop.com/api-reference/beta/bounties/retrieve-bounty.md)
  permits anonymous reads of an already-known public bounty ID. It does not
  provide anonymous marketplace listing. No actual public bounty ID was obtained.
* [Auth & API Keys](https://docs.whop.com/developer/guides/auth-scoping.md)
  distinguishes user OAuth from account/app API credentials.

No authenticated bounty request was made because no Whop creator OAuth grant is
configured. During the initial research, `api.whop.com` was absent from the
published egress domains and required an allowlist update. After the owner's
subsequent environment publication, the official API host returned HTTP 200
for its public OAuth discovery metadata. That resolves the old network blocker
for this metadata request; it does not establish authenticated bounty access.

Bounties are **not assumed to be the same product or pricing model as CPM
Content Rewards**. Bounty contracts expose gross rewards and winner slots;
those values cannot honestly be converted to a reward rate per 1,000 views.
Any connector must retain that distinction and must not fund a bounty or
activate advertising. Paid advertising campaign APIs are not substitutes for
creator rewards.

## Jordan payout support: documented, account still unverified

Whop's official [Set Up Payouts guide](https://docs.whop.com/manage-your-business/manage-payouts/set-up-payouts.md)
explicitly lists **Jordan** among supported payout countries. It requires country
selection, identity/KYC verification, and an available payout method. The
[Payout Methods guide](https://docs.whop.com/manage-your-business/manage-payouts/payout-methods.md)
states that available methods vary by country and are shown in the account's
withdrawal flow.

This establishes general published payout-country support. It does not verify
this owner's identity, account access, bank/method availability, campaign
participation, new-account acceptance, or actual payout receipt. Creator
residency, audience geography, social-account eligibility and payout eligibility
must remain separate checks.

## Permitted methods and actual campaign status

[Whop's Terms](https://whop.com/tos/) prohibit automated monitoring/scraping of
the service without written consent. Its `robots.txt` allows public paths and
disallows `/api/`, but robots permission is not a replacement for the Terms.
Campaign-page crawling was stopped after reading those terms. No login-gated
pages, private web endpoints, session cookies or access-control bypasses were
used. Public developer documentation explicitly offers an index for AI tools;
that documentation was used to identify supported API routes.

**Real campaign shortlist: unavailable.** No actual campaign records, current
budgets, approved materials or creator-specific terms were obtained. There is
therefore no defensible ranked recommendation for a new creator in Jordan yet.
The next permitted discovery step is owner-authorized user OAuth for the
documented clipping-bounty route, or a provider-approved Content Rewards export,
feed/API, or written automation permission. API access alone will not establish
that a given campaign accepts a brand-new YouTube/Instagram account.

## Implemented read-only connector

`content_rewards.whop.WhopBounties` now implements the documented authenticated
GET list operation and cursor pagination. Its API date is explicitly pinned to
the reference's `2026-10-28` contract. It sends bearer credentials only in the
Authorization header, follows no redirects, bounds pages/response size, and
sanitizes provider failures. It contains no funding, submission, advertising,
publication or payout writes.

The returned observations preserve the original record, quoted gross/net fixed
reward, total pool, slots and pending work, lifecycle state and creator-country
rules. New-account acceptance, rights and payout verification remain false.
Partial pagination is explicitly identified. The connector does not create fake
CPM rates or mark a candidate selectable based on its appearance in a response.

Validation: **33 connector tests passed** using HTTPX mock responses. They cover
actual documented request construction, pagination, country mismatches, fixed
reward preservation, malformed records, redirects and credential-safe errors.
The existing project was not rebuilt and prior suites were not rerun. A live
creator-authorized API result is still required before claiming real discovery.

## Owner authorization and verified read-only scope

The public [OAuth guide](https://docs.whop.com/developer/guides/oauth.md),
[List Bounties reference](https://docs.whop.com/api-reference/beta/bounties/list-bounties.md),
[Permission Catalog reference](https://docs.whop.com/api-reference/beta/api-keys/list-the-permission-catalog.md),
[List OAuth Grants reference](https://docs.whop.com/api-reference/beta/users/list-oauth-grants.md),
and [Troubleshooting guide](https://docs.whop.com/developer/troubleshooting.md)
were rechecked on 2026-10-29. The contracts establish:

* Authorization is `GET https://api.whop.com/oauth/authorize` with
  `response_type=code`, exact registered `redirect_uri`, random `state`,
  PKCE `code_challenge`, and `code_challenge_method=S256`.
* Code exchange is `POST https://api.whop.com/oauth/token`, JSON body containing
  `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, and
  `code_verifier`. The documented PKCE exchange does not send `client_secret`.
* Access tokens last one hour. Refresh uses the same token endpoint and JSON
  `grant_type=refresh_token`, `refresh_token`, and `client_id`. **Refresh tokens
  rotate on every use.** A successful replacement must be durably stored before
  another unattended run uses it. If `company_id` was used at authorization, it
  must match during refresh; this creator discovery flow omits account scoping.
* The token interface documents `access_token`, `refresh_token`, `token_type`,
  and `expires_in`. It does not promise a `scope` echo. `id_token` is optional
  and only appears when `openid` was requested. Requesting profile, email or
  OpenID scopes is unnecessary for an owner-operated bounty reader, and
  `/oauth/userinfo` must not be used without its required `openid` scope.
* The beta listing operation explicitly requires `bounty:basic:read`. The
  Permission Catalog describes complete action identifiers such as
  `company:basic:read`; retrieving its actual data requires authentication.
  OAuth Grants likewise describes fully qualified actions.
* **The live issuer metadata resolves the prior uncertainty.** At 14:13
  Asia/Amman on 2026-10-29, anonymous GET
  `https://api.whop.com/.well-known/openid-configuration` returned HTTP 200,
  issuer `https://api.whop.com`, the documented authorization/token endpoints,
  and `scopes_supported` containing `bounty:basic:read`. Neither `bounty` nor
  `bounty:basic` appears in that advertised list. The current broker requests
  exactly `bounty:basic:read`, and rejects an explicitly different returned
  permission rather than widening authorization.
* Earlier implementation retained `bounty:basic` at the owner's explicit
  instruction while only the documentation discrepancy was known. That was
  historical, unverified behavior; no real grant was obtained with it. The
  latest request to verify the official read-only scope, combined with the
  live issuer evidence, led to correcting the request **before any consent**.
  This is a documented scope correction, not a claim that the unsupported
  strings are aliases. No identity, submission, write or payout scope is added.
* OAuth error bodies can contain `error` and `error_description`. Do not echo
  arbitrary descriptions, provider bodies, callback URLs or credentials to logs
  or chat. A denied grant is not a reason to request account passwords.
* Existing grants can accumulate permissions across authorizations. Use a
  dedicated minimal app or review/revoke older broader grants in
  [Authorized apps](https://whop.com/dashboard/settings/authorized-apps) before
  treating a new minimal authorization request as proof of a minimal token.

See [Whop authorization](whop-authorization.md) for the owner-operated setup
and the real callback deployment prerequisite. The authorization code travels
from Whop directly to the registered callback; the owner does not copy a code,
callback URL, access token or refresh token into chat or a terminal command.

A deployable callback implementation does not establish that a public callback
already exists. No real owner grant, live token rotation, Jordan-filtered bounty
response or CPM campaign was verified during this documentation review.
