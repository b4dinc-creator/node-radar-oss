#!/bin/zsh
# Install and start the Node Radar launchd agent for the current user.
set -e
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/Library/LaunchAgents/com.noderadar.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/node-radar"
sed -e "s|__PROJECT__|$PROJECT|g" -e "s|__HOME__|$HOME|g" "$PROJECT/launchd/com.noderadar.plist.template" > "$DEST"
launchctl bootout "gui/$UID/com.noderadar" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$DEST"
echo "installed $DEST; logs: $HOME/Library/Logs/node-radar/service.log"
