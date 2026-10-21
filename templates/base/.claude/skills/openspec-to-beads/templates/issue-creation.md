# Issue Creation Templates

## Basic Issue

```bash
bd create "[<change>] <category>: <task-description>" \
  --priority <smart-priority> \
  --type <smart-type> \
  --labels "spec:<change>,category:<category-slug>,complexity:<low|medium|high>" \
  --json
```

**Fields:**
- `<change>` — OpenSpec change name (e.g., `add-auth`)
- `<category>` — Functional area (DB, API, Config, Service, Test, Docs)
- `<smart-priority>` — See priority-rules.md (0-4)
- `<smart-type>` — See type detection rules (`task`, `feature`, `chore`, `epic`)

## Epic Issue

```bash
bd create "[EPIC] <change-name>" \
  --type epic \
  --priority 0 \
  --labels "spec:<change>,epic,openspec" \
  --json
```

Always create one epic per OpenSpec change as a parent container.

## Discovery Issue

```bash
bd create "[<change>] DISCOVERED: <gap-description>" \
  --type task \
  --priority 1 \
  --labels "spec:<change>,discovered,proactive" \
  --json
```

Link to the task where the gap was found:
```bash
bd dep add <discovery-id> <source-task-id> --type discovered-from
```

## Dependency Templates

### Sequential (blocks)
```bash
bd dep add <child-id> <parent-id> --type blocks
```

### Cross-category (blocks)
```bash
bd dep add <api-task-id> <db-task-id> --type blocks
```

### Parallel work (related)
```bash
bd dep add <test-task-id> <feature-task-id> --type related
```

### Epic hierarchy (parent-child)
```bash
bd dep add <epic-id> <task-id> --type parent-child
```
