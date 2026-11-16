# Koppie AUR packages

Ready-to-push AUR packages for the Koppie Linux apps:

| Package | Version | What it installs |
|---|---|---|
| `koppie-driver-manager` | 1.0.0-7 | GUI driver manager (now runs `pacman -Syu` with the driver, so kernel + headers stay in sync; icon from Papirus) |
| `koppie-update-manager` | 1.0.0-6 | GUI system update center + weekly notifier (icon from Papirus) |
| `koppie-software-centre` | 0.3-1 | GUI app store (pacman + AUR + Flatpak), the GNOME Software-style one |

After this, users get the GUI apps straight away:

    yay -S koppie-software-centre

## One-time setup (3 steps)

### 1. Upload the source tarballs to GitHub

The PKGBUILDs download their sources from your `koppie-repo`, so the three
tarballs in `sources/` must be uploaded first:

    sources/koppie-driver-manager-1.0.0.tar.gz    -> pkg-sources/koppie-driver-manager/
    sources/koppie-update-manager-1.0.0.tar.gz    -> pkg-sources/koppie-update-manager/
    sources/koppie-software-centre-0.3.tar.gz     -> pkg-sources/koppie-software-centre/   (new folder)

Use the web UI (<https://github.com/maularaihan-git/koppie-repo>) or a token.
The `sha256sums` in each PKGBUILD match **these exact files** — if you re-create
a tarball, update the checksum (or tell me and I will).

### 2. Create the AUR account + SSH key

1. <https://archlinux.org/account/register/>
2. `ssh-keygen -t ed25519 -C "aur"` (skip if you already have a key)
3. `cat ~/.ssh/id_ed25519.pub` -> paste at <https://aur.archlinux.org/> under **SSH Public Keys**
4. `sudo pacman -S --needed openssh`

### 3. Push

    ./push-to-aur.sh

The script checks the login, regenerates `.SRCINFO`, commits and pushes all
three packages. Re-run it any time you bump a version.

## Updating a package later

1. Change the app, bump `pkgver` or `pkgrel` in `PKGBUILD`.
2. Re-create the matching tarball in `sources/` and upload it (keep the same
   filename), update `sha256sums`.
3. `./push-to-aur.sh`

## Local test build (no upload needed)

    makepkg -f        # put the tarball next to the PKGBUILD first (already done here)

## Notes

- `koppie-driver-manager` and `koppie-update-manager` ship a bundled
  `lib/customtkinter`, so the only deps are `python`, `tk` and `python-pillow`.
- `koppie-software-centre` depends on `python-pyqt6`, `polkit`, `flatpak`,
  `pacman-contrib` and `archlinux-appstream-data`; `yay` is an optdepend
  (AUR search turns off automatically without it).
- The AUR packages carry the **same names** as your `koppie` repo packages, so
  they replace each other cleanly instead of conflicting.
