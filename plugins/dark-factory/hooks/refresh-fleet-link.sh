#!/usr/bin/env bash
# Keeps the fleet's plugin symlink current (dark-factory plugin, SessionStart).
#
# The server units (fleet.py provision) call fleet.py through ~/.local/share/dark-factory/plugin, because an installed
# plugin lives in a per-version directory that /plugin update leaves behind. Here: if that link exists and points
# elsewhere, repoint it at this plugin — unless the link's plugin is newer: projects on one server may pin different
# versions, and a session of an older one must not take the server units back to its version. Never creates the link
# (machines without the fleet stay untouched). Silent, fast, always exit 0.
link="${FLEET_PLUGIN_LINK:-$HOME/.local/share/dark-factory/plugin}"
root="${CLAUDE_PLUGIN_ROOT:-}"
[ -n "$root" ] && [ -L "$link" ] || exit 0
target="$(readlink "$link" 2>/dev/null)"
[ "$target" = "$root" ] && exit 0
version() { sed -n 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1/.claude-plugin/plugin.json" 2>/dev/null | head -n 1; }
ours="$(version "$root")" theirs="$(version "$target")"
# a dangling link or one without a readable version is repointed; ours unreadable → leave a working link alone
if [ -n "$theirs" ]; then
  [ -n "$ours" ] || exit 0
  [ "$(printf '%s\n%s\n' "$ours" "$theirs" | sort -V | tail -n 1)" = "$ours" ] || exit 0
fi
ln -sfn "$root" "$link.new" 2>/dev/null && mv -T "$link.new" "$link" 2>/dev/null
rm -f "$link.new" 2>/dev/null
exit 0
