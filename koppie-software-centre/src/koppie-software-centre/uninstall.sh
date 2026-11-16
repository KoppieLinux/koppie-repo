#!/usr/bin/env bash
set -euo pipefail
SUDO="sudo"; [ "$(id -u)" -eq 0 ] && SUDO=""
$SUDO rm -rf /usr/local/lib/koppie-software-centre
$SUDO rm -f /usr/local/bin/koppie-software-centre /usr/share/applications/koppie-software-centre.desktop
$SUDO rm -f /usr/share/icons/hicolor/*/apps/koppie-software-centre.png
echo "Koppie Software Centre removed."
