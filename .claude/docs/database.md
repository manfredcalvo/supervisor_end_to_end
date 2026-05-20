# Database Patterns

## Schema Modifications

1. Modify `packages/db/src/schema.ts`
2. Run `npm run db:generate`
3. Review generated SQL in `packages/db/migrations/`
4. Run `npm run db:migrate`
5. Commit both `schema.ts` and migration files

**CRITICAL**: All tables are in the `ai_chatbot` schema, NOT the public schema (`pgSchema('ai_chatbot')` in `schema.ts:14`).

## Drizzle Configuration

Located at the project root in `drizzle.config.ts` — automatically detected by all `drizzle-kit` commands.

## Migration Script

`scripts/migrate.ts` handles auth before running migrations:
- Loads `.env` via dotenv
- Calls `getConnectionUrl()` from `@chat-template/db` (fetches Databricks token as PG password)
- Creates the `ai_chatbot` schema if it doesn't exist
- Runs all pending SQL migrations from `packages/db/migrations/`

**⚠️ DO NOT use `db:push` in production** — it bypasses migrations and can drop data!
