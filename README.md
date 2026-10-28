# Content Rewards Automation

Automated cloud-based system for discovering campaigns on Whop and Vyro, creating short videos, publishing to YouTube Shorts and Instagram Reels, and tracking earnings.

This repository now contains a working development foundation. **It is not a live income-generating business yet.** No real account is connected, no real campaign eligibility or payout is verified, no video has been published, and no paid service is enabled.

## Implemented phases

| Phase | Implemented and tested | External prerequisite |
| --- | --- | --- |
| Environment | Python 3.12, locked dependencies, SQLite, CLI, authenticated API, CI | Publish the cloud environment snapshot for future tasks |
| Discovery and analysis | Normalized JSON imports, permitted HTTPS feeds, explained scores out of 10 | Whop Content Rewards / `vyro.com` official API or permitted export/feed access |
| Selection and editing | New-account/Jordan gates; choose best eligible campaign; approved local footage to portrait H264/AAC MP4 | Actual campaign terms, rights, fresh budget and eligibility evidence |
| Publishing | YouTube resumable upload; Instagram container/status/publish; exact media approval; duplicate-write barriers | Owner OAuth, platform permissions, verified target IDs, first-publication review; Instagram immutable hosting |
| Tracking | Provider view snapshots, submission/approval/payment evidence ledger | Provider campaign submission/earnings API remains unverified; ledger entries are operator-recorded |
| Recurrence | Durable schedules, worker, Docker services with restart policies | An authorized always-on cloud host and persistent storage; none provisioned here |

See [validation results](docs/validation.md), [integration evidence and limitations](docs/integrations.md), [operations](docs/operations.md), and [architecture](docs/architecture.md).

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

Selection separately requires explicit Jordan (`JO`) eligibility, new-account permission, zero minimum followers, an allowed target platform, positive rate/budget, approved materials, verified requirements/rights, and evidence no older than seven days. A verification flag is an operator attestation supported by actual campaign terms; this software cannot establish account eligibility from a flag alone. Provider feeds cannot self-authorize these flags. Unknown payout access is not assumed available.

## Operating limits

Whop Content Rewards and Vyro campaign APIs have **not** been confirmed. No restricted scraping or undocumented endpoints are used. An official Whop advertising campaign API is not treated as a creator rewards API. Vyro means [vyro.com](https://vyro.com/).

The transport adapters are mock-tested. Google upload methods were checked against Google's official discovery definition. Instagram's live contract, chosen version and permissions still require verification. No live publishing or account integration test has passed yet. Access-token refresh is not implemented; expiring credentials must be renewed securely before unattended publishing can be considered operational.

Publication requires explicit approval of each rendered job, bound to its bytes, metadata, account and campaign evidence. After the first approved live publication, broader recurring publication consent can be designed around verified platform/campaign rules; it is intentionally not silently granted here. Campaign submissions, approval and payout are never inferred from views.

No cloud subscription, paid generation, paid API, hosting purchase, payout action or publication occurs during installation. Docker files prepare deployment; they do not create a free hosting entitlement or deploy anything. Development environment publication preserves files, not an always-on business worker.
