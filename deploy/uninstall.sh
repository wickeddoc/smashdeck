#!/usr/bin/env bash
# Stop SmashDeck, remove its systemd user service and stop it starting at
# login. Leaves the udev rule, config.yaml and the venv untouched.
set -euo pipefail

UNIT=smashdeck.service
UNIT_FILE=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$UNIT

systemctl --user disable --now "$UNIT" 2>/dev/null || true
rm -f "$UNIT_FILE"
systemctl --user daemon-reload
systemctl --user reset-failed "$UNIT" 2>/dev/null || true

echo "==> removed $UNIT"
if [[ -f /etc/udev/rules.d/70-streamdeck.rules ]]; then
    echo "==> /etc/udev/rules.d/70-streamdeck.rules left in place;"
    echo "    remove it with: sudo rm /etc/udev/rules.d/70-streamdeck.rules"
fi
