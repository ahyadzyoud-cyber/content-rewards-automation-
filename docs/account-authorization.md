# Account authorization and credential renewal

Only the account owner can complete consent, identity/channel verification and
payout setup. No password, session cookie, API secret, authorization code or
callback URL should be sent in chat. Enter secret values in secure environment
configuration; do not commit them or place them in workflow artifacts.

## YouTube

The in-memory `YouTubeTokenProvider` implements Google's official OAuth token
endpoint, `POST https://oauth2.googleapis.com/token`, using the
`grant_type=refresh_token` form. It caches access tokens until shortly before
expiry and permits one refresh in flight. A failed refresh does not fall back
to an expired or unknown token. No token value is written to SQLite, files,
URLs, logs or error messages. Publishing writes are not retried by this helper.

Account-owner participation:

1. Select an owner-controlled Google Cloud project and enable YouTube Data API
   v3. Confirm the project's free quota, consent configuration and any public
   upload audit restriction. Do not enable billing or purchase quota.
2. Configure an appropriate OAuth client and legitimate owner-operated consent
   flow. This project requests only
   `https://www.googleapis.com/auth/youtube.upload` and
   `https://www.googleapis.com/auth/youtube.readonly`. A service account is not
   treated as ownership of a normal YouTube channel.
3. Authorize the actual channel owner and grant offline access. Place
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` and the
   verified `YOUTUBE_CHANNEL_ID` in secure settings. The client ID and channel ID
   are identifiers; the client secret and refresh token are credentials.
   An existing `YOUTUBE_ACCESS_TOKEN` can be used for short-lived testing, but
   its presence alone does not provide renewal.
4. Run the read-only account connection check before enabling live publishing.
   Confirm that the returned channel is the intended target. Complete any
   channel verification, API app review and audience-default configuration
   required by Google before reviewing the first public upload.

`GoogleAuthorizationSession` is a library helper for a registered installed-app
loopback flow. It generates cryptographic state and PKCE S256, requests offline
consent, accepts only a matching callback, exchanges the code once, and requires
the granted upload/readonly scopes and an offline refresh token. State and the
PKCE verifier remain in memory in the same process. The helper does not start a
callback server or present an account-connection UI by itself. A trusted
owner-operated flow must capture the callback locally; do not paste its code or
URL into chat or save it in source files. The returned `OAuthTokens` object
redacts its sensitive fields from `repr` and must be delivered only to secure
credential configuration.

Proxy-backed secrets need their supported route verified. The refresh operation
sends the client secret and refresh token in an HTTPS **form body** to
`oauth2.googleapis.com`; a placeholder that can only be substituted into API
headers does not establish a working refresh credential. Reuse available
bindings, test the token exchange, and request an appropriate secure runtime
binding if body substitution is unsupported. Never extract proxy-held raw
secrets. The resulting access token is sent in the Authorization header only
to `www.googleapis.com` by the YouTube adapter.

Google consent mode, refresh-token expiry/revocation, account policy and project
audit status can limit unattended operation. Verify current console settings
and a real refresh; mocked protocol tests do not establish any of those facts.
If Google rotates a refresh token, the provider retains the rotated value in
memory for that process only. It deliberately does not persist it automatically;
a verified secure secret-manager integration would be needed for durable
rotation across fresh worker processes.

References (the live documentation pages were previously blocked by the cloud
proxy; account verification remains outstanding):

* [Installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
* [Refreshing an access token](https://developers.google.com/identity/protocols/oauth2/web-server#offline)
* [YouTube OAuth scopes](https://developers.google.com/youtube/v3/guides/authentication)

## Instagram

Authorize a professional creator/business account using the chosen Instagram
Login API and the currently supported Meta API version. Configure
`INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID` and
`INSTAGRAM_API_VERSION` securely. Complete Meta's app review/access-level
requirements for the actual account and current publishing/insights permissions.
Confirm the returned professional account identity using the read-only check.
No personal account or unsupported API version is assumed eligible.

`StaticTokenProvider` can reject an access token with a known expired timestamp.
It does not claim to renew it. Instagram long-lived token refresh commonly uses
an endpoint whose documented examples put the token in the query string. This
project does not add a speculative alternative or place tokens in URLs: a
current supported credential transport must be verified against Meta's official
documentation before implementing unattended renewal. Until then, securely
renew the authorized token before expiry, and do not call continuous unattended
Instagram publishing verified.

Instagram also needs the owner's approved immutable HTTPS media host, exact
SHA256-named video bytes, campaign rights and first-publication review. No host,
subscription, paid API or account conversion with a cost is activated here.

Reference: [Instagram Login documentation](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login).

## Campaign accounts and payouts

Whop Content Rewards and `vyro.com` campaign access remain separate from social
account authorization. Obtain a provider-approved API/feed/export and verify
Jordan eligibility, new-account acceptance, editing/publication rights,
submission rules and supported payouts from the actual campaign terms. Complete
identity and payout verification only inside the official provider account.
Neither OAuth nor a view count establishes campaign earnings or payout access.
