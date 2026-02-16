# igfetch — Instagram Reel Fetcher

When the user sends an **Instagram reel URL** (e.g. `https://www.instagram.com/reel/ABC123/`), use the igfetch API to download the video.

## How to call igfetch

From inside this workspace (OpenClaw container), the igfetch server is reachable at the **host**. Use the Docker gateway IP:

- **URL:** `http://172.17.0.1:8787/fetch` (Docker host gateway; try `172.18.0.1` if unreachable)
- **Method:** POST
- **Headers:** `X-IGFETCH-TOKEN: zcFgheV07W4MmJvlXPa68AIBkisnQ25t`
- **Body:** `{"url":"<instagram_reel_url>"}`

## Example (via exec/curl)

```bash
curl -sS -X POST http://172.17.0.1:8787/fetch \
  -H "X-IGFETCH-TOKEN: zcFgheV07W4MmJvlXPa68AIBkisnQ25t" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.instagram.com/reel/ABC123/"}'
```

Response: `{ "jobId", "url", "mp4Path" }` — the MP4 is saved on the host at the given path.

## When to use

- User sends an Instagram reel link in WhatsApp or any channel
- User asks to "fetch" or "download" an Instagram reel
- User pastes a URL matching `instagram.com/reel/` or `instagram.com/p/`

## What to do with the result

- If successful: tell the user the video was fetched; the mp4Path is on the VPS
- If the user wants the file: they may need to retrieve it via SSH or a shared path
- If it fails: report the error (e.g. "Reel not found", "Login expired — re-run igfetch_login")
