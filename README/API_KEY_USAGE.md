# Using an API Key to Fetch Organizations for the Home Page

This short guide shows how to call the ShowWise API using an API key to retrieve organization data for a website home page.

1) Create a key in the UI
- Go to the `API Keys` page in the backend and use the "Quick: Generate Home Page Key" buttons to create a key labeled `home-page` for your instance. Copy the generated key (it starts with `sk_`).

2) Call the API to get all organizations
- Endpoint: `GET /api/organizations`
- Header: `X-API-Key: <YOUR_KEY>`

Example using curl:

```bash
curl -H "X-API-Key: sk_XXXXXXXXXXXXXXXXXXXXXXXXXXXX" \
  https://your-showwise-host.example.com/api/organizations
```

If your `settings.json` has `allow_public_read` disabled, an API key will be required. The response will be JSON similar to:

```json
{
  "success": true,
  "organizations": {
    "demo": {
      "name": "Demo Organization",
      "subdomain": "demo",
      "url": "https://demo.sfx-crew.com",
      ...
    }
  },
  "count": 1,
  "timestamp": "2026-02-19T..."
}
```

3) Fetch a single organization by slug (optional)

```bash
curl -H "X-API-Key: sk_XXXXXXXXXXXXXXXXXXXXXXXXXXXX" \
  https://your-showwise-host.example.com/api/organizations/demo
```

Notes
- Use HTTPS in production.
- Keep API keys secret; treat them like passwords.
- Cache the organizations JSON on your website to avoid frequent API calls.
- If you want the home page to fetch a single org by subdomain, use `/api/organizations/by-subdomain/<subdomain>`.
