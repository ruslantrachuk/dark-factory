# Conversion Workflow Examples

## Example 1: Feature — Add Authentication

### Input: OpenSpec change `add-auth`

```
specs/add-auth/
├── proposal.md   # JWT auth for REST API
├── specs/        # Token lifecycle, refresh, revocation
├── design.md     # PostgreSQL + Redis, middleware pattern
└── tasks.md      # 6 implementation tasks
```

### Conversion Analysis

- **Scope:** 3 systems (DB, API middleware, token service)
- **Gaps detected:** JWT refresh rotation, auth metrics monitoring
- **Dependencies:** DB schema → middleware → refresh logic

### Output: 8 Beads Issues

```bash
# Epic
bd create "[EPIC] add-auth: JWT Authentication" \
  --type epic --priority 0 \
  --labels "spec:add-auth,epic,openspec" --json
# → bd-42

# P0 — Infrastructure (3 issues)
bd create "[add-auth] DB: Create users and tokens tables" \
  --priority 0 --type task \
  --labels "spec:add-auth,category:db,complexity:medium" --json
# → bd-43

bd create "[add-auth] Config: JWT secret and Redis connection" \
  --priority 0 --type task \
  --labels "spec:add-auth,category:config,complexity:low" --json
# → bd-44

bd create "[add-auth] DB: Token migration with rollback" \
  --priority 0 --type task \
  --labels "spec:add-auth,category:db,complexity:medium" --json
# → bd-45

# P1 — Implementation (4 issues)
bd create "[add-auth] API: JWT validation middleware" \
  --priority 1 --type feature \
  --labels "spec:add-auth,category:api,complexity:medium" --json
# → bd-46

bd create "[add-auth] Service: Refresh token rotation" \
  --priority 1 --type feature \
  --labels "spec:add-auth,category:service,complexity:high" --json
# → bd-47

bd create "[add-auth] Tests: Auth integration tests" \
  --priority 1 --type task \
  --labels "spec:add-auth,category:test,complexity:medium" --json
# → bd-48

# P1 — Discovery
bd create "[add-auth] DISCOVERED: Auth metrics monitoring" \
  --priority 1 --type task \
  --labels "spec:add-auth,discovered,proactive" --json
# → bd-49

# Dependencies
bd dep add bd-42 bd-43 --type parent-child  # epic → db
bd dep add bd-46 bd-43 --type blocks        # middleware needs DB
bd dep add bd-46 bd-44 --type blocks        # middleware needs config
bd dep add bd-47 bd-43 --type blocks        # refresh needs DB
bd dep add bd-48 bd-46 --type related       # tests parallel to impl
bd dep add bd-49 bd-46 --type discovered-from
```

### Result

```
bd ready
# → bd-43 [add-auth] DB: Create users and tokens tables (P0)
# → bd-44 [add-auth] Config: JWT secret and Redis connection (P0)
```

Two tasks unblocked, ready to start in parallel.

---

## Example 2: Bug Fix — Duplicate Transactions

### Input: OpenSpec change `duplicate-transaction-fix`

### Output: 4 Beads Issues

```bash
# P0 — Critical
bd create "[dup-fix] Test: Reproduce duplicate transaction bug" \
  --priority 0 --type task \
  --labels "spec:dup-fix,category:test,complexity:low" --json
# → bd-120

bd create "[dup-fix] DB: Add unique constraint on transactions" \
  --priority 0 --type task \
  --labels "spec:dup-fix,category:db,complexity:medium" --json
# → bd-121

# P1 — Implementation
bd create "[dup-fix] API: Idempotency key validation" \
  --priority 1 --type feature \
  --labels "spec:dup-fix,category:api,complexity:medium" --json
# → bd-122

# P1 — Discovery
bd create "[dup-fix] DISCOVERED: Duplicate detection logging" \
  --priority 1 --type task \
  --labels "spec:dup-fix,discovered,proactive" --json
# → bd-123

# Dependencies
bd dep add bd-121 bd-120 --type blocks     # fix after repro
bd dep add bd-122 bd-121 --type blocks     # API after DB
bd dep add bd-123 bd-122 --type discovered-from
```

### Result

```
bd ready
# → bd-120 [dup-fix] Test: Reproduce duplicate transaction bug (P0)
```

One task ready — start with reproducing the bug.
