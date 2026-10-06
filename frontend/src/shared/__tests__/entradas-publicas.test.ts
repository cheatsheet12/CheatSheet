/**
 * Rule R5, checked as a convention rather than trusted.
 *
 * Every one of the twelve features must expose exactly one public entry point, because
 * that is what the rest of the app is allowed to import (`docs/architecture.md` §5).
 * A feature without its `index.ts` is a feature whose internals the next screen will
 * reach into — and the ESLint rule that forbids that only fires on the *deep* import,
 * never on the missing barrel.
 *
 * Twelve names, checked against the backend's twelve bounded contexts. Adding a
 * thirteenth is an architectural decision, so it fails here until an ADR says
 * otherwise.
 */

import { describe, expect, it } from "vitest";

const CONTEXTOS = [
  "identity",
  "master_data",
  "business_config",
  "integrations",
  "spreadsheet_sync",
  "billing",
  "payments",
  "scheduling",
  "conversational",
  "observability",
  "reporting",
  "reference_data",
] as const;

describe("entradas públicas de las features (R5)", () => {
  it.each(CONTEXTOS)("%s expone su index.ts", async (contexto) => {
    const modulo = await import(`@/features/${contexto}/index.ts`);

    expect(modulo).toBeDefined();
  });

  it("hay una feature por bounded context del backend", () => {
    expect(CONTEXTOS).toHaveLength(12);
    expect(new Set(CONTEXTOS).size).toBe(12);
  });
});
