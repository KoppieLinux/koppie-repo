# Koppie Software Centre

A light app store for Koppie Linux (Arch + KDE Plasma). One place for
Official Repo (`pacman`), AUR (`yay`) and Flatpak apps. Python + PyQt6.

## Install
    ./install.sh        # needs sudo; installs deps, the launcher and the menu entry
    ./uninstall.sh      # removes everything

Run without installing (for testing): `python3 -m koppie_sc`

## Needs
python-pyqt6, polkit (pkexec), flatpak, pacman-contrib (`checkupdates`),
and optionally `yay` for the AUR.

## What's new in v0.3
- Real icons everywhere: rows and the detail page now pull icons from the local AppStream data
  (system catalogue + Flatpak) when the icon theme does not know the app. Local files first
  (no network), only rare remote icons are downloaded once and kept in `~/.cache/koppie-software-centre`.
- The icon index is built once in the background and cached on disk, so old hardware only pays
  the few seconds of parsing on the very first run.
- `install.sh` now also installs `archlinux-appstream-data` (descriptions, icons, screenshots for
  repo apps) and refreshes the Flatpak app list with `flatpak update --appstream`.

## What's new in v0.2
- Click any app row (Explore / Search / Installed) to open its detail page: icon, version, source badge,
  download size, full description (AppStream, pacman, yay or flatpak info) and lazy-loaded screenshots.
- AUR badge is amber. `-bin` AUR packages are listed before ones that must be compiled;
  installing a compile-from-source AUR package shows a friendly warning first.
- Lockfile check (`/var/lib/pacman/db.lck`) before every pacman/yay task, with a friendly popup.
- Clean uninstall: `pacman -Rs` (plus unused Flatpak runtimes), with a confirm dialog that lists what else goes.
- System Care (gear button, top right): Clean Package Cache, Refresh Arch Keyring.

## Safety
- Repo installs run `pkexec pacman -Syu --needed <app>`, AUR installs run `yay -Syu --needed <app>`,
  so the system is never left half-upgraded.
- "Update All" does one full `yay -Syu` (or `pacman -Syu`) plus `flatpak update`.
- Passwords are asked by the KDE polkit dialog; the app never sees them.

## Files
- `koppie_sc/backend.py`  pacman / yay / flatpak logic (no Qt)
- `koppie_sc/workers.py`  background threads
- `koppie_sc/ui.py`       window and widgets
- `icons/`                logo in all sizes (installed to the hicolor icon theme)
- `koppie_sc/catalog.py`  apps on the Explore tab (edit this to change them)
