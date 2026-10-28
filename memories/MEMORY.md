Vault Obsidian (otak kedua): /home/ubuntu/.hermes/obsidian, GitHub addictive378/obsidian (main). Folder: 00-Inbox, 10-Systems, 20-Research, 30-Briefs, 40-Drafts, 50-Published, 90-Log; peta di START-HERE.md. Simpan riset/brief/draft/keputusan ke vault, bukan hanya di chat.
§
Adi (pemilik) menjalankan blog + kanal video dengan profil Hermes: `default` (leader — koordinator/review), `writer` (artikel blog), `videomaker` (video 1 menit, Remotion, ~/video-studio), `softwareengineer` (kode/debug/deploy, SOUL di ~/.hermes/profiles/softwareengineer/SOUL.md). Combo 9router: leader, writer, videomaker, softwareengineer.
§
Cron VPS tiap 5 menit menjalankan ~/sync-vault.sh (tag hermes-obsidian-sync): fetch→rebase→push 3x retry, konflik disimpan di branch hermes-conflict-*, flock, log ~/.hermes/logs/sync-vault.log.
§
Agent Reach 1.6.0 di ~/.local/bin/agent-reach (skill tersymlink ke ~/.hermes/skills/agent-reach). Channel aktif: github, youtube, bilibili, v2ex, web (read-only, tanpa login). Channel lain butuh login browser — TIDAK bisa di VPS headless ini.
§
2026-10-24: Google Drive terhubung via OAuth2 (project herrmes-512606, scope Drive+Docs+Sheets). Kredensial di ~/.hermes/ dan disalin ke tiap profil. Workspace: writer → 'writer-workspace' (1pbpZkIUhNrCRwBVpHTzqfGpk7pjhh0FE), videomaker → 'videomaker-workspace' (11bDbv8E3pHGPSot2YmqyFk6Eb8R-Y3Vd). Setup script tidak mendukung --services; URL otorisasi dibuat manual untuk scope minimal.
§
Video: ~/video-studio = proyek Remotion 4.0.538 (Node v26.7.0), 60s @30fps. Konten diedit di src/specs/*.ts (VideoSpec). Komposisi: OneMinute-Vertical/Horizontal/Square. Verifikasi pakai --frames=0-299 dulu. Belum ada audio/TTS.
§
Situs berita produksi: ~/news-web (Next.js 16 + PostgreSQL 14, GitHub addictive378/news-web) live di https://wartanusaku.site. systemd news-web.service di 127.0.0.1:3000, nginx + Let's Encrypt. Admin: /admin dilindungi Basic Auth nginx (htpasswd /etc/nginx/.htpasswd-warta) + rate limit 20/menit. Kelola akun: `npm run admin -- list|create|passwd|delete`. API integrasi writer: POST /api/integrations/hermes/articles (Bearer HERMES_API_KEY, mode draft).