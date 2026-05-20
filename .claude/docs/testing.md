# Testing Practices

## Test Structure

```
tests/
├── e2e/              # Browser automation tests (Playwright)
├── routes/           # API endpoint tests
├── ai-sdk-provider/  # Unit tests for AI provider logic
├── api-mocking/      # MSW mock server setup
├── pages/            # Page object models
└── fixtures.ts       # Test fixtures (multi-user scenarios)
```

## Running Tests

```bash
npm test                              # Run all Playwright tests
npx playwright test --ui              # Interactive UI mode
npx playwright test --headed --project=e2e  # Browser visible
```

**Test projects:** `unit`, `e2e`, `routes`
**Test timeout:** 240 seconds

## Mocking

MSW automatically mocks Databricks API calls when `PLAYWRIGHT=True`. The test environment is auto-detected via this env var — no manual setup needed.
