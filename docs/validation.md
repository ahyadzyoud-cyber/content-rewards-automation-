# Validation record

Validated on 2026-10-28 in the actual cloud environment.

* GitHub `main` resolved to `f8911ed1605c8356cc869177e029276097cd9de4`
  (`Create README.md`). The existing checkout was initialized from that commit;
  project implementation changes are present locally for review.
* Python 3.12.14, uv 0.12.23, FFmpeg 7.1.5 and ffprobe were available natively.
  Frozen dependency installation and repeated initialization passed.
* `bash scripts/install.sh`: lint passed; **155 tests passed**. One upstream
  Starlette TestClient deprecation warning was emitted; no tests failed or were
  skipped. Coverage includes scoring/evidence gates, real media conversion,
  HTTP transports, authenticated API, publishing approvals, concurrent claims,
  atomic candidate reservation, scheduler persistence and isolated CLI workflow.
* `uv build`: source distribution and wheel built successfully.
* `uv run --frozen python scripts/demo.py`: synthetic import, ranking, best
  candidate selection, real portrait rendering, separate-process persistence
  and scheduling passed. Live publication was blocked as expected. The temporary
  fixture was removed and never entered the real ledger.
* `bash scripts/start.sh`: actual loopback HTTP health/authenticated status,
  unauthorized rejection, unverified campaign import/ranking and stop/restart
  persistence passed against a temporary database. Temporary bearer credentials
  were generated in memory and never logged or saved.
* Docker image built successfully from the pinned official Python base using
  frozen runtime dependencies and a non-editable package install. The environment
  required existing proxy DNS mapping and its trusted CA bundle mounted during
  build. TLS and Debian package signature verification remained enabled. The
  helper `scripts/build_container.py` reproduced the successful build.
* The synthetic video demo also passed inside the non-root Docker image with
  networking disabled. This verified FFmpeg 5.1 compatibility in the image.
* Docker Compose configuration validation, API health, fail-closed missing
  authentication, worker execution and restart persistence passed. The isolated
  smoke project's containers and generated volume were removed after validation.
* `git diff --check` passed. Generated dependencies, state, media, caches,
  logs and build outputs are ignored. The original README was expanded under
  the owner's explicit project-initialization instruction.

The saved environment draft contains the native install script, service startup
instructions, required network domains, two API access-token requirements, and
account/version/hosting/admin settings. Draft saving does not publish a snapshot,
apply network changes to the current instance or supply credentials.

Not executed: real account authorization, real campaign API discovery, live
YouTube/Instagram publication/insights, campaign submission or payout, OAuth
refresh, and production deployment. Whop Content Rewards and `vyro.com` official
campaign APIs remain unconfirmed. See `integrations.md` for source evidence and
observed network blocks. No restricted scraping, paid service activation, real
publication or earnings claim occurred.

## Continuation validation

The initial 39-file implementation was committed and pushed to GitHub `main` as
`f80a5a7`. The continuation preserves that project and adds credential lifecycle,
readiness/preflight and scheduled cloud observation capabilities.

* **275 tests passed**, with no failed or skipped tests, after the continuation.
  Lint, source/wheel builds, and the isolated real-FFmpeg CLI demo passed.
* Google refresh tests cover expiry, concurrent refresh, token invalidation,
  PKCE/state consent and sanitized failures. A mocked integrated account-check,
  approved upload and metrics sequence reused one renewed token without storing
  credentials. These are protocol tests, not a live Google authorization claim.
* Real HTTP startup verified authenticated readiness reporting and blocked
  account checks with missing credentials. The report correctly returned zero
  real campaigns and `business_live=false`.
* The updated Docker image rebuilt successfully and passed its offline non-root
  synthetic video demo. Native and container checks remain development evidence.
* The cloud helper executed two successive local observation runs, restoring its
  validated checkpoint between them and reaching sequence two. Without a
  permitted feed it reported `blocked_no_permitted_feed`, with no publication
  and `production_verified=false`. Artifact metadata/history failure cases and
  skipped-job handling were tested with a fake GitHub API.
* The six-hour GitHub cron is implemented behind two repository-variable gates.
  Setup did not enable those variables or dispatch a remote cloud job. Repository
  visibility, free allowance, remote CI outcome and production execution could
  not be checked because GitHub API requests remain Forbidden at the proxy.
* Public Whop/Content Rewards/Vyro requests remain blocked. An accessible official
  Whop SDK describes paid ad campaigns, not an applicable creator rewards API.
  No real campaign or Jordan eligibility recommendation was invented.

The draft adds `api.github.com`, `whop.com` and `www.whop.com`, plus secure Google
refresh-token/client-secret requirements and public client-ID metadata. The
settings still need the product's save/publish action to apply; no secret values
were supplied, and no paid activation or real publication was performed.
