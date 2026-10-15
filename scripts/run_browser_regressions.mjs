import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const playwrightModule = process.env.PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = require(playwrightModule);

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:8000';
const origin = new URL(baseUrl).origin;
const artifactDir = path.resolve(process.env.BROWSER_ARTIFACT_DIR || path.join(root, 'artifacts'));
const suiteTimeoutMs = Number(process.env.BROWSER_SUITE_TIMEOUT_MS || 60_000);
const readinessTimeoutMs = Number(process.env.BROWSER_READINESS_TIMEOUT_MS || 30_000);

const allSuiteNames = [
  'browser_product',
  'browser_new_request',
  'browser_flight_ui',
  'browser_mobile',
  'browser_navigation',
  'browser_tutorial_pending',
  'browser_availability_races',
  'browser_uat_guards',
  'browser_adaptive',
  'browser_route_choices',
  'browser_shopping',
];
const suiteNames = (process.env.BROWSER_SUITES
  ? process.env.BROWSER_SUITES.split(',').map((name) => name.trim()).filter(Boolean)
  : allSuiteNames);
for (const name of suiteNames) {
  if (!allSuiteNames.includes(name)) {
    throw new Error(`Unknown browser suite ${name}; expected one of ${allSuiteNames.join(', ')}`);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 5_000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function waitForServer() {
  const deadline = Date.now() + readinessTimeoutMs;
  let lastError = 'server did not answer';
  while (Date.now() < deadline) {
    try {
      const response = await fetchWithTimeout(`${baseUrl}/`, {}, 2_000);
      if (response.ok) {
        return;
      }
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(250);
  }
  throw new Error(`Intent Judge was not ready at ${baseUrl}: ${lastError}`);
}

async function loadSuite(name) {
  const source = await fs.readFile(path.join(root, 'scripts', `${name}.js`), 'utf8');
  // These files are first-party, reviewed browser journeys. Each intentionally
  // exports one async page => result function rather than a test-runner suite.
  const suite = eval(source);
  if (typeof suite !== 'function') {
    throw new TypeError(`${name}.js must evaluate to an async page function`);
  }
  return suite;
}

async function runSuite(browser, name) {
  const started = Date.now();
  const context = await browser.newContext({
    baseURL: baseUrl,
    viewport: { width: 1280, height: 900 },
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15_000);
  page.setDefaultNavigationTimeout(30_000);

  const consoleLines = [];
  const pageErrors = [];
  const requestFailures = [];
  page.on('console', (message) => {
    consoleLines.push(`[${message.type()}] ${message.text()}`);
  });
  page.on('pageerror', (error) => {
    pageErrors.push(error.stack || error.message);
  });
  page.on('requestfailed', (request) => {
    requestFailures.push(`${request.method()} ${request.url()} :: ${request.failure()?.errorText || 'failed'}`);
  });

  const logPath = path.join(artifactDir, `${name}-harness.log`);
  const failureScreenshot = path.join(artifactDir, `${name}-harness-failure.png`);
  const log = (message) => {
    consoleLines.push(`[harness] ${message}`);
  };

  try {
    await page.goto(origin, { waitUntil: 'domcontentloaded' });
    const suite = await loadSuite(name);
    let timeoutHandle;
    try {
      const timeout = new Promise((_, reject) => {
        timeoutHandle = setTimeout(() => reject(new Error(`suite exceeded ${suiteTimeoutMs}ms`)), suiteTimeoutMs);
      });
      const result = await Promise.race([Promise.resolve(suite(page)), timeout]);
      if (!result || result.result !== 'PASS') {
        throw new Error(`${name} returned an invalid result: ${JSON.stringify(result)}`);
      }
      if (pageErrors.length) {
        throw new Error(`${name} emitted page errors: ${pageErrors.join(' | ')}`);
      }
      log(`PASS runtime_ms=${Date.now() - started}`);
      await fs.writeFile(logPath, [...consoleLines, ...pageErrors.map((line) => `[pageerror] ${line}`), ...requestFailures.map((line) => `[requestfailed] ${line}`)].join('\n') + '\n');
      return { name, ...result, runtime_ms: Date.now() - started };
    } finally {
      clearTimeout(timeoutHandle);
    }
  } catch (error) {
    log(`FAIL runtime_ms=${Date.now() - started} ${error instanceof Error ? error.stack || error.message : String(error)}`);
    try {
      await page.screenshot({ path: failureScreenshot, fullPage: true });
    } catch (screenshotError) {
      log(`failure screenshot unavailable: ${screenshotError instanceof Error ? screenshotError.message : String(screenshotError)}`);
    }
    await fs.writeFile(logPath, [...consoleLines, ...pageErrors.map((line) => `[pageerror] ${line}`), ...requestFailures.map((line) => `[requestfailed] ${line}`)].join('\n') + '\n');
    throw error;
  } finally {
    await context.close();
  }
}

await fs.mkdir(artifactDir, { recursive: true });
await waitForServer();
const launchOptions = { headless: process.env.HEADLESS !== '0' };
if (process.env.BROWSER_EXECUTABLE_PATH) {
  launchOptions.executablePath = process.env.BROWSER_EXECUTABLE_PATH;
}
const browser = await chromium.launch(launchOptions);
const results = [];
const failures = [];
try {
  for (const name of suiteNames) {
    try {
      const result = await runSuite(browser, name);
      results.push(result);
      console.log(JSON.stringify(result));
    } catch (error) {
      const failure = { name, error: error instanceof Error ? error.message : String(error) };
      failures.push(failure);
      console.error(JSON.stringify({ result: 'FAIL', ...failure }));
    }
  }
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(JSON.stringify({ result: 'FAIL', passed: results.map(({ name }) => name), failures }));
  process.exitCode = 1;
} else {
  console.log(JSON.stringify({ result: 'PASS', suites: results.length, total_runtime_ms: results.reduce((sum, result) => sum + result.runtime_ms, 0) }));
}
