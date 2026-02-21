#!/usr/bin/env node
/**
 * One-time interactive Instagram login to produce a Playwright storageState.
 * Writes: ${IGFETCH_BASE}/state/storageState.json
 *
 * Run as the dedicated user (e.g., igfetch).
 */

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

function mustEnv(name, fallback = undefined) {
  const v = process.env[name] ?? fallback;
  if (!v) throw new Error(`Missing env: ${name}`);
  return v;
}

(async () => {
  const base = mustEnv('IGFETCH_BASE', '/opt/harness/igfetch');
  const stateDir = path.join(base, 'state');
  const statePath = path.join(stateDir, 'storageState.json');

  fs.mkdirSync(stateDir, { recursive: true });

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Instagram may redirect; start at login.
  await page.goto('https://www.instagram.com/accounts/login/', { waitUntil: 'domcontentloaded' });

  console.log('\nLogin in the opened browser window.');
  console.log('When you reach a logged-in Instagram home/feed (or can open any reel), come back here.');
  console.log('Then press ENTER to save session state.\n');

  await new Promise((resolve) => {
    process.stdin.resume();
    process.stdin.once('data', () => resolve());
  });

  await context.storageState({ path: statePath });
  console.log(`Saved storageState → ${statePath}`);

  await browser.close();
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
