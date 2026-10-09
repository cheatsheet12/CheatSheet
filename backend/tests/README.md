# backend/tests

Mirrors the structure of `backend/src/cheatsheet/`, so a test sits where its subject
does:

```
tests/
├── contexts/<context>/{domain,application,infrastructure}/
├── shared/
└── api/
```

Rules ([`../../docs/code-standards.md`](../../docs/code-standards.md) §4):

- **No test touches the network.** ARCA, MercadoPago, WhatsApp, Google Sheets and the
  LLM are always faked or mocked. A test hitting AFIP homologation is not a test, it is
  a source of flaky failures.
- Domain tests need no fixtures beyond the aggregate itself — that is the point of
  keeping the domain free of I/O (R1).
- Date and time are injected, never read from the clock inside business logic.
- Minimum coverage 80%, gated in CI. Lowering the threshold is forbidden.
- Naming: `test_<what>_<condition>_<expected>()`.

Every fixed bug starts with the test that reproduces it.

To run the whole CI pipeline locally (PostgreSQL, Redis, RLS checks, coverage, frontend)
see [`../scripts/local_ci/README.md`](../scripts/local_ci/README.md) and
[ADR-0016](../../docs/adr/0016-local-ci-verification.md).
