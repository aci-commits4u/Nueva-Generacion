/*
 * Real DOM UAT for the adaptive_fast flight flow.
 *
 * Run with a fresh, headless Playwright CLI session only after the live UAT
 * budget is explicitly released:
 *   playwright-cli -s=fast-live-uat run-code --filename=scripts/browser_fast_live_uat.js
 *
 * This suite intentionally does not intercept routes, seed state, choose
 * fallback mode, or fill missing airport fields in Review. It stops before
 * review when natural-language grounding is incomplete.
 */
async page => {
  const startedAt = Date.now();
  const initialText = 'Get me from Toronto to London, and also no layovers, less than 800 $. I can travel November 12, 2026.';
  const completeText = 'Use the exact date November 12, 2026. Depart from YYZ or YHM and arrive at LHR or LGW. Keep no layovers and keep the maximum strictly less than 800 dollars.';
  const correctionText = 'Actually allow one layover, but keep both airport choices and everything else.';
  const maxModelStages = 4;
  const evidence = {
    result: 'PASS',
    scenario: 'fresh-flight-two-send-plus-one-correction',
    inputs: { initial: initialText, complete_update: completeText, correction: correctionText },
    stages: [],
    failures: [],
  };

  const fail = message => {
    evidence.result = 'FAIL';
    evidence.failures.push(message);
    throw new Error(message);
  };
  const assert = (condition, message) => { if (!condition) fail(message); };
  const pathOf = response => new URL(response.url()).pathname;
  const bodyOf = async response => { try { return await response.json(); } catch { return null; } };
  const readStatus = () => page.evaluate(() => fetch('/api/ai/status').then(response => response.json()));
  const sorted = value => Array.isArray(value) ? [...value].sort() : value;
  const fieldsFor = draft => draft?.fields || {};
  const questionFields = draft => (draft?.questions || []).map(question => question.field || question.criterion_key || null).filter(Boolean);

  const recordStatus = async label => {
    const status = await readStatus();
    evidence.status = evidence.status || {};
    evidence.status[label] = {
      pipeline: status.pipeline,
      available: status.available,
      interpretation_calls: status.interpretation_calls,
      remaining_calls: status.remaining_calls,
      session_remaining_calls: status.session_remaining_calls,
      remaining_interpretations: status.remaining_interpretations,
      reason_code: status.reason?.code || null,
    };
    return status;
  };

  const assertGrounded = (draft, label, expectedMaxConnections) => {
    const fields = fieldsFor(draft);
    assert(sorted(fields.origin_airports)?.join(',') === 'YHM,YYZ', `${label}: origin airport set is ${JSON.stringify(fields.origin_airports)}`);
    assert(sorted(fields.destination_airports)?.join(',') === 'LGW,LHR', `${label}: destination airport set is ${JSON.stringify(fields.destination_airports)}`);
    assert(fields.departure_date === '2026-11-12', `${label}: date is ${JSON.stringify(fields.departure_date)}`);
    assert(fields.max_total_cents === 79999, `${label}: strict budget is ${JSON.stringify(fields.max_total_cents)}`);
    assert(fields.max_connections === expectedMaxConnections, `${label}: max connections is ${JSON.stringify(fields.max_connections)}`);
    const forbidden = questionFields(draft).filter(field => ['origin_airports', 'destination_airports', 'departure_date', 'max_total_cents', 'max_connections'].includes(field));
    assert(forbidden.length === 0, `${label}: re-asked a settled field: ${JSON.stringify(forbidden)}`);
    return fields;
  };

  const sendModelTurn = async (path, button, label, intentId) => {
    const before = await readStatus();
    const started = Date.now();
    const responsePromise = page.waitForResponse(response => response.request().method() === 'POST' && pathOf(response) === path, { timeout: 90_000 });
    await button.click();
    const response = await responsePromise;
    const after = await readStatus();
    const body = await bodyOf(response);
    const modelCalls = Math.max(0, Number(before.remaining_calls || 0) - Number(after.remaining_calls || 0));
    const stage = { label, path, http_status: response.status(), latency_ms: Date.now() - started, model_calls: modelCalls };
    evidence.stages.push(stage);
    assert(evidence.stages.reduce((total, item) => total + item.model_calls, 0) <= maxModelStages, `${label}: exceeded ${maxModelStages}-stage cap`);
    if (response.status() !== 200) {
      evidence.result = 'FAIL';
      evidence.failures.push(`${label}: HTTP ${response.status()} ${body?.error?.code || body?.detail || 'unknown error'}`);
      throw new Error(`${label}: HTTP ${response.status()} ${body?.error?.code || body?.detail || 'unknown error'}`);
    }
    evidence.status = evidence.status || {};
    evidence.status[`after_${label}`] = {
      remaining_calls: after.remaining_calls,
      session_remaining_calls: after.session_remaining_calls,
      remaining_interpretations: after.remaining_interpretations,
    };
    if (intentId) evidence.intent_id = intentId;
    return body;
  };

  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto('http://127.0.0.1:8767/?domain=flight', { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: 'What should your agent know?' }).waitFor({ timeout: 20_000 });
  const before = await recordStatus('before');
  assert(before.available === true, `live AI unavailable: ${before.reason?.code || 'unknown'}`);
  assert(before.pipeline === 'adaptive_fast', `expected adaptive_fast, observed ${before.pipeline}`);
  assert(before.interpretation_calls === 1, `ordinary fast turn advertised ${before.interpretation_calls} model calls`);
  assert(Number(before.session_remaining_calls) >= 4, 'fewer than four live stages available; aborting without a partial UAT');

  await page.getByLabel('What would you like to find?').fill(initialText);
  const initial = await sendModelTurn('/api/intents', page.getByRole('button', { name: 'Start a conversation' }), 'flight_initial');
  const intentId = initial.id;
  evidence.initial = { fields: initial.fields, questions: questionFields(initial) };
  await page.getByRole('heading', { name: 'Let’s get your intent right.' }).waitFor({ timeout: 30_000 });

  await page.getByLabel('Add a detail or change your request').fill(completeText);
  const complete = await sendModelTurn(`/api/intents/${intentId}/clarify`, page.getByRole('button', { name: 'Send clarification' }), 'flight_complete_update', intentId);
  evidence.complete = { fields: complete.fields, questions: questionFields(complete), adaptive_action: complete.adaptive_plan?.action || null };
  assertGrounded(complete, 'complete update', 0);
  await page.screenshot({ path: 'artifacts/fast-live-flight-complete.png', fullPage: true });

  await page.getByLabel('Add a detail or change your request').fill(correctionText);
  const correction = await sendModelTurn(`/api/intents/${intentId}/clarify`, page.getByRole('button', { name: 'Send clarification' }), 'flight_correction', intentId);
  evidence.correction = { fields: correction.fields, questions: questionFields(correction), adaptive_action: correction.adaptive_plan?.action || null };
  assertGrounded(correction, 'correction', 1);
  await page.screenshot({ path: 'artifacts/fast-live-flight-correction.png', fullPage: true });

  await page.getByRole('button', { name: 'Review requirements' }).click();
  await page.getByRole('heading', { name: 'Review what will be checked.' }).waitFor({ timeout: 15_000 });
  const reviewValues = {
    departure: await page.getByLabel('Departure airports *').inputValue(),
    arrival: await page.getByLabel('Arrival airports *').inputValue(),
    date: await page.locator('#field-departure_date-single').inputValue(),
    budget: await page.getByLabel('Maximum all-in price (USD) *').inputValue(),
    max_connections: await page.getByLabel('Maximum connections').inputValue(),
  };
  evidence.review = reviewValues;
  assert(reviewValues.departure.replace(/\s/g, '') === 'YYZ,YHM', `review lost departure airports: ${reviewValues.departure}`);
  assert(reviewValues.arrival.replace(/\s/g, '') === 'LHR,LGW', `review lost arrival airports: ${reviewValues.arrival}`);
  assert(reviewValues.date === '2026-11-12', `review lost date: ${reviewValues.date}`);
  assert(reviewValues.budget === '799.99', `review lost budget: ${reviewValues.budget}`);
  assert(reviewValues.max_connections === '1', `review lost correction: ${reviewValues.max_connections}`);
  const noPreference = page.getByRole('button', { name: 'No preference for unanswered optional details' });
  if (await noPreference.count() && await noPreference.isVisible()) await noPreference.click();
  await page.getByLabel('I reviewed my original request').check();
  await page.getByRole('button', { name: 'Approve these requirements' }).click();
  await page.getByRole('heading', { name: 'Two offers. One approved intent.' }).waitFor({ timeout: 20_000 });
  const comparison = await page.locator('#workspace').innerText();
  evidence.comparison = {
    pass_visible: /Intent-checked/.test(comparison),
    hold_visible: /On hold/.test(comparison),
    corrected_difference_visible: /Required: 1\s*Offer: 3|Required: 1.*Offer: 3/s.test(comparison),
  };
  assert(evidence.comparison.pass_visible, 'matching signed offer was not intent-checked');
  assert(evidence.comparison.hold_visible, 'three-connection signed offer was not held');
  assert(evidence.comparison.corrected_difference_visible, 'comparison did not show Required: 1 / Offer: 3');
  await page.screenshot({ path: 'artifacts/fast-live-flight-correction-comparison.png', fullPage: true });
  const after = await recordStatus('after');
  evidence.runtime_ms = Date.now() - startedAt;
  evidence.model_stage_total = evidence.stages.reduce((total, item) => total + item.model_calls, 0);
  evidence.status_after = { remaining_calls: after.remaining_calls, session_remaining_calls: after.session_remaining_calls, remaining_interpretations: after.remaining_interpretations };
  return evidence;
}
