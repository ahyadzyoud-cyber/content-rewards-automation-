import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {AUTHORIZATION_ENDPOINT, REQUESTED_SCOPE, TOKEN_ENDPOINT, accessToken as workerAccessToken, base64url, bountyParameters, digest, handleRequest as workerHandleRequest, randomValue, runScheduledSafely as workerRunScheduledSafely, scheduledRun as workerScheduledRun, seal, unseal} from '../src/worker.mjs';
import worker from '../src/worker.mjs';

const schema = readFileSync(new URL('../schema.sql', import.meta.url), 'utf8');
function workersFetchContract(fetcher) {
  if (!fetcher) return undefined;
  return async (url, options = {}) => {
    // Unlike Node/browser Fetch, Workers only implements follow and manual.
    // Source: developers.cloudflare.com/workers/runtime-apis/request/
    if (options.redirect !== undefined && !['follow', 'manual'].includes(options.redirect)) {
      throw new TypeError('Workers supports only follow or manual redirect modes');
    }
    assert.equal(options.redirect, 'manual', 'Credential-bearing requests must never follow redirects');
    return fetcher(url, options);
  };
}
const handleRequest = (request, env, fetcher) => workerHandleRequest(request, env, workersFetchContract(fetcher));
const accessToken = (env, fetcher, ...args) => workerAccessToken(env, workersFetchContract(fetcher), ...args);
const scheduledRun = (env, fetcher, ...args) => workerScheduledRun(env, workersFetchContract(fetcher), ...args);
const runScheduledSafely = (env, fetcher, ...args) => workerRunScheduledSafely(env, workersFetchContract(fetcher), ...args);

function setup() {
  const sqlite = new DatabaseSync(':memory:'); sqlite.exec(schema);
  const adapter = {
    prepare(sql) {
      const statement = sqlite.prepare(sql); let args = [];
      const result = {
        bind(...values) { args = values; return result; },
        async first() { return statement.get(...args) || null; },
        async all() { return {results: statement.all(...args)}; },
        async run() { return {meta: statement.run(...args)}; },
      }; return result;
    },
    async batch(statements) {
      sqlite.exec('BEGIN');
      try { const results = []; for (const statement of statements) results.push(await statement.run()); sqlite.exec('COMMIT'); return results; }
      catch (error) { sqlite.exec('ROLLBACK'); throw error; }
    },
    withSession(value) { assert.equal(value, 'first-primary'); return adapter; },
  };
  const env = {DB: adapter, PUBLIC_ORIGIN: 'https://owner.example.workers.dev', WHOP_CLIENT_ID: 'app_owner', OWNER_PASSWORD: randomValue(), WHOP_BROKER_API_TOKEN: randomValue(), TOKEN_ENCRYPTION_KEY: randomValue(), REWARDS_LIVE_PUBLISHING: 'false'};
  return {env, sqlite};
}
function req(env, path, options = {}) { return new Request(env.PUBLIC_ORIGIN + path, options); }
function post(env, path, fields, cookie) {
  return req(env, path, {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded', Origin: env.PUBLIC_ORIGIN, ...(cookie ? {Cookie: cookie} : {})}, body: new URLSearchParams(fields)});
}
const forbiddenFetch = () => { throw new Error('No external HTTP expected'); };
async function ownerLogin(env) {
  const result = await handleRequest(post(env, '/owner/login', {password: env.OWNER_PASSWORD}), env, forbiddenFetch);
  assert.equal(result.status, 303);
  const cookie = result.headers.get('Set-Cookie').split(';')[0];
  const page = await handleRequest(req(env, '/', {headers: {Cookie: cookie}}), env, forbiddenFetch);
  const content = await page.text();
  return {cookie, csrf: /name="csrf" value="([^"]+)"/.exec(content)[1]};
}
async function authorizeStart(env, owner) {
  const result = await handleRequest(post(env, '/oauth/start', {csrf: owner.csrf}, owner.cookie), env, forbiddenFetch);
  assert.equal(result.headers.get('Referrer-Policy'), 'no-referrer');
  assert.equal(result.status, 303); return new URL(result.headers.get('Location'));
}
function tokenResponse(access = 'access-one', refresh = 'refresh-one') {
  return new Response(JSON.stringify({access_token: access, refresh_token: refresh, token_type: 'Bearer', expires_in: 3600}), {headers: {'Content-Type': 'application/json'}});
}
async function seedTokens(env, expiresAt, refresh = 'refresh-old', access = 'access-old') {
  const encrypted = await seal(env, 'whop-tokens:v1', {accessToken: access, refreshToken: refresh, expiresAt});
  await env.DB.prepare("UPDATE whop_credentials SET encrypted_payload=?,expires_at=?,status='ready' WHERE owner='owner'").bind(encrypted, expiresAt).run();
}
async function credentials(env) { return env.DB.prepare("SELECT * FROM whop_credentials WHERE owner='owner'").first(); }
function apiRequest(env, path) { return req(env, path, {headers: {Authorization: 'Bearer ' + env.WHOP_BROKER_API_TOKEN}}); }
async function seedSnapshots(env, now, broad = true) {
  for (const goal of ['clipping', 'ugc_content']) {
    await env.DB.prepare('INSERT OR REPLACE INTO whop_observations(goal,encrypted_payload,observed_at,authorization_generation) VALUES(?,?,?,0)')
      .bind(goal, await seal(env, 'whop-observations:' + goal + ':v1', {records: [], business_goal_type: broad && goal === 'ugc_content' ? 'all' : goal, discovery_strategy: broad && goal === 'ugc_content' ? 'all_open_goals_including_untagged_v2' : 'targeted_goal_v1', pricing_model: 'fixed_reward_per_approved_submission'}), now).run();
  }
}

// Real SQLite executes exactly the production CAS/RETURNING schema, while HTTP
// stays a deterministic fake: no authorization, publication or paid API call.
test('requested read-only scope matches official OAuth discovery metadata snapshot', () => {
  // Public issuer metadata retrieved 2026-10-29, before requesting consent.
  // Source: https://api.whop.com/.well-known/openid-configuration
  const official = {
    issuer: 'https://api.whop.com',
    authorization_endpoint: 'https://api.whop.com/oauth/authorize',
    token_endpoint: 'https://api.whop.com/oauth/token',
    bounty_scopes: ['bounty:basic:read', 'bounty:capture_clip:complete', 'bounty:capture_clip:create',
      'bounty:capture_clip:discard', 'bounty:create', 'bounty:submission:create',
      'bounty:submission:delete', 'bounty:submission:vote', 'bounty:update'],
  };
  assert.equal(REQUESTED_SCOPE, 'bounty:basic:read');
  assert.ok(official.bounty_scopes.includes(REQUESTED_SCOPE));
  assert.ok(!official.bounty_scopes.includes('bounty'));
  assert.ok(!official.bounty_scopes.includes('bounty:basic'));
  assert.equal(AUTHORIZATION_ENDPOINT, official.authorization_endpoint);
  assert.equal(TOKEN_ENDPOINT, official.token_endpoint);
});

test('AES-GCM authenticates purpose, key and ciphertext, including large private snapshots', async () => {
  const {env} = setup(); const data = {refreshToken: 'private-value', payload: 'a'.repeat(300_000)};
  const encrypted = await seal(env, 'whop-tokens:v1', data);
  assert.ok(!encrypted.includes('private-value'));
  assert.deepEqual(await unseal(env, 'whop-tokens:v1', encrypted), data);
  await assert.rejects(unseal(env, 'different-purpose', encrypted), /could not be read/);
  await assert.rejects(unseal({...env, TOKEN_ENCRYPTION_KEY: randomValue()}, 'whop-tokens:v1', encrypted), /could not be read/);
  await assert.rejects(unseal(env, 'whop-tokens:v1', encrypted.slice(0, -5)), /could not be read/);
});

test('owner actions require strong secrets, configured origin, POST Origin, and API bearer secret', async () => {
  const {env} = setup();
  assert.equal((await handleRequest(req(env, '/'), {...env, REWARDS_LIVE_PUBLISHING: 'true'})).status, 503);
  assert.equal((await handleRequest(req(env, '/'), {...env, OWNER_PASSWORD: 'short'})).status, 503);
  assert.equal((await handleRequest(new Request('http://owner.example.workers.dev/'), env)).status, 400);
  assert.equal((await handleRequest(req(env, '/api/status'), env)).status, 401);
  const foreign = post(env, '/owner/login', {password: env.OWNER_PASSWORD}); foreign.headers.set('Origin', 'https://foreign.invalid');
  assert.equal((await handleRequest(foreign, env)).status, 403);
  assert.equal((await handleRequest(req(env, '/oauth/start'), env)).status, 404);
});

test('public health checks real database and key while owner configuration is incomplete', async () => {
  const {env} = setup();
  const response = await handleRequest(req(env, '/health'), {...env, WHOP_CLIENT_ID: '', OWNER_PASSWORD: ''}, forbiddenFetch);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {status: 'ok', live_publishing: false, requested_scope: 'bounty:basic:read', authorization_window_minutes: 30, owner_configuration_complete: false, production_verified: false});
  assert.equal((await handleRequest(req(env, '/health'), {...env, TOKEN_ENCRYPTION_KEY: ''}, forbiddenFetch)).status, 503);
  assert.equal((await handleRequest(req(env, '/health'), {...env, REWARDS_LIVE_PUBLISHING: 'true'}, forbiddenFetch)).status, 503);
});

test('owner form documents preserve same-origin navigation Origin without exposing cross-origin referrers', async () => {
  const {env} = setup();
  const loginPage = await handleRequest(req(env, '/'), env, forbiddenFetch);
  assert.equal(loginPage.headers.get('Referrer-Policy'), 'same-origin');
  assert.equal(loginPage.headers.get('Cache-Control'), 'no-store');
  const owner = await ownerLogin(env);
  const ownerPage = await handleRequest(req(env, '/', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.equal(ownerPage.headers.get('Referrer-Policy'), 'same-origin');
  assert.ok((await ownerPage.text()).includes('action="/oauth/start"'));
  const callback = await handleRequest(req(env, '/oauth/callback?code=synthetic-untrusted'), env, forbiddenFetch);
  assert.equal(callback.status, 303);
  assert.equal(callback.headers.get('Referrer-Policy'), 'no-referrer');
  assert.equal(callback.headers.get('Location'), '/oauth/result/owner-session-required');
});

test('private opportunity page requires owner session and does not accept the machine credential', async () => {
  const {env, sqlite} = setup();
  for (const request of [req(env, '/opportunities'), apiRequest(env, '/opportunities')]) {
    const denied = await handleRequest(request, env, forbiddenFetch);
    assert.equal(denied.status, 303);
    assert.equal(denied.headers.get('Location'), '/');
    assert.equal(await denied.text(), '');
    assert.equal(denied.headers.get('Cache-Control'), 'no-store');
    assert.equal(denied.headers.get('Referrer-Policy'), 'no-referrer');
  }
  const owner = await ownerLogin(env);
  sqlite.prepare('UPDATE oauth_sessions SET expires_at=0').run();
  const expired = await handleRequest(req(env, '/opportunities', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.equal(expired.status, 303);
  assert.equal(expired.headers.get('Location'), '/');
  assert.equal(await expired.text(), '');
  assert.equal(expired.headers.get('Cache-Control'), 'no-store');
  assert.equal(expired.headers.get('Referrer-Policy'), 'no-referrer');
});

test('private opportunity page escapes provider text, lists small rewards, and makes no writes or external requests', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env);
  await seedTokens(env, Date.now() + 3600_000, 'hidden-refresh-token', 'hidden-access-token');
  const records = [
    {id: 'bnty_small', title: 'Small opportunity', description: 'Original brief\nwith a second line.', currency: 'usd', net_reward_amount: 0.01, spots_remaining: 8, status: 'open', allowed_country_codes: []},
    {id: 'bnty_hostile', title: '<script>alert("title")</script>', description: '</div><img src="https://evil.invalid/leak" onerror="alert(1)">\n<script>alert(2)</script>', currency: 'usd', net_reward_amount: 7, spots_remaining: 90, status: 'open', allowed_country_codes: ['JO', 'GB'], metadata: {access_token: 'hidden-provider-metadata'}},
    {id: 'bnty_euro', title: 'Different currency', description: 'A separate currency, no conversion.', currency: 'eur', net_reward_amount: 500, spots_remaining: 1, status: 'open', allowed_country_codes: ['DE']},
    {id: 'bnty_unknown', title: 'Unknown quoted amount', description: 'Do not invent amounts or residency.', currency: 'usd', net_reward_amount: '1000', spots_remaining: null, status: 'open', allowed_country_codes: null},
  ];
  const ciphertext = await seal(env, 'whop-observations:clipping:v1', {records, pagination_complete: false, arbitrary_private_field: 'hidden-snapshot-field'});
  sqlite.prepare('INSERT INTO whop_observations(goal,encrypted_payload,observed_at,authorization_generation) VALUES(?,?,?,0)').run('clipping', ciphertext, Date.now());
  const before = sqlite.prepare('SELECT total_changes() AS n').get().n;
  const response = await handleRequest(req(env, '/opportunities', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  assert.equal(response.headers.get('Referrer-Policy'), 'no-referrer');
  assert.ok(response.headers.get('Content-Security-Policy').includes("default-src 'none'"));
  const content = await response.text();
  assert.ok(content.indexOf('Weaknesses to resolve') < content.indexOf('<article>'));
  assert.ok(content.includes('&lt;script&gt;alert(&quot;title&quot;)&lt;/script&gt;'));
  assert.ok(content.includes('&lt;img src=&quot;https://evil.invalid/leak&quot;'));
  assert.ok(!content.includes('<script>'));
  assert.ok(!content.includes('<img'));
  assert.ok(content.includes('Original brief\nwith a second line.'));
  assert.ok(content.includes('white-space:pre-wrap'));
  assert.ok(content.includes('Quoted net fixed reward: 0.01 USD'));
  assert.ok(content.includes('Quoted net fixed reward: Unknown USD'));
  assert.ok(content.includes('Allowed creator residency: Worldwide'));
  assert.ok(content.includes('Provider rules include Jordan; account admission still unverified'));
  assert.ok(content.includes('Provider rules do not include Jordan'));
  assert.ok(content.includes('Residency rules unverified'));
  assert.ok(content.includes('pagination incomplete or unverified'));
  assert.ok(content.indexOf('Different currency') < content.indexOf('&lt;script&gt;alert(&quot;title&quot;)'));
  assert.ok(content.indexOf('&lt;script&gt;alert(&quot;title&quot;)') < content.indexOf('Small opportunity'));
  assert.ok(content.indexOf('Small opportunity') < content.indexOf('Unknown quoted amount'));
  for (const secret of [env.OWNER_PASSWORD, env.WHOP_BROKER_API_TOKEN, env.TOKEN_ENCRYPTION_KEY, owner.cookie.split('=')[1], owner.csrf, ciphertext, 'hidden-refresh-token', 'hidden-access-token', 'hidden-provider-metadata', 'hidden-snapshot-field']) assert.ok(!content.includes(secret));
  assert.equal(sqlite.prepare('SELECT total_changes() AS n').get().n, before);
  const home = await handleRequest(req(env, '/', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.ok((await home.text()).includes('href="/opportunities"'));
});

test('private opportunity page excludes old authorization snapshots and shows an honest empty state', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env);
  await seedTokens(env, Date.now() + 3600_000);
  sqlite.prepare('UPDATE whop_credentials SET authorization_generation=2').run();
  const encrypted = await seal(env, 'whop-observations:clipping:v1', {records: [{title: 'Previous owner opportunity'}]});
  sqlite.prepare('INSERT INTO whop_observations(goal,encrypted_payload,observed_at,authorization_generation) VALUES(?,?,?,1)').run('clipping', encrypted, Date.now());
  let page = await handleRequest(req(env, '/opportunities', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  let content = await page.text();
  assert.equal(page.status, 200);
  assert.ok(content.includes('No saved opportunities are available for the current ready authorization'));
  assert.ok(!content.includes('Previous owner opportunity'));
  sqlite.prepare("UPDATE whop_credentials SET status='reauthorization_required',authorization_generation=1").run();
  page = await handleRequest(req(env, '/opportunities', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  content = await page.text();
  assert.ok(!content.includes('Previous owner opportunity'));
  assert.ok(content.includes('No saved opportunities are available'));
});

test('private opportunity page identifies stale snapshots and rejects unexpected parameters', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env);
  await seedTokens(env, Date.now() + 3600_000);
  const encrypted = await seal(env, 'whop-observations:clipping:v1', {records: [], pagination_complete: true});
  sqlite.prepare('INSERT INTO whop_observations(goal,encrypted_payload,observed_at,authorization_generation) VALUES(?,?,?,0)').run('clipping', encrypted, Date.now() - 7 * 3600_000);
  const page = await handleRequest(req(env, '/opportunities', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  const content = await page.text();
  assert.ok(content.includes('older than the six-hour discovery interval'));
  assert.ok(content.includes('pagination complete'));
  assert.equal((await handleRequest(req(env, '/opportunities?code=private', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch)).status, 400);
  assert.equal((await handleRequest(post(env, '/opportunities', {csrf: owner.csrf}, owner.cookie), env, forbiddenFetch)).status, 404);
});

test('authorization forms allow only the owner and verified Whop redirect origins', async () => {
  const {env} = setup(), owner = await ownerLogin(env);
  const document = await handleRequest(req(env, '/', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  const policy = document.headers.get('Content-Security-Policy');
  const targets = policy.split(';').map(value => value.trim()).find(value => value.startsWith('form-action ')).split(/\s+/).slice(1);
  assert.deepEqual(targets, ["'self'", 'https://api.whop.com', 'https://whop.com']);
  assert.ok(policy.includes("default-src 'none'"));
  assert.ok(policy.includes("base-uri 'none'"));
  assert.ok(policy.includes("frame-ancestors 'none'"));
  const start = await handleRequest(post(env, '/oauth/start', {csrf: owner.csrf}, owner.cookie), env, forbiddenFetch);
  assert.equal(start.status, 303);
  assert.equal(start.headers.get('Referrer-Policy'), 'no-referrer');
  assert.equal(new URL(start.headers.get('Location')).origin, 'https://api.whop.com');
  assert.equal(new URL(start.headers.get('Location')).searchParams.get('scope'), 'bounty:basic:read');
});

test('owner form actions still reject missing, null and foreign Origin before writing state', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env);
  for (const path of ['/owner/login', '/oauth/start', '/owner/logout']) {
    for (const origin of [null, 'null', 'https://foreign.invalid', env.PUBLIC_ORIGIN + '.foreign.invalid', env.PUBLIC_ORIGIN + '/']) {
      const request = post(env, path, {password: env.OWNER_PASSWORD, csrf: owner.csrf}, owner.cookie);
      if (origin === null) request.headers.delete('Origin');
      else request.headers.set('Origin', origin);
      const denied = await handleRequest(request, env, forbiddenFetch);
      assert.equal(denied.status, 403, path + ' must reject ' + origin);
      assert.deepEqual(await denied.json(), {error: 'Same-origin owner action required'});
    }
  }
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 0);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM owner_login_throttle').get().n, 0);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_sessions').get().n, 1);
});

test('PKCE start uses only verified read scope, hashed expiring state, browser cookie and CSRF', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env);
  assert.equal((await handleRequest(post(env, '/oauth/start', {csrf: 'wrong'}, owner.cookie), env)).status, 403);
  const auth = await authorizeStart(env, owner);
  assert.equal(auth.origin + auth.pathname, 'https://api.whop.com/oauth/authorize');
  assert.equal(auth.searchParams.get('scope'), 'bounty:basic:read');
  assert.equal(auth.searchParams.get('code_challenge_method'), 'S256');
  assert.equal(auth.searchParams.get('redirect_uri'), env.PUBLIC_ORIGIN + '/oauth/callback');
  assert.ok(!auth.searchParams.has('client_secret'));
  const stored = sqlite.prepare('SELECT * FROM oauth_states').get();
  assert.notEqual(stored.state_hash, auth.searchParams.get('state'));
  const payload = await unseal(env, 'whop-oauth-state:v1', stored.encrypted_payload);
  assert.equal(await digest(payload.verifier), auth.searchParams.get('code_challenge'));
  assert.equal(stored.expires_at - Date.now() > 500_000, true);
  const headers = (await handleRequest(req(env, '/'), env)).headers;
  assert.equal(headers.get('Referrer-Policy'), 'same-origin');
  assert.equal(headers.get('Cache-Control'), 'no-store');
  assert.ok(headers.get('Content-Security-Policy').includes("form-action 'self' https://api.whop.com"));
});

test('successful callback persists encrypted credentials and strips code from redirect; state cannot replay', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env), auth = await authorizeStart(env, owner);
  let calls = 0;
  const exchange = async (url, options) => {
    calls++; assert.equal(url, 'https://api.whop.com/oauth/token'); assert.equal(options.method, 'POST');
    assert.equal(options.redirect, 'manual'); assert.equal(options.headers['Content-Type'], 'application/json');
    const body = JSON.parse(options.body);
    assert.equal(body.grant_type, 'authorization_code'); assert.equal(body.code, 'private-callback-code');
    assert.equal(await digest(body.code_verifier), auth.searchParams.get('code_challenge'));
    assert.equal(body.redirect_uri, env.PUBLIC_ORIGIN + '/oauth/callback');
    assert.ok(!Object.hasOwn(body, 'client_secret')); return tokenResponse();
  };
  const path = '/oauth/callback?code=private-callback-code&state=' + auth.searchParams.get('state');
  const result = await handleRequest(req(env, path, {headers: {Cookie: owner.cookie}}), env, exchange);
  assert.equal(result.status, 303); assert.equal(result.headers.get('Location'), env.PUBLIC_ORIGIN + '/');
  const row = await credentials(env); assert.equal(row.status, 'ready');
  assert.ok(!row.encrypted_payload.includes('access-one')); assert.ok(!row.encrypted_payload.includes('refresh-one'));
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 0);
  const replay = await handleRequest(req(env, path, {headers: {Cookie: owner.cookie}}), env, exchange);
  assert.equal(replay.status, 303); assert.equal(replay.headers.get('Location'), '/oauth/result/authorization-request-unavailable'); assert.equal(calls, 1);
  const state = await (await handleRequest(apiRequest(env, '/api/status'), env)).json();
  assert.equal(state.authorized, true); assert.equal(state.scope_verified, false); assert.equal(state.live_publishing, false);
  assert.ok(!JSON.stringify(state).includes('access-one'));
});

test('callback denial, wrong browser, expired state and invalid parameters all clean callback URL without HTTP', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env), auth = await authorizeStart(env, owner);
  const state = auth.searchParams.get('state');
  const wrongBrowser = await handleRequest(req(env, '/oauth/callback?code=secret&state=' + state), env, forbiddenFetch);
  assert.equal(wrongBrowser.headers.get('Location'), '/oauth/result/owner-session-required');
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 1);
  const denied = await handleRequest(req(env, '/oauth/callback?error=access_denied&state=' + state, {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.equal(denied.headers.get('Location'), '/oauth/result/provider-denied');
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 0);
  const another = await authorizeStart(env, owner); sqlite.prepare('UPDATE oauth_states SET expires_at=0').run();
  const expired = await handleRequest(req(env, '/oauth/callback?code=secret&state=' + another.searchParams.get('state'), {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.equal(expired.headers.get('Location'), '/oauth/result/authorization-request-unavailable');
  const duplicate = await handleRequest(req(env, '/oauth/callback?state=' + state + '&state=' + state + '&code=secret', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.equal(duplicate.headers.get('Location'), '/oauth/result');
});

test('renewed authorization window survives cleanup and a 26-minute consent return', async context => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env), started = Date.now();
  sqlite.prepare('UPDATE oauth_sessions SET expires_at=?').run(started + 60_000);
  const start = await handleRequest(post(env, '/oauth/start', {csrf: owner.csrf}, owner.cookie), env, forbiddenFetch);
  assert.equal(start.status, 303);
  assert.equal(start.headers.get('Set-Cookie').split(';')[0], owner.cookie);
  assert.ok(start.headers.get('Set-Cookie').includes('Max-Age=1800'));
  assert.ok(start.headers.get('Set-Cookie').includes('Secure; HttpOnly; SameSite=Lax'));
  const state = sqlite.prepare('SELECT * FROM oauth_states').get();
  const session = sqlite.prepare('SELECT expires_at FROM oauth_sessions').get();
  assert.equal(state.expires_at, session.expires_at);
  assert.ok(state.expires_at >= started + 30 * 60_000 && state.expires_at < started + 30 * 60_000 + 1000);
  await runScheduledSafely(env, forbiddenFetch, started + 15 * 60_000);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 1);
  context.mock.method(Date, 'now', () => started + 26 * 60_000);
  let exchanges = 0;
  const url = '/oauth/callback?code=fixture-delayed-code&state=' + new URL(start.headers.get('Location')).searchParams.get('state');
  const result = await handleRequest(req(env, url, {headers: {Cookie: owner.cookie}}), env, () => {
    exchanges++; return tokenResponse('delayed-access', 'delayed-refresh');
  });
  assert.equal(result.headers.get('Location'), env.PUBLIC_ORIGIN + '/');
  assert.equal(exchanges, 1); assert.equal((await credentials(env)).status, 'ready');
  const persisted = await unseal(env, 'whop-tokens:v1', (await credentials(env)).encrypted_payload);
  assert.equal(persisted.refreshToken, 'delayed-refresh');
});

test('legacy ten-minute transaction is purged before a 26-minute return without a token exchange', async context => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env), started = Date.now();
  const auth = await authorizeStart(env, owner);
  sqlite.prepare('UPDATE oauth_states SET expires_at=?').run(started + 10 * 60_000);
  await runScheduledSafely(env, forbiddenFetch, started + 15 * 60_000);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 0);
  context.mock.method(Date, 'now', () => started + 26 * 60_000);
  const result = await handleRequest(req(env, '/oauth/callback?code=fixture-expired-code&state=' + auth.searchParams.get('state'), {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.equal(result.headers.get('Location'), '/oauth/result/authorization-request-unavailable');
  assert.equal((await credentials(env)).status, 'empty');
  assert.equal((await credentials(env)).version, 0);
});

test('authorization start cannot resurrect a session revoked after CSRF validation', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env), batch = env.DB.batch;
  env.DB.batch = async statements => { sqlite.prepare('DELETE FROM oauth_sessions').run(); return batch(statements); };
  const result = await handleRequest(post(env, '/oauth/start', {csrf: owner.csrf}, owner.cookie), env, forbiddenFetch);
  assert.equal(result.status, 401);
  assert.equal(result.headers.get('Set-Cookie'), null);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_sessions').get().n, 0);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 0);
});

test('wrong CSRF cannot extend the authorization session or create pending state', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env);
  const before = sqlite.prepare('SELECT expires_at FROM oauth_sessions').get().expires_at;
  const result = await handleRequest(post(env, '/oauth/start', {csrf: 'wrong'}, owner.cookie), env, forbiddenFetch);
  assert.equal(result.status, 403);
  assert.equal(result.headers.get('Set-Cookie'), null);
  assert.equal(sqlite.prepare('SELECT expires_at FROM oauth_sessions').get().expires_at, before);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 0);
});

test('token-exchange failure gives a safe reason and never retries the consumed code', async () => {
  const {env} = setup(), owner = await ownerLogin(env), auth = await authorizeStart(env, owner);
  let calls = 0;
  const exchange = async () => { calls++; return new Response(JSON.stringify({error: 'fixture-private-upstream', access_token: 'fixture-private-token'}), {status: 403}); };
  const url = '/oauth/callback?code=fixture-private-code&state=' + auth.searchParams.get('state');
  const result = await handleRequest(req(env, url, {headers: {Cookie: owner.cookie}}), env, exchange);
  assert.equal(result.headers.get('Location'), '/oauth/result/token-exchange-failed');
  assert.equal((await credentials(env)).status, 'reauthorization_required');
  const message = await handleRequest(req(env, result.headers.get('Location')), env, forbiddenFetch);
  const text = await message.text();
  assert.ok(text.includes('Whop token exchange was not completed'));
  assert.ok(!text.includes('fixture-private'));
  await handleRequest(req(env, url, {headers: {Cookie: owner.cookie}}), env, exchange);
  assert.equal(calls, 1);
});

test('token endpoint redirects are rejected without forwarding or retrying the authorization code', async () => {
  for (const status of [301, 302, 303, 307, 308]) {
    const {env} = setup(), owner = await ownerLogin(env), auth = await authorizeStart(env, owner);
    let calls = 0;
    const exchange = async (url, options) => {
      calls++; assert.equal(url, TOKEN_ENDPOINT); assert.equal(options.redirect, 'manual');
      assert.equal(JSON.parse(options.body).code, 'fixture-redirect-code');
      return new Response('', {status, headers: {Location: 'https://unrelated.example.invalid/collect'}});
    };
    const url = '/oauth/callback?code=fixture-redirect-code&state=' + auth.searchParams.get('state');
    const response = await handleRequest(req(env, url, {headers: {Cookie: owner.cookie}}), env, exchange);
    assert.equal(response.headers.get('Location'), '/oauth/result/token-exchange-failed');
    const saved = await credentials(env);
    assert.equal(saved.status, 'reauthorization_required');
    assert.equal(saved.encrypted_payload, null);
    const message = await handleRequest(req(env, response.headers.get('Location')), env, forbiddenFetch);
    const text = await message.text();
    assert.ok(!text.includes('unrelated.example.invalid'));
    assert.ok(!text.includes('fixture-redirect-code'));
    await handleRequest(req(env, url, {headers: {Cookie: owner.cookie}}), env, exchange);
    assert.equal(calls, 1);
    assert.equal((await credentials(env)).version, saved.version);
  }
});

test('refresh endpoint redirects fail closed without following or replaying a rotating token', async () => {
  const {env} = setup(); await seedTokens(env, Date.now() - 1);
  let calls = 0;
  const refresh = async (url, options) => {
    calls++; assert.equal(url, TOKEN_ENDPOINT); assert.equal(options.redirect, 'manual');
    assert.equal(JSON.parse(options.body).refresh_token, 'refresh-old');
    return new Response('', {status: 307, headers: {Location: 'https://unrelated.example.invalid/collect'}});
  };
  await assert.rejects(accessToken(env, refresh), /authorization was rejected/);
  assert.equal((await credentials(env)).status, 'reauthorization_required');
  await assert.rejects(accessToken(env, refresh), /authorization required/);
  assert.equal(calls, 1);
});

test('bounty discovery rejects provider redirects without forwarding bearer credentials or changing their store', async () => {
  for (const status of [301, 302, 303, 307, 308]) {
    const {env} = setup(); await seedTokens(env, Date.now() + 3600_000);
    const before = await credentials(env); let calls = 0;
    const listed = async (url, options) => {
      calls++; assert.ok(url.startsWith('https://api.whop.com/api/v1/bounties?'));
      assert.equal(options.redirect, 'manual'); assert.equal(options.headers.Authorization, 'Bearer access-old');
      return new Response('', {status, headers: {Location: 'https://unrelated.example.invalid/collect'}});
    };
    const response = await handleRequest(apiRequest(env, '/api/bounties?business_goal_type=clipping'), env, listed);
    assert.equal(response.status, 502);
    assert.ok(!(await response.text()).includes('unrelated.example.invalid'));
    assert.equal(calls, 1);
    assert.deepEqual(await credentials(env), before);
  }
});

test('safe callback result pages are fixed messages and retain no-referrer/no-store', async () => {
  const {env} = setup();
  for (const reason of ['owner-session-required', 'authorization-request-unavailable', 'provider-denied', 'token-exchange-failed']) {
    const result = await handleRequest(req(env, '/oauth/result/' + reason), env, forbiddenFetch);
    assert.equal(result.status, 200);
    assert.equal(result.headers.get('Referrer-Policy'), 'no-referrer');
    assert.equal(result.headers.get('Cache-Control'), 'no-store');
  }
  assert.equal((await handleRequest(req(env, '/oauth/result/untrusted'), env, forbiddenFetch)).status, 404);
  assert.equal((await handleRequest(req(env, '/oauth/result/provider-denied?error_description=private'), env, forbiddenFetch)).status, 400);
});

test('rotation is durably claimed before HTTP, concurrent callers cannot consume refresh twice, restart reads new token', async () => {
  const {env} = setup(); await seedTokens(env, Date.now() - 1);
  let release; const held = new Promise(resolve => { release = resolve; }); let calls = 0;
  let entered; const started = new Promise(resolve => { entered = resolve; });
  const refresh = async (_url, options) => {
    calls++; assert.equal((await credentials(env)).status, 'rotating');
    assert.equal(JSON.parse(options.body).refresh_token, 'refresh-old');
    entered(); await held; return tokenResponse('access-new', 'refresh-new');
  };
  const one = accessToken(env, refresh); await started;
  await assert.rejects(accessToken(env, refresh), /renewal is in progress or uncertain/);
  release(); assert.equal(await one, 'access-new'); assert.equal(calls, 1);
  const row = await credentials(env); assert.equal(row.status, 'ready'); assert.equal(row.renewal_count, 1);
  const persisted = await unseal(env, 'whop-tokens:v1', row.encrypted_payload); assert.equal(persisted.refreshToken, 'refresh-new');
  assert.equal(await accessToken({...env}, forbiddenFetch), 'access-new');
});

test('ambiguous refresh failure durably blocks old token replay and sanitizes provider errors', async () => {
  const {env} = setup(); await seedTokens(env, Date.now() - 1); let calls = 0;
  const fail = async () => { calls++; throw new Error('leaked refresh-old private response'); };
  await assert.rejects(accessToken(env, fail), error => !error.message.includes('refresh-old') && /could not be confirmed/.test(error.message));
  assert.equal((await credentials(env)).status, 'reauthorization_required');
  await assert.rejects(accessToken(env, fail), /authorization required/); assert.equal(calls, 1);
});

test('unchanged refresh token and unexpected returned permission are rejected without persistence', async () => {
  for (const response of [() => tokenResponse('new', 'refresh-old'), () => new Response(JSON.stringify({access_token: 'new', refresh_token: 'rotated', expires_in: 3600, token_type: 'Bearer', scope: 'bounty:create'}))]) {
    const {env} = setup(); await seedTokens(env, Date.now() - 1);
    await assert.rejects(accessToken(env, response)); assert.equal((await credentials(env)).status, 'reauthorization_required');
  }
});

test('lost persistence after consuming refresh does not permit replay or resurrect stale authorization', async () => {
  const {env} = setup(); await seedTokens(env, Date.now() - 1); const original = env.DB.prepare;
  env.DB.prepare = function(sql) { if (sql.includes("SET encrypted_payload=?,expires_at=?,status='ready'")) throw new Error('storage failed'); return original(sql); };
  let calls = 0; await assert.rejects(accessToken(env, async () => { calls++; return tokenResponse('new', 'new-refresh'); }));
  await assert.rejects(accessToken(env, async () => { calls++; return tokenResponse(); })); assert.equal(calls, 1);
  assert.notEqual((await credentials(env)).status, 'ready');
});

test('fresh authorization cannot overwrite an in-flight rotation claim', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env), auth = await authorizeStart(env, owner);
  sqlite.prepare("UPDATE whop_credentials SET status='rotating' WHERE owner='owner'").run();
  const result = await handleRequest(req(env, '/oauth/callback?code=secret&state=' + auth.searchParams.get('state'), {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.equal(result.headers.get('Location'), '/oauth/result'); assert.equal((await credentials(env)).status, 'rotating');
});

test('private bounty API forwards only bounded official GET filters and never auto-expands permission', async () => {
  const {env} = setup(); await seedTokens(env, Date.now() + 3600_000);
  let calls = 0;
  const external = async (url, options) => {
    calls++; const target = new URL(url); assert.equal(target.origin + target.pathname, 'https://api.whop.com/api/v1/bounties');
    assert.equal(target.searchParams.get('country'), 'JO'); assert.equal(options.method, 'GET'); assert.equal(options.headers.Authorization, 'Bearer access-old');
    return new Response(JSON.stringify({secret: 'do-not-reflect'}), {status: 403});
  };
  const result = await handleRequest(apiRequest(env, '/api/bounties?business_goal_type=clipping'), env, external);
  assert.equal(result.status, 403); const text = await result.text(); assert.ok(text.includes('bounty:basic:read')); assert.ok(!text.includes('do-not-reflect')); assert.equal(calls, 1);
  for (const query of ['country=US&business_goal_type=clipping', 'business_goal_type=clipping&first=101', 'business_goal_type=ugc_content&join=true', 'business_goal_type=clipping&first=1&first=2', 'business_goal_type=other']) {
    assert.equal((await handleRequest(apiRequest(env, '/api/bounties?' + query), env, forbiddenFetch)).status, 400);
  }
  assert.equal((await handleRequest(req(env, '/api/bounties?business_goal_type=clipping', {method: 'POST'}), env, forbiddenFetch)).status, 404);
});

test('explicit all-goal discovery omits the optional provider filter and retains untagged offers', async () => {
  const {env} = setup(); await seedTokens(env, Date.now() + 3600_000);
  const records = [{id: 'bnty_untagged', business_goal_type: null}, {id: 'bnty_other', business_goal_type: 'other'}];
  let calls = 0;
  const external = async (url, options) => {
    calls++; const target = new URL(url);
    assert.equal(target.origin + target.pathname, 'https://api.whop.com/api/v1/bounties');
    assert.equal(target.searchParams.has('business_goal_type'), false);
    assert.equal(target.searchParams.get('country'), 'JO');
    assert.equal(target.searchParams.get('status'), 'open');
    assert.equal(target.searchParams.get('first'), '100');
    assert.equal(options.method, 'GET');
    assert.equal(options.headers.Authorization, 'Bearer access-old');
    return new Response(JSON.stringify({data: records, page_info: {has_next_page: false}}));
  };
  const response = await handleRequest(apiRequest(env, '/api/bounties?business_goal_type=all'), env, external);
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).data, records);
  assert.equal(calls, 1);
  assert.equal(REQUESTED_SCOPE, 'bounty:basic:read');
});

test('scheduled renewal refreshes ahead of expiry and stores sanitized durable diagnostics', async () => {
  const {env} = setup(), now = Date.parse('2026-10-29T01:30:00Z'); await seedTokens(env, now + 20 * 60_000);
  await seedSnapshots(env, now);
  let calls = 0;
  const result = await runScheduledSafely(env, async () => { calls++; return tokenResponse('new-access', 'new-refresh'); }, now);
  assert.equal(result.status, 'renewal_checked'); assert.equal(calls, 1);
  const state = await (await handleRequest(apiRequest(env, '/api/status'), env)).json();
  assert.equal(state.durable_renewal_verified, true); assert.equal(state.last_scheduled_status, 'renewal_checked');
});

test('production fetch entry ignores Cloudflare ExecutionContext and uses actual fetch', async () => {
  const {env} = setup(); await seedTokens(env, Date.now() + 3600_000);
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = workersFetchContract(async (url, options) => {
    calls++; assert.ok(url.startsWith('https://api.whop.com/api/v1/bounties?'));
    assert.equal(options.headers.Authorization, 'Bearer access-old');
    return new Response(JSON.stringify({data: [], page_info: {has_next_page: false}}));
  });
  try {
    const response = await worker.fetch(apiRequest(env, '/api/bounties?business_goal_type=clipping'), env, {waitUntil() {}});
    assert.equal(response.status, 200); assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test('new consent resets old grant proof and cached private observations', async () => {
  const {env, sqlite} = setup(), owner = await ownerLogin(env);
  await seedTokens(env, Date.now() + 3600_000); await seedSnapshots(env, Date.now());
  sqlite.prepare('UPDATE whop_credentials SET renewal_count=9,last_renewed_at=?').run(Date.now());
  const auth = await authorizeStart(env, owner);
  const result = await handleRequest(req(env, '/oauth/callback?code=new-owner-code&state=' + auth.searchParams.get('state'), {headers: {Cookie: owner.cookie}}), env, () => tokenResponse());
  assert.equal(result.headers.get('Location'), env.PUBLIC_ORIGIN + '/');
  const current = await (await handleRequest(apiRequest(env, '/api/status'), env)).json();
  assert.equal(current.authorized, true); assert.equal(current.scope_verified, false);
  assert.equal(current.durable_renewal_verified, false); assert.equal(current.renewal_count, 0);
  assert.equal(current.last_renewed_at, null);
  assert.equal((await (await handleRequest(apiRequest(env, '/api/discovery/latest'), env)).json()).reports.length, 0);
});

test('callback configuration failure still removes codes from browser URL', async () => {
  const {env} = setup();
  const response = await handleRequest(req(env, '/oauth/callback?code=private-code&state=private-state'), {...env, OWNER_PASSWORD: ''});
  assert.equal(response.status, 303); assert.equal(response.headers.get('Location'), '/oauth/result');
  assert.equal(await response.text(), '');
});

test('status marks expired ready credentials as requiring renewal', async () => {
  const {env} = setup(); await seedTokens(env, Date.now() - 1);
  const state = await (await handleRequest(apiRequest(env, '/api/status'), env)).json();
  assert.equal(state.renewal_required, true);
});

test('delayed cron discovery uses durable due time and avoids repeated recent snapshots', async () => {
  const {env} = setup(), now = Date.now(); await seedTokens(env, now + 3600_000);
  let calls = 0;
  const external = async () => { calls++; return new Response(JSON.stringify({data: [], page_info: {has_next_page: false}})); };
  const first = await scheduledRun(env, external, now);
  assert.equal(first.status, 'private_fixed_bounties_observed'); assert.equal(calls, 5);
  const again = await scheduledRun(env, forbiddenFetch, now + 60_000);
  assert.equal(again.status, 'renewal_checked'); assert.equal(calls, 5);
});

test('the next cron upgrades recent targeted snapshots to a broad encrypted scan without changing D1 keys', async () => {
  const {env, sqlite} = setup(), now = Date.now(); await seedTokens(env, now + 3600_000);
  await seedSnapshots(env, now, false);
  const goals = [];
  const external = async url => {
    const target = new URL(url);
    if (target.pathname.endsWith('/products')) return new Response(JSON.stringify({data: [], page_info: {has_next_page: false}}));
    const goal = target.searchParams.get('business_goal_type'); goals.push(goal);
    return new Response(JSON.stringify({data: goal === null ? [{id: 'bnty_legacy', business_goal_type: null}] : [], page_info: {has_next_page: false}}));
  };
  const result = await scheduledRun(env, external, now + 60_000);
  assert.equal(result.status, 'private_fixed_bounties_observed');
  assert.deepEqual(goals, ['clipping', null]);
  assert.deepEqual(result.summaries.map(item => item.goal), ['clipping', 'all']);
  const rows = sqlite.prepare('SELECT * FROM whop_observations ORDER BY goal').all();
  assert.deepEqual(rows.map(row => row.goal), ['clipping', 'ugc_content']);
  assert.ok(!rows[1].encrypted_payload.includes('bnty_legacy'));
  const broad = await unseal(env, 'whop-observations:ugc_content:v1', rows[1].encrypted_payload);
  assert.equal(broad.business_goal_type, 'all');
  assert.equal(broad.discovery_strategy, 'all_open_goals_including_untagged_v2');
  assert.equal(broad.records[0].business_goal_type, null);
  assert.equal(broad.eligible_campaigns_verified, false);
  assert.equal(broad.live_publication_performed, false);
  assert.equal((await scheduledRun(env, forbiddenFetch, now + 120_000)).status, 'renewal_checked');
  const owner = await ownerLogin(env);
  const page = await handleRequest(req(env, '/opportunities', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  const content = await page.text();
  assert.ok(content.includes('All open goals, including untagged offers'));
  assert.ok(content.includes('goal: Untagged'));
});

test('broad and targeted saved offers are not displayed as duplicate opportunities', async () => {
  const {env} = setup(), now = Date.now(); await seedTokens(env, now + 3600_000);
  await scheduledRun(env, async () => new Response(JSON.stringify({data: [{id: 'bnty_overlap', title: 'One observed opportunity', currency: 'usd', net_reward_amount: 0.01, business_goal_type: 'clipping'}], page_info: {has_next_page: false}})), now);
  const owner = await ownerLogin(env);
  const response = await handleRequest(req(env, '/opportunities', {headers: {Cookie: owner.cookie}}), env, forbiddenFetch);
  assert.equal((await response.text()).split('<h2>One observed opportunity</h2>').length - 1, 1);
});

test('scheduled public marketplace searches send no credentials and keep deduplicated leads separate from bounties', async () => {
  const {env, sqlite} = setup(), now = Date.now(); await seedTokens(env, now + 3600_000);
  const searches = [];
  await scheduledRun(env, async (url, options) => {
    const target = new URL(url);
    assert.equal(target.origin, 'https://api.whop.com');
    assert.equal(options.method, 'GET'); assert.equal(options.redirect, 'manual');
    assert.equal(options.headers['Api-Version-Date'], '2026-10-28');
    if (target.pathname.endsWith('/bounties')) return new Response(JSON.stringify({data: [{id: 'bnty_real'}], page_info: {has_next_page: false}}));
    assert.equal(target.pathname, '/api/v1/products');
    assert.equal(target.searchParams.get('first'), '20');
    assert.equal(target.searchParams.has('account_id'), false);
    assert.equal(new Headers(options.headers).has('Authorization'), false);
    assert.equal(new Headers(options.headers).has('Cookie'), false);
    assert.ok(!url.includes('access-old'));
    const query = target.searchParams.get('query'); searches.push(query);
    return new Response(JSON.stringify({data: [{id: 'prod_research', title: 'Public lead', headline: 'Unverified program', account: {private_field: 'not-retained'}, plans: [{price: 500}], arbitrary: 'not-retained'}], page_info: {has_next_page: query === 'ugc'}}));
  }, now);
  assert.deepEqual(searches, ['content rewards', 'ugc', 'clipping']);
  const row = sqlite.prepare("SELECT encrypted_payload FROM whop_observations WHERE goal='ugc_content'").get();
  assert.ok(!row.encrypted_payload.includes('Public lead'));
  const report = await unseal(env, 'whop-observations:ugc_content:v1', row.encrypted_payload);
  assert.deepEqual(report.records, [{id: 'bnty_real'}]);
  assert.deepEqual(report.marketplace_leads.leads, [{id: 'prod_research', title: 'Public lead', headline: 'Unverified program', source_api_url: 'https://api.whop.com/api/v1/products/prod_research'}]);
  assert.deepEqual(report.marketplace_leads.queries.map(query => query.pagination_complete), [true, false, true]);
  assert.ok(report.marketplace_leads.queries.every(query => query.status === 'observed' && query.pages_fetched === 1));
  assert.equal(report.marketplace_leads.pricing_model, 'unverified_marketplace_products');
  assert.equal(report.marketplace_leads.eligible_campaigns_verified, false);
  assert.equal(report.marketplace_leads.live_publication_performed, false);
  assert.ok(!JSON.stringify(report).includes('not-retained'));
});

test('public marketplace failures stay sanitized and do not prevent bounty snapshots or later searches', async () => {
  const {env, sqlite} = setup(), now = Date.now(); await seedTokens(env, now + 3600_000);
  const queries = [];
  const result = await scheduledRun(env, async (url, options) => {
    const target = new URL(url);
    if (target.pathname.endsWith('/bounties')) return new Response(JSON.stringify({data: [{id: 'bnty_preserved'}], page_info: {has_next_page: false}}));
    assert.equal(new Headers(options.headers).has('Authorization'), false);
    const query = target.searchParams.get('query'); queries.push(query);
    if (query === 'content rewards') return new Response('private-error-body', {status: 302, headers: {Location: 'https://other.invalid/purchase'}});
    if (query === 'ugc') throw new Error('private-access-token-in-error');
    return new Response(JSON.stringify({data: [{id: 'prod_good', title: 'One retained lead', headline: null}, {id: 'https://other.invalid', title: 'bad'}], page_info: {has_next_page: false}}));
  }, now);
  assert.equal(result.status, 'private_fixed_bounties_observed');
  assert.deepEqual(queries, ['content rewards', 'ugc', 'clipping']);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS count FROM whop_observations').get().count, 2);
  const row = sqlite.prepare("SELECT encrypted_payload FROM whop_observations WHERE goal='ugc_content'").get();
  const report = await unseal(env, 'whop-observations:ugc_content:v1', row.encrypted_payload);
  assert.deepEqual(report.records, [{id: 'bnty_preserved'}]);
  assert.deepEqual(report.marketplace_leads.queries.map(query => query.status), ['http_error', 'invalid_or_unavailable', 'partial_invalid_records']);
  assert.ok(report.marketplace_leads.queries.every(query => query.pagination_complete === false));
  assert.equal(report.marketplace_leads.leads.length, 1);
  for (const secret of ['private-error-body', 'private-access-token-in-error', 'other.invalid', 'access-old']) assert.ok(!JSON.stringify(report).includes(secret));
});

test('an existing all-goal v1 snapshot is refreshed once to add the public marketplace lead scan', async () => {
  const {env, sqlite} = setup(), now = Date.now(); await seedTokens(env, now + 3600_000);
  await seedSnapshots(env, now);
  const legacy = await seal(env, 'whop-observations:ugc_content:v1', {records: [], business_goal_type: 'all', discovery_strategy: 'all_open_goals_including_untagged_v1'});
  sqlite.prepare("UPDATE whop_observations SET encrypted_payload=? WHERE goal='ugc_content'").run(legacy);
  let calls = 0;
  const first = await scheduledRun(env, async () => { calls++; return new Response(JSON.stringify({data: [], page_info: {has_next_page: false}})); }, now + 60_000);
  assert.equal(first.status, 'private_fixed_bounties_observed'); assert.equal(calls, 5);
  assert.equal((await scheduledRun(env, forbiddenFetch, now + 120_000)).status, 'renewal_checked');
});

test('new grant while old discovery HTTP is in flight cannot save stale account records', async () => {
  const {env, sqlite} = setup(), now = Date.now(); await seedTokens(env, now + 3600_000);
  let calls = 0;
  const external = async () => {
    calls++; sqlite.prepare('UPDATE whop_credentials SET authorization_generation=authorization_generation+1').run();
    return new Response(JSON.stringify({data: [{id: 'bnty_old_account'}], page_info: {has_next_page: false}}));
  };
  await assert.rejects(scheduledRun(env, external, now), /authorization changed/);
  assert.equal(calls, 1); assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM whop_observations').get().n, 0);
});

test('scheduled discovery persists only encrypted fixed-bounty snapshots and reports real pagination limits', async () => {
  const {env, sqlite} = setup(), now = Date.parse('2026-10-29T06:00:00Z'); await seedTokens(env, now + 3600_000);
  let calls = 0;
  const external = async (url, options) => {
    calls++; assert.equal(options.method, 'GET'); assert.ok(url.startsWith('https://api.whop.com/api/v1/'));
    const target = new URL(url);
    if (target.pathname.endsWith('/products')) return new Response(JSON.stringify({data: [], page_info: {has_next_page: false}}));
    const next = !target.searchParams.has('after');
    return new Response(JSON.stringify({data: [{id: 'bnty_private', private_brief: 'never-public'}], page_info: {has_next_page: next, end_cursor: next ? 'cursor-one' : null}}));
  };
  const result = await scheduledRun(env, external, now); assert.equal(result.status, 'private_fixed_bounties_observed'); assert.equal(calls, 7);
  const rows = sqlite.prepare('SELECT * FROM whop_observations').all(); assert.equal(rows.length, 2);
  assert.ok(!rows[0].encrypted_payload.includes('never-public'));
  const snapshots = await (await handleRequest(apiRequest(env, '/api/discovery/latest'), env)).json();
  assert.equal(snapshots.reports[0].pricing_model, 'fixed_reward_per_approved_submission'); assert.equal(snapshots.reports[0].eligible_campaigns_verified, false); assert.equal(snapshots.reports[0].pagination_complete, true);
});

test('aged uncertain claim requires reauthorization without reusing refresh token; status survives scheduler failure', async () => {
  const {env, sqlite} = setup(), now = Date.now(); await seedTokens(env, now - 1);
  sqlite.prepare("UPDATE whop_credentials SET status='rotating',updated_at=?").run(now - 600_000);
  const result = await runScheduledSafely(env, forbiddenFetch, now);
  assert.equal(result.status, 'blocked_owner_or_provider_action'); assert.equal((await credentials(env)).status, 'reauthorization_required');
  const status = await (await handleRequest(apiRequest(env, '/api/status'), env)).json();
  assert.equal(status.last_scheduled_status, 'blocked_owner_or_provider_action'); assert.equal(status.live_publishing, false);
});

test('owner password guessing has a bounded persistent throttle', async () => {
  const {env} = setup();
  for (let index = 0; index < 12; index++) assert.equal((await handleRequest(post(env, '/owner/login', {password: 'wrong'}), env)).status, 401);
  assert.equal((await handleRequest(post(env, '/owner/login', {password: 'wrong'}), env)).status, 429);
});

test('oversized and duplicate forms fail closed without database authorization writes', async () => {
  const {env} = setup();
  const huge = await handleRequest(post(env, '/owner/login', {password: 'a'.repeat(5000)}), env);
  assert.equal(huge.status, 502);
  const duplicate = req(env, '/owner/login', {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded', Origin: env.PUBLIC_ORIGIN}, body: 'password=x&password=y'});
  assert.equal((await handleRequest(duplicate, env)).status, 400);
  assert.equal((await credentials(env)).status, 'empty');
});
