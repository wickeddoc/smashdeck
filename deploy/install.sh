#!/usr/bin/env bash
# Install SmashDeck as a systemd user service that starts with your graphical
# (Wayland/X11) desktop session and stops at logout. Safe to re-run: it
# re-renders the unit and restarts the service, e.g. after changing paths.
#
#   deploy/install.sh            install (or update) and start the service
#   deploy/install.sh --dry-run  show what would be done; change nothing
#
# Python interpreter, first match wins:
#   1. $SMASHDECK_PYTHON
#   2. <repo>/.venv/bin/python             (a regular venv directory)
#   3. $WORKON_HOME/<name>/bin/python      (.venv is a virtualenvwrapper file
#                                           naming <name>; WORKON_HOME defaults
#                                           to ~/.virtualenvs)
set -euo pipefail

UNIT=smashdeck.service
UDEV_RULE=70-streamdeck.rules
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
UNIT_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user

DRY_RUN=0
case ${1:-} in
    "") ;;
    --dry-run) DRY_RUN=1 ;;
    *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac

say() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
run() {
    if (( DRY_RUN )); then printf '    would run: %s\n' "$*"; else "$@"; fi
}

find_python() {
    if [[ -n ${SMASHDECK_PYTHON:-} ]]; then
        printf '%s\n' "$SMASHDECK_PYTHON"
    elif [[ -x $REPO/.venv/bin/python ]]; then
        printf '%s\n' "$REPO/.venv/bin/python"
    elif [[ -f $REPO/.venv ]]; then
        printf '%s\n' "${WORKON_HOME:-$HOME/.virtualenvs}/$(<"$REPO/.venv")/bin/python"
    else
        return 1
    fi
}

# --- preflight -----------------------------------------------------------------

PYTHON=$(find_python) || die "no Python found; set SMASHDECK_PYTHON=/path/to/venv/bin/python"
[[ -x $PYTHON ]] || die "$PYTHON is not executable; set SMASHDECK_PYTHON"
"$PYTHON" -c 'import StreamDeck, PIL, yaml, phue, kasa, tapo, jeepney, psutil' 2>/dev/null \
    || die "$PYTHON lacks dependencies; run: $PYTHON -m pip install -r $REPO/requirements.txt"
[[ -f $REPO/config.yaml ]] \
    || die "$REPO/config.yaml is missing; copy config.yaml.dist and edit it"
case $REPO$PYTHON in
    *[\|\&\\\"]*) die "paths containing | & \\ or \" are not supported" ;;
esac
command -v systemctl >/dev/null || die "systemctl not found; this installer needs systemd"

say "repo:   $REPO"
say "python: $PYTHON"

# Two instances can't share the deck: refuse while one runs outside systemd.
# Only a python process running this repo's main.py counts (not an editor).
runs_this_main() {
    local pid=$1 arg argv=()
    mapfile -d '' -t argv 2>/dev/null < "/proc/$pid/cmdline" || return 1
    [[ ${argv[0]##*/} == python* ]] || return 1
    for arg in "${argv[@]:1}"; do
        [[ $arg == "$REPO/main.py" ]] && return 0
        if [[ $arg == main.py || $arg == ./main.py ]] \
            && [[ $(readlink "/proc/$pid/cwd" 2>/dev/null) == "$REPO" ]]; then
            return 0
        fi
    done
    return 1
}
service_pid=$(systemctl --user show --property=MainPID --value "$UNIT" 2>/dev/null || echo 0)
for pid in $(pgrep -f 'main\.py' || true); do
    [[ $pid == "$service_pid" ]] && continue
    if runs_this_main "$pid"; then
        msg="SmashDeck is already running outside systemd (PID $pid); stop it first"
        (( DRY_RUN )) && say "note: $msg" || die "$msg"
    fi
done

# --- 1. udev: let the logged-in user open the Stream Deck ------------------------

if grep -qs '0fd9' /etc/udev/rules.d/*.rules /usr/lib/udev/rules.d/*.rules; then
    say "udev rule for the Stream Deck already present"
else
    say "installing /etc/udev/rules.d/$UDEV_RULE (needs sudo)"
    run sudo install -m 0644 "$REPO/deploy/$UDEV_RULE" "/etc/udev/rules.d/$UDEV_RULE"
    run sudo udevadm control --reload-rules
    run sudo udevadm trigger --subsystem-match=usb --subsystem-match=hidraw
    say "if the deck is still not accessible, unplug and replug it"
fi

# --- 2. the user unit ------------------------------------------------------------

unit_text=$(sed -e "s|@REPO@|$REPO|g" -e "s|@PYTHON@|$PYTHON|g" "$REPO/deploy/$UNIT.in")
if (( DRY_RUN )); then
    say "would write $UNIT_DIR/$UNIT:"
    printf '%s\n' "$unit_text" | sed 's/^/    | /'
else
    mkdir -p "$UNIT_DIR"
    printf '%s\n' "$unit_text" > "$UNIT_DIR/$UNIT"
    say "wrote $UNIT_DIR/$UNIT"
fi

# --- 3. enable at login and (re)start now ----------------------------------------

run systemctl --user daemon-reload
run systemctl --user enable "$UNIT"
run systemctl --user restart "$UNIT"

(( DRY_RUN )) && exit 0

sleep 3
if systemctl --user is-active --quiet "$UNIT"; then
    say "smashdeck is running and will start at every login"
    say "logs: journalctl --user -u smashdeck -f"
else
    systemctl --user status "$UNIT" --no-pager --lines=20 || true
    die "the service did not stay up; see: journalctl --user -u smashdeck"
fi
