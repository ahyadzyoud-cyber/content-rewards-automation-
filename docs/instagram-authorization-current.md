# Current Instagram contract checks

Checked against Meta's public official documentation on **2026-10-28** after
publication of the existing cloud environment. Documentation access now works;
no Instagram account token was available, no token endpoint was called, and no
media container or publication was created. These are contract checks, not live
account authorization or production verification.

## Owner authorization

The existing adapter uses **Instagram API with Instagram Login**, hosted at
`graph.instagram.com`. It requires a professional business or creator account,
an appropriate Meta app, and the actual account owner's authorization. Do not
silently substitute Facebook Login tokens or personal-account credentials.

Meta's current [get-started guide](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/get-started.md)
provides this owner-operated path if Business Login has not been implemented:

1. In the Meta app dashboard, open **Instagram > API setup with Instagram business
   login**.
2. Choose **Generate token** beside the target Instagram account and complete the
   official Instagram login/consent flow.
3. Enter the resulting token only in secure environment credential settings as
   `INSTAGRAM_ACCESS_TOKEN`; do not send it in chat or commit it.
4. Configure the verified professional account identifier as
   `INSTAGRAM_ACCOUNT_ID`, and a supported app API version as
   `INSTAGRAM_API_VERSION`. The current official examples and media-insights
   reference use `v26.0`; this is evidence of the documented version, not a
   claim that this particular app's permissions and access are ready.
5. Complete any account/app review, access-level, or Page Publishing Authorization
   required for the actual account, then run `rewards verify-accounts` before
   enabling live publication. Keep `REWARDS_LIVE_PUBLISHING=false` until the real
   first video is reviewed and approved.

The publishing and insights requirements list these permissions for this login
mode: `instagram_business_basic`, `instagram_business_content_publish`, and
`instagram_business_manage_insights`. Request only the functionality actually
used. Meta app access levels and roles still need verification for the real
owner; token presence alone does not prove those grants.

## Identity: professional ID versus app-scoped ID

The official get-started guide uses `GET /<VERSION>/me` with `user_id,username`
and permits requesting `account_type` too. It explicitly distinguishes:

| Field | Documented meaning |
| --- | --- |
| `id` | App-scoped identifier |
| `user_id` | Professional Instagram account identifier used as `<IG_ID>` |
| `account_type` | `Business` or `Media_Creator` |

The guide's sample response contains one account under `data`; account identity
must be obtained from the authorized token and matched to the configured
professional account. Do not equate an arbitrary returned app-scoped `id` with
the publishing target. The adapter now requests `/me`, accepts a direct account
object or Meta's documented single-account `data` wrapper, matches `user_id` to
the configured target, and normalizes the documented professional account-type
casing. Missing identities, multiple accounts, app-scoped-only matches and
personal/unknown types fail closed. These cases have targeted mocked tests;
real account authorization still requires the owner's consent.

## Token lifecycle and remaining renewal limitation

The official [Business Login guide](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login)
states that login-flow tokens are initially valid for one hour, whereas tokens
generated through the app dashboard are long-lived and valid for 60 days.
Short-lived to long-lived exchange is a server-side operation.

The dedicated [Refresh Access Token reference](https://developers.facebook.com/documentation/instagram-platform/reference/refresh_access_token)
explicitly documents **GET** `https://graph.instagram.com/refresh_access_token`
with both `grant_type=ig_refresh_token` and `access_token` as **required query
parameters**. It does not document POST or an Authorization-header replacement
for that endpoint. No alternative transport was assumed or tested with fake
credentials.

The input token must already be a long-lived token, be at least 24 hours old,
and remain unexpired. Successful refresh extends validity for 60 days from the
refresh. An expired token cannot be refreshed; the owner must authorize again.
The refresh endpoint requires `instagram_business_basic`.

The existing project intentionally excludes credentials from URLs. Consequently,
the current documented refresh protocol has **not** been added as a speculative
header/form variant. Credential renewal remains a specific operational gap for
continuous unattended Instagram publishing; securely renewing an authorized
dashboard token can support a bounded test period, but is not proof of durable
automatic renewal. A verified credential transport and secure persistence design
must be completed before continuous operation is claimed.

## Publishing and media hosting

The current [Content Publishing guide](https://developers.facebook.com/documentation/instagram-platform/content-publishing)
confirms the container -> processing status -> `media_publish` sequence used by
the adapter, and shows Authorization bearer headers for publication requests.
For the project's Instagram Login route, the approved video must remain
publicly fetchable at publication time. The existing content-addressed immutable
hosting and exact-byte checks remain applicable.

The same guide and dedicated [resumable upload reference](https://developers.facebook.com/documentation/instagram-platform/content-publishing/resumable-uploads.md)
limit local-file resumable uploads to apps using **Facebook Login for Business**.
They use `graph.facebook.com` and `rupload.facebook.com`, with different login
and token requirements. That is not a supported no-host fallback for the
existing Instagram Login adapter. No hosting plan, alternate login integration,
paid service, or public video upload was activated.

Before live scheduling, query the real account's
`/<IG_ID>/content_publishing_limit` instead of assuming available publishing
capacity. Returned media/container IDs do not prove final public processing,
campaign acceptance, or reward eligibility.

The adapter now reads `quota_usage,config` from that endpoint using the existing
Bearer-header transport. The official [capacity reference](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit.md)
explicitly supports Instagram Login on `graph.instagram.com`. The workflow
requires a valid account-reported remaining capacity before creating a container
and checks again after processing, before revalidating approval and publishing.
Unknown, malformed or exhausted capacity blocks publication. The returned quota
is used because Meta's guide and reference give different example limits; no
universal post limit is hard-coded. Mocked tests verify those gates; actual
account capacity remains unverified until owner authorization.

## Views and earnings

The current [Instagram Media Insights reference](https://developers.facebook.com/documentation/instagram-platform/reference/instagram-media/insights.md)
supports `views,likes,comments,saved,shares,reach` for the applicable media types.
Without a breakdown request, metric counts are documented in `values[].value`;
`total_value` describes requested breakdown results. The existing adapter does
not request a breakdown.

Meta says unavailable insight data may be an empty dataset rather than zero and
metrics may be delayed up to 48 hours. Views describe platform interactions,
not campaign-qualified views or earnings. Account permissions, actual media
insights, campaign submission, approval and payout still require live evidence.

Public source checks returned HTTP 200 on the canonical documentation paths.
Some old `/docs/...` paths redirect to `/documentation/...`; a few guessed legacy
paths return a generic HTML page despite HTTP 200 and were excluded as evidence.
The official [documentation index](https://developers.facebook.com/documentation/instagram-platform/llms.txt)
was used to resolve the applicable reference pages.
