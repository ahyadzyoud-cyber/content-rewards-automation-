# Owner participation required

Current evidence: the source implementation is pushed to GitHub; local and
container development/dry-run checks pass. No real campaign has been retrieved,
no social account is connected, no real video has been prepared or published,
and production execution/tracking are unverified. The business is not live.

These are the owner-only steps; automated implementation and checks continue
without asking for passwords or secret values in chat.

1. **Apply the cloud access settings.** Review/save the prepared environment
   settings and publish the environment. The available configuration tool saves
   a draft but cannot apply it or publish the snapshot. Current proxy requests to
   campaign sites and GitHub's API still return Forbidden. The draft includes
   `whop.com`, `www.whop.com`, `docs.whop.com`, `vyro.com`, `api.github.com`, Google
   OAuth/YouTube and Meta API/documentation destinations. Once applied, the agent
   can retry provider discovery, GitHub visibility/free-usage checks and cloud
   workflow dispatch. A raw Git push already works and does not establish these
   separate API permissions.
2. **Authorize the target social accounts securely.** For Google, authorize the
   owner-controlled YouTube channel for upload/readonly scopes and offline
   access, then configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   `YOUTUBE_REFRESH_TOKEN` and `YOUTUBE_CHANNEL_ID` in secure settings. An existing
   access token is optional for short-lived testing. For Instagram, authorize a
   professional account with the actual Meta app's publishing/insights access;
   configure `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID` and the verified
   `INSTAGRAM_API_VERSION`. Complete required channel/app/account verification.
   Do not enable billing or purchase API quota. See `account-authorization.md`.
3. **Complete campaign account and payout verification.** In Whop Content Rewards
   and `vyro.com`, verify that a creator residing in Jordan can join the actual
   campaign and receive payouts, and finish required identity/payout setup on
   the official platform. Make provider-approved campaign terms/export/feed and
   approved material access available through its permitted route. No restricted
   scraping or unverified private endpoint will be used. Jordan audience targets
   alone do not prove Jordan creator or payout eligibility. No real best campaign
   can be selected until this evidence exists. See `campaign-access.md`.
4. **Authorize existing free hosting and execution where needed.** Instagram
   requires an approved immutable HTTPS video host and permission to host the
   campaign footage. No service was purchased or provisioned. GitHub scheduling
   stays behind its two opt-in gates until standard-runner/free allowance,
   artifact storage and spending controls are verified. After API access works,
   the agent can inspect and configure this within the authorized free scope;
   paid capacity still requires separate owner permission. See
   `cloud-deployment.md`.
5. **Approve the first real video when it exists.** The agent will prepare the
   highest-ranked verified candidate and produce a preflight packet containing
   the exact video hash, title/caption, campaign terms and remaining blockers.
   Review the real video and target account before the explicit approval command.
   There is currently no real campaign/video to approve; the synthetic demo is
   not presented as one. Keep `REWARDS_LIVE_PUBLISHING=false` until that review.

Read-only connection checks: `uv run --frozen rewards verify-accounts`.
Evidence report: `uv run --frozen rewards readiness`.
Real prepared job review: `uv run --frozen rewards preflight JOB_ID`.
None of these commands approves a publication or initiates a payout.
