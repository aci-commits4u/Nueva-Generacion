const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}[character]));

function money(cents, currency = 'USD') {
  if (cents === null || cents === undefined || cents === '') return 'Price unavailable';
  const amount = Number(cents);
  if (!Number.isFinite(amount)) return 'Price unavailable';
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount / 100);
  } catch {
    return `$${(amount / 100).toFixed(2)}`;
  }
}

function dateTime(value) {
  if (!value || typeof value !== 'string') return 'Time unavailable';
  const localParts = value.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  const date = localParts ? new Date(Date.UTC(
    Number(localParts[1]), Number(localParts[2]) - 1, Number(localParts[3]),
    Number(localParts[4]), Number(localParts[5])
  )) : new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace('T', ' ').replace(/([+-]\d\d:\d\d|Z)$/, '');
  return new Intl.DateTimeFormat('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'UTC'
  }).format(date);
}

function duration(minutes) {
  if (minutes === null || minutes === undefined || minutes === '') return 'Duration unavailable';
  if (!Number.isFinite(Number(minutes))) return 'Duration unavailable';
  const value = Math.max(0, Number(minutes));
  const hours = Math.floor(value / 60);
  const mins = value % 60;
  return hours ? `${hours}h ${mins}m` : `${mins}m`;
}

function stops(value, nonstop) {
  if (nonstop === true) return 'Nonstop';
  if (value === null || value === undefined || value === '') return 'Stops unknown';
  if (value === 0) return '0 connections reported';
  if (Number.isInteger(Number(value))) return `${value} connection${Number(value) === 1 ? '' : 's'}`;
  return 'Stops unknown';
}

function fieldList(fields, key) {
  return Array.isArray(fields?.[key]) ? fields[key].filter(Boolean).map(String) : [];
}

function scopeField(label, key, values, selected) {
  if (!values.length) return '';
  return `<fieldset class="live-scope-fieldset">
    <legend>${esc(label)}</legend>
    <div class="live-scope-options">${values.map(value => {
      const checked = selected.includes(value);
      return `<label class="live-scope-option"><input type="checkbox" data-live-scope="${esc(key)}" value="${esc(value)}" ${checked ? 'checked' : ''}><span>${esc(value)}</span></label>`;
    }).join('')}</div>
    <p class="live-scope-help">Leave all selected to search every approved ${key === 'origin_airports' ? 'departure' : 'arrival'} airport. This narrows the search only; it does not change your approved intent.</p>
  </fieldset>`;
}

function checkLabel(check) {
  const labels = {
    max_total_cents: 'Quote price',
    origin_airports: 'Departure airport',
    destination_airports: 'Arrival airport',
    departure_date: 'Departure date',
    nonstop: 'Stops'
  };
  return labels[check?.check_id] || String(check?.check_id || 'Requirement').replaceAll('_', ' ');
}

function advisoryChecks(result) {
  const checks = Array.isArray(result?.advisory_checks) ? result.advisory_checks : [];
  if (!checks.length) return '<p class="live-option-note">No advisory comparison was returned for this quote.</p>';
  return `<div class="live-advisory-checks" aria-label="Advisory comparison to your approved intent">${checks.map(check => {
    const status = String(check?.status || 'UNKNOWN').toUpperCase();
    const tone = status === 'MATCH' ? 'match' : status === 'CONFLICT' ? 'conflict' : 'unknown';
    return `<div class="live-advisory-check"><span>${esc(checkLabel(check))}</span><b class="live-check-${tone}">${esc(status)}</b></div>`;
  }).join('')}</div>`;
}

function kiwiUrl(value) {
  if (!value || typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (url.protocol !== 'https:' || !(host === 'kiwi.com' || host.endsWith('.kiwi.com')) || url.username || url.password || url.hash) return null;
    return url.toString();
  } catch {
    return null;
  }
}

function optionCard(result, index) {
  const facts = result?.facts && typeof result.facts === 'object' ? result.facts : {};
  const origin = result?.origin || facts.origin || '—';
  const destination = result?.destination || facts.destination || '—';
  const price = result?.price_cents ?? result?.price_quote?.amount_cents;
  const currency = result?.currency || result?.price_quote?.currency || 'USD';
  const link = kiwiUrl(result?.booking_url || result?.bookingUrl);
  const carrier = result?.carrier || 'Carrier unavailable';
  const departure = result?.departure_at || facts.departure_at || facts.departure_local;
  const arrival = result?.arrival_at || facts.arrival_at;
  const connectionCount = result?.connections ?? facts.connection_count;
  const nonstop = result?.nonstop ?? facts.nonstop;
  const verification = result?.verification_status || 'external_unverified';
  return `<article class="live-flight-card" data-live-result>
    <div class="live-flight-card-top"><span class="live-result-index">${String(index + 1).padStart(2, '0')}</span><span class="live-unverified">External quote</span></div>
    <div class="live-flight-route"><strong>${esc(origin)}</strong><span aria-hidden="true">→</span><strong>${esc(destination)}</strong></div>
    <p class="live-flight-carrier">${esc(carrier)} <span>·</span> ${esc(stops(connectionCount, nonstop))}</p>
    <div class="live-flight-times"><div><span>DEPARTS</span><b>${esc(dateTime(departure))}</b></div><div><span>ARRIVES</span><b>${esc(dateTime(arrival))}</b></div><div><span>DURATION</span><b>${esc(duration(result?.duration_minutes ?? facts.duration_minutes))}</b></div></div>
    <div class="live-flight-price"><span>From provider</span><strong>${esc(money(price, currency))}</strong></div>
    ${advisoryChecks(result)}
    <div class="live-flight-action">${link ? `<a class="secondary live-kiwi-link" href="${esc(link)}" target="_blank" rel="noopener noreferrer">View on Kiwi <span aria-hidden="true">↗</span></a>` : '<span class="live-no-link">Provider link unavailable</span>'}<span class="live-verification-label">${esc(verification.replaceAll('_', ' '))}</span></div>
  </article>`;
}

function resultList(data) {
  const results = Array.isArray(data?.results) ? data.results : Array.isArray(data?.results_normalized) ? data.results_normalized : [];
  if (!results.length) return `<div class="live-empty"><span class="live-empty-mark" aria-hidden="true">—</span><div><h3>No live options matched this search</h3><p>Try another approved airport scope or date, then search again. Nothing was booked.</p></div></div>`;
  const firstResults = results.slice(0, 2);
  const remainingResults = results.slice(2);
  return `<div class="live-results-grid">${firstResults.map(optionCard).join('')}</div>${remainingResults.length ? `<details class="live-more-results"><summary>Show ${remainingResults.length} more flight option${remainingResults.length === 1 ? '' : 's'}</summary><div class="live-results-grid">${remainingResults.map((result, index) => optionCard(result, index + 2)).join('')}</div></details>` : ''}`;
}

export function shoppingMarkup({ approved, shopping, environment = 'development' }) {
  const fields = approved?.fields || approved || {};
  const origins = fieldList(fields, 'origin_airports');
  const destinations = fieldList(fields, 'destination_airports');
  const selectedOrigins = Array.isArray(shopping?.selectedOrigins) ? shopping.selectedOrigins : origins;
  const selectedDestinations = Array.isArray(shopping?.selectedDestinations) ? shopping.selectedDestinations : destinations;
  const status = shopping?.status || 'idle';
  const isLoading = status === 'loading';
  const resultData = shopping?.data;
  const error = shopping?.error;
  const query = resultData?.query_summary || resultData?.query || null;
  const queryLabel = query ? `${(query.origins || []).join(', ')} → ${(query.destinations || []).join(', ')} · ${query.adults || shopping.adults || 1} adult${Number(query.adults || shopping.adults || 1) === 1 ? '' : 's'}` : '';
  return `<section class="live-shopping" aria-labelledby="live-shopping-title" data-live-shopping data-environment="${esc(environment)}">
    <div class="live-shopping-heading"><div><span class="eyebrow">LIVE DISCOVERY / READ-ONLY</span><h2 id="live-shopping-title">Search live flight options</h2><p>Search one-way flight options using the approved airports and date, then compare current Kiwi quotes with the signed demo offers.</p></div><span class="live-provider-badge"><span class="live-provider-dot" aria-hidden="true"></span> Kiwi MCP</span></div>
    <div class="live-shopping-boundary"><strong>What this does</strong><span>Finds external options. It does not approve, purchase, or replace the signed offer check below.</span></div>
    <form id="live-shopping-form" class="live-shopping-form">
      <div class="live-shopping-controls">
        <label class="live-adult-control" for="live-adults">Adults<select id="live-adults" name="adults">${Array.from({length: 9}, (_, index) => index + 1).map(value => `<option value="${value}" ${Number(shopping?.adults || 1) === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label>
        <div class="live-approved-scope"><span class="live-control-label">Search scope</span><span class="live-scope-summary">${origins.join(', ') || 'Departure airport'} → ${destinations.join(', ') || 'Arrival airport'}</span></div>
        <button class="primary live-search-submit" type="submit" ${isLoading ? 'disabled aria-busy="true"' : ''}>${isLoading ? '<span class="live-search-spinner" aria-hidden="true"></span>Searching…' : 'Search live options'} <span aria-hidden="true">→</span></button>
      </div>
      ${(origins.length > 1 || destinations.length > 1) ? `<details class="live-scope-details"${shopping?.scopeError ? ' open' : ''}><summary>Narrow the approved airport set <span>optional</span></summary><p class="small">These choices only change which live queries run. Your approved requirements stay exactly as reviewed.</p>${scopeField('Departure airports', 'origin_airports', origins, selectedOrigins)}${scopeField('Arrival airports', 'destination_airports', destinations, selectedDestinations)}</details>` : ''}
    </form>
    ${shopping?.scopeError ? `<p class="error-text live-scope-error" role="alert">${esc(shopping.scopeError)}</p>` : ''}
    ${status === 'error' ? `<div class="live-shopping-error" role="alert"><strong>Live search could not finish.</strong><p>${esc(error || 'The provider did not return a usable response. Your approved intent is unchanged.')}</p><button type="button" class="text-button" data-live-retry>Try this search again</button></div>` : ''}
    ${status === 'loading' ? `<div class="live-results-loading" aria-live="polite"><div class="live-loading-line"></div><div class="live-loading-grid"><span></span><span></span></div><p>Kiwi is checking the approved route. This can take a few seconds.</p></div>` : status === 'success' ? `<div class="live-results-heading" role="status" aria-live="polite"><div><span class="eyebrow">CURRENT PROVIDER RESPONSE</span><h3>${resultData?.results?.length || resultData?.results_normalized?.length || 0} live option${(resultData?.results?.length || resultData?.results_normalized?.length || 0) === 1 ? '' : 's'}</h3></div><span class="live-query-label">${esc(queryLabel || 'Approved scope')}</span></div>${resultList(resultData)}<p class="live-notice">${esc(resultData?.notice || resultData?.not_verified_notice || resultData?.not_verified || 'External quotes are not merchant-signed. Final availability and price are confirmed on Kiwi.')}</p>` : status === 'idle' ? `<div class="live-shopping-idle"><span class="live-idle-mark" aria-hidden="true">↗</span><p>Search once the requirements are approved. The results stay separate from the deterministic signed-offer check.</p></div>` : ''}
  </section>`;
}
