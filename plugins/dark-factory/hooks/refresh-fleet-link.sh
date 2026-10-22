#!/usr/bin/env bash
# Keeps the fleet's plugin symlink current (dark-factory plugin, SessionStart).
#
# The server units (fleet.py provision) call fleet.py through ~/.local/share/dark-factory/plugin, because an installed
# plugin lives in a per-version directory that /plugin update leaves behind. Here: if that link exists and points
# elsewhere, repoint it at this plugin. Never creates it (machines without the fleet stay untouched). Silent, fast,
# always exit 0.
link="${FLEET_PLUGIN_LINK:-$HOME/.local/share/dark-factory/plugin}"
root="${CLAUDE_PLUGIN_ROOT:-}"
[ -n "$root" ] && [ -L "$link" ] || exit 0
[ "$(readlink "$link" 2>/dev/null)" = "$root" ] && exit 0
ln -sfn "$root" "$link.new" 2>/dev/null && mv -T "$link.new" "$link" 2>/dev/null
rm -f "$link.new" 2>/dev/null
exit 0
