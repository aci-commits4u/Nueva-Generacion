/*
 * Browser UAT for live discovery.
 *
 * The setup is a real user journey: type an original request, choose the
 * explicit offline mode, review, and approve it through the rendered UI. Only
 * the read-only provider response is mocked below so this regression suite is
 * repeatable and does not consume Kiwi calls. The separate real-provider
 * smoke run is recorded outside this suite.
 */

async page => {
  const artifact = name => `artifacts/${name}`;
  const origin = new URL(page.url()).origin;
  page.setDefaultTimeout(20_000);

  const mockResult = (overrides = {}) => ({
    record_type: 'external_discovery_result',
    status: 'external_unverified',
    provider: 'kiwi',
    retrieved_at: '2026-10-15T01:00:00Z',
    currency: 'USD',
    query: { query_count: 1 },
    query_summary: {
      query_count: 1,
      origins: ['EWR'],
      destinations: ['MCO'],
      adults: 2,
    },
    results: [
      {
        record_type: 'external_discovery',
        id: 'uat-kiwi-1',
        verification_status: 'external_unverified',
        verified: false,
        price_cents: 14800,
        booking_url: 'https://www.kiwi.com/u/uat-example-1',
        carrier: 'UA',
        origin: 'EWR',
        destination: 'MCO',
        departure_at: '2026-11-12T06:00:00-05:00',
        arrival_at: '2026-11-12T08:56:00-05:00',
        duration_minutes: 176,
        connections: null,
        advisory_checks: [
          { check_id: 'max_total_cents', status: 'MATCH', requirement: 29999, offer_value: 14800 },
          { check_id: 'origin_airports', status: 'MATCH', requirement: ['EWR', 'JFK'], offer_value: 'EWR' },
          { check_id: 'destination_airports', status: 'MATCH', requirement: ['MCO', 'FLL'], offer_value: 'MCO' },
          { check_id: 'departure_date', status: 'MATCH', requirement: '2026-11-12', offer_value: '2026-11-12' },
          { check_id: 'nonstop', status: 'UNKNOWN', requirement: true, offer_value: null },
        ],
      },
      {
        record_type: 'external_discovery',
        id: 'uat-kiwi-2',
        verification_status: 'external_unverified',
        verified: false,
        price_cents: 25900,
        booking_url: 'https://kiwi.com/u/uat-example-2',
        carrier: 'B6',
        origin: 'JFK',
        destination: 'FLL',
        departure_at: '2026-11-12T09:20:00-05:00',
        arrival_at: '2026-11-12T12:35:00-05:00',
        duration_minutes: 195,
        connections: 1,
        advisory_checks: [
          { check_id: 'max_total_cents', status: 'MATCH', requirement: 29999, offer_value: 25900 },
          { check_id: 'origin_airports', status: 'MATCH', requirement: ['EWR', 'JFK'], offer_value: 'JFK' },
          { check_id: 'destination_airports', status: 'MATCH', requirement: ['MCO', 'FLL'], offer_value: 'FLL' },
          { check_id: 'departure_date', status: 'MATCH', requirement: '2026-11-12', offer_value: '2026-11-12' },
          { check_id: 'nonstop', status: 'CONFLICT', requirement: true, offer_value: false },
        ],
      },
    ],
    notice: 'External quotes only. They are not merchant-signed and cannot approve or execute a purchase.',
    ...overrides,
  });

  const responseJson = async (route, status, body) => {
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  };

  const setScope = async (input, checked) => {
    if ((await input.isChecked()) === checked) return;
    // The checkbox is visually hidden by the accessible pill control. Click
    // its real label, preserving the same path a keyboard/mouse user takes.
    await input.locator('xpath=..').click();
    if ((await input.isChecked()) !== checked) throw new Error('Airport scope pill did not update its checkbox state.');
  };

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${origin}/?domain=flight`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: 'What should your agent know?' }).waitFor();
  await page.getByText('Interpretation settings', { exact: true }).click();
  await page.getByLabel('AI availability').selectOption('offline');

  // Type a request with several accepted airport identities. The parser only
  // receives the request via the UI; no fixture draft or API seed is used.
  const originalRequest = 'Book a nonstop flight under $300. Depart from EWR or JFK. Arrive at MCO or FLL. Travel dates 2026-11-12.';
  await page.getByLabel('What would you like to find?').fill(originalRequest);
  await page.getByRole('button', { name: 'Start a conversation' }).click();
  await page.getByRole('heading', { name: 'Let’s get your intent right.' }).waitFor();
  await page.getByRole('button', { name: 'Review requirements' }).click();
  await page.getByRole('heading', { name: 'Review what will be checked.' }).waitFor();
  await page.getByRole('button', { name: 'No preference for unanswered optional details' }).click();
  await page.getByLabel('I reviewed my original request').check();
  await page.getByRole('button', { name: 'Approve these requirements' }).click();
  await page.getByRole('heading', { name: 'Two offers. One approved intent.' }).waitFor();

  const live = page.locator('[data-live-shopping]');
  await live.waitFor();
  if (await live.locator('input[data-live-scope="origin_airports"]').count() !== 2) {
    throw new Error('Approved multiple departure airports did not render as a selectable live scope.');
  }
  if (await live.locator('input[data-live-scope="destination_airports"]').count() !== 2) {
    throw new Error('Approved multiple arrival airports did not render as a selectable live scope.');
  }

  await live.getByText('Narrow the approved airport set', { exact: false }).click();
  const origins = live.locator('input[data-live-scope="origin_airports"]');
  const destinations = live.locator('input[data-live-scope="destination_airports"]');
  if (!(await origins.nth(0).isChecked()) || !(await origins.nth(1).isChecked()) ||
      !(await destinations.nth(0).isChecked()) || !(await destinations.nth(1).isChecked())) {
    throw new Error('Live scope did not start with every approved airport selected.');
  }

  // Empty scope must be a visible client-side validation and must not call the
  // provider. This catches the old “click the box and ask again” regression.
  await setScope(origins.nth(0), false);
  await setScope(origins.nth(1), false);
  let shoppingRequests = 0;
  page.on('request', request => {
    if (new URL(request.url()).pathname.endsWith('/shopping')) shoppingRequests += 1;
  });
  await live.getByRole('button', { name: /Search live options/ }).click();
  await page.getByRole('alert').filter({ hasText: 'Choose at least one approved departure airport' }).waitFor();
  if (shoppingRequests !== 0) throw new Error(`Empty airport scope made ${shoppingRequests} provider request(s).`);

  // Narrow to one origin and one destination, then verify the actual request
  // body. The backend receives a subset of approved values, never new values.
  await setScope(origins.nth(0), true);
  await setScope(destinations.nth(1), false);
  let requestBody = null;
  await page.route('**/api/intents/*/shopping', async route => {
    requestBody = route.request().postDataJSON();
    const first = mockResult().results[0];
    const third = { ...first, id: 'uat-kiwi-3', price_cents: 19900, carrier: 'AA' };
    await responseJson(route, 200, mockResult({
      query_summary: { query_count: 1, origins: ['EWR'], destinations: ['MCO'], adults: 2 },
      results: [first, third, { ...third, id: 'uat-kiwi-4', price_cents: 22900, carrier: 'DL' }],
    }));
  });
  await live.locator('#live-adults').selectOption('2');
  await live.getByRole('button', { name: /Search live options/ }).click();
  await live.locator('[data-live-result]').first().waitFor();
  if (!requestBody || requestBody.adults !== 2 || JSON.stringify(requestBody.origin_airports) !== JSON.stringify(['EWR']) ||
      JSON.stringify(requestBody.destination_airports) !== JSON.stringify(['MCO'])) {
    throw new Error(`Narrowed scope was not sent exactly: ${JSON.stringify(requestBody)}`);
  }
  if (await live.locator(':scope > .live-results-grid > [data-live-result]').count() !== 2) throw new Error('The first two live results were not kept visible.');
  const moreOptions = live.locator('details.live-more-results');
  if (await moreOptions.locator('summary').innerText() !== 'Show 1 more flight option') throw new Error('Additional live results did not use the native disclosure label.');
  await moreOptions.locator('summary').click();
  if (await live.locator('[data-live-result]').count() !== 3) throw new Error('Native disclosure did not reveal the remaining live option.');
  await moreOptions.locator('summary').click();
  if (await live.getByText('External quotes only.', { exact: false }).count() !== 1) throw new Error('External quote warning was not rendered.');
  if (await live.locator('button:has-text("purchase")').count()) throw new Error('Live discovery exposed a purchase action.');
  const kiwiLink = live.locator('.live-kiwi-link').first();
  if (await kiwiLink.getAttribute('target') !== '_blank' || await kiwiLink.getAttribute('rel') !== 'noopener noreferrer') {
    throw new Error('Live provider link is missing safe target/rel attributes.');
  }
  await page.screenshot({ path: artifact('browser-shopping-multi-scope.png'), fullPage: true });

  // Retry path: first response fails, then the explicit retry succeeds. No
  // implicit fallback or second request is allowed before the user clicks.
  let retryCalls = 0;
  await page.unroute('**/api/intents/*/shopping');
  await page.route('**/api/intents/*/shopping', async route => {
    retryCalls += 1;
    if (retryCalls === 1) {
      await responseJson(route, 502, { detail: 'Kiwi is temporarily unavailable.', error: { code: 'provider_error', message: 'Kiwi is temporarily unavailable.' } });
    } else {
      await responseJson(route, 200, mockResult({ query_summary: { query_count: 1, origins: ['EWR'], destinations: ['MCO'], adults: 2 }, results: [mockResult().results[0]] }));
    }
  });
  await live.getByRole('button', { name: /Search live options/ }).click();
  await live.getByRole('alert').filter({ hasText: 'Kiwi is temporarily unavailable' }).waitFor();
  if (retryCalls !== 1) throw new Error(`Provider retry happened without an explicit click: ${retryCalls} call(s).`);
  await live.getByRole('button', { name: 'Try this search again' }).click();
  await live.locator('[data-live-result]').first().waitFor();
  if (retryCalls !== 2) throw new Error(`Explicit retry did not make exactly one second request: ${retryCalls}.`);
  await page.unroute('**/api/intents/*/shopping');

  // A delayed old response must be ignored after the user starts another
  // request. This exercises navigation guards through the actual buttons.
  let releaseShopping;
  const delayedShopping = new Promise(resolve => { releaseShopping = resolve; });
  await page.route('**/api/intents/*/shopping', async route => {
    await delayedShopping;
    await responseJson(route, 200, mockResult());
  });
  await live.getByRole('button', { name: /Search live options/ }).click();
  await page.getByRole('button', { name: '＋ New request' }).click();
  await page.getByRole('heading', { name: 'What should your agent know?' }).waitFor();
  releaseShopping();
  await page.waitForTimeout(250);
  if (await page.locator('[data-live-shopping]').count()) throw new Error('Stale live response rendered after starting a new request.');
  await page.unroute('**/api/intents/*/shopping');

  // Responsive UAT at a narrow viewport. Check layout geometry as a user
  // would see it, not just CSS source text.
  await page.setViewportSize({ width: 390, height: 844 });
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (mobileOverflow > 1) throw new Error(`Mobile layout overflows horizontally by ${mobileOverflow}px.`);
  await page.screenshot({ path: artifact('browser-shopping-mobile.png'), fullPage: true });

  return {
    result: 'PASS',
    mode: 'explicit offline typed journey + deterministic shopping route mock',
    multipleAirportScope: true,
    emptyScopeBlockedWithoutProviderCall: true,
    narrowedScopeBodyVerified: true,
    externalQuoteBoundary: true,
    explicitRetryOnly: true,
    staleNavigationIgnored: true,
    mobileOverflowPx: mobileOverflow,
  };
}
