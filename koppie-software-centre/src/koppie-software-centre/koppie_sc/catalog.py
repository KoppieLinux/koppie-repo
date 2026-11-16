"""Hand-picked apps shown on the Explore tab.

(category, name, summary, source, package id, icon name)
source: "repo" = Official Repo (pacman), "flatpak" = Flathub
"""

CATEGORIES = ["All", "Browsers", "Office", "Multimedia", "Graphics",
              "Communication", "Utilities", "Games"]

APPS = [
    ("Browsers", "Firefox", "Fast and private web browser", "repo", "firefox", "firefox"),
    ("Browsers", "Chromium", "Open-source web browser", "repo", "chromium", "chromium"),
    ("Browsers", "Falkon", "Light web browser, great for older computers", "repo", "falkon", "falkon"),
    ("Browsers", "Brave", "Browser with a built-in ad blocker", "flatpak", "com.brave.Browser", "com.brave.Browser"),

    ("Office", "LibreOffice", "Documents, spreadsheets and presentations", "repo", "libreoffice-fresh", "libreoffice-startcenter"),
    ("Office", "ONLYOFFICE", "Office suite that works well with Microsoft files", "flatpak", "org.onlyoffice.desktopeditors", "org.onlyoffice.desktopeditors"),
    ("Office", "Okular", "Read PDF files and ebooks", "repo", "okular", "okular"),
    ("Office", "Thunderbird", "Email, calendar and contacts", "repo", "thunderbird", "thunderbird"),

    ("Multimedia", "VLC", "Plays almost any video or music file", "repo", "vlc", "vlc"),
    ("Multimedia", "Elisa", "Simple and light music player", "repo", "elisa", "elisa"),
    ("Multimedia", "Audacity", "Record and edit audio", "repo", "audacity", "audacity"),
    ("Multimedia", "Kdenlive", "Easy video editor", "repo", "kdenlive", "kdenlive"),
    ("Multimedia", "OBS Studio", "Record your screen or stream live", "repo", "obs-studio", "com.obsproject.Studio"),
    ("Multimedia", "Spotify", "Stream music online", "flatpak", "com.spotify.Client", "com.spotify.Client"),

    ("Graphics", "GIMP", "Edit photos and images", "repo", "gimp", "gimp"),
    ("Graphics", "Krita", "Digital painting and drawing", "repo", "krita", "krita"),
    ("Graphics", "Inkscape", "Draw logos and vector graphics", "repo", "inkscape", "inkscape"),

    ("Communication", "Telegram", "Fast and simple messaging", "repo", "telegram-desktop", "telegram"),
    ("Communication", "Discord", "Chat with friends and communities", "repo", "discord", "discord"),
    ("Communication", "Signal", "Private messaging", "flatpak", "org.signal.Signal", "org.signal.Signal"),
    ("Communication", "Zoom", "Video meetings", "flatpak", "us.zoom.Zoom", "us.zoom.Zoom"),

    ("Utilities", "KeePassXC", "Keep your passwords safe", "repo", "keepassxc", "keepassxc"),
    ("Utilities", "qBittorrent", "Download torrent files", "repo", "qbittorrent", "qbittorrent"),
    ("Utilities", "BleachBit", "Free up disk space and clean junk files", "repo", "bleachbit", "bleachbit"),
    ("Utilities", "Flameshot", "Take and mark up screenshots", "repo", "flameshot", "flameshot"),
    ("Utilities", "Kate", "Text and code editor", "repo", "kate", "kate"),
    ("Utilities", "Timeshift", "Back up and restore your system", "repo", "timeshift", "timeshift"),

    ("Games", "SuperTuxKart", "Fun kart racing game", "repo", "supertuxkart", "supertuxkart"),
    ("Games", "0 A.D.", "Historical strategy game", "repo", "0ad", "0ad"),
    ("Games", "Steam", "Buy and play PC games", "flatpak", "com.valvesoftware.Steam", "steam"),
]
