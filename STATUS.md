# STATUS — push ke AUR (update: 16 Nov 2026, 17:00)

## Selesai ✓
- 3 paket siap & build lolos: `koppie-driver-manager 1.0.0-7`,
  `koppie-update-manager 1.0.0-6`, `koppie-software-centre 0.3-1`
  (PKGBUILD + .SRCINFO + paket jadi ada di folder masing-masing)
- **Ikon diganti pakai artwork Papirus** (16 Nov):
  update-manager = `Papirus/48x48/apps/update-manager.svg` (panah refresh oranye),
  driver-manager = `Papirus/48x48/apps/driver-manager.svg` (= `jockey.svg`, chip hijau).
  Sudah dipasang di sistem (`hicolor/512x512` + `pixmaps`, icon cache di-refresh)
  DAN masuk tarball + PKGBUILD (`app/assets/koppie-*-manager-icon.png`,
  `koppie-logo.png` tetap dipakai buat logo header di dalam app).
  sha256 tarball lama berubah, sudah diganti di PKGBUILD:
  driver `6cb16344...`, update `4046f605...`
- Source tarball: `sources/*.tar.gz` (sha256 sudah dikunci di PKGBUILD)
- `openssh` terpasang, key AUR dibuat: `~/.ssh/id_ed25519`
  (public key: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGoSziqx/1Epjm1XaP3YF6D2dr5NbKkkEtNTDlPvSIUM aur)
- `push-to-aur.sh` sudah dites: nyampe ke `aur.archlinux.org` (pakai `-4`,
  karena jaringan ini nggak punya route IPv6), berhenti bersih di gerbang auth.

## Belum bisa (nunggu)
1. **AUR nutup registrasi baru** (HTTP 503, kebijakan Arch karena gelombang bot).
   Pantau: https://aur.archlinux.org/register atau mailing list `aur-general`.
   Begitu buka → daftar https://archlinux.org/account/register/ →
   tempel public key di https://aur.archlinux.org/ (SSH Public Keys).
2. **3 tarball belum di-upload ke GitHub** `maularaihan-git/koppie-repo`
   -> `pkg-sources/<nama>/` (folder `koppie-software-centre` bikin baru).

## Lanjut besok
- Setelah 1 & 2 beres: `./push-to-aur.sh` (bisa dijalankan dari mesin ini).
- Alternatif sementara: paket juga bisa dimasukkan ke `koppie-repo` biar user
  Koppie bisa `pacman -S koppie-software-centre` tanpa nunggu AUR.
