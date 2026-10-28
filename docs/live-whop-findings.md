# Whop and Content Rewards: verified access findings

Checked on 2026-10-28 after the environment was published. No account credentials
were supplied, no campaign was joined, and no content or payout was submitted.

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
* The documented read scope is `bounty:basic:read`. A user OAuth token lists
  bounties that the user can see and work. An account API key represents an
  account and primarily lists its own bounties; it is not equivalent to creator
  marketplace access.
* [Retrieve Bounty](https://docs.whop.com/api-reference/beta/bounties/retrieve-bounty.md)
  permits anonymous reads of an already-known public bounty ID. It does not
  provide anonymous marketplace listing. No actual public bounty ID was obtained.
* [Auth & API Keys](https://docs.whop.com/developer/guides/auth-scoping.md)
  distinguishes user OAuth from account/app API credentials.

No authenticated API request was made because no Whop creator OAuth grant is
configured. `api.whop.com` was not included in the published custom egress
domains inspected at the start of this research; a supported environment
allowlist update is needed before testing this specific API route.

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

## Exact owner authorization prerequisite

Whop's public [OAuth guide](https://docs.whop.com/developer/guides/oauth.md)
was read successfully on 2026-10-28. It documents OAuth 2.1 with PKCE, rather
than a creator token that can simply be copied from **API keys**. The owner
must use an existing trusted OAuth client and callback flow:

1. Open the documented [Developer Dashboard](https://whop.com/dashboard/developer)
   and select the existing app authorized for this integration. In its **OAuth**
   section, register the callback's exact redirect URI. Do not copy the guide's
   example callback URL into this project: this repository does not currently
   provide a Whop consent/callback server or a secure token vault.
2. Use **View available scopes** in the OAuth section to request
   `bounty:basic:read`, the scope named by the List Bounties reference. Grant no
   funding, payout, advertisement or submission writes. Additional identity
   scopes are only needed if the trusted flow actually uses userinfo.
3. Start the trusted app's **Sign in with Whop** flow and sign in as the actual
   creator. Review and approve the requested read permission. The documented
   authorize endpoint is `https://api.whop.com/oauth/authorize`; the trusted
   client generates state and a PKCE S256 challenge. Do not narrow the grant to
   one `company_id` unless account-scoped access is actually intended.
4. The trusted callback verifies the returned state and exchanges the code using
   `POST https://api.whop.com/oauth/token` with the matching redirect URI,
   client ID and PKCE verifier. **Do not paste the callback URL, authorization
   code, token, client secret or password into chat.** The documented PKCE
   example does not send a client secret in that exchange; this read connector
   does not require one merely because the app dashboard also displays it.
5. Deliver the authorized access token through secure credential settings as
   `WHOP_ACCESS_TOKEN`, restricted to `api.whop.com`. Then the existing
   read-only connector can verify actual access and inspect returned bounty
   terms. If permissions were newly added to an existing app, the official
   [Permissions guide](https://docs.whop.com/developer/guides/permissions.md)
   identifies **Dashboard → Settings → Authorized apps** for re-approval.

If no trusted registered OAuth client/callback exists, establishing that
authorization path is a prerequisite; the connector cannot obtain a user grant
from an account API key or extract a first-party login session instead. No app
was created or installed during this research.

Whop documents a one-hour access-token lifetime and refresh-token rotation on
every refresh. Unattended operation therefore additionally needs a legitimate
renewal flow that stores each rotated credential in a secure persistent store.
The current connector accepts an already-authorized token and does not claim
that renewal or secure rotation storage is operational. Neither OAuth consent
nor a successful country-filtered result proves new-social-account acceptance,
campaign compliance or completed payout verification.
