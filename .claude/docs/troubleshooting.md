# Known Limitations & Troubleshooting

## Known Limitations

- No support for image or other multimodal inputs.
- Supported auth methods: Databricks CLI (local dev) and service principal OAuth (production). PAT, Azure MSI, etc. are NOT supported.
- One database per app (fixed `ai_chatbot` schema). To share an instance across apps, update the schema name in `packages/db/src/schema.ts` and run `npm run db:generate`.

## Troubleshooting

**"Invalid access token"** — Re-authenticate: `databricks auth login`

**"reference does not exist"** — Update CLI: `brew upgrade databricks`

**"Resource not found" during deploy** — Use `databricks bundle summary` to inspect state, then `databricks bundle unbind <resource>` or `databricks bundle bind <resource>`.

**App fails with database errors** — Ensure the first `databricks bundle deploy` ran before the final deploy so the Lakebase project exists and is wired up.
