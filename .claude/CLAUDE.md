# Supervisor Agent End-to-End — Context for Claude

## Project Overview

Production-ready full-stack chatbot for **Databricks environments**. Architecture: document ingestion → Knowledge Assistants → Multi-Agent Supervisor → chat UI. Monorepo (npm workspaces) with an Express.js backend, React/Vite frontend, Databricks Lakebase (PostgreSQL) via Drizzle ORM, and Vercel AI SDK for streaming.

Full architecture & file map: @.claude/docs/architecture.md

---

## Key Commands

```bash
npm run dev              # Start client (3000) + server (3001)
npm run build            # DB migrate → build client → build server
npm run lint             # Biome lint + auto-fix
databricks bundle deploy # Deploy to dev
databricks bundle run databricks_chatbot  # Start the app
```

Full command reference: @.claude/docs/commands.md

---

## Global Rules

- **Formatter/Linter**: Biome only — NOT ESLint or Prettier. Full style guide: @.claude/docs/code-style.md
- **Database migrations**: always `db:generate` → review SQL → `db:migrate` → commit both files. Never `db:push` in production. Details: @.claude/docs/database.md
- **Auth**: header-based in production (reverse proxy injects `X-Forwarded-*`); Databricks CLI OAuth for local dev. Details: @.claude/docs/auth-and-env.md
- **Dependencies**: use `npm install <pkg> --workspace=<name>` for workspace-specific packages.

---

## Deployment

Databricks Asset Bundle (`databricks.yml`). Two-step first deploy: `bundle deploy` → run pipeline job → `get_endpoints.py --update` → `bundle deploy` again.

Full deployment details: @.claude/docs/deployment.md

---

## Reference Docs

- Architecture & file map: @.claude/docs/architecture.md
- All commands: @.claude/docs/commands.md
- Deployment (DAB resources, targets, variables): @.claude/docs/deployment.md
- Database patterns & migration workflow: @.claude/docs/database.md
- Auth & environment variables: @.claude/docs/auth-and-env.md
- Code style (Biome, TypeScript, React, Express): @.claude/docs/code-style.md
- Testing (Playwright, MSW): @.claude/docs/testing.md
- Known limitations & troubleshooting: @.claude/docs/troubleshooting.md

---

**Note for Claude**: This file is automatically loaded as context. Use the `@` references above to load detailed docs only when relevant to the current task. Keep this file updated as the project evolves.
