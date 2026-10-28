# Vyro public-access findings

Checked **2026-10-28** after the cloud environment was published. The intended
provider is [vyro.com](https://vyro.com/), the creator clipping/rewards platform.
The earlier proxy-blocked observation is superseded for this host: its public
home, campaign index, terms, creator terms, help index, content requirements,
robots and public campaign sitemap each returned HTTP 200.

This was a bounded review of public pages. No account was created, no gated app
page or private endpoint was queried, no source media was downloaded, and no
campaign was marked eligible or imported into the publishing ledger.

## Real public campaign observations

Source: [Vyro's public campaign index](https://vyro.com/campaigns). The page
advertises rates **per one million views**; the table divides those displayed
rates by 1,000 to show the comparable advertised rate per 1,000 views. The page
uses the `$` symbol; settlement currency and qualifying-view calculation still
need confirmation from the applicable brief/account. These are advertised
rates, not estimates of likely income.

| Research priority by displayed rate | Public campaign label | Advertised rate / 1,000 views | Observed limitation |
| --- | --- | --- | --- |
| 1 (tie) | [Sinjin: ROBLOX TOTAL DRAMA ISLAND is mean…](https://vyro.com/campaigns/flamingo-roblox-total-drama-island-is-mean-7nOCbhEf) | $2.50 | Campaign brief, budget, creator eligibility and new-account rules unknown |
| 1 (tie) | [StinkyAsher: I PLAYED IN THE FIRST EVER TOTAL DRAMA ROBLOX TOURNAMENT](https://vyro.com/campaigns/flamingo-roblox-total-drama-island-is-mean-84rRsLDH) | $2.50 | Same unknowns |
| 1 (tie) | [Mitch Gaming: i competed in a TOTAL DRAMA ROBLOX TOURNAMENT](https://vyro.com/campaigns/stinkyasher-i-played-in-the-first-ever-total-drama-roblox-tournament-b1Twfv00) | $2.50 | Same unknowns |
| 1 (tie) | [Flamingo: ROBLOX TOTAL DRAMA ISLAND is mean…](https://vyro.com/campaigns/total-drama-roblox-streamer-tournament-3u_iicP8) | $2.50 | Same unknowns |
| 2 | [Joy 101 — iHeartPodcasts](https://vyro.com/campaigns/dont-lie-to-me-sxwKjxIU) | $2.00 | Same unknowns |
| 3 (tie) | [Shark Tank Edits — Ketone-IQ](https://vyro.com/campaigns/shark-tank-edits-TOV7A-kY) | $1.50 | Same unknowns; product claims/rights require actual brief review |
| 3 (tie) | [Microdrama series — Valorant](https://vyro.com/campaigns/microdrama-series-episode-1-xurZBrxP) | $1.50 | Same unknowns |
| 3 (tie) | [Valorant Champs Shanghai Podcast](https://vyro.com/campaigns/valorant-champs-shanghai-podcast-RwfZmYQt) | $1.50 | Same unknowns |
| 3 (tie) | [YT Only: Cinematic edits — Ketone-IQ](https://vyro.com/campaigns/cinematic-edits-CvTq3Hys) | $1.50 | Title suggests YouTube only; do not assume Instagram permission |

The index also marks these three campaigns **“Locked for new posts”**:

* MrBeast Gaming: Escape Call of Duty's DMZ, Win $1,000,000 — $1.50/1,000.
* Lose 150 Lbs Together, Win $250,000 — $1.00/1,000.
* Don't Lie To Me Podcast — $2.00/1,000.

Some public card labels differ from the slugs in their own links. The table
preserves the observed label/link association; it does not claim the linked
campaign brief has been verified. Do not resolve these differences by guessing
campaign identity or reusing older cached names.

No candidate is currently verified suitable for a new Jordan-based creator.
Remaining budget, competition, qualifying-view conditions, account-age/follower
minimums, creator-country admission and source/editing/hosting permissions are
unknown. Therefore a full profitability/eligibility score out of ten or an
automatic selection would overstate the evidence. The order above is only a
research priority by publicly advertised reward rate.

## Eligibility and payout evidence

[Creator Terms](https://vyro.com/clipper-terms) require legal residency in a
territory where Vyro makes the platform available, age 18 or older and local age
of majority, complete registration, at least one eligible social account, social
account authentication/linking, and approval by the applicable payment provider.
Campaigns can be open-entry or invite-only; Vyro/client decides which creators
may participate. No explicit Jordan admission or universal new-account
permission was established from the reviewed public resources.

The [home FAQ](https://vyro.com/) says withdrawals start at $10, once per week,
with Stripe or PayPal depending on location. The Creator Terms also describe
third-party processors (including Whop as an example) and provider approval.
These statements do not establish which route the owner's Jordan account can
actually use. Verify the actual account's payout onboarding before relying on
any campaign reward.

The FAQ says social accounts must be linked before a post can be submitted;
views count from submission, pending figures update hourly, and approval plus
the campaign's minimum threshold are required for earning. Campaign pool
exhaustion can stop accrual. A general social view count is not evidence of a
Vyro-approved balance or cash received.

## Automation permission is a separate blocker

[robots.txt](https://vyro.com/robots.txt) allows public paths and excludes
`/admin`. This permits discovering public pages for this review but does not
override the provider's terms or grant a recurring data-collection license.

The [Terms](https://vyro.com/terms) and
[Creator Terms](https://vyro.com/clipper-terms) prohibit data mining, scraping,
AI/LLM training or other unauthorized data collection. The
[Content Requirements](https://vyro.com/content-requirements) explicitly list
“Using bots, scrapers, or automation to collect or manipulate platform data”
under unauthorized data access. They also prohibit spam promotion, giving
automated posting as an example. That wording does not establish permission
for this project's scheduled campaign collection or social publishing.

No public official campaign discovery/submission/earnings API contract or
provider-approved normalized feed was found in the reviewed public links.
References to “API integrations” in these terms describe Vyro connecting to
social platforms; they do not grant third parties a Vyro API.

Consequently:

* Do not configure a recurring Vyro HTML scraper, replay private app calls or
  infer an API from the app's internal implementation.
* Use only a provider-approved API/feed/export, with explicit authorization for
  its intended automated use and public redistribution if cloud artifacts are
  involved.
* Before automated Vyro campaign posting, obtain confirmation that official
  social API scheduling for the actual campaign is permitted, together with
  approved materials/editing/hosting rights and required disclosures.
* The owner must complete Vyro social authentication, creator-country/account
  verification and actual payout onboarding inside the official account. No
  password, cookie or payment secret should be supplied in chat.

Public observations are stored separately in ignored
`.data/research/vyro-public-observations.json`; they are not a permitted recurring
feed, approval, campaign selection or earnings record.
