#!/usr/bin/env bash
# Installs Koppie Software Centre system-wide on Arch Linux (KDE).
set -euo pipefail
cd "$(dirname "$0")"

SUDO="sudo"; [ "$(id -u)" -eq 0 ] && SUDO=""
LIB=/usr/local/lib/koppie-software-centre

echo "==> Checking dependencies"
need=()
python3 -c 'import PyQt6.QtWidgets' 2>/dev/null || need+=(python-pyqt6)
command -v checkupdates >/dev/null || need+=(pacman-contrib)
command -v flatpak      >/dev/null || need+=(flatpak)
command -v pkexec       >/dev/null || need+=(polkit)
# AppStream data = descriptions, icons and screenshots for repo apps
pacman -Q archlinux-appstream-data >/dev/null 2>&1 || need+=(archlinux-appstream-data)
if [ ${#need[@]} -gt 0 ]; then
    echo "    Installing: ${need[*]} (full upgrade first, to avoid a partial upgrade)"
    $SUDO pacman -Syu --needed "${need[@]}"
fi
command -v yay >/dev/null || echo "    Note: 'yay' not found. AUR search/install will stay off until you install it."

if command -v flatpak >/dev/null; then
    echo "==> Refreshing the Flatpak app list (icons and descriptions)"
    timeout 90 $SUDO flatpak update --appstream -y --noninteractive >/dev/null 2>&1 || \
        echo "    Note: could not refresh it now (no internet?). It will update on its own later."
fi

echo "==> Installing files"
$SUDO rm -rf "$LIB"
$SUDO install -d "$LIB"
$SUDO cp -r koppie_sc "$LIB/"
$SUDO find "$LIB" -name __pycache__ -prune -exec rm -rf {} +
$SUDO python3 -m compileall -q "$LIB/koppie_sc"
$SUDO install -Dm755 bin/koppie-software-centre /usr/local/bin/koppie-software-centre
$SUDO install -Dm644 koppie-software-centre.desktop /usr/share/applications/koppie-software-centre.desktop

for size in 16 22 32 48 64 128 256 512; do
    $SUDO install -Dm644 "icons/koppie-software-centre-$size.png" \
        "/usr/share/icons/hicolor/${size}x${size}/apps/koppie-software-centre.png"
done
$SUDO gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true

# refresh the KDE application menu (run as the normal user)
if [ "$(id -u)" -ne 0 ]; then
    (kbuildsycoca6 --noincremental >/dev/null 2>&1 || true)
fi
echo "==> Done! Open the Application Launcher and search for 'Koppie Software Centre'."
echo "    Or run: koppie-software-centre"
