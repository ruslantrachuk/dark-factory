# <Project> tests

Policy and shares — [CODING_STANDARDS §Test pyramid](../../CODING_STANDARDS.md). This page covers
where things live and how to run them.

## Layer = directory

| Directory | Marker | What it checks |
|---|---|---|
| `unit/` | `unit` | pure rules: no database, file writes, network or client |
| `integration/` | `integration` | service on a live dependency: database, files, local server |
| `api/` | `api` | HTTP through the test client: roles, status codes, response shape |
| `e2e/` | `e2e` | browser against a running preview — release gate, not per-PR |

The layer marker is set by `conftest.py` from the directory — nobody writes it by hand. The meta-test
`unit/test_layers.py` collects a real run and guards that every test lives in a layer directory, has
exactly one layer, and that unit tests do not use file-writing fixtures or project fixtures from `FORBIDDEN_IN_UNIT`.

The `e2e/` directory is collected only when playwright is installed (the e2e dependency group): without
it a regular run does not see the directory and does not fail on import.

## Commands

From `app/`, inside the project environment (`<project environment command, e.g.: source .venv/bin/activate>`):

```bash
python -m pytest tests -q -m "not e2e"            # unit + integration + api
python -m pytest tests -q -m unit                 # the base only
python -m pytest tests/e2e -m e2e                 # end-to-end scenarios (need playwright and chromium)
python -m tests.e2e.make_screenshots              # user-guide screenshots + manifest
```

From the project root:

```bash
app/.venv/bin/python scripts/pyramid.py           # layer shares (with Vitest if app/frontend exists)
app/.venv/bin/python scripts/pyramid.py --ratchet # unit share has not dropped vs .harness/pyramid-baseline.json
python3 scripts/check_doc_links.py                # links and images in docs/user-guide/
```

User-guide screenshots are never taken by hand: only `make_screenshots` on synthetic data — it also
rewrites `docs/user-guide/screenshot-manifest.json`, and `unit/test_user_guide.py` checks the hashes.
