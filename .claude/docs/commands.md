# Essential Commands

## Development

```bash
npm install              # Install all workspace dependencies
npm run dev              # Start both client (3000) and server (3001)
npm run dev:server       # Server only
npm run dev:client       # Client only
```

## Building

```bash
npm run build            # Full build: DB migrate → client → server
npm run build:client     # Build client only (outputs to client/dist/)
npm run build:server     # Build server only (outputs to server/dist/)
```

## Database Operations

```bash
npm run db:generate      # Generate SQL migration files from schema changes
npm run db:migrate       # Run pending SQL migrations (PRODUCTION-SAFE)
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

## Code Quality

```bash
npm run lint             # Lint with Biome (auto-fix enabled)
npm run lint:fix         # Lint + format
npm run format           # Format only
```

## Testing

```bash
npm test                              # Run all Playwright tests
npx playwright test --ui              # Interactive UI mode
npx playwright test --headed --project=e2e  # Browser visible
```

**Test projects:** `unit`, `e2e`, `routes`
**Test timeout:** 240 seconds

## Deployment (Databricks Asset Bundle)

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
