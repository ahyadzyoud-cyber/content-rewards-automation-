# Content Rewards Automation

Automated cloud-based system for discovering campaigns on Whop and Vyro, creating short videos, publishing to YouTube Shorts and Instagram Reels, and tracking earnings.

This repository contains a published development environment and a working development foundation. **It is not a live income-generating business yet.** No real social account is connected, no campaign eligibility or account payout is verified, no video has been published, and no paid plan is enabled.

Public provider access now works. Read [current Whop findings](docs/live-whop-findings.md), [real Vyro listings and restrictions](docs/live-vyro-findings.md), and [current Meta authorization](docs/instagram-authorization-current.md). Vyro's highest observed advertised rate is $2.50 per 1,000 views for four Total Drama Roblox offers; none is verified eligible for a new creator in Jordan. Whop's official fixed-reward clipping bounty API is implemented separately from CPM rewards:

```bash
# Requires owner OAuth and the approved api.whop.com destination; never send a token in chat.
rewards discover-whop --country JO --goal clipping
```

Provider campaigns cannot become selectable until their actual automated workflow has explicit authorization and evidence (`automation_authorized` and `automation_evidence`). Official API access does not establish campaign-specific posting, rights or payout permission. No recurring website scraper is included.

## Implemented phases

| Phase | Implemented and tested | External prerequisite |
| --- | --- | --- |
| Environment | Published Python 3.12 environment, locked dependencies, SQLite, CLI, authenticated API, passing cloud CI | Optional new Whop API destination/creator consent |
| Discovery and analysis | Official Whop fixed-bounty reader, normalized imports, permitted feeds, explained CPM scores | Creator OAuth; CPM/Vyro source permission and verified campaign terms |
| Selection and editing | New-account/Jordan gates; choose best eligible campaign; approved local footage to portrait H264/AAC MP4 | Actual campaign terms, rights, fresh budget and eligibility evidence |
| Publishing | YouTube refresh-token renewal and resumable upload; Instagram container/status/publish; exact media approval; duplicate-write barriers | Owner OAuth, platform permissions, verified target IDs, first-publication review; Instagram immutable hosting and renewal verification |
| Tracking | Provider view snapshots, submission/approval/payment evidence ledger | Provider campaign submission/earnings API remains unverified; ledger entries are operator-recorded |
| Recurrence | Two verified GitHub cloud observer runs with Git checkpoint restore; six-hour schedule | Permitted data; live business still requires authorized publishing and a private production ledger |

See [validation results](docs/validation.md), [campaign access](docs/campaign-access.md), [account authorization](docs/account-authorization.md), [cloud execution](docs/cloud-deployment.md), and [owner actions](docs/next-actions.md).

## Development

Use the existing checkout: every cloud task is already isolated; do not create a worktree for setup.
Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), FFmpeg and ffprobe with libx264/AAC/drawtext support.

```bash
cd /workspace/content-rewards-automation-
bash scripts/install.sh
uv run --frozen python scripts/demo.py
bash scripts/start.sh
```

The install script uses `uv.lock`, initializes ignored `.data/` state, and runs lint and tests. Startup runs the API on loopback port 8000 and a separate scheduler worker. Live publication defaults to disabled. No secrets are required for development, rendering, ranking, tests, or the synthetic demo. The demo uses a temporary database and generated footage; **it never imports fake campaign evidence into the real ledger**.

The application reads process environment variables. `.env.example` documents them; native CLI/startup do not automatically load `.env`. Enter real credentials in secure environment settings, never in source control or chat. Docker Compose reads a local ignored `.env` file.

```bash
uv run --frozen ruff check .
uv run --frozen pytest -q
uv build
uv run --frozen rewards status
uv run --frozen rewards readiness
uv run --frozen rewards verify-accounts
```

The API requires `Authorization: Bearer <REWARDS_ADMIN_TOKEN>` for every business endpoint. Only `/health` is public. Missing authentication configuration disables business endpoints. Set a strong random token securely if using the API. CLI commands operate directly on the local database without an API token. Do not expose the API publicly without HTTPS and access controls.

## Real campaign data

Import an authorized export using `uv run --frozen rewards import-campaigns campaigns.json`. The file must be a JSON array using the schema in [examples/campaigns.json](examples/campaigns.json); the example is deliberately **unverified and unselectable**. Local paths in `materials` identify the exact footage approved by the campaign. URLs alone do not download or authorize materials.

```bash
uv run --frozen rewards rank --platform youtube
uv run --frozen rewards prepare --platform youtube
uv run --frozen rewards prepare --platform instagram
uv run --frozen rewards list job
```

`prepare` selects the highest-ranked eligible campaign without an existing candidate for that platform and renders it for review. No eligible campaigns means a clear blocker, not a fabricated recommendation. Its draft has the campaign title as the video headline; requirements for hooks, disclosures, exact captions, prohibited edits, originality or account content still need review. For custom metadata use the explicit `plan` and `render` commands in the operations guide.

Scores are **heuristic priority scores, not profit predictions**:

* Reward rate: up to 3 points, `3 × rate / (rate + 5)`.
* Verified fresh country eligibility: 2 points.
* Competition: up to 1.5 points, `1.5 / (1 + entries / 100)`; unknown gets zero.
* Remaining budget: up to 2 points, `2 × budget / (budget + 1000)`.
* Verified requirements and rights: up to 1.5 points, decreasing with requirement count.

Selection separately requires explicit Jordan (`JO`) creator-residency eligibility, new-account permission, zero minimum followers, an allowed target platform, positive rate/budget, approved materials, verified requirements/rights, evidence no older than seven days, and no known expired deadline. Audience geography is a separate field. The optional payout evidence, qualifying-view terms and per-video cap support real publication review. A verification flag is an operator attestation supported by actual campaign terms; this software cannot establish account eligibility from a flag alone. Provider feeds cannot self-authorize these flags. Unknown payout access is not assumed available.

## Operating limits

The official Whop clipping/UGC **bounty** read API is now documented and implemented, with fixed rewards distinct from CPM Content Rewards. A CPM Content Rewards discovery/submission API and a Vyro third-party campaign API remain unverified. No restricted scraping or undocumented endpoints are used. Vyro means [vyro.com](https://vyro.com/).

The transport adapters are mock-tested. Google upload methods were checked against Google's official discovery definition. Instagram's live contract, chosen version and permissions still require verification. No live publishing or account integration test has passed yet. Google offline credential renewal is implemented and wired through account verification, upload and tracking; its live token exchange still needs owner authorization and verified secure bindings. Instagram renewal remains unverified.

Publication requires explicit approval of each rendered job, bound to its bytes, metadata, account and campaign evidence. After the first approved live publication, broader recurring publication consent can be designed around verified platform/campaign rules; it is intentionally not silently granted here. Campaign submissions, approval and payout are never inferred from views.

No cloud subscription, paid generation, paid API, hosting purchase, payout action or publication occurs during installation. Docker files prepare deployment; they do not create a free hosting entitlement or deploy anything. Development environment publication preserves files, not an always-on business worker.

The preferred [free public observer](docs/free-cloud-observer.md) runs on standard public GitHub runners every six hours. Two actual runs passed, including checkpoint restoration into sequence 2. It uses a small public Git branch instead of billed artifact storage or privileged variable APIs. With no permitted feed configured, it reports that blocker and keeps publication/production verification false. This verifies cloud execution and state persistence, not a live business. The older artifact-based workflow remains behind its original opt-in gates and is not activated by this setup.
