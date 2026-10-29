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

async function fixtureBrowser({oldDocumentPolicy = false, oldProviderPolicy = false, unapprovedProvider = false} = {}) {
  const fixture = createFixture();
  const {env} = fixture;
  const context = await browser.newContext({serviceWorkers: 'block'});
  const metadata = [], authorizations = [], unapprovedRequests = [];
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
        assert.ok(!headers.cookie, 'The owner session cookie must not reach the provider API');
        authorizations.push({origin: url.origin, method: 'GET', path: '/oauth/authorize', status: 302,
          no_referrer: true, no_owner_cookie: true, intercepted: true});
        const frontend = new URL('https://whop.com/oauth/authorize');
        frontend.search = url.search;
        await fulfill(302, {Location: unapprovedProvider ? 'https://unapproved.example.invalid/collect' : frontend.href,
          'Referrer-Policy': 'no-referrer'}, '');
        return;
      }
      if (url.origin === 'https://whop.com') {
        if (url.pathname === '/favicon.ico' && request.method === 'GET') {
          await fulfill(204, {'Content-Type': 'image/x-icon'}, '');
          return;
        }
        assert.equal(request.method, 'GET');
        assert.ok(!headers.referer, 'Provider redirects must not receive the owner-page referrer');
        assert.ok(!headers.cookie, 'The owner session cookie must not reach the provider frontend');
        assert.ok(['/oauth/authorize', '/login'].includes(url.pathname));
        const status = url.pathname === '/oauth/authorize' ? 307 : 200;
        authorizations.push({origin: url.origin, method: 'GET', path: url.pathname, status,
          no_referrer: true, no_owner_cookie: true, intercepted: true});
        if (status === 307) {
          await fulfill(307, {Location: 'https://whop.com/login', 'Referrer-Policy': 'no-referrer'}, '');
        } else {
          await fulfill(200, {'Content-Type': 'text/html'}, '<title>Whop fixture login</title><h1>Whop fixture login</h1><p>No external request was made.</p>');
        }
        return;
      }
      if (url.origin === 'https://unapproved.example.invalid') {
        unapprovedRequests.push({origin: url.origin, path: url.pathname});
        await fulfill(200, {'Content-Type': 'text/html'}, '<title>Unexpected provider navigation</title>');
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
      if (oldProviderPolicy && request.method === 'GET' && url.pathname === '/') {
        outgoing['content-security-policy'] = outgoing['content-security-policy']
          .replace(/form-action[^;]*/, "form-action 'self' https://api.whop.com");
      }
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
  return {env, page, context, metadata, authorizations, unapprovedRequests, sqlite: fixture.sqlite,
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
async function observeCsp(page) {
  await page.evaluate(() => {
    globalThis.__ownerCspViolations = [];
    document.addEventListener('securitypolicyviolation', event => {
      // A browser blockedURI may contain PKCE/state query values; record only the directive.
      globalThis.__ownerCspViolations.push(event.effectiveDirective);
    });
  });
}
async function waitForFormCsp(page) {
  await page.waitForFunction(() => globalThis.__ownerCspViolations?.includes('form-action'));
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
    await fixture.page.waitForURL(url => url.origin === 'https://whop.com' && url.pathname === '/login');
    await fixture.page.getByRole('heading', {name: 'Whop fixture login'}).waitFor();
    assert.equal(fixture.authorizations.length, 3);
    assert.deepEqual(fixture.authorizations.map(({origin, path, status}) => ({origin, path, status})), [
      {origin: 'https://api.whop.com', path: '/oauth/authorize', status: 302},
      {origin: 'https://whop.com', path: '/oauth/authorize', status: 307},
      {origin: 'https://whop.com', path: '/login', status: 200},
    ]);
    assert.ok(fixture.authorizations.every(row => row.no_owner_cookie && row.no_referrer));
    const retained = (await fixture.context.cookies(fixture.env.PUBLIC_ORIGIN)).find(item => item.name === '__Host-whop_owner');
    assert.ok(retained && retained.value === cookie.value, 'Provider navigation must preserve the owner session');
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

test('Chrome reproduces the old CSP blocking the verified provider frontend redirect after OAuth start succeeds', async () => {
  await runSafely('old-csp-blocks-provider-redirect-chain', async fixture => {
    await signIn(fixture);
    await fixture.page.getByRole('button', {name: 'Authorize Whop discovery'}).waitFor();
    await observeCsp(fixture.page);
    await fixture.page.getByRole('button', {name: 'Authorize Whop discovery'}).click({noWaitAfter: true});
    await waitForFormCsp(fixture.page);
    const current = new URL(fixture.page.url());
    assert.equal(current.origin, fixture.env.PUBLIC_ORIGIN);
    assert.equal(current.pathname, '/');
    const action = fixture.metadata.find(row => row.path === '/oauth/start');
    assert.equal(action.origin, fixture.env.PUBLIC_ORIGIN);
    assert.equal(action.status, 303);
    assert.equal(fixture.sqlite.prepare('SELECT COUNT(*) AS n FROM oauth_states').get().n, 1);
    assert.deepEqual(fixture.authorizations.map(({origin, path, status}) => ({origin, path, status})), [
      {origin: 'https://api.whop.com', path: '/oauth/authorize', status: 302},
    ]);
    assert.equal(fixture.unapprovedRequests.length, 0);
  }, {oldProviderPolicy: true});
});

test('Chrome still blocks an unrelated origin in the provider redirect chain without leaking the owner cookie', async () => {
  await runSafely('unapproved-provider-redirect-remains-blocked', async fixture => {
    await signIn(fixture);
    await fixture.page.getByRole('button', {name: 'Authorize Whop discovery'}).waitFor();
    await observeCsp(fixture.page);
    await fixture.page.getByRole('button', {name: 'Authorize Whop discovery'}).click({noWaitAfter: true});
    await waitForFormCsp(fixture.page);
    assert.equal(new URL(fixture.page.url()).origin, fixture.env.PUBLIC_ORIGIN);
    const action = fixture.metadata.find(row => row.path === '/oauth/start');
    assert.equal(action.status, 303);
    assert.equal(fixture.authorizations.length, 1);
    assert.ok(fixture.authorizations[0].no_owner_cookie && fixture.authorizations[0].no_referrer);
    assert.equal(fixture.unapprovedRequests.length, 0, 'CSP must block before any request to the unrelated origin');
    assert.ok((await fixture.context.cookies(fixture.env.PUBLIC_ORIGIN)).some(item => item.name === '__Host-whop_owner'));
  }, {unapprovedProvider: true});
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
