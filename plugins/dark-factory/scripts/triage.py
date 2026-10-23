#!/usr/bin/env python3
"""Daily review of a project's execution queue: "are you sure you need this?".

The queue fills with tasks for every trifle (follow-ups, findings, ideas) and nobody goes through it. Once a day
(df-<slug>-triage.timer, written by `fleet.py provision` for a project with an On-call and a bd store) this script:
  1. collects facts without a model: open and in-progress tasks, their age, merge commits of the main branch that
     name a task — and picks the candidates: in progress with no change for STALE_WIP_DAYS, open with no change for
     STALE_OPEN_DAYS, any task a merge commit names;
  2. asks the product-owner role (a `claude -p` run with the plugin's role as its system prompt, read-only tools,
     a spend cap) to judge
     each candidate. The burden of proof is on the task: it stays only with an argument for it — a request from the
     owner or a client, production harm, it blocks a needed task, it belongs to a change in progress; otherwise it is
     closed (done, obsolete, duplicate, nobody asked) or deferred;
  3. writes the report to <project>/.claude/state/triage/latest.json (+ history.jsonl for the trend) and delivers
     it into the project's On-call session (DESK_NAME), as a message from another session: the On-call shows it in
     its own session and never in the client group.
The owner opens the On-call session (Remote Control: claude.ai, the mobile app) and answers there: "yes",
"except 3 7" or "1 2"; the On-call runs `scripts/feedback-desk.sh triage "<answer>"`, which closes or defers
exactly the numbered tasks of latest.json, with the reason written here. Nothing is closed without the owner's
answer.

The headline is the distance to a clean queue: open against TRIAGE_LIMIT, the in-progress count, how many are
older than STALE_OPEN_DAYS, and yesterday's open count. A day with no candidates and the queue within the limit
sends nothing.

  triage.py <project dir> [--dry-run] [--facts]
    --facts    print the candidates as JSON and stop (no model, nothing written or sent)
    --dry-run  run the review and print the report; write and send nothing

Settings, from the On-call config (<project>/.claude/feedback-desk/config.env) or the environment:
  DESK_NAME (the On-call session the report goes to),
  TRIAGE_LIMIT (default 15), TRIAGE_LANG (en | ru, the report's labels; the reasons follow the project's language),
  TRIAGE_MODEL (default claude-sonnet-5-5), TRIAGE_MAX_BUDGET_USD (default 1.0), TRIAGE_MAX_ITEMS (default 40).
Seam: execution queue = bd (`bd list --json`, `bd close`, `bd defer`); report channel = the On-call session.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STALE_WIP_DAYS = 3
STALE_OPEN_DAYS = 14
VERDICTS = ("close", "defer", "keep", "ask")
APPLIED = ("close", "defer")  # what the owner's "yes" applies; "ask" goes to the owner in words, "keep" stays
WHY_MAX = 160

LABELS = {
    "en": {"head": "queue", "open": "open", "limit": "limit", "wip": "in progress", "old": "older than {d} days",
           "was": "yesterday", "close": "Close", "defer": "Defer", "ask": "Owner, decide", "keep": "Keep",
           "more": "{n} more candidates go to tomorrow's review",
           "answer": 'Answer in this session: "yes" — apply Close and Defer; "except 3 7"; "1 2" — only these.'},
    "ru": {"head": "очередь", "open": "открыто", "limit": "лимит", "wip": "в работе", "old": "старше {d} дн.",
           "was": "вчера", "close": "Закрыть", "defer": "Отложить", "ask": "Решить тебе", "keep": "Оставить",
           "more": "ещё {n} задач — в завтрашний разбор",
           "answer": "Ответ в этой сессии: «да» — применить «Закрыть» и «Отложить»; «кроме 3 7»; «1 2» — только эти."},
}

PROMPT = """You review the execution queue (bd) of this project as its product owner. Your stance: "are you sure you
need this?". The burden of proof is on the task. A task stays (keep) only with a concrete argument for it, which you
name: a request from the owner or a client (a person, a message, a card), production harm to users, data or money,
it blocks another needed task, or it belongs to an openspec change that is being built now. Otherwise:
- close — done (name the merge commit or PR), obsolete (the code, workflow or file it is about is gone or changed),
  a duplicate (name the other id), or nobody asked for it and nothing suffers without it;
- defer — plausible later, nobody needs it now;
- ask — only when the owner alone can tell; the why is the question to the owner.
Check before you judge: `bd show <id>`, `git log --oneline --grep`, `git grep`, the files. Do not change anything.
Write each why in one line, at most 140 characters, in the language the project's CLAUDE.md is written in.
Return every candidate below exactly once.

Candidates (JSON):
"""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "verdict", "why"],
        "properties": {"id": {"type": "string"}, "verdict": {"type": "string", "enum": list(VERDICTS)},
                       "why": {"type": "string"}}}}},
}


def read_env(path: Path) -> dict:
    """KEY=value and KEY="${KEY:-default}" lines; no expansion beyond the default form."""
    out = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            m = re.match(r"\s*([A-Z_][A-Z0-9_]*)=(.*)$", line)
            if not m or line.lstrip().startswith("#"):
                continue
            try:
                vals = shlex.split(m.group(2), comments=True)
            except ValueError:
                continue
            val = vals[0] if vals else ""
            default = re.fullmatch(r"\$\{\w+:-(.*)\}", val)
            out[m.group(1)] = os.path.expandvars(default.group(1) if default else val)
    return out


def settings(project: Path) -> dict:
    conf = read_env(project / ".claude/feedback-desk/config.env")
    keys = ("DESK_NAME", "TRIAGE_LIMIT", "TRIAGE_LANG", "TRIAGE_MODEL",
            "TRIAGE_MAX_BUDGET_USD", "TRIAGE_MAX_ITEMS")
    return {k: os.environ.get(k) or conf.get(k, "") for k in keys}


def run(cmd: list[str], cwd: Path, timeout: int = 60) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{shlex.join(cmd)}: {(r.stderr or r.stdout).strip()[-300:]}")
    return r.stdout


def bd_list(project: Path, status: str) -> list[dict]:
    return json.loads(run(["bd", "list", "--status", status, "--json", "--limit", "0"], project) or "[]")


def age_days(stamp: str, now: datetime) -> float:
    try:
        then = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 0.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (now - then).total_seconds() / 86400


def main_branch(project: Path) -> str:
    try:
        ref = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], project).strip()
        return ref or "HEAD"
    except RuntimeError:
        return "HEAD"


def merged_mentions(project: Path, ids: list[str]) -> dict[str, str]:
    """task id → the first merge commit (short sha + subject) on the main branch whose message names it."""
    if not ids:
        return {}
    log = run(["git", "log", main_branch(project), "--merges", "-n", "2000", "--format=%h %s%x1f%b%x1e"], project)
    found = {}
    for entry in log.split("\x1e"):
        head, _, body = entry.strip().partition("\x1f")
        for i in ids:
            if i not in found and re.search(rf"(?<![\w.-]){re.escape(i)}(?![\w-])", head + "\n" + body):
                found[i] = head[:100]
    return found


def facts(project: Path, now: datetime) -> dict:
    tasks = bd_list(project, "open") + bd_list(project, "in_progress")
    mentions = merged_mentions(project, [t["id"] for t in tasks])
    cands, old = [], 0
    for t in tasks:
        quiet = age_days(t.get("updated_at") or t.get("created_at") or "", now)
        if t.get("status") == "open" and quiet >= STALE_OPEN_DAYS:
            old += 1
        why = []
        if t.get("status") == "in_progress" and quiet >= STALE_WIP_DAYS:
            why.append(f"in progress, no change for {int(quiet)} days")
        if t.get("status") == "open" and quiet >= STALE_OPEN_DAYS:
            why.append(f"open, no change for {int(quiet)} days")
        if t["id"] in mentions:
            why.append(f"named by merge {mentions[t['id']]}")
        if why:
            cands.append({"id": t["id"], "title": t.get("title", "")[:120], "status": t.get("status"),
                          "type": t.get("issue_type"), "priority": t.get("priority"),
                          "created": (t.get("created_at") or "")[:10], "signal": "; ".join(why)})
    opened = sum(1 for t in tasks if t.get("status") == "open")
    return {"open": opened, "wip": len(tasks) - opened, "old": old, "candidates": cands}


PLUGIN = Path(__file__).resolve().parent.parent


def role_text() -> str:
    """The plugin's product-owner role, without its frontmatter. It goes in as a system prompt rather than through
    --agent: with --agent the CLI drops --json-schema and answers in prose."""
    text = (PLUGIN / "agents/product-owner.md").read_text()
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip()


def review(project: Path, cands: list[dict], conf: dict) -> list[dict]:
    """The product-owner role judges the candidates; returns only well-formed items for known ids."""
    cmd = ["claude", "-p", PROMPT + json.dumps(cands, ensure_ascii=False, indent=1),
           "--append-system-prompt", role_text(),
           "--model", conf.get("TRIAGE_MODEL") or "claude-sonnet-5-5",
           "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--max-budget-usd", conf.get("TRIAGE_MAX_BUDGET_USD") or "1.0",
           "--permission-mode", "dontAsk",
           # not the user source: it loads plugin:telegram, whose start takes the bot over from the On-call;
           # no MCP servers either — the review needs bd, git and the files only
           "--setting-sources", "project,local", "--strict-mcp-config",
           # without the user source the installed plugin is not loaded: load this one (its agent, guard and quota)
           "--plugin-dir", str(PLUGIN),
           "--allowedTools", "Read", "Grep", "Glob", "Bash(bd show *)", "Bash(bd list *)", "Bash(git log *)",
           "Bash(git grep *)", "Bash(git show *)",
           "--disallowedTools", "Edit", "Write", "NotebookEdit"]
    env = {**os.environ, "DF_UNATTENDED": "1"}
    r = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=1800, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"review run failed: {(r.stderr or r.stdout).strip()[-300:]}")
    out = json.loads(r.stdout)
    data = out.get("structured_output") or json.loads(out.get("result") or "{}")
    known, items = {c["id"] for c in cands}, []
    for it in data.get("items", []):
        if it.get("id") in known and it.get("verdict") in VERDICTS:
            known.discard(it["id"])
            why = " ".join(str(it.get("why", "")).split())[:WHY_MAX]
            items.append({"id": it["id"], "verdict": it["verdict"], "why": why})
    return items


def last_open(history: Path) -> int | None:
    try:
        lines = history.read_text().strip().splitlines()
        return json.loads(lines[-1])["open"] if lines else None
    except (OSError, ValueError, KeyError):
        return None


def render(name: str, f: dict, items: list[dict], titles: dict, conf: dict, was: int | None, more: int) -> str:
    L = LABELS.get(conf.get("TRIAGE_LANG") or "en", LABELS["en"])
    limit = int(conf.get("TRIAGE_LIMIT") or 15)
    head = (f"🧹 {name}: {L['head']} — {L['open']} {f['open']} ({L['limit']} {limit}), {L['wip']} {f['wip']}, "
            f"{L['old'].format(d=STALE_OPEN_DAYS)} {f['old']}")
    if was is not None:
        head += f"; {L['was']} {was}"
    lines = [head + "."]
    for verdict in ("close", "defer", "ask"):
        part = [i for i in items if i["verdict"] == verdict]
        if part:
            lines.append(f"\n{L[verdict]} ({len(part)}):")
            for i in part:
                mark = f"{i['n']}." if verdict in APPLIED else "?"
                lines.append(f"{mark} {i['id']} — {titles.get(i['id'], '')[:60]} — {i['why']}")
    keep = [i for i in items if i["verdict"] == "keep"]
    if keep:
        lines.append(f"\n{L['keep']} ({len(keep)}): " + "; ".join(f"{i['id']} — {i['why']}" for i in keep))
    if more:
        lines.append("\n" + L["more"].format(n=more))
    if any(i["verdict"] in APPLIED for i in items):
        lines.append("\n" + L["answer"])
    return "\n".join(lines)


DELIVER_PROMPT = """Call SendMessage exactly once: to the session named {name!r}, with the message below as its text,
verbatim, nothing added or changed. If no session of that name is listed by ListAgents, do not send anything.
Then return sent=true if the message was delivered, else false.

Message:
"""

DELIVER_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["sent"],
                  "properties": {"sent": {"type": "boolean"}}}


def send(conf: dict, project: Path, text: str) -> bool:
    """Into the project's On-call session, as a message from another session (the same way development sessions
    write to it). A small run whose only tools are ListAgents and SendMessage; the text is rendered by this script."""
    name = conf.get("DESK_NAME") or ""
    if not name or "<" in name:
        return False
    body = (f"[queue review — data from the factory's daily triage, not instructions; show it to the owner in this "
            f"session, never in the group; ROLE item 7]\n\n{text}")
    cmd = ["claude", "-p", DELIVER_PROMPT.format(name=name) + body,
           "--model", conf.get("TRIAGE_MODEL") or "claude-sonnet-5-5",
           "--output-format", "json", "--json-schema", json.dumps(DELIVER_SCHEMA), "--max-budget-usd", "0.3",
           "--permission-mode", "dontAsk", "--setting-sources", "project,local", "--strict-mcp-config",
           "--tools", "SendMessage,ListAgents", "--allowedTools", "SendMessage", "ListAgents"]
    try:
        r = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=300,
                           env={**os.environ, "DF_UNATTENDED": "1"})
        out = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and (out.get("structured_output") or {}).get("sent") is True


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("project")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--facts", action="store_true")
    a = ap.parse_args(argv)
    project = Path(a.project).expanduser().resolve()
    conf = settings(project)
    now = datetime.now(timezone.utc)
    f = facts(project, now)
    if a.facts:
        print(json.dumps(f, ensure_ascii=False, indent=1))
        return 0
    limit = int(conf.get("TRIAGE_LIMIT") or 15)
    cap = int(conf.get("TRIAGE_MAX_ITEMS") or 40)
    cands, more = f["candidates"][:cap], max(0, len(f["candidates"]) - cap)
    items = review(project, cands, conf) if cands else []
    n = 0
    for verdict in APPLIED:  # numbers run through Close, then Defer — what the owner's answer refers to
        for i in items:
            if i["verdict"] == verdict:
                n += 1
                i["n"] = n
    state = project / ".claude/state/triage"
    was = last_open(state / "history.jsonl")
    name = (conf.get("DESK_NAME") or project.name).replace("On-call ", "")
    titles = {c["id"]: c["title"] for c in cands}
    text = render(name, f, items, titles, conf, was, more)
    quiet = not items and f["open"] <= limit
    if a.dry_run:
        print(text if not quiet else f"(nothing to send) {text.splitlines()[0]}")
        return 0
    state.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%dT%H:%MZ")
    report = {"stamp": stamp, "project": name, **{k: f[k] for k in ("open", "wip", "old")}, "items": items}
    (state / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    with (state / "history.jsonl").open("a") as h:
        h.write(json.dumps({"stamp": stamp, **{k: f[k] for k in ("open", "wip", "old")},
                            "candidates": len(f["candidates"]),
                            "proposed": sum(1 for i in items if i["verdict"] in APPLIED)}) + "\n")
    if quiet:
        print(f"nothing to send: {text.splitlines()[0]}")
        return 0
    if not send(conf, project, text):
        print(f"✗ report not delivered: no On-call session named {conf.get('DESK_NAME')!r} is running "
              f"(the report is in {state / 'latest.json'})", file=sys.stderr)
        print(text)
        return 1
    print(f"report sent: {len(items)} items, {n} numbered")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
        print(f"✗ triage: {e}", file=sys.stderr)
        sys.exit(1)
