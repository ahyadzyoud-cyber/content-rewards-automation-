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
