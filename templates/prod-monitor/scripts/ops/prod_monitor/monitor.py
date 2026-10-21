"""Prod monitor — an agent on the Claude Agent SDK (subscription, token from `claude setup-token`).

Read-only: prod DB (fixed queries project.CHECKS), hosting (MCP, read-only), gh (releases),
HTTP probe. Fixes nothing. The ok/warn/crit verdict goes to the On-call "monitor" channel (`deliver`);
ok after crit is "resolved" (fixed), ok after ok goes nowhere (the On-call agent does not spend a turn).

    python -m prod_monitor.monitor [--trigger '<json from the watchdog>'] [--test-delivery]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from . import project
from .checks import read_only_connection
from .deliver import deliver
from .envfile import read_env_file
from .verdict import parse_verdict, plan

HERE = Path(__file__).resolve().parent
LAST_VERDICT = project.STATE_DIR / "monitor_last.json"
DEDUP_STATE = project.STATE_DIR / "monitor_sent.json"  # what has already gone to the group (verdict.plan)


def _text(payload: object) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, default=str, ensure_ascii=False)}]
    }


@tool(
    "db_check",
    f"Read-only prod DB check. name one of: {', '.join(project.CHECKS)}",
    {"name": str},
)
async def db_check(args: dict) -> dict:
    sql = project.CHECKS.get(args["name"])
    if sql is None:
        return _text({"error": f"unknown check, use one of {list(project.CHECKS)}"})
    with read_only_connection() as conn:
        now = conn.execute("select now() t").fetchone()["t"]
        return _text({"now_utc": now, "rows": conn.execute(sql).fetchall()})


@tool(
    "http_probe",
    "GET a prod path from this server, e.g. /health/ready. Timeout = server network OR prod down.",
    {"path": str},
)
async def http_probe(args: dict) -> dict:
    started = time.monotonic()
    url = project.PROD_URL + args["path"]
    done = subprocess.run(
        ["curl", "-s", "-m", "10", "-o", "/dev/null", "-w", "%{http_code}", url],
        capture_output=True,
        text=True,
    )
    return _text({"http_code": done.stdout, "seconds": round(time.monotonic() - started, 1)})


@tool("gh_release_status", "Latest GitHub releases and last runs of the release workflow.", {})
async def gh_release_status(args: dict) -> dict:
    def run(*cmd: str) -> str:
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=project.REPO, timeout=60
        ).stdout

    wf = project.RELEASE_WORKFLOW
    return _text(
        {
            "releases": run("gh", "release", "list", "-L", "3"),
            "release_runs": run("gh", "run", "list", "-w", wf, "-L", "3") if wf else "",
        }
    )


VERDICT_FORMAT = """
Catalogue of known incidents (check against it, name incidents by name, suggest the step from it):
{incidents}

Final answer — ONLY JSON without markdown:
{{"status": "ok|warn|crit", "findings": [{{"severity": "info|warn|crit", "key": "short_stable_problem_name", "what": "...", "evidence": "...", "next_step": "..."}}],
 "message_for_group": "2–5 lines of plain text in {language}, no markdown; only if status is warn/crit, otherwise an empty string"}}
crit — users are suffering right now (the product or its key function is down). warn — a real degradation already
visible in the data (not a "risk", not "may happen"). ok — everything else, including the known background from the catalogue.
key — the same short name for the same problem from pass to pass: it keeps the group from getting repeats.
People read the group: write a message only about a real outage, never "all good" and never about risks."""

PROD_TOOLS = ["mcp__prod__db_check", "mcp__prod__http_probe", "mcp__prod__gh_release_status"]


def _options() -> ClaudeAgentOptions:
    env = {}
    token = read_env_file(project.TOKEN_FILE).get("CLAUDE_CODE_OAUTH_TOKEN")
    if token:  # otherwise — the current Claude Code login on the machine
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    incidents = (HERE / "incidents.md").read_text()
    verdict_format = VERDICT_FORMAT.format(incidents=incidents, language=project.LANGUAGE)
    return ClaudeAgentOptions(
        system_prompt=project.PROMPT + verdict_format,
        model=project.MODEL,
        tools=[],  # no built-in Bash/Edit/Write
        mcp_servers={
            "prod": create_sdk_mcp_server("prod", tools=[db_check, http_probe, gh_release_status])
        },
        # local only (the hosting MCP is there). The user source enables plugin:telegram, which on start kills
        # the reader of the bot token — that is, the On-call agent. Project hooks (quota watchdog) are not
        # loaded either: the monitor is called rarely, and with an exhausted quota the watchdog alerts without a model.
        setting_sources=["local"],
        allowed_tools=project.HOSTING_READ + PROD_TOOLS,
        disallowed_tools=project.HOSTING_WRITE,
        permission_mode="dontAsk",
        max_turns=25,
        cwd=str(project.REPO),  # the agent has no built-in file tools
        env=env,
    )


async def _ask(trigger: dict | None) -> tuple[str | None, str]:
    prompt = f"Check prod of {project.PROJECT} now."
    if trigger:
        seen = trigger.get("anomalies") or "nothing"
        prompt += f"\nWhy you were woken: {trigger.get('reason')}. The watchdog sees: {seen}."
    started, result, stats = time.monotonic(), None, ""
    async for msg in query(prompt=prompt, options=_options()):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    args = json.dumps(block.input, ensure_ascii=False)[:120]
                    print(f"  → {block.name} {args}", flush=True)
        elif isinstance(msg, ResultMessage):
            result = msg.result
            took = time.monotonic() - started
            stats = f"{msg.subtype} {took:.0f}s turns={msg.num_turns} cost=${msg.total_cost_usd}"
    return result, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", default="")
    parser.add_argument("--test-delivery", action="store_true")
    args = parser.parse_args()
    if args.test_delivery:
        text = "Monitor: delivery check through the channel, no action needed."
        print("delivery:", deliver("test", text))
        return 0

    result, stats = asyncio.run(_ask(json.loads(args.trigger) if args.trigger else None))
    print(f"== {stats}\n{result}", flush=True)
    verdict = parse_verdict(result)
    if verdict is None:
        return 1  # the watchdog sends the alert itself if it sees anomalies

    try:
        state = json.loads(DEDUP_STATE.read_text())
    except (OSError, ValueError):
        state = {}
    project.STATE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_VERDICT.write_text(json.dumps(verdict, ensure_ascii=False, indent=1))

    status, new_state = plan(verdict, state, datetime.now(UTC))
    if status:
        text = verdict.get("message_for_group") or "(empty)"
        where = deliver(status, text, verdict.get("findings"))
        print("delivery:", where)
        if where not in {"channel", "direct"}:
            return 0  # not delivered — keep the state, the next pass will try again
    DEDUP_STATE.write_text(json.dumps(new_state, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
