# Canon modules — what else can be installed on top of base

The project was deployed from `dark-factory/templates/base`. Besides base, the canon has **optional modules**:
each solves one problem and is installed when the project has that problem. Module files are not copied into the project at
deployment; they are copied at setup. Here — what exists and when it is time.

The catalog is a canon file: a new module or a change to an existing one reaches the project via `scripts/harness-diff.sh`
(status "canon moved ahead"). The project's installed modules are listed in the factory's registry, column "Contents".

| Module | What it gives | When it is time to install | How to install |
|---|---|---|---|
| `night-local` | An autonomous night: task queue engine, watchdog, operator CLI, runbook. Mac or VPS, no corporate perimeter | The task queue in bd is labelled and specs exist, but development only happens while a human is present | `templates/night-local/MANIFEST.md`, its own pilot order |
| `release-tag` | Prod is rolled out only by tag, not by a merge into the main branch | The hosting builds prod from a branch: every push rebuilds prod | `templates/release-tag/MANIFEST.md`, §Setup |
| `feedback-desk` | An On-call agent for the client's Telegram group: receives messages, forwards them to the development session, replies to the group | The client or a reviewer looks at the stand and writes remarks in Telegram rather than in the tracker | The module's `feedback-desk` skill, section A; the bot, token and pairing are done by the owner |
| `observability` | Business metrics, dashboard as code, alert catalog, log-based investigation | The project has a prod with live users | `templates/observability/MANIFEST.md`, §Setup |
| `prod-monitor` | Agent-based prod monitoring: a model-free watchdog every minute; an agent on the Claude Agent SDK only reads (DB, hosting, logs, release) and writes to the group via the On-call agent about a real outage | Prod with live users, the On-call agent (feedback-desk) is already installed, and outages are learned about from users | `templates/prod-monitor/MANIFEST.md`, §Setup; the module's `prod-monitor` skill; subscription token and DB access — the owner |
| `code-audit` | Fan-out code audit across many repositories with evidence and spot checks | The project is an audit of someone else's system (due diligence, presale) or a full review of your own spanning many repos is needed | `templates/code-audit/MANIFEST.md`, §Setup; the method is the `code-audit` skill from base |

## Rules

- A module is installed **by the owner's decision**, not on the agent's initiative: you saw a "time to install" sign — propose it with
  a link to the table row, do not install it.
- Setup follows the module's `MANIFEST.md` in a clone of the canon (`../dark-factory` or `$DARK_FACTORY_DIR`), with an entry
  in the project's devlog and in the factory's registry.
- A deviation from a module found in a project is a reason to bring it into the canon during a review pass, not a silent local edit.
