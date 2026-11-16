#!/usr/bin/env bash
# Pushes the three Koppie packages to the AUR.
# Run this once, from this folder, after the source tarballs are uploaded
# (see README.md step 1) and your AUR SSH key is registered (step 2).
set -euo pipefail
cd "$(dirname "$0")"

PACKAGES=(koppie-driver-manager koppie-update-manager koppie-software-centre)
GIT_NAME="maularaihan-git"
GIT_MAIL="maularaihan-git@users.noreply.github.com"

# Some networks have no IPv6 route; AUR must be reached over IPv4.
export GIT_SSH_COMMAND="ssh -4 -o StrictHostKeyChecking=accept-new"

echo "==> Checking prerequisites"
command -v git >/dev/null || { echo "git is missing:  sudo pacman -S --needed git"; exit 1; }
command -v ssh >/dev/null || { echo "openssh is missing:  sudo pacman -S --needed openssh"; exit 1; }

if ! timeout 20 ssh -4 -o BatchMode=yes -o StrictHostKeyChecking=accept-new -T aur@aur.archlinux.org 2>&1 | grep -qi "authenticated"; then
    cat << 'EOF'
Could not log in to the AUR with your SSH key.

Do this once:
  1. Create an account:  https://archlinux.org/account/register/
  2. Generate a key (skip if you already have one):
         ssh-keygen -t ed25519 -C "aur"
  3. Show it:            cat ~/.ssh/id_ed25519.pub
  4. Paste it at:        https://aur.archlinux.org/   -> "SSH Public Keys"
  5. Run this script again.
EOF
    exit 1
fi
echo "    AUR login OK"

for pkg in "${PACKAGES[@]}"; do
    echo "==> $pkg"
    work="$(mktemp -d)"

    # AUR gives an empty repo for a brand-new package; clone it if it exists.
    if ! git clone -q "ssh://aur@aur.archlinux.org/$pkg.git" "$work/$pkg" 2>/dev/null; then
        mkdir -p "$work/$pkg"
        git -C "$work/$pkg" init -q
        git -C "$work/$pkg" remote add origin "ssh://aur@aur.archlinux.org/$pkg.git"
        echo "    (new AUR package)"
    fi

    cp "$pkg/PKGBUILD" "$work/$pkg/"
    (cd "$pkg" && makepkg --printsrcinfo > .SRCINFO)
    cp "$pkg/.SRCINFO" "$work/$pkg/"

    git -C "$work/$pkg" add PKGBUILD .SRCINFO
    if git -C "$work/$pkg" diff --cached --quiet; then
        echo "    Nothing changed, skipping"
        rm -rf "$work"
        continue
    fi
    git -C "$work/$pkg" -c user.name="$GIT_NAME" -c user.email="$GIT_MAIL" \
        commit -qm "Update PKGBUILD"
    git -C "$work/$pkg" push -q origin HEAD
    echo "    Pushed!"
    rm -rf "$work"
done

echo "==> Done. Packages appear at https://aur.archlinux.org/packages?q=koppie"
