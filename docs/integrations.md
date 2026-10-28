# External integration status

Last checked: **2026-10-28 UTC**. Transport tests use HTTPX mock responses;
they prove request construction and failure handling, not account authorization,
campaign eligibility, payout access, or a successful real publication.

## What was verified

* The official Google Python API client's
  [YouTube discovery definition](https://github.com/googleapis/google-api-python-client/blob/main/googleapiclient/discovery_cache/documents/youtube.v3.json)
  was reachable. It defines `videos.insert`, resumable video uploads,
  `videos.list` statistics, and the YouTube OAuth scopes. No YouTube account was
  connected and no upload was made.
* The public npm registry metadata for
  [`@whop/sdk` version 2.6.0](https://registry.npmjs.org/@whop/sdk/2.6.0)
  points to [Whop's SDK repository](https://github.com/whopio/whopsdk-typescript).
  Its archive was inspected after verifying the registry-provided SHA-512
  integrity. Among 93 top-level API resource groups, `adCampaigns` exists;
  no Content Rewards discovery/submission resource was found. Ad campaigns are
  paid advertising resources and **are not a substitute for creator reward
  campaigns**. This observation does not prove that a separate or private
  Content Rewards API does not exist.
* Requests to `docs.whop.com`, `developers.google.com`,
  `developers.facebook.com`, and `vyro.com` were blocked by the environment
  proxy with CONNECT HTTP 403. `https://vyro.com/robots.txt` and
  `https://vyro.com/sitemap.xml` were also blocked. No restricted pages were
  scraped and no provider API access was assumed. Saved network configuration
  changes require runtime application before those reads can be retried.

## Whop and Content Rewards

Reference: [Whop API documentation](https://docs.whop.com/api-reference/introduction).
Whop having an API does not establish that this account can discover all
Content Rewards campaigns, submit clips, or read reward balances through that
API. None of those operations has been authenticated or verified here.

The implemented discovery path accepts an explicitly configured HTTPS JSON
feed or a local JSON import. Feeds are treated as untrusted observations: they
cannot mark their own country eligibility, requirements, or material rights as
verified. Before selection, the operator must verify the actual campaign terms,
Jordan eligibility, payout conditions, new-account permission, allowed
platforms, remaining budget, approved materials, and evidence freshness.

Campaign submissions, decisions, and confirmed earnings can be recorded in the
local ledger with references to provider evidence. They are not inferred from
views and are not automatically marked submitted, approved, or paid.

To enable an official connector later, obtain the applicable documented API,
account permissions, and provider-approved automation workflow. Implement and
test the connector against that contract rather than scraping private endpoints.

## Vyro

The project owner identified the intended platform as
**[vyro.com](https://vyro.com/)**, for creator clipping and content rewards. It
must not be confused with similarly named AI media services on other domains.

No public official campaign, submission, balance, or payout API could be
verified in this environment because the public website and discovery documents
were blocked. Therefore no invented Vyro endpoints or authenticated scraping
are included. The same evidence-based JSON workflow is available until the
platform provides or confirms an approved API/feed. No paid service or
subscription has been activated.

## YouTube Shorts

References:

* [Resumable uploads](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol)
* [`videos.insert`](https://developers.google.com/youtube/v3/docs/videos/insert)
* [`videos.list`](https://developers.google.com/youtube/v3/docs/videos/list)
* [OAuth authorization](https://developers.google.com/youtube/v3/guides/authentication)
* [YouTube API policies](https://developers.google.com/youtube/terms/developer-policies)

`YouTubePublisher` uses YouTube Data API v3 with bearer authorization. It
initiates a resumable upload, validates the Google upload URL, streams the local
MP4, and records the returned video ID. The constructor defaults to **private**
uploads. The orchestrator can select public uploads only after its publication
gates have passed. There is no separate Shorts upload endpoint; eligible
vertical video is uploaded through `videos.insert`, and YouTube determines its
Shorts classification.

`verify_account()` reads the authorized user's YouTube channel through
`channels.list(mine=true)`. Reading a channel does not prove that an upload will
pass policy review, that the OAuth project is audited, that sufficient quota
remains, or that public upload privileges are enabled. Projects requiring a
YouTube API compliance audit may be restricted to private uploads. New-account
verification and any project audit must be completed through Google/YouTube.

Use an OAuth client and consent flow for the actual channel owner. Request
`youtube.upload` for uploads and the appropriate readonly scope for channel and
video statistics; supply authorized access tokens through secret configuration.
Google offline token refresh is now implemented by `YouTubeTokenProvider` and
wired through the workflow's account checks, upload and tracking. Live OAuth
authorization, refresh and secure form-body delivery remain unverified. Initial
account-owner consent is never faked. Expired or missing permissions fail safely. Confirm audience
classification, titles, campaign disclosures, copyright permissions, and channel
defaults before the first approved upload.

Statistics are read from `videos.list(part=statistics)` and stored as observed
view/like/comment counts. Missing statistics are errors, not fabricated zeroes.
View counts do not establish campaign approval or earnings.

## Instagram Reels

References (live documentation access remains unverified):

* [Instagram API with Instagram Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login)
* [Content publishing](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing)
* [Insights](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/insights)

`InstagramPublisher` targets `graph.instagram.com` using Instagram Login for an
authorized **professional (business or creator) account**. A personal account
is not treated as publishing-ready. The API version is required explicitly;
there is no silent `latest` version. Confirm the supported version and fields
against Meta's documentation and the configured app before enabling live mode.

The adapter separates the required stages:

1. Create a `REELS` media container with an approved video at a publicly
   accessible HTTPS URL and its caption.
2. Read the container's `status_code` until it is `FINISHED`.
3. Call `media_publish` with the container ID after publication gates pass.
4. Read the published media's insights for views and available engagement.

An Instagram-reachable URL is required; a local MP4 path or localhost address
cannot be used. The project does not purchase or provision hosting. Configure
an existing approved hosting destination, ensure material rights cover hosting,
and allow Meta to fetch the approved video. No credentials are embedded in
video URLs or API URLs.

Expected Instagram Login permissions include `instagram_business_basic`,
`instagram_business_content_publish`, and the current insights permission
required by the chosen version (`instagram_business_manage_insights` where
applicable). App review, access levels, account roles, token expiry, permission
names, and insights availability require live verification. The Facebook Login
API has different token/account/permission requirements and is not silently
mixed into this adapter. `verify_account()` checks the configured account ID
and professional account type; it does not claim app-review approval.

## Failure handling and safe activation

Provider response bodies and credentials are never included in adapter errors.
Redirects are not followed. YouTube upload-session hosts are restricted to the
configured Google API host; feed requests are restricted to the explicitly
configured HTTPS hostname, with payload-size and campaign-count limits. DNS and
cloud egress controls must also restrict feed destinations.

Publishing writes are not retried automatically. A network error, HTTP 5xx, or
invalid success response after the final upload/publish call is an
`IndeterminatePublishError`: the post may exist. Reconcile the actual account
before authorizing another attempt to avoid duplicate publications.

Live operation still needs account-owner OAuth authorization, current campaign
eligibility and rights evidence, payout verification, a configured supported
Instagram API version, and the owner's first-publication approval. Tokens must
be entered through secure environment settings, never committed or sent in
chat. Paid services remain disabled unless separately approved by the owner.
