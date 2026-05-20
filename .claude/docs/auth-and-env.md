# Authentication & Environment Variables

## How Authentication Works

Header-based authentication — expects a reverse proxy to inject:

- `X-Forwarded-User` — User ID (required)
- `X-Forwarded-Email` — User email (optional)
- `X-Forwarded-Preferred-Username` — Display name (optional)

## Auth Middleware

- `authMiddleware` — Extracts session (doesn't reject)
- `requireAuth` — Returns 401 if no session
- `requireChatAccess` — Validates user owns the chat

## Local Development

Uses **Databricks CLI authentication** when `npm run dev` is running:

- Set `DATABRICKS_CONFIG_PROFILE` in `.env`
- Run `databricks auth login --profile <name>` first

## Environment Variables

### Required for Local Development

```bash
DATABRICKS_CONFIG_PROFILE=your-profile-name
DATABRICKS_SERVING_ENDPOINT=your-supervisor-endpoint

# Optional: Lakebase for persistent chat history
PGHOST=your-lakebase-host
PGDATABASE=databricks_postgres
PGPORT=5432
```

### Production (Databricks Apps — injected automatically)

- `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` / `DATABRICKS_HOST` — Service principal OAuth
- `LAKEBASE_ENDPOINT` — Lakebase autoscaling endpoint path (from `database` resource binding)
- `MLFLOW_EXPERIMENT_ID` — MLflow experiment ID (from `mlflow-experiment` resource binding)
- `DATABRICKS_SERVING_ENDPOINT` — Supervisor endpoint name (from `serving-endpoint` resource binding)

## Supported Auth Methods

- Databricks CLI OAuth U2M (local dev)
- Service principal OAuth (production)

PAT, Azure MSI, etc. are **NOT** supported.
