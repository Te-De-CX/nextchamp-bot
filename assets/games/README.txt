NextChamp — per-game challenge banners
=======================================

Drop one .jpg file per game here, named after the game's `slug`
exactly as returned by the API. The bot matches on slug, NOT the
display name, so use the filenames below exactly.

Current games & their slugs:

  [ ] efootball.jpg                → eFootball
  [ ] fc-mobile.jpg                → FC Mobile
  [ ] cod-mobile.jpg               → COD Mobile
  [ ] 8-ball-pool.jpg              → 8 Ball Pool
  [ ] chess.jpg                    → Chess
  [ ] rocket-league-sideswipe.jpg  → Rocket League Sideswipe

Also provide:

  ../default.jpg                   → fallback when a game has no banner

Notes:
- Only .jpg is scanned. Convert other formats before dropping them in.
- Filenames are case-sensitive on macOS/Linux. Use lowercase exactly as above.
- If a game image is missing, the bot falls back to default.jpg.
- If default.jpg is missing too, the post goes text-only (caption only, no image).
- Recommended size: 1280×720 (16:9) or 1080×1080 (1:1).