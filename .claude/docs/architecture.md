# Architecture

## Monorepo Structure

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

## Key Technologies

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
