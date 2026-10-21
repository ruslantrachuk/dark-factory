# Dependency Detection Patterns

## Key Patterns

### Sequential within Category
Task X.2 ALWAYS blocks on X.1 by convention.

### Database → API
Database operations block API development.

### Config → Implementation
System setup must precede feature coding.

### Implementation → Tests
Tests are **parallel-compatible** work (NOT blocking). Use `related`, not `blocks`.

### Core → Polish
Enhancements depend on foundational functionality.

## Dependency Types

| Type | Meaning | Effect on `bd ready` |
|------|---------|---------------------|
| `blocks` | Cannot begin until prerequisite completes | **Hides from ready queue** |
| `related` | Parallel-compatible, shares context | No effect |
| `parent-child` | Hierarchical (epic → task) | No effect |
| `discovered-from` | Traceability for gap origin | No effect |

## Gap Detection Framework

| Missing element | When to detect | Priority |
|----------------|---------------|:--------:|
| Rollback plan | Migrations without rollback | P1 |
| Rate limiting | API endpoints without protection | P1 |
| Error handling | External integrations without resilience | P1 |
| Monitoring | Features without observability | P2 |
| Test coverage | Implementation without tests | P1 |
