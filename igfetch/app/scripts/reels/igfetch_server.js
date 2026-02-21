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

async function extractVideoUrlFromDom(page) {
  // Method 1: Get video element src (Instagram hydrates via JS)
  try {
    const video = await page.waitForSelector('video', { timeout: 8000 });
    if (video) {
      const src = await video.getAttribute('src');
      if (src && (src.includes('.mp4') || src.includes('video') || src.includes('fbcdn') || src.includes('cdninstagram'))) {
        return src;
      }
      // Also try currentSrc (for dynamically set sources)
      const currentSrc = await page.evaluate((el) => el.currentSrc || el.src || null, video);
      if (currentSrc) return currentSrc;
    }
  } catch {
    // video element not found or no src
  }
  return null;
}

async function extractVideoUrlFromNetwork(page) {
  const candidates = new Set();
  page.on('response', async (resp) => {
    try {
      const url = resp.url();
      if (url.includes('.mp4') || (url.includes('video') && (url.includes('fbcdn') || url.includes('cdninstagram') || url.includes('instagram')))) {
        candidates.add(url);
      }
      // Also catch fbcdn.net video URLs without .mp4 in path
      if ((url.includes('fbcdn.net') || url.includes('cdninstagram.com')) && (url.includes('video') || url.includes('mp4') || resp.request().resourceType() === 'media')) {
        candidates.add(url);
      }
    } catch {
      // ignore
    }
  });
  await page.waitForTimeout(5000);
  const sorted = [...candidates].sort((a, b) => b.length - a.length);
  return sorted[0] ?? null;
}

async function extractVideoUrlFromPageJson(page) {
  // Method 3: Instagram embeds GraphQL/JSON in the page - look for video_url
  try {
    const json = await page.evaluate(() => {
      const scripts = document.querySelectorAll('script[type="application/json"]');
      for (const s of scripts) {
        try {
          const data = JSON.parse(s.textContent);
          const str = JSON.stringify(data);
          const match = str.match(/https?:\/\/[^"'\s]+\.mp4[^"'\s]*/);
          if (match) return match[0];
          const cdnMatch = str.match(/https?:\/\/([^"'\s]*cdninstagram[^"'\s]*|([^"'\s]*fbcdn[^"'\s]*video[^"'\s]*))/);
          if (cdnMatch) return cdnMatch[0];
        } catch {}
      }
      return null;
    });
    return json;
  } catch {
    return null;
  }
}

async function extractVideoUrl(page) {
  // Try DOM first (most reliable when it works)
  let url = await extractVideoUrlFromDom(page);
  if (url) return url;

  // Try embedded JSON
  url = await extractVideoUrlFromPageJson(page);
  if (url) return url;

  // Fall back to network interception
  url = await extractVideoUrlFromNetwork(page);
  return url;
}

async function downloadToFile(url, outPath) {
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) throw new Error(`download failed: ${res.status} ${res.statusText}`);
  const buffer = await res.arrayBuffer();
  fs.writeFileSync(outPath, Buffer.from(buffer));
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

  await page.goto(reelUrl, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});

  try {
    await page.waitForTimeout(2000);
    await page.keyboard.press('Space');
    await page.waitForTimeout(1500);
  } catch {}

  const videoUrl = await extractVideoUrl(page);
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
