/** Real Chromium navigation tests; every page request is intercepted locally.
 * No production credentials, live D1, Whop requests, consent, or publication.
 */
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {after, before, test} from 'node:test';
import {AUTHORIZATION_ENDPOINT, REQUESTED_SCOPE, handleRequest} from '../src/worker.mjs';
import {createFixture} from '../test-support/fixture.mjs';

// createRequire also supports an already installed development copy via NODE_PATH.
const {chromium} = createRequire(import.meta.url)('playwright');
let browser;
before(async () => {
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
    headless: true,
    args: ['--no-sandbox', '--disable-background-networking'],
  });
});
after(async () => { await browser?.close(); });

async function fixtureBrowser({oldDocumentPolicy = false} = {}) {
  const fixture = createFixture();
  const {env} = fixture;
  const context = await browser.newContext({serviceWorkers: 'block'});
  const metadata = [], authorizations = [];
  const page = await context.newPage();
  page.setDefaultTimeout(10_000);
  const cdp = await context.newCDPSession(page);
  // Playwright route handlers cover only the first URL of a redirect chain.
  // CDP intercepts every hop BEFORE network, including the synthetic Whop URL.
  await cdp.send('Fetch.enable', {patterns: [{urlPattern: '*', requestStage: 'Request'}]});
  cdp.on('Fetch.requestPaused', event => {
    (async () => {
      const request = event.request, url = new URL(request.url);
      const headers = Object.fromEntries(new Headers(request.headers));
      async function fulfill(status, outgoing, body) {
        await cdp.send('Fetch.fulfillRequest', {requestId: event.requestId, responseCode: status,
          responseHeaders: Object.entries(outgoing).map(([name, value]) => ({name, value})),
          body: Buffer.from(body).toString('base64')});
      }
      if (url.origin === 'https://api.whop.com') {
        if (url.pathname === '/favicon.ico' && request.method === 'GET') {
          await fulfill(204, {'Content-Type': 'image/x-icon'}, '');
          return;
        }
        assert.equal(url.origin + url.pathname, AUTHORIZATION_ENDPOINT);
        assert.equal(request.method, 'GET');
        assert.equal(url.searchParams.get('scope'), REQUESTED_SCOPE);
        assert.equal(url.searchParams.get('redirect_uri'), env.PUBLIC_ORIGIN + '/oauth/callback');
        assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
        assert.ok(/^[A-Za-z0-9_-]{43}$/.test(url.searchParams.get('state') || ''));
        assert.ok(/^[A-Za-z0-9_-]{43}$/.test(url.searchParams.get('code_challenge') || ''));
        assert.ok(!headers.referer, 'Cross-origin consent must receive no owner-page referrer');
        authorizations.push({method: 'GET', path: '/oauth/authorize', no_referrer: true, intercepted: true});
        await fulfill(200, {'Content-Type': 'text/html'}, '<title>Intercepted consent</title><p>No external request was made.</p>');
        return;
      }
      if (url.origin === 'https://foreign.example.invalid') {
        await fulfill(200, {'Content-Type': 'text/html'},
          '<form method="post" action="' + env.PUBLIC_ORIGIN + '/owner/login">' +
          '<input name="password" type="password"><button>Cross-origin sign in</button></form>');
        return;
      }
      if (url.origin !== env.PUBLIC_ORIGIN) {
        await cdp.send('Fetch.failRequest', {requestId: event.requestId, errorReason: 'BlockedByClient'});
        throw new Error('Unexpected external request was blocked');
      }
      const incoming = new Request(request.url, {method: request.method, headers,
        body: request.method === 'POST' ? request.postData : undefined});
      const response = await handleRequest(incoming, env, () => {
        throw new Error('Worker provider HTTP must never run in browser fixtures');
      });
      const outgoing = Object.fromEntries(response.headers);
      if (oldDocumentPolicy && request.method === 'GET' && url.pathname === '/') outgoing['referrer-policy'] = 'no-referrer';
      // Explicit safe fields only. No bodies, cookies, passwords, CSRF/state or queries.
      metadata.push({method: request.method, path: url.pathname,
        origin: headers.origin || 'missing', fetch_mode: headers['sec-fetch-mode'] || 'missing',
        fetch_site: headers['sec-fetch-site'] || 'missing', navigation: event.resourceType === 'Document',
        resource_type: event.resourceType.toLowerCase(), status: response.status,
        document_policy: outgoing['referrer-policy']});
      await fulfill(response.status, outgoing, await response.arrayBuffer());
    })().catch(async () => {
      // No raw browser/HTTP exception text or secret-bearing request details.
      const url = new URL(event.request.url);
      metadata.push({fixture_route_failure: true, origin: url.origin, path: url.pathname});
      try { await cdp.send('Fetch.failRequest', {requestId: event.requestId, errorReason: 'BlockedByClient'}); } catch {}
    });
  });
  return {env, page, context, metadata, authorizations, sqlite: fixture.sqlite,
    async close() { await context.close(); fixture.sqlite.close(); }};
}

async function signIn(fixture) {
  await fixture.page.goto(fixture.env.PUBLIC_ORIGIN + '/');
  await fixture.page.locator('input[name="password"]').fill(fixture.env.OWNER_PASSWORD);
  await fixture.page.getByRole('button', {name: 'Sign in', exact: true}).click();
}
function loginMetadata(fixture) {
  return fixture.metadata.find(row => row.method === 'POST' && row.path === '/owner/login');
}
async function runSafely(name, body, options) {
  const fixture = await fixtureBrowser(options);
  try {
    await body(fixture);
    assert.ok(!fixture.metadata.some(row => row.fixture_route_failure), 'Every request must be intercepted successfully');
    console.log(JSON.stringify({scenario: name, requests: fixture.metadata, intercepted_authorizations: fixture.authorizations}));
  } catch {
    // Browser exception text may contain form values or full OAuth navigation URLs.
    console.error(JSON.stringify({scenario: name, requests: fixture.metadata, failed: true}));
    throw new Error('Browser security regression failed: ' + name);
  } finally { await fixture.close(); }
}

test('Chrome reproduces no-referrer native POST as Origin:null and strict rejection', async () => {
  await runSafely('old-policy-reproduces-null-origin', async fixture => {
    await signIn(fixture);
    assert.ok((await fixture.page.textContent('body')).includes('Same-origin owner action required'));
    const request = loginMetadata(fixture);
    assert.equal(request.origin, 'null');
    assert.equal(request.navigation, true);
    assert.equal(request.resource_type, 'document');
    assert.equal(request.status, 403);
    assert.equal(fixture.sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_sessions').get().n, 0);
  }, {oldDocumentPolicy: true});
});

test('Chrome signs in, retains cookie protections, starts PKCE without referrer, and signs out', async () => {
  await runSafely('fixed-policy-complete-owner-workflow', async fixture => {
    await signIn(fixture);
    await fixture.page.getByRole('button', {name: 'Authorize Whop discovery'}).waitFor();
    const request = loginMetadata(fixture);
    assert.equal(request.origin, fixture.env.PUBLIC_ORIGIN);
    assert.equal(request.navigation, true);
    assert.equal(request.resource_type, 'document');
    assert.equal(request.status, 303);
    const cookies = await fixture.context.cookies();
    const cookie = cookies.find(item => item.name === '__Host-whop_owner');
    assert.ok(cookie && cookie.httpOnly && cookie.secure && cookie.sameSite === 'Lax');
    assert.equal(cookie.path, '/');
    assert.equal(cookie.domain, new URL(fixture.env.PUBLIC_ORIGIN).hostname);
    await fixture.page.getByRole('button', {name: 'Authorize Whop discovery'}).click();
    await fixture.page.waitForURL(url => url.origin === 'https://api.whop.com' && url.pathname === '/oauth/authorize');
    assert.equal(fixture.authorizations.length, 1);
    const authorization = fixture.metadata.find(row => row.path === '/oauth/start');
    assert.equal(authorization.origin, fixture.env.PUBLIC_ORIGIN);
    assert.equal(authorization.status, 303);
    await fixture.page.goto(fixture.env.PUBLIC_ORIGIN + '/');
    await fixture.page.getByRole('button', {name: 'Sign out'}).click();
    await fixture.page.getByRole('button', {name: 'Sign in', exact: true}).waitFor();
    const logout = fixture.metadata.find(row => row.path === '/owner/logout');
    assert.equal(logout.origin, fixture.env.PUBLIC_ORIGIN);
    assert.equal(logout.status, 303);
    assert.ok(!(await fixture.context.cookies()).some(item => item.name === '__Host-whop_owner'));
    assert.equal(fixture.sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_sessions').get().n, 0);
  });
});

test('Chrome same-origin form with a tampered CSRF token remains rejected', async () => {
  await runSafely('tampered-csrf-remains-rejected', async fixture => {
    await signIn(fixture);
    await fixture.page.getByRole('button', {name: 'Authorize Whop discovery'}).waitFor();
    await fixture.page.locator('form[action="/oauth/start"] input[name="csrf"]').evaluate(input => { input.value = 'tampered'; });
    await fixture.page.getByRole('button', {name: 'Authorize Whop discovery'}).click();
    assert.ok((await fixture.page.textContent('body')).includes('Owner form expired'));
    const action = fixture.metadata.find(row => row.path === '/oauth/start');
    assert.equal(action.origin, fixture.env.PUBLIC_ORIGIN);
    assert.equal(action.status, 403);
    assert.equal(fixture.authorizations.length, 0);
    assert.equal(fixture.sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 0);
  });
});

test('Chrome foreign-origin form remains rejected even with the correct synthetic password', async () => {
  await runSafely('foreign-origin-remains-rejected', async fixture => {
    await fixture.page.goto('https://foreign.example.invalid/');
    await fixture.page.locator('input[name="password"]').fill(fixture.env.OWNER_PASSWORD);
    await fixture.page.getByRole('button', {name: 'Cross-origin sign in'}).click();
    assert.ok((await fixture.page.textContent('body')).includes('Same-origin owner action required'));
    const request = loginMetadata(fixture);
    assert.equal(request.origin, 'https://foreign.example.invalid');
    assert.equal(request.navigation, true);
    assert.equal(request.status, 403);
    assert.equal(fixture.sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_sessions').get().n, 0);
  });
});
