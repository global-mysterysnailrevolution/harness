## igfetch (Instagram Reel Fetcher)
- **When**: User sends an Instagram reel URL (e.g. in WhatsApp) or asks to fetch/download a reel
- **API**: `POST http://172.17.0.1:8787/fetch` (host from container)
- **Headers**: `X-IGFETCH-TOKEN: zcFgheV07W4MmJvlXPa68AIBkisnQ25t`
- **Body**: `{"url":"<instagram_reel_url>"}`
- **How**: Use exec to run `curl -X POST http://172.17.0.1:8787/fetch -H "X-IGFETCH-TOKEN: zcFgheV07W4MmJvlXPa68AIBkisnQ25t" -H "Content-Type: application/json" -d '{"url":"URL"}'`
- **Full doc**: See `IGFETCH.md`
