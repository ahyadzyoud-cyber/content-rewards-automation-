/** Private, owner-operated, read-only Whop authorization broker.
 * No tokens leave this Worker. No publishing, submissions, joining or payments.
 * Refresh rotation is durably claimed BEFORE sending the consuming request.
 * An ambiguous rotation is never retried with the old refresh token.
 */
export const REQUESTED_SCOPE = 'bounty:basic:read';
export const AUTHORIZATION_ENDPOINT = 'https://api.whop.com/oauth/authorize';
export const TOKEN_ENDPOINT = 'https://api.whop.com/oauth/token';
const API_BOUNTIES = 'https://api.whop.com/api/v1/bounties';
const API_VERSION = '2026-10-28';
const COOKIE = '__Host-whop_owner';
const SESSION_MS = 30 * 60_000;
// Account verification/consent can take longer than ten minutes. Keep the
// single-use PKCE transaction within the same bounded owner-session window.
const STATE_MS = SESSION_MS;
const CALLBACK_RESULTS = {
  'owner-session-required': ['Owner session expired', 'Sign in to the owner page, then start a new Whop authorization. Your existing account settings are unchanged.'],
  'authorization-request-unavailable': ['Authorization request expired or unavailable', 'This request expired, was already used, or no longer matches this browser. Start a new authorization from the owner page.'],
  'provider-denied': ['Whop authorization was not completed', 'Whop returned an authorization error. No credentials were saved. Start a new authorization from the owner page.'],
  'token-exchange-failed': ['Whop token exchange was not completed', 'The authorization response could not be exchanged and validated safely. Start a new authorization; consumed codes are never retried.'],
};
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', {fatal: true});

export class SafeError extends Error {
  constructor(message, status = 409, callbackResult = null) { super(message); this.status = status; this.callbackResult = callbackResult; }
}

export function base64url(bytes) {
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 16384) binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}
function decode64(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]+$/.test(value)) throw new SafeError('Encryption key configuration is invalid', 503);
  try {
    const bytes = Uint8Array.from(atob(value.replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0));
    if (base64url(bytes) !== value) throw new Error();
    return bytes;
  } catch { throw new SafeError('Encryption key configuration is invalid', 503); }
}
export function randomValue() { return base64url(crypto.getRandomValues(new Uint8Array(32))); }
export async function digest(value) { return base64url(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(value)))); }
async function equal(left, right) {
  const a = await digest(left), b = await digest(right);
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}
async function encryptionKey(env) {
  const raw = decode64(env.TOKEN_ENCRYPTION_KEY);
  if (raw.length !== 32) throw new SafeError('Encryption key must contain 32 random bytes', 503);
  return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt']);
}
export async function seal(env, purpose, value) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt({name: 'AES-GCM', iv, additionalData: encoder.encode(purpose)}, await encryptionKey(env), encoder.encode(JSON.stringify(value)));
  return 'v1.' + base64url(iv) + '.' + base64url(new Uint8Array(encrypted));
}
export async function unseal(env, purpose, value) {
  try {
    const [version, iv, ciphertext, extra] = value.split('.');
    if (version !== 'v1' || extra !== undefined) throw new Error();
    const plaintext = await crypto.subtle.decrypt({name: 'AES-GCM', iv: decode64(iv), additionalData: encoder.encode(purpose)}, await encryptionKey(env), decode64(ciphertext));
    return JSON.parse(decoder.decode(plaintext));
  } catch { throw new SafeError('Private stored authorization could not be read; owner reauthorization is required', 503); }
}

function configuration(env) {
  let origin;
  try { origin = new URL(env.PUBLIC_ORIGIN); } catch { throw new SafeError('Set the actual HTTPS PUBLIC_ORIGIN before authorization', 503); }
  if (origin.protocol !== 'https:' || origin.origin !== env.PUBLIC_ORIGIN || origin.username || origin.password || origin.port) throw new SafeError('PUBLIC_ORIGIN must be an exact HTTPS origin', 503);
  if (!env.DB || !env.WHOP_CLIENT_ID || !/^[A-Za-z0-9_-]{1,200}$/.test(env.WHOP_CLIENT_ID)) throw new SafeError('Configure the private database and Whop public app client ID', 503);
  for (const key of ['OWNER_PASSWORD', 'WHOP_BROKER_API_TOKEN']) {
    if (typeof env[key] !== 'string' || env[key].length < 32 || env[key].length > 512) throw new SafeError('Configure strong owner and private API secrets before authorization', 503);
  }
  if (env.REWARDS_LIVE_PUBLISHING !== 'false') throw new SafeError('This broker requires REWARDS_LIVE_PUBLISHING=false', 503);
  return origin;
}
function database(env) { return env.DB.withSession ? env.DB.withSession('first-primary') : env.DB; }
function response(body, status = 200, extra = {}) {
  return new Response(body, {status, headers: {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store', 'Pragma': 'no-cache',
    'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    // Whop's authorization API redirects to its whop.com consent/login UI.
    // Chrome enforces form-action over that redirect chain as well as the POST.
    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://api.whop.com https://whop.com; frame-ancestors 'none'; base-uri 'none'",
    'Strict-Transport-Security': 'max-age=31536000', ...extra,
  }});
}
function json(value, status = 200, extra = {}) { return response(JSON.stringify(value), status, extra); }
function escape(value) { return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
function html(title, body, status = 200, extra = {}) {
  return response('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>' + escape(title) + '</title><body><h1>' + escape(title) + '</h1>' + body + '</body></html>', status, {'Content-Type': 'text/html; charset=utf-8', ...extra});
}
function ownerPage(body) {
  // Native form POSTs inherit the document's referrer policy. no-referrer
  // serializes Origin as null in Chrome, even for a same-origin navigation.
  // Preserve exact-origin validation while withholding cross-origin referrers.
  return html('Whop owner authorization', body, 200, {'Referrer-Policy': 'same-origin'});
}
function requireOrigin(request, env) {
  if (request.headers.get('Origin') !== env.PUBLIC_ORIGIN) throw new SafeError('Same-origin owner action required', 403);
}
async function form(request) {
  if (!request.headers.get('Content-Type')?.startsWith('application/x-www-form-urlencoded')) throw new SafeError('An owner form is required', 400);
  const body = await readBytes(request.body, 4096);
  const params = new URLSearchParams(decoder.decode(body));
  for (const key of new Set(params.keys())) if (params.getAll(key).length !== 1) throw new SafeError('Duplicate form field', 400);
  return params;
}
function cookieValue(request) {
  const cookies = (request.headers.get('Cookie') || '').split(';').map(part => part.trim()).filter(part => part.startsWith(COOKIE + '='));
  if (cookies.length !== 1) return null;
  const token = cookies[0].slice(COOKIE.length + 1);
  return /^[A-Za-z0-9_-]{43}$/.test(token) ? token : null;
}
function sessionCookie(value, age = SESSION_MS / 1000) { return COOKIE + '=' + value + '; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=' + age; }
async function session(request, env, now = Date.now()) {
  const token = cookieValue(request);
  if (!token) throw new SafeError('Owner login required', 401, 'owner-session-required');
  const hash = await digest(token);
  const row = await database(env).prepare('SELECT encrypted_payload,expires_at FROM oauth_sessions WHERE session_hash=?').bind(hash).first();
  if (!row || row.expires_at <= now) throw new SafeError('Owner session expired; sign in again', 401, 'owner-session-required');
  const payload = await unseal(env, 'whop-owner-session:v1', row.encrypted_payload);
  return {hash, csrf: payload.csrf};
}
async function csrfForm(request, env) {
  requireOrigin(request, env);
  const owner = await session(request, env);
  const values = await form(request);
  if (!await equal(values.get('csrf') || '', owner.csrf)) throw new SafeError('Owner form expired; reload and retry', 403);
  return {owner, values};
}
async function login(request, env) {
  requireOrigin(request, env);
  const values = await form(request);
  const throttle = await database(env).prepare("INSERT INTO owner_login_throttle(owner,window_start,attempts) VALUES('owner',?,1) ON CONFLICT(owner) DO UPDATE SET attempts=CASE WHEN window_start<? THEN 1 ELSE attempts+1 END,window_start=CASE WHEN window_start<? THEN excluded.window_start ELSE window_start END RETURNING attempts").bind(Date.now(), Date.now() - 5 * 60_000, Date.now() - 5 * 60_000).first();
  if (!throttle || throttle.attempts > 12) throw new SafeError('Owner sign-in temporarily limited; wait five minutes', 429);
  if (!await equal(values.get('password') || '', env.OWNER_PASSWORD)) throw new SafeError('Owner sign-in failed', 401);
  const db = database(env), now = Date.now(), token = randomValue();
  const encrypted = await seal(env, 'whop-owner-session:v1', {csrf: randomValue()});
  await db.batch([
    db.prepare('DELETE FROM oauth_sessions'),
    db.prepare('DELETE FROM owner_login_throttle'),
    db.prepare('INSERT INTO oauth_sessions(session_hash,encrypted_payload,expires_at) VALUES(?,?,?)').bind(await digest(token), encrypted, now + SESSION_MS),
  ]);
  return response('', 303, {'Location': env.PUBLIC_ORIGIN + '/', 'Set-Cookie': sessionCookie(token)});
}
async function home(request, env) {
  let owner;
  try { owner = await session(request, env); } catch (error) { if (error.status !== 401) throw error; }
  if (!owner) return ownerPage('<p>Use the owner password stored in your secure deployment settings. Never share credentials or callback codes in chat.</p><form method="post" action="/owner/login"><label>Owner password <input type="password" name="password" autocomplete="current-password" required></label><button>Sign in</button></form>');
  const state = await status(env);
  return ownerPage('<p>Authorization: ' + escape(state.authorization) + '. Permission: read available bounties. Publishing stays disabled.</p><p>Complete Whop authorization within ' + STATE_MS / 60_000 + ' minutes of starting it.</p><form method="post" action="/oauth/start"><input type="hidden" name="csrf" value="' + escape(owner.csrf) + '"><button>Authorize Whop discovery</button></form><form method="post" action="/owner/logout"><input type="hidden" name="csrf" value="' + escape(owner.csrf) + '"><button>Sign out</button></form>');
}
async function start(request, env) {
  const {owner} = await csrfForm(request, env);
  const now = Date.now(), state = randomValue(), verifier = randomValue() + randomValue();
  const expiresAt = now + STATE_MS;
  const encrypted = await seal(env, 'whop-oauth-state:v1', {verifier, createdAt: now});
  const db = database(env);
  // Refresh only this already-authenticated, CSRF-validated session. Atomic
  // conditional writes cannot resurrect a session revoked during this request.
  const writes = await db.batch([
    db.prepare('UPDATE oauth_sessions SET expires_at=? WHERE session_hash=? AND expires_at>?').bind(expiresAt, owner.hash, now),
    db.prepare("INSERT INTO oauth_states(owner,state_hash,session_hash,encrypted_payload,expires_at) SELECT 'owner',?,?,?,? WHERE EXISTS(SELECT 1 FROM oauth_sessions WHERE session_hash=? AND expires_at=?) ON CONFLICT(owner) DO UPDATE SET state_hash=excluded.state_hash,session_hash=excluded.session_hash,encrypted_payload=excluded.encrypted_payload,expires_at=excluded.expires_at")
      .bind(await digest(state), owner.hash, encrypted, expiresAt, owner.hash, expiresAt),
  ]);
  if (writes.length !== 2 || writes.some(write => write?.meta?.changes !== 1)) throw new SafeError('Owner session expired; sign in again', 401, 'owner-session-required');
  const url = new URL(AUTHORIZATION_ENDPOINT);
  url.search = new URLSearchParams({client_id: env.WHOP_CLIENT_ID, redirect_uri: env.PUBLIC_ORIGIN + '/oauth/callback', response_type: 'code', scope: REQUESTED_SCOPE, state, code_challenge: await digest(verifier), code_challenge_method: 'S256'}).toString();
  return response('', 303, {'Location': url.href, 'Set-Cookie': sessionCookie(cookieValue(request), STATE_MS / 1000)});
}
export async function readBytes(stream, maximum) {
  if (!stream) return new Uint8Array();
  const reader = stream.getReader(), chunks = []; let total = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      total += value.length;
      if (total > maximum) { await reader.cancel(); throw new SafeError('Response exceeded its private size limit', 502); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(total); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return bytes;
}
async function requestTokens(env, body, fetcher = fetch, now = Date.now) {
  const started = now(); let result;
  try {
    result = await fetcher(TOKEN_ENDPOINT, {method: 'POST', headers: {'Content-Type': 'application/json', Accept: 'application/json'}, body: JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(20_000)});
  } catch { throw new SafeError('Whop token request could not be confirmed; authorize again rather than replaying a consumed token', 503); }
  if (!result.ok) throw new SafeError('Whop authorization was rejected; verify the app has only bounty:basic:read and authorize again', result.status === 401 || result.status === 403 ? 403 : 409);
  let tokens;
  try { tokens = JSON.parse(decoder.decode(await readBytes(result.body, 131072))); }
  catch { throw new SafeError('Whop returned an invalid authorization response; authorize again', 502); }
  const secret = value => typeof value === 'string' && value.length >= 1 && value.length <= 32768 && !/\s/.test(value);
  if (!tokens || !secret(tokens.access_token) || !secret(tokens.refresh_token) || !Number.isSafeInteger(tokens.expires_in) || tokens.expires_in < 120 || tokens.expires_in > 86400 || typeof tokens.token_type !== 'string' || tokens.token_type.toLowerCase() !== 'bearer') throw new SafeError('Whop returned incomplete authorization; authorize again', 502);
  if (tokens.scope !== undefined) {
    const granted = typeof tokens.scope === 'string' ? tokens.scope.split(/\s+/).filter(Boolean) : tokens.scope;
    if (!Array.isArray(granted) || granted.length !== 1 || granted[0] !== REQUESTED_SCOPE) throw new SafeError('Whop returned an unrequested permission; review app scopes and authorize again', 403);
  }
  const expiresAt = started + tokens.expires_in * 1000;
  if (now() >= expiresAt - 60_000) throw new SafeError('Whop authorization response arrived too late; authorize again', 503);
  return {accessToken: tokens.access_token, refreshToken: tokens.refresh_token, expiresAt, requestedScope: REQUESTED_SCOPE, permissionVerified: false};
}
async function markFailed(db, version) {
  await db.prepare("UPDATE whop_credentials SET status='reauthorization_required',encrypted_payload=NULL,expires_at=0,updated_at=? WHERE owner='owner' AND version=? AND status IN ('rotating','authorizing')").bind(Date.now(), version).run();
}
async function saveTokens(env, db, version, tokens, status) {
  const encrypted = await seal(env, 'whop-tokens:v1', tokens);
  const row = await db.prepare("UPDATE whop_credentials SET encrypted_payload=?,expires_at=?,status='ready',updated_at=? WHERE owner='owner' AND version=? AND status=? RETURNING version")
    .bind(encrypted, tokens.expiresAt, Date.now(), version, status).first();
  if (!row) throw new SafeError('Authorization changed during renewal; the latest owner authorization takes precedence', 409);
}
async function callback(request, env, fetcher) {
  const url = new URL(request.url), owner = await session(request, env);
  if (url.search.length > 8192 || [...new Set(url.searchParams.keys())].some(key => url.searchParams.getAll(key).length !== 1)) throw new SafeError('Invalid OAuth callback', 400);
  const state = url.searchParams.get('state');
  if (!state || !/^[A-Za-z0-9_-]{43}$/.test(state)) throw new SafeError('Invalid or expired authorization state; start again', 400);
  const db = database(env);
  const stateRow = await db.prepare("DELETE FROM oauth_states WHERE owner='owner' AND state_hash=? AND session_hash=? AND expires_at>? RETURNING encrypted_payload").bind(await digest(state), owner.hash, Date.now()).first();
  if (!stateRow) throw new SafeError('Invalid, expired or already-used authorization state; start again', 400, 'authorization-request-unavailable');
  if (url.searchParams.has('error')) throw new SafeError('Whop returned an authorization error', 400, 'provider-denied');
  const code = url.searchParams.get('code');
  if (typeof code !== 'string' || code.length < 1 || code.length > 4096 || /\s/.test(code)) throw new SafeError('Invalid OAuth callback', 400);
  const payload = await unseal(env, 'whop-oauth-state:v1', stateRow.encrypted_payload);
  const claim = await db.prepare("UPDATE whop_credentials SET status='authorizing',encrypted_payload=NULL,expires_at=0,version=version+1,authorization_generation=authorization_generation+1,renewal_count=0,last_renewed_at=NULL,updated_at=? WHERE owner='owner' AND status!='rotating' RETURNING version").bind(Date.now()).first();
  if (!claim) throw new SafeError('Renewal is in progress; wait for it to finish before starting fresh owner authorization', 409);
  try {
    await db.batch([db.prepare('DELETE FROM whop_observations'), db.prepare('DELETE FROM whop_runs')]);
    const tokens = await requestTokens(env, {grant_type: 'authorization_code', code, redirect_uri: env.PUBLIC_ORIGIN + '/oauth/callback', client_id: env.WHOP_CLIENT_ID, code_verifier: payload.verifier}, fetcher);
    await saveTokens(env, db, claim.version, tokens, 'authorizing');
  } catch (error) {
    await markFailed(db, claim.version);
    throw new SafeError('Whop token exchange could not be completed safely; start a new authorization', error instanceof SafeError ? error.status : 503, 'token-exchange-failed');
  }
  // Remove the code/state from the browser's current URL before displaying status.
  return response('', 303, {'Location': env.PUBLIC_ORIGIN + '/'});
}

export async function accessToken(env, fetcher = fetch, now = Date.now, renewalWindow = 120_000) {
  const db = database(env);
  const row = await db.prepare("SELECT encrypted_payload,expires_at,version,status FROM whop_credentials WHERE owner='owner'").first();
  if (!row || row.status !== 'ready') throw new SafeError(row?.status === 'rotating' ? 'Credential renewal is in progress or uncertain; do not replay the old refresh token' : 'Owner Whop authorization required', 409);
  const tokens = await unseal(env, 'whop-tokens:v1', row.encrypted_payload);
  if (row.expires_at > now() + renewalWindow) return tokens.accessToken;
  const claim = await db.prepare("UPDATE whop_credentials SET status='rotating',version=version+1,updated_at=? WHERE owner='owner' AND status='ready' AND version=? RETURNING version")
    .bind(now(), row.version).first();
  if (!claim) throw new SafeError('Credential renewal is already claimed; retry later without replaying its token', 409);
  try {
    const renewed = await requestTokens(env, {grant_type: 'refresh_token', refresh_token: tokens.refreshToken, client_id: env.WHOP_CLIENT_ID}, fetcher, now);
    if (renewed.refreshToken === tokens.refreshToken) throw new SafeError('Whop did not rotate the refresh token; authorize again', 502);
    await saveTokens(env, db, claim.version, renewed, 'rotating');
    await db.prepare("UPDATE whop_credentials SET renewal_count=renewal_count+1,last_renewed_at=? WHERE owner='owner' AND version=? AND status='ready'").bind(now(), claim.version).run();
    return renewed.accessToken;
  } catch (error) { await markFailed(db, claim.version); throw error; }
}

async function apiAuthorization(request, env) {
  const authorization = request.headers.get('Authorization') || '';
  if (!authorization.startsWith('Bearer ') || !await equal(authorization.slice(7), env.WHOP_BROKER_API_TOKEN)) throw new SafeError('Private API authorization required', 401);
}
export function bountyParameters(url) {
  const allowed = new Set(['country', 'status', 'business_goal_type', 'first', 'after']);
  for (const key of url.searchParams.keys()) if (!allowed.has(key) || url.searchParams.getAll(key).length !== 1) throw new SafeError('Unsupported or repeated bounty filter', 400);
  if ((url.searchParams.get('country') || 'JO') !== 'JO' || (url.searchParams.get('status') || 'open') !== 'open') throw new SafeError('This owner integration reads only open bounties for Jordan residents', 400);
  const goal = url.searchParams.get('business_goal_type');
  if (!['clipping', 'ugc_content'].includes(goal)) throw new SafeError('Choose clipping or ugc_content', 400);
  const first = url.searchParams.get('first') || '100';
  if (!/^[1-9][0-9]{0,2}$/.test(first) || Number(first) > 100) throw new SafeError('Use a bounded bounty page size from 1 to 100', 400);
  const params = new URLSearchParams({country: 'JO', status: 'open', business_goal_type: goal, first});
  const after = url.searchParams.get('after');
  if (after !== null) {
    if (!after || after.length > 4096 || /\s/.test(after)) throw new SafeError('Invalid bounty cursor', 400);
    params.set('after', after);
  }
  return params;
}
async function bountyPage(env, params, token, fetcher) {
  let result;
  try {
    result = await fetcher(API_BOUNTIES + '?' + params, {method: 'GET', headers: {Authorization: 'Bearer ' + token, Accept: 'application/json', 'Api-Version-Date': API_VERSION}, redirect: 'error', signal: AbortSignal.timeout(20_000)});
  } catch { throw new SafeError('Official Whop discovery could not complete', 503); }
  if (result.status === 401 || result.status === 403) throw new SafeError('Whop rejected bounty discovery; verify the bounty:basic:read grant and app access. No permission was expanded', 403);
  if (!result.ok) throw new SafeError('Official Whop discovery returned HTTP ' + result.status, 502);
  let page;
  try { page = JSON.parse(decoder.decode(await readBytes(result.body, 1_000_000))); }
  catch { throw new SafeError('Whop returned an invalid or oversized bounty page', 502); }
  if (!page || !Array.isArray(page.data) || page.data.length > Number(params.get('first')) || !page.page_info || typeof page.page_info.has_next_page !== 'boolean') throw new SafeError('Whop returned invalid bounty pagination', 502);
  return page;
}
async function status(env) {
  const db = database(env);
  const row = await db.prepare("SELECT status,expires_at,updated_at,renewal_count,last_renewed_at FROM whop_credentials WHERE owner='owner'").first();
  const observations = await db.prepare("SELECT COUNT(*) AS count,MAX(observed_at) AS latest FROM whop_observations WHERE authorization_generation=(SELECT authorization_generation FROM whop_credentials WHERE owner='owner' AND status='ready') AND observed_at>=?").bind(Date.now() - 7 * 86400_000).first();
  const run = await db.prepare("SELECT observed_at,status,http_status FROM whop_runs WHERE owner='owner'").first();
  return {authorization: row?.status || 'empty', requested_scope: REQUESTED_SCOPE, expires_at: row?.expires_at || null, updated_at: row?.updated_at || null, authorized: row?.status === 'ready', renewal_required: row?.status !== 'ready' || row.expires_at <= Date.now() + 120_000, refresh_in_progress: row?.status === 'rotating', durable_renewal_verified: (row?.renewal_count || 0) > 0, scope_verified: (observations?.count || 0) > 0, discovery_verified: (observations?.count || 0) > 0, renewal_count: row?.renewal_count || 0, last_renewed_at: row?.last_renewed_at || null, discovery_snapshots: observations?.count || 0, latest_discovery_at: observations?.latest || null, last_scheduled_at: run?.observed_at || null, last_scheduled_status: run?.status || null, last_scheduled_http_status: run?.http_status || null, live_publishing: false, production_verified: false};
}
export async function scheduledRun(env, fetcher = fetch, now = Date.now()) {
  configuration(env);
  const db = database(env);
  await db.batch([
    db.prepare('DELETE FROM oauth_sessions WHERE expires_at<=?').bind(now),
    db.prepare('DELETE FROM oauth_states WHERE expires_at<=?').bind(now),
    // A crash after the consuming HTTP write leaves an uncertain claim. Aged
    // claims require fresh owner consent, never reuse the old refresh token.
    db.prepare("UPDATE whop_credentials SET status='reauthorization_required',encrypted_payload=NULL,expires_at=0 WHERE owner='owner' AND status IN ('rotating','authorizing') AND updated_at<?").bind(now - 5 * 60_000),
  ]);
  const authorization = await db.prepare("SELECT authorization_generation FROM whop_credentials WHERE owner='owner' AND status='ready'").first();
  const token = await accessToken(env, fetcher, () => now, 35 * 60_000);
  if (!authorization) throw new SafeError('Owner Whop authorization required', 409);
  const generation = authorization.authorization_generation;
  const snapshots = await db.prepare('SELECT COUNT(*) AS count,MIN(observed_at) AS oldest FROM whop_observations WHERE authorization_generation=?').bind(generation).first();
  // Persisted due times tolerate delayed cron delivery and recover partial runs.
  if (snapshots?.count === 2 && snapshots.oldest > now - 6 * 3600_000) return {status: 'renewal_checked', live_publishing: false};
  const summaries = [];
  for (const goal of ['clipping', 'ugc_content']) {
    const params = new URLSearchParams({country: 'JO', status: 'open', business_goal_type: goal, first: '50'});
    const records = [], cursors = new Set(); let complete = false;
    for (let index = 0; index < 2; index++) {
      const page = await bountyPage(env, params, token, fetcher);
      records.push(...page.data);
      if (!page.page_info.has_next_page) { complete = true; break; }
      const cursor = page.page_info.end_cursor;
      if (typeof cursor !== 'string' || !cursor || cursor.length > 4096 || /\s/.test(cursor) || cursors.has(cursor)) throw new SafeError('Whop returned invalid discovery pagination', 502);
      cursors.add(cursor); params.set('after', cursor);
    }
    const report = {provider: 'whop', pricing_model: 'fixed_reward_per_approved_submission', country_filter: 'JO', business_goal_type: goal, observed_at: new Date(now).toISOString(), pagination_complete: complete, records, eligible_campaigns_verified: false, live_publication_performed: false};
    if (encoder.encode(JSON.stringify(report)).length > 1_000_000) throw new SafeError('Private discovery snapshot exceeded its free storage safety limit', 502);
    const encrypted = await seal(env, 'whop-observations:' + goal + ':v1', report);
    const saved = await db.prepare("INSERT INTO whop_observations(goal,encrypted_payload,observed_at,authorization_generation) SELECT ?,?,?,? WHERE EXISTS(SELECT 1 FROM whop_credentials WHERE owner='owner' AND status='ready' AND authorization_generation=?) ON CONFLICT(goal) DO UPDATE SET encrypted_payload=excluded.encrypted_payload,observed_at=excluded.observed_at,authorization_generation=excluded.authorization_generation RETURNING goal").bind(goal, encrypted, now, generation, generation).first();
    if (!saved) throw new SafeError('Owner authorization changed during discovery; old account observations were discarded', 409);
    summaries.push({goal, records: records.length, pagination_complete: complete});
  }
  return {status: 'private_fixed_bounties_observed', summaries, live_publishing: false};
}
export async function handleRequest(request, env, fetcher = fetch) {
  const callbackAttempt = new URL(request.url).pathname === '/oauth/callback';
  try {
    const url = new URL(request.url);
    if (url.origin !== env.PUBLIC_ORIGIN) throw new SafeError('Use the configured owner HTTPS origin', 400);
    if (request.method === 'GET' && url.pathname === '/health' && !url.search) {
      if (env.REWARDS_LIVE_PUBLISHING !== 'false' || !env.DB) throw new SafeError('Private deployment is not ready', 503);
      await encryptionKey(env);
      await database(env).prepare('SELECT 1 AS healthy').first();
      let ownerConfigured = true;
      try { configuration(env); } catch { ownerConfigured = false; }
      return json({status: 'ok', live_publishing: false, requested_scope: REQUESTED_SCOPE,
        authorization_window_minutes: STATE_MS / 60_000,
        owner_configuration_complete: ownerConfigured, production_verified: false});
    }
    configuration(env);
    if (url.pathname !== '/oauth/callback' && url.pathname !== '/api/bounties' && url.search) throw new SafeError('Unexpected request parameters', 400);
    if (request.method === 'GET' && url.pathname === '/') return await home(request, env);
    if (request.method === 'GET' && url.pathname === '/oauth/result') return html('Whop authorization not completed', '<p>The authorization attempt was invalid, expired, cancelled or rejected. Its private callback parameters have been removed from this page. Start again from owner settings. Only the verified read-only bounty permission is requested; permissions are not expanded automatically.</p><p><a href="/">Return to owner settings</a></p>');
    if (request.method === 'GET' && url.pathname.startsWith('/oauth/result/')) {
      const reason = url.pathname.slice('/oauth/result/'.length);
      if (Object.hasOwn(CALLBACK_RESULTS, reason)) {
        const [title, message] = CALLBACK_RESULTS[reason];
        return html(title, '<p>' + escape(message) + '</p><p><a href="/">Return to owner settings</a></p>');
      }
    }
    if (request.method === 'POST' && url.pathname === '/owner/login') return await login(request, env);
    if (request.method === 'POST' && url.pathname === '/owner/logout') {
      const {owner} = await csrfForm(request, env);
      await database(env).prepare('DELETE FROM oauth_sessions WHERE session_hash=?').bind(owner.hash).run();
      return response('', 303, {Location: env.PUBLIC_ORIGIN + '/', 'Set-Cookie': sessionCookie('', 0)});
    }
    if (request.method === 'POST' && url.pathname === '/oauth/start') return await start(request, env);
    if (request.method === 'GET' && url.pathname === '/oauth/callback') return await callback(request, env, fetcher);
    if (request.method === 'GET' && url.pathname === '/status') { await session(request, env); return json(await status(env)); }
    if (request.method === 'GET' && url.pathname === '/api/status') { await apiAuthorization(request, env); return json(await status(env)); }
    if (request.method === 'GET' && url.pathname === '/api/bounties') {
      await apiAuthorization(request, env);
      const params = bountyParameters(url);
      const token = await accessToken(env, fetcher);
      return json(await bountyPage(env, params, token, fetcher));
    }
    if (request.method === 'GET' && url.pathname === '/api/discovery/latest') {
      await apiAuthorization(request, env);
      const rows = await database(env).prepare("SELECT goal,encrypted_payload,observed_at FROM whop_observations WHERE authorization_generation=(SELECT authorization_generation FROM whop_credentials WHERE owner='owner' AND status='ready') ORDER BY goal").all();
      const reports = [];
      for (const row of rows.results) reports.push(await unseal(env, 'whop-observations:' + row.goal + ':v1', row.encrypted_payload));
      return json({reports, live_publishing: false, production_verified: false});
    }
    return json({error: 'Route not found'}, 404);
  } catch (error) {
    // Always leave the callback URL, including error paths, without copying its query.
    if (callbackAttempt) {
      const reason = error instanceof SafeError && Object.hasOwn(CALLBACK_RESULTS, error.callbackResult) ? '/' + error.callbackResult : '';
      return response('', 303, {Location: '/oauth/result' + reason});
    }
    // No raw errors, request URLs, provider bodies or credential values in logs.
    return json({error: error instanceof SafeError ? error.message : 'Private authorization storage or service failed; check deployment settings securely'}, error instanceof SafeError ? error.status : 503);
  }
}
export async function runScheduledSafely(env, fetcher = fetch, now = Date.now()) {
  let result;
  try { result = await scheduledRun(env, fetcher, now); }
  catch (error) { result = {status: 'blocked_owner_or_provider_action', http_status: error instanceof SafeError ? error.status : 503, live_publishing: false}; }
  try { await database(env).prepare("INSERT INTO whop_runs(owner,observed_at,status,http_status) VALUES('owner',?,?,?) ON CONFLICT(owner) DO UPDATE SET observed_at=excluded.observed_at,status=excluded.status,http_status=excluded.http_status").bind(now, result.status, result.http_status || 200).run(); } catch { /* No secret-bearing logging fallback. */ }
  return result;
}
export default {
  fetch(request, env) { return handleRequest(request, env); },
  scheduled(_controller, env, context) {
    // Surface only a sanitized result; never log callback URLs or token payloads.
    context.waitUntil(runScheduledSafely(env));
  },
};
