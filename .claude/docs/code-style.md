# Code Style Guidelines

## Formatting Rules (Biome)

**IMPORTANT**: This project uses Biome, NOT ESLint or Prettier.

- **Indentation**: 2 spaces
- **Line width**: 80 characters
- **Quotes**: Single quotes for strings, double quotes for JSX attributes
- **Semicolons**: Always required
- **Trailing commas**: Always (all contexts)
- **Arrow parentheses**: Always include
- **Line endings**: LF (Unix)

## TypeScript Conventions

- **Strict mode**: Enabled
- **Target**: ES2022
- **Module**: ESNext with bundler resolution
- **Imports**: Use TypeScript path aliases for workspace packages:
  ```typescript
  import { something } from "@chat-template/core";
  import { auth } from "@chat-template/auth";
  import { db } from "@chat-template/db";
  ```

## Component Organization (React)

- Use functional components with hooks
- Place shared UI components in `client/src/components/ui/`
- Place app-specific components in `client/src/components/elements/`

## API Route Patterns (Express)

- All routes use Express Router
- Authentication middleware applied globally or per-route
- Error handling with `ChatSDKError` class
- Schema validation with Zod schemas
- Streaming responses use Vercel AI SDK utilities
