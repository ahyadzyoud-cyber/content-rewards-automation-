# Actual campaign discovery and verification

Checked **2026-10-28**, beginning at `2026-10-28T13:33:32Z`. No actual
campaign records were obtained from Whop, Content Rewards, or Vyro during this
check. Consequently there is **no verified best campaign for new accounts in
Jordan yet**. Synthetic test/demo campaigns are not business opportunities and
must never be imported into the real ledger as if they were provider data.

## Observed access

| Public source requested | Observed result | What this establishes |
| --- | --- | --- |
| [Whop home](https://whop.com/) | Proxy CONNECT HTTP 403 | The cloud proxy blocked the HTTPS tunnel; the website itself was not reached. |
| [Candidate Whop Content Rewards listing](https://whop.com/content-rewards/) | Proxy CONNECT HTTP 403 | Neither this public route nor any campaign contents could be confirmed. This is not an API endpoint. |
| [Whop documentation](https://docs.whop.com/) | Proxy CONNECT HTTP 403 | Current documentation could not be read from this host. |
| [Whop API introduction](https://docs.whop.com/api-reference/introduction) | Proxy CONNECT HTTP 403 | No creator campaign API contract or authorization requirements were confirmed here. |
| [Vyro home](https://vyro.com/) | Proxy CONNECT HTTP 403 | No public campaign data or API documentation was obtained. |
| [Vyro robots.txt](https://vyro.com/robots.txt) | Proxy CONNECT HTTP 403 | Public crawler guidance could not be read. |
| [Vyro sitemap](https://vyro.com/sitemap.xml) | Proxy CONNECT HTTP 403 | No documentation or campaign-listing pointers were obtained. |
| [Official Whop SDK reference source](https://raw.githubusercontent.com/whopio/whopsdk-typescript/main/reference.md) | HTTP 200; 476,153 bytes | The public official SDK reference was readable. Its only campaign-related section was **Ad Campaigns**; no Content Rewards/clipping resource was found. |
| [Official Whop SDK README source](https://raw.githubusercontent.com/whopio/whopsdk-typescript/main/README.md) | HTTP 200 | Links the SDK to Whop's API documentation; contains no Content Rewards/clipping contract. |
| [Official Ad Campaigns client source](https://raw.githubusercontent.com/whopio/whopsdk-typescript/main/src/api/resources/adCampaigns/client/Client.ts) | HTTP 200 | Defines an Ad Campaign as a container for **paid ads on an ad network**. This must not be used as a creator rewards campaign API. |
| [Published `@whop/sdk` metadata](https://registry.npmjs.org/@whop/sdk/latest) | HTTP 200; version `2.6.0` | The registry identifies Whop's official SDK repository. The package archive matched its registry-provided SHA-512 integrity. Of 93 top-level API resource groups, only `adCampaigns` was campaign-related. |

These results do not prove that a separate, private, or newly introduced
Content Rewards/Vyro API does not exist. They establish that no applicable
documented API was available to implement from the accessible official sources.
No provider login, restricted scraping, reverse-engineered private endpoint,
submission write, payout operation, or paid advertising action was attempted.

The intended Vyro platform is **`https://vyro.com/`**, as identified by the
owner. Other similarly named domains or AI-generation products are not sources
for this business.

## Network prerequisite

The saved draft inspected for this check allowed `docs.whop.com` and
`vyro.com`; it did not yet include `whop.com`. All three public destinations
remained blocked in the current machine. A draft rule does not prove that the
running proxy has applied it.

Preserve existing custom domains and presets when adding `whop.com`. Apply the
environment settings to the running environment, then retry these specific
public reads. Do not disable TLS verification, bypass the platform proxy, or
interpret this proxy failure as an account-login or campaign-eligibility result.
Reaching a public website later still will not establish permission to scrape
or access an undocumented authenticated API.

## What can unblock actual campaign selection

One of the following provider-supported inputs is required for each platform:

* A publicly documented, permitted read-only campaign listing/feed, including its
  actual URL, schema, access terms, and any necessary authorized account scope.
* A provider-supported export of available campaigns and their full terms from
  the owner's authorized account. Use an export or other permitted material;
  never send account cookies, passwords, or raw tokens in chat.
* Official API documentation supplied by the provider, plus authorization for
  the specific discovery/submission/earnings operations. Permission to read a
  generic Whop merchant API is insufficient evidence for Content Rewards access.

No extra API key is requested merely because a public network request failed.
First resolve public connectivity and identify an actual applicable contract.
If authentication is then required, configure credentials through secure
environment settings and verify the precise read-only operation before enabling
recurring discovery. Neither a working generic API call nor an API key's
presence proves access to all campaigns.

For a first real campaign, collect the following source evidence before marking
its normalized record verified:

| Required evidence | Selection decision it supports |
| --- | --- |
| Campaign/provider ID and canonical terms URL, with observation time | Links the opportunity to a real, current source. |
| Reward currency, rate, qualifying-view definition, caps, fees and payment conditions | Allows a meaningful profitability comparison; advertised rates are not guaranteed income. |
| Remaining distributable budget and active/deadline status | Prevents selecting exhausted or closed opportunities. |
| Creator-residency rules explicitly permitting Jordan, or authoritative provider confirmation | Establishes creator eligibility. Audience-location requirements must be checked separately. |
| Jordan payout availability and the owner's completed identity/payout verification | Establishes that participation can actually result in a receivable payout. |
| New-account permission, minimum followers/account age, account approval requirements and supported YouTube/Instagram posting | Determines whether a newly created channel/account qualifies. |
| Complete content, disclosure, attribution, language, audience geography and submission requirements | Determines whether the proposed content can comply. |
| Explicitly approved downloadable materials and their license/usage restrictions | Establishes rights to edit, host and publish the exact material on the selected platform. |
| Competition entry count, if officially available | Supports competition scoring; missing data remains unknown. |

The current score is a transparent **prioritization heuristic**, not a forecast
of profit: reward rate, verified country eligibility, competition, remaining
budget, and requirement complexity contribute up to ten points. Unknown
competition is not counted as no competition. Hard eligibility, fresh-evidence,
new-account, platform, material-rights, active-budget and requirement gates apply
even when a campaign has a high numeric score. Review net costs and any
provider-specific restrictions from actual terms before treating a high score
as a business decision.

## Existing implementation available once evidence is obtained

The project can already validate/import normalized records, clear verification
assertions from untrusted feeds, rank separately for YouTube and Instagram,
prepare approved local media, and preserve observed metrics independently from
operator-evidenced submissions and earnings. A provider feed cannot approve
its own eligibility or publication.

Add a live provider connector only after the actual official contract is
verified. Do not add a placeholder adapter that returns test campaign names,
reuse paid advertising endpoints, infer Jordan eligibility from the provider's
global availability, or call view-derived estimates confirmed earnings. Account
authorization, payout setup, exact first-publication review, and any paid
service remain separate owner-controlled actions.
