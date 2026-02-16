# Web Adapter Skill

Site adapters let you replay multi-step web workflows via direct HTTP requests instead of driving a browser. Each adapter is a JSON file that captures the request pattern for a specific site/workflow.

## Using Adapters

### List available adapters

```
python3 /data/harness/scripts/tools/web_adapter_tool.py list_adapters
```

### Execute an adapter

```
python3 /data/harness/scripts/tools/web_adapter_tool.py execute_adapter --args '{"adapter": "site-name", "vars": {"field1": "value1", "field2": "value2"}}'
```

### Validate an adapter (dry-run)

```
python3 /data/harness/scripts/tools/web_adapter_tool.py validate_adapter --args '{"adapter": "site-name"}'
```

This shows required variables, step count, and any schema errors without making HTTP requests.

## Creating Adapters

After completing a browser recon session, create an adapter to avoid browser usage next time.

### Adapter JSON format

Save to `harness/adapters/<site-name>.json`:

```json
{
  "site": "example-saas.com",
  "description": "What this adapter does (one line)",
  "auth": {
    "type": "bearer_token",
    "source_env": "EXAMPLE_API_TOKEN"
  },
  "steps": [
    {
      "method": "GET",
      "url": "https://example-saas.com/api/csrf-token",
      "extract": {
        "csrf": "$.token"
      }
    },
    {
      "method": "POST",
      "url": "https://example-saas.com/api/submit",
      "headers": {
        "X-CSRF-Token": "{{csrf}}"
      },
      "body": {
        "title": "{{title}}",
        "content": "{{content}}"
      },
      "extract": {
        "result_id": "$.data.id"
      }
    }
  ]
}
```

### Field reference

**Top-level fields:**

| Field         | Required | Description                                         |
| ------------- | -------- | --------------------------------------------------- |
| `site`        | yes      | Domain or identifier for the target site             |
| `description` | yes      | One-line description of what the adapter does        |
| `auth`        | no       | Authentication config (default: `{"type": "none"}`) |
| `steps`       | yes      | Array of HTTP request steps, executed in order       |

**Auth types:**

| Type             | Fields needed                              |
| ---------------- | ------------------------------------------ |
| `none`           | (nothing)                                  |
| `bearer_token`   | `source_env` -- env var holding the token  |
| `api_key`        | `source_env`, `header` (default X-API-Key) |
| `session_cookie` | `source_env` -- env var holding the cookie |
| `basic`          | `user_env`, `pass_env`                     |

**Step fields:**

| Field     | Required | Description                                              |
| --------- | -------- | -------------------------------------------------------- |
| `method`  | yes      | HTTP method (GET, POST, PUT, PATCH, DELETE, HEAD)        |
| `url`     | yes      | URL with optional `{{var}}` placeholders                 |
| `headers` | no       | Dict of HTTP headers, supports `{{var}}`                 |
| `body`    | no       | Request body (dict for JSON, string for raw)             |
| `extract` | no       | Dict mapping var names to JSONPath-like extraction paths |

### Variable interpolation

Use `{{variable_name}}` in URLs, headers, and body fields. Variables come from:

1. The `vars` dict passed by the caller
2. Values extracted from previous steps via `extract`
3. Environment variables (for auth)

### Extraction paths

Extraction uses simple dot/bracket notation:

- `$.token` -- top-level key
- `$.data.id` -- nested key
- `$.items[0].name` -- array index + key

Extracted values are added to the execution context and available to subsequent steps.

## Guidelines for creating adapters

1. **One adapter per workflow.** Don't try to put all of a site's functionality in one file.
2. **Name clearly.** Use `<site>_<action>.json`, e.g. `github_create_issue.json`.
3. **Document auth requirements.** If the adapter needs a token, say so in the description and list the env var.
4. **Test with validate first.** Run `validate_adapter` before `execute_adapter`.
5. **Keep secrets in env vars.** Never hardcode tokens or passwords in the adapter JSON.
6. **Handle CSRF.** If the site uses CSRF tokens, make the first step a GET that extracts the token, then use it in subsequent steps.

## When NOT to create an adapter

- The site uses heavy JS rendering and has no API endpoints (stay in browser lane)
- The workflow involves CAPTCHA solving
- The site changes its API frequently (adapter maintenance cost exceeds browser cost)
- One-time tasks that won't be repeated
