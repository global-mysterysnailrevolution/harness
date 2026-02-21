#!/usr/bin/env node
/**
 * Localhost-only IG Reel fetcher.
 *
 * POST /fetch
 *  - Header: X-IGFETCH-TOKEN
 *  - JSON: { url: "https://www.instagram.com/reel/..." }
 *  - Returns: { jobId, url, mp4Path }
 *
 * Notes:
 * - Instagram changes often; the extraction logic may need maintenance.
 * - Keep this bound to 127.0.0.1.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const Fastify = require('fastify');
const { chromium } = require('playwright');

function env(name, fallback = undefined) {
  return process.env[name] ?? fallback;
}
function mustEnv(name, fallback = undefined) {
  const v = env(name, fallback);
  if (!v) throw new Error(`Missing env: ${name}`);
  return v;
}

const IGBIND = mustEnv('IGFETCH_BIND', '127.0.0.1');
const IGPORT = Number(mustEnv('IGFETCH_PORT', '8787'));
const IGTOKEN = mustEnv('IGFETCH_TOKEN');
const BASE = mustEnv('IGFETCH_BASE', '/opt/harness/igfetch');

const statePath = path.join(BASE, 'state', 'storageState.json');
const downloadsDir = path.join(BASE, 'downloads');
fs.mkdirSync(downloadsDir, { recursive: true });

function requireToken(req, reply) {
  const tok = req.headers['x-igfetch-token'];
  if (!tok || tok !== IGTOKEN) {
    reply.code(401).send({ error: 'unauthorized' });
    return false;
  }
  return true;
}

function isLikelyReelUrl(url) {
  try {
    const u = new URL(url);
    return /(^|\.)instagram\.com$/.test(u.hostname) && /\/(reel|p)\//.test(u.pathname);
  } catch {
    return false;
  }
}

async function extractVideoUrlFromNetwork(page) {
  // Heuristic approach: watch network responses for URLs that look like MP4.
  // Instagram often uses .mp4 endpoints on cdninstagram.
  // We'll capture the first "best" candidate seen.
  const candidates = new Set();

  page.on('response', async (resp) => {
    try {
      const url = resp.url();
      if (url.includes('.mp4') && (url.includes('cdninstagram') || url.includes('fbcdn') || url.includes('instagram'))) {
        candidates.add(url);
      }
    } catch {
      // ignore
    }
  });

  // Give it time to load media.
  await page.waitForTimeout(4000);

  // Prefer longer-looking URLs with mp4.
  const sorted = [...candidates].sort((a, b) => b.length - a.length);
  return sorted[0] ?? null;
}

async function downloadToFile(url, outPath) {
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) throw new Error(`download failed: ${res.status} ${res.statusText}`);
  const file = fs.createWriteStream(outPath);
  await new Promise((resolve, reject) => {
    res.body.pipe(file);
    res.body.on('error', reject);
    file.on('finish', resolve);
  });
}

async function fetchReelMp4(reelUrl) {
  if (!fs.existsSync(statePath)) {
    throw new Error(`Missing storageState: ${statePath}. Run igfetch_login.js first.`);
  }

  const jobId = crypto.randomUUID();
  const mp4Path = path.join(downloadsDir, `${jobId}.mp4`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: statePath });
  const page = await context.newPage();

  await page.goto(reelUrl, { waitUntil: 'domcontentloaded' });

  // Try to coax the player to load.
  // Some reels require interaction before video loads.
  try {
    await page.waitForTimeout(1000);
    await page.keyboard.press('Space');
  } catch {}

  const videoUrl = await extractVideoUrlFromNetwork(page);
  if (!videoUrl) {
    await browser.close();
    throw new Error('Could not detect mp4 URL from network responses (Instagram may have changed).');
  }

  await downloadToFile(videoUrl, mp4Path);
  await browser.close();

  return { jobId, url: reelUrl, mp4Path, videoUrl };
}

async function main() {
  const fastify = Fastify({ logger: true });

  fastify.post('/fetch', async (req, reply) => {
    if (!requireToken(req, reply)) return;

    const { url } = req.body ?? {};
    if (!url || typeof url !== 'string' || !isLikelyReelUrl(url)) {
      return reply.code(400).send({ error: 'invalid_url' });
    }

    try {
      const result = await fetchReelMp4(url);
      // Don’t return videoUrl unless you want it; it can be long and transient.
      return reply.send({ jobId: result.jobId, url: result.url, mp4Path: result.mp4Path });
    } catch (err) {
      req.log.error({ err }, 'fetch failed');
      return reply.code(500).send({ error: 'fetch_failed', detail: String(err.message ?? err) });
    }
  });

  fastify.get('/health', async () => ({ ok: true }));

  await fastify.listen({ host: IGBIND, port: IGPORT });
  fastify.log.info(`igfetch listening on http://${IGBIND}:${IGPORT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
