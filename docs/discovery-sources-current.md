# Current official campaign discovery

Research checked on 2026-10-30. No new offer is verified eligible, no campaign
video is represented as fully compliant, and publication remains disabled.
The former two offers remain deferred; they were not forced into another workflow.

## Wider Whop bounty discovery

The official [List Bounties contract](https://docs.whop.com/api-reference/beta/bounties/list-bounties.md)
says `business_goal_type` is optional and excludes pre-taxonomy offers when
present. Removing that filter returned **63 open bounties**, fully paginated,
using the existing read-only owner grant. Twelve had no declared goal. The
`country=JO` filter includes worldwide offers and other offers admitting the
actual creator residence; it does not limit the search to local advertisers.

```sh
rewards discover-whop --country JO --goal all --max-pages 20
```

Full private briefs were reviewed for video relevance. Most new records concern
engagement, reviews, bulk messages or referrals rather than legitimate video
creation. Other records require paid-sale conversions, unrelated work or
unverified admission. Newly found promotional/video offers have specific
blockers: one supplies footage but requires a submission livestream and
unverified betting-promotion permissions; another requires an Instagram Story
and community enrollment whose exact product/price is unresolved. A Reel is
not a substitute for a Story, and a paid enrollment is not authorized.

The existing encrypted cloud schedule now includes all open goals. It retains
the old storage keys/encryption purposes and public/private separation; no D1
schema, credentials or scope changed. Bounded snapshots explicitly report
incomplete pagination rather than pretending to cover the entire marketplace.

## Public marketplace leads, separate from bounties

The official [List Products contract](https://docs.whop.com/api-reference/beta/products/list-products.md)
supports anonymous public marketplace searches when `account_id` is omitted.
The verified request contract uses `Api-Version-Date: 2026-10-28`, no bearer
credential, and no redirect following. Five bounded searches returned 500
results / 479 distinct products; pagination was incomplete. Products include
courses and services and must not be counted as 479 reward campaigns.

New research leads include:

| Public lead | Advertised offer | Missing evidence |
| --- | --- | --- |
| Finsta App | $2/1,000 views; AI-generated content explicitly accepted | Full terms, funded budget, residency/new-account admission, personal profile link and submission access |
| BarnsideLIVE | $10/1,000 Instagram views; supplied broadcast footage | Actual files/license, full brief, automation and account eligibility |
| Zostel | $1/1,000 Instagram views; supplied travel footage | Actual files, measurement window, budget and admission; Indian audience targeting is distinct from creator residence |

Zero-priced variants were verified for these leads, but a free community join
does not establish campaign funding, eligibility, rights or automated-posting
permission. No membership, checkout, paid feature or purchase was initiated.
The scheduled cloud scan now retains bounded public product leads privately,
in a separate `marketplace_leads` field, without treating them as fixed bounties
or approved CPM campaigns. Three first-page searches run on the six-hour
discovery cadence; per-query errors and incomplete pagination are explicit.

A public Whop product supplied this direct campaign source:
https://contentrewards.com/discover/5d2dc18b-a699-460f-8390-7b0074c5d998

That host is currently proxy-blocked. It is included in the saved additive
network draft so its official brief and materials can be investigated directly
after the owner publishes the existing environment update.

## Vyro and other providers

[Vyro's agent index](https://vyro.com/llms.txt) now advertises public Markdown,
sitemap and JSON-LD surfaces and expressly says there is no public API,
OpenAPI, webhook or MCP server. Bounded reads of those declared surfaces found
new campaign advertising, but Markdown brief pages return loading placeholders.
Full terms/materials remain behind creator access. Agent research guidance does
not grant recurring scraping or automated publication permission; provider
terms and creator-account admission still need verification.

Fresh requests to the official JoinBrands, Billo, Insense, Collabstr,
Passionfroot, impact.com, Trend and Cohley homepages failed at the network proxy.
This is not evidence that campaigns do not exist. Exact homepage hosts were
added to the pending draft, preserving existing hosts and package-manager
presets. No guessed help/API subdomains, unrestricted network policy or new
credential destinations were added. A saved draft requires owner publication
before access can be claimed; host access alone grants no scraping permission.
