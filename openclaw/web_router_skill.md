# Web Router Skill

This skill defines how you interact with the web. The goal is to minimize token usage and latency by routing tasks through the fastest possible path.

## The Two Lanes

**Fast lane** -- HTTP fetch, search API, site adapters. Text in, text out. Cheap, fast, reliable.

**Slow lane** -- Playwright browser automation. Screenshots, clicks, JS execution. Expensive, slow, fragile. Use only when fast lane is blocked.

## Routing Rules

Follow these rules **in order** for every web task:

### Rule 1: Read-only? Use fetch.

If the task is "read this page / summarize / find info / compare options":

```
harness_call_tool fetch:fetch {"url": "https://example.com", "max_length": 5000}
```

This returns the page as clean markdown text. Reason over the text directly. **Never open a browser just to read a page.**

If fetch returns an error (403, empty body, JS-rendered content), move to Rule 4.

### Rule 2: Search? Use the search API.

If the task is "find X / search for Y / what are my options for Z":

```
harness_call_tool brave-search:brave_web_search {"query": "your search terms", "count": 5}
```

This returns structured results with titles, URLs, and snippets. Read the snippets first. Only fetch individual URLs if you need more detail.

**Never open 10 browser tabs to compare search results.** The search tool does that in one call.

Note: brave-search requires a BRAVE_API_KEY. If not configured, tell the user to set it up in `harness/secrets/brave.env`.

### Rule 3: Known site? Use an adapter.

Before using the browser for any interactive task (fill form, submit data, check status), check if a site adapter exists:

```
harness_call_tool web-adapter:list_adapters {}
```

If an adapter matches the target site, use it:

```
harness_call_tool web-adapter:execute_adapter {"adapter": "site-name", "vars": {"field1": "value1"}}
```

Adapters replay captured API requests directly -- no browser needed.

### Rule 4: Auth/JS blocks everything? Browser recon (one time).

Only use Playwright when:
- fetch returns 403 / empty / JS-required content
- The site requires login / CAPTCHA / complex JS interaction
- No adapter exists for this site

When you do use the browser, treat it as a **recon mission**:
1. Complete the task in the browser
2. While doing so, note the actual HTTP requests being made (endpoints, headers, payloads)
3. After completing the task, **propose creating an adapter** so next time you can skip the browser

### Rule 5: After browser recon, propose an adapter.

After any successful browser interaction, suggest to the user:

> "I completed [task] via browser. I noticed the site uses [endpoint] with [payload shape]. Want me to create a site adapter so I can do this faster next time without opening a browser?"

If the user agrees, create the adapter JSON in `harness/adapters/`. See the Web Adapter Skill for the format.

## Default Behavior

- **If in doubt, try fetch first.** It's free and instant.
- **Chrome is a last resort**, not a default.
- **Cache awareness:** If you fetched a URL earlier in this conversation, don't fetch it again unless the user asks for fresh data.
- **Error escalation:** fetch fails -> try with `raw: true` -> if still fails -> browser.

## Cost Awareness

Every browser interaction costs significantly more tokens than a fetch call because it involves screenshots, DOM parsing, and multi-step navigation. A single fetch call might use 500 tokens. A browser session for the same page might use 5,000-15,000 tokens. Route accordingly.
