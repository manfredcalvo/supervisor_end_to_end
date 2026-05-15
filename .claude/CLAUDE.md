# Supervisor Agent End-to-End — Context for Claude

## Project Overview

This is a production-ready, full-stack chatbot application built for **Databricks environments**. It demonstrates a complete end-to-end supervisor agent architecture: document ingestion → Knowledge Assistants → Multi-Agent Supervisor → chat UI.

**Key characteristics:**

- Monorepo architecture with npm workspaces
- Express.js backend + React frontend (Vite)
- PostgreSQL database (Databricks Lakebase autoscaling) with Drizzle ORM
- Vercel AI SDK for streaming responses
- Databricks-native authentication and deployment via Asset Bundles

## Architecture

### Monorepo Structure

```
supervisor_agent_end_to_end/
├── client/                 # React + Vite frontend
├── server/                 # Express backend
├── packages/
│   ├── core/              # Domain types, errors, schemas
│   ├── auth/              # Authentication utilities
│   ├── ai-sdk-providers/  # Databricks AI SDK integration
│   ├── db/                # Database layer (Drizzle ORM)
│   └── utils/             # Shared utilities
├── notebooks/             # Databricks pipeline notebooks (01–06)
├── notebooks/config/      # KA and Supervisor YAML configs
└── scripts/               # Utility scripts
```

**IMPORTANT**: This is an npm workspaces monorepo. When adding dependencies:

- Root dependencies: For build tools, linting, testing
- Workspace dependencies: Add to the specific package (client, server, or packages/\*)
- Use `npm install <package> --workspace=<workspace-name>` for workspace-specific deps

### Key Technologies

**Frontend:**

- React 18 with TypeScript 5.6
- Vite 5 (build tool and dev server)
- Tailwind CSS 4.1 + Radix UI components
- React Router v6
- Vercel AI SDK (`@ai-sdk/react`) for streaming

**Backend:**

- Express 5.1 with TypeScript
- Vercel AI SDK (`ai` package) for streaming responses
- Zod for schema validation
- Header-based authentication (expects reverse proxy)

**Database:**

- PostgreSQL 17 (Databricks Lakebase autoscaling)
- Drizzle ORM 0.44 with migrations
- Custom schema: `ai_chatbot`
- Tables: User, Chat, Message_v2

**Testing:**

- Playwright 1.50 for E2E tests
- MSW (Mock Service Worker) 2.11 for API mocking
- Test environment auto-detected via `PLAYWRIGHT=True`

**Code Quality:**

- Biome 1.9.4 for linting and formatting (NOT ESLint/Prettier)

---

## Essential Commands

### Development

```bash
npm install              # Install all workspace dependencies
npm run dev              # Start both client (3000) and server (3001)
npm run dev:server       # Server only
npm run dev:client       # Client only
```

### Building

```bash
npm run build            # Full build: DB migrate → client → server
npm run build:client     # Build client only (outputs to client/dist/)
npm run build:server     # Build server only (outputs to server/dist/)
```

### Database Operations

```bash
npm run db:generate      # Generate SQL migration files from schema changes
npm run db:migrate       # Run pending SQL migrations (PRODUCTION-SAFE)
npm run db:reset         # Reset database (DESTRUCTIVE - deletes all data)
npm run db:studio        # Open Drizzle Studio (visual DB editor)
npm run db:push          # Push schema directly (DEVELOPMENT ONLY - can be destructive)
npm run db:pull          # Pull schema from database
npm run db:check         # Check migration consistency
```

**IMPORTANT Migration Workflow:**
1. Modify `packages/db/src/schema.ts`
2. Run `npm run db:generate` to create SQL migration file
3. Review the generated SQL in `packages/db/migrations/`
4. Run `npm run db:migrate` to apply migrations
5. Commit both `schema.ts` and migration files

**⚠️ DO NOT use `db:push` in production** — it bypasses migrations and can drop data!

### Code Quality

```bash
npm run lint             # Lint with Biome (auto-fix enabled)
npm run lint:fix         # Lint + format
npm run format           # Format only
```

### Testing

```bash
npm test                              # Run all Playwright tests
npx playwright test --ui              # Interactive UI mode
npx playwright test --headed --project=e2e  # Browser visible
```

**Test projects:** `unit`, `e2e`, `routes`
**Test timeout:** 240 seconds

### Deployment (Databricks Asset Bundle)

```bash
databricks bundle validate             # Validate bundle config
databricks bundle deploy               # Deploy to dev (default)
databricks bundle deploy -t staging    # Deploy to staging
databricks bundle deploy -t prod       # Deploy to production
databricks bundle run databricks_chatbot  # Start the app
databricks bundle summary              # View deployment status
```

**Two-step deploy required on first run:**

1. `databricks bundle deploy` — creates the Lakebase project and wires up the app
2. After running the pipeline job, run `scripts/get_endpoints.py --profile <profile> --update` to populate endpoint variables, then `databricks bundle deploy` again

---

## Deployment Architecture

### Databricks Asset Bundle Resources (`databricks.yml`)

| Resource | Type | Description |
|---|---|---|
| `chatbot_lakebase` | `postgres_projects` | Lakebase autoscaling DB (PG 17) |
| `create_supervisor_agent` | `jobs` | Full pipeline job (ingest → KAs → Supervisor → eval → monitor) |
| `databricks_chatbot` | `apps` | Databricks App (React + Express) |

**App resource bindings:**

- `serving-endpoint` — Supervisor MAS endpoint (CAN_QUERY) → `DATABRICKS_SERVING_ENDPOINT`
- `ka-data-management-endpoint` — Data Management KA endpoint (CAN_QUERY)
- `ka-ai-analytics-endpoint` — AI & Analytics KA endpoint (CAN_QUERY)
- `mlflow-experiment` — MLflow experiment (CAN_MANAGE) → `MLFLOW_EXPERIMENT_ID`
- `database` — Lakebase postgres branch (CAN_CONNECT_AND_CREATE) → `LAKEBASE_ENDPOINT`

### Deployment Targets

- **dev** (default): user-scoped suffix (`dev-{username}`)
- **staging**: shared staging environment
- **prod**: production environment

### Key `databricks.yml` Variables

| Variable | Description |
|---|---|
| `serving_endpoint_name` | Supervisor MAS serving endpoint |
| `ka_data_management_endpoint` | Data Management KA endpoint |
| `ka_ai_analytics_endpoint` | AI & Analytics KA endpoint |
| `mlflow_experiment_id` | MLflow experiment ID |
| `catalog` / `schema` | Unity Catalog location |
| `data_management_volume_name` | Volume with Data Management PDFs |
| `ai_analytics_volume` | Volume with AI & Analytics PDFs |
| `vector_search_endpoint` | Vector Search endpoint name |

Use `scripts/get_endpoints.py --profile <profile> --update` to auto-populate endpoint variables after running the pipeline job.

---

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

---

## Code Style Guidelines

### Formatting Rules (Biome)

**IMPORTANT**: This project uses Biome, NOT ESLint or Prettier.

- **Indentation**: 2 spaces
- **Line width**: 80 characters
- **Quotes**: Single quotes for strings, double quotes for JSX attributes
- **Semicolons**: Always required
- **Trailing commas**: Always (all contexts)
- **Arrow parentheses**: Always include
- **Line endings**: LF (Unix)

### TypeScript Conventions

- **Strict mode**: Enabled
- **Target**: ES2022
- **Module**: ESNext with bundler resolution
- **Imports**: Use TypeScript path aliases for workspace packages:
  ```typescript
  import { something } from "@chat-template/core";
  import { auth } from "@chat-template/auth";
  import { db } from "@chat-template/db";
  ```

### Component Organization (React)

- Use functional components with hooks
- Place shared UI components in `client/src/components/ui/`
- Place app-specific components in `client/src/components/elements/`

### API Route Patterns (Express)

- All routes use Express Router
- Authentication middleware applied globally or per-route
- Error handling with `ChatSDKError` class
- Schema validation with Zod schemas
- Streaming responses use Vercel AI SDK utilities

---

## Database Patterns

### Schema Modifications

1. Modify `packages/db/src/schema.ts`
2. Run `npm run db:generate`
3. Review generated SQL in `packages/db/migrations/`
4. Run `npm run db:migrate`
5. Commit both `schema.ts` and migration files

**CRITICAL**: All tables are in the `ai_chatbot` schema, NOT the public schema (`pgSchema('ai_chatbot')` in `schema.ts:14`).

### Drizzle Configuration

Located at the project root in `drizzle.config.ts` — automatically detected by all `drizzle-kit` commands.

---

## Authentication

### How It Works

Header-based authentication — expects a reverse proxy to inject:

- `X-Forwarded-User` — User ID (required)
- `X-Forwarded-Email` — User email (optional)
- `X-Forwarded-Preferred-Username` — Display name (optional)

### Auth Middleware

- `authMiddleware` — Extracts session (doesn't reject)
- `requireAuth` — Returns 401 if no session
- `requireChatAccess` — Validates user owns the chat

### Local Development

Uses **Databricks CLI authentication** when `npm run dev` is running:

- Set `DATABRICKS_CONFIG_PROFILE` in `.env`
- Run `databricks auth login --profile <name>` first

---

## Testing Practices

```
tests/
├── e2e/              # Browser automation tests (Playwright)
├── routes/           # API endpoint tests
├── ai-sdk-provider/  # Unit tests for AI provider logic
├── api-mocking/      # MSW mock server setup
├── pages/            # Page object models
└── fixtures.ts       # Test fixtures (multi-user scenarios)
```

MSW automatically mocks Databricks API calls when `PLAYWRIGHT=True`.

---

## File Locations Reference

### Configuration Files

- `databricks.yml` — Databricks Asset Bundle config
- `app.yaml` — Databricks app runtime config (Node.js 20, build + migrate + start)
- `drizzle.config.ts` — Drizzle ORM and migration configuration
- `biome.jsonc` — Linting and formatting rules
- `playwright.config.ts` — Test configuration
- `tsconfig.json` — Root TypeScript config
- `.env.example` — Environment variable template
- `.databricksignore` — Excludes output/ PDFs from app deployment

### Important Code Paths

- `server/src/index.ts` — Express server entry point
- `server/src/routes/` — API route definitions
- `client/src/App.tsx` — React root component
- `packages/db/src/schema.ts` — Database schema
- `packages/db/src/queries.ts` — Database query helpers
- `packages/core/src/errors.ts` — Error definitions
- `packages/ai-sdk-providers/` — Databricks AI provider implementations
- `notebooks/config/` — KA and Supervisor YAML configs

### Scripts

- `scripts/get_endpoints.py` — Retrieves supervisor/KA endpoints and MLflow experiment ID after pipeline run; use `--update` to write to `databricks.yml`
- `scripts/lakebase-role-setup.py` — Creates Postgres role and grants permissions for the app service principal
- `scripts/scrape_databricks_docs.py` — Scrapes Databricks docs to generate PDFs for KA ingestion

---

## Known Limitations

- No support for image or other multimodal inputs.
- Supported auth methods: Databricks CLI (local dev) and service principal OAuth (production). PAT, Azure MSI, etc. are NOT supported.
- One database per app (fixed `ai_chatbot` schema). To share an instance across apps, update the schema name in `packages/db/src/schema.ts` and run `npm run db:generate`.

---

## Troubleshooting

**"Invalid access token"** — Re-authenticate: `databricks auth login`

**"reference does not exist"** — Update CLI: `brew upgrade databricks`

**"Resource not found" during deploy** — Use `databricks bundle summary` to inspect state, then `databricks bundle unbind <resource>` or `databricks bundle bind <resource>`.

**App fails with database errors** — Ensure Step 2 (first bundle deploy) ran before Step 4 (final deploy) so the Lakebase project exists and is wired up.

---

**Note for Claude**: This file is automatically loaded as context. Refer to these guidelines for commands, patterns, and conventions. Keep this file updated as the project evolves.
