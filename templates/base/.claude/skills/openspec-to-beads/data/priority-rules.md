# Priority & Type Detection Rules

## Priority Logic

### P0 — Infrastructure / Blockers
Infrastructure/setup tasks, migrations, schema, config, database setup, environment configuration.

**Examples:**
- "Setup PostgreSQL users table"
- "Create database migration"
- "Configure Redis connection"

### P1 — Core Work
Core business logic, implementation tasks, tests, documentation, API endpoints, service layer logic.

**Examples:**
- "Implement JWT validation"
- "Add transaction import API"
- "Write integration tests"
- "Document API endpoints"

### P2 — Polish / Nice-to-haves
UI polish, optional enhancements, non-critical documentation.

**Examples:**
- "Add loading animation"
- "Improve error messages"
- "Add tooltip explanations"

## Type Detection

| Keywords in task | Beads type |
|-----------------|:----------:|
| setup, configure, install, refactor, improve, optimize, test, validate | `task` |
| implement, add, create, new functionality | `feature` |
| document, update docs, cleanup, remove deprecated | `chore` |
| Parent container for multiple related tasks | `epic` |

## Complexity Labels

| Level | Criteria |
|-------|---------|
| `complexity:low` | Straightforward tasks with clear steps |
| `complexity:medium` | Standard development, design decisions needed |
| `complexity:high` | Architectural changes, cross-cutting, high risk |

## Priority Adjustments

**Increase by 1** if task mentions: "urgent", "critical", "blocking", "security"

**Decrease by 1** if task mentions: "nice-to-have", "future", "optional", "enhancement"
