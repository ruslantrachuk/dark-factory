# Canon modules — what else can be installed on top of base

The project was deployed from the dark-factory plugin's `templates/base`. Besides base, the plugin has **optional modules**:
each solves one problem and is installed when the project has that problem. Module files are not copied into the project at
deployment (except `release` when the project has production); they are copied at setup, by `/dark-factory:add <module>`. Here — what exists and when it is time.

The catalog is a canon file: a new module or a change to an existing one reaches the project via `scripts/harness-diff.sh`
(status "canon moved ahead"). The project's installed modules are listed in the factory's registry, column "Contents".

| Module (`/dark-factory:add …`) | What it gives | When it is time to install | How to install |
|---|---|---|---|
| `feature-pipeline` | Workflow scripts the development session launches: one bd task from a spec or an OpenSpec phase to a committed, reviewed branch (plan, critic, parallel build, review, full gates, the PR description); stops before the PR | Features are planned as OpenSpec phases or specs with bd tasks, and building them by hand in the session takes most of the owner's attention | `/dark-factory:add feature-pipeline` |
| `release` (`release-tag`) | Prod is rolled out only by tag (`vYYYY.MM.DD.N`), not by a merge into the main branch | The project has a production deploy (it comes with base when the owner said so) | `/dark-factory:add release` |
| `on-call` (`feedback-desk`) | An On-call agent for the client's Telegram group: receives messages, forwards them to the development session, replies to the group | The client or a reviewer looks at the preview and writes remarks in Telegram rather than in the tracker | `/dark-factory:add on-call`; the bot, token and pairing are done by the owner |
| `observability` | Business metrics, dashboard as code, alert catalog, log-based investigation | The project has a prod with live users | `/dark-factory:add observability` |
| `monitor` (`prod-monitor`) | Agent-based prod monitoring: a model-free watchdog every minute; an agent on the Claude Agent SDK only reads (DB, hosting, logs, release) and writes to the group via the On-call agent about a real outage | Prod with live users, the On-call agent is already installed, and outages are learned about from users | `/dark-factory:add monitor`; the read-only DB role and the subscription token — the owner |
| `code-audit` | Fan-out code audit across many repositories with evidence and spot checks | The project is an audit of someone else's system (due diligence, presale) or a full review of your own spanning many repos is needed | `/dark-factory:add code-audit`; the method is the `code-audit` skill from base |

## Rules

- A module is installed **by the owner's decision**, not on the agent's initiative: you saw a "time to install" sign — propose it with
  a link to the table row, do not install it.
- `/dark-factory:add <module>` follows the module's `MANIFEST.md` ("Setup by /dark-factory:add") from the installed plugin — no clone needed —
  and the install is recorded in the PR description and in the factory's registry, if there is one.
- A deviation from a module found in a project is a reason to bring it into the canon during a review pass, not a silent local edit.
