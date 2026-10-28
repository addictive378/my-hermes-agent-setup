#!/usr/bin/env bash
# Clean traffic baseline from an nginx access log.
#
# Purpose: measure HUMAN readership before any traffic-dependent decision
# (ad network approval, editorial prioritisation). Raw log counts are
# dominated by bots and scanners and are not a readership number.
#
# Usage:
#   sudo bash scripts/traffic-summary.sh [path-to-access.log]
#
# Requires the bot filter to be active first, otherwise crawler noise
# dominates and the number is meaningless (see nginx bot-filter notes).
set -uo pipefail

LOG="${1:-/var/log/nginx/wartanusaku.access.log}"

if [ ! -r "$LOG" ]; then
  echo "Tidak bisa membaca $LOG — jalankan dengan sudo." >&2
  exit 1
fi

echo "=== Ringkasan trafik bersih — $(date '+%Y-%m-%d %H:%M') ==="
echo "log: $LOG"
echo

# Count only 200s from real browser UAs, excluding crawler/bot signatures.
# The article regex must match the app's actual route shape.
sudo awk '
  {
    status = $9
    path   = $7
    agent  = $0
    sub(/^.*" "/, "", agent)          # UA is the last quoted field

    if (status != 200) next
    if (agent !~ /Chrome|Safari|Firefox|Edg/) next
    if (agent ~ /bot|crawler|spider|ClaudeBot|Googlebot|bingbot|serpstat|heritrix|zgrab|l9|GO-http/) next

    total++
    if (path ~ /^\/(sains|bisnis|teknologi|indonesia|politik|internasional|opini|olahraga)\/[a-z0-9-]+$/) {
      article++; art[path]++
    } else if (path == "/") {
      home++
    } else {
      other++
    }
  }
  END {
    printf "Request 200 dari browser (bukan bot) : %d\n", total
    printf "  - halaman artikel                  : %d\n", article
    printf "  - homepage                         : %d\n", home
    printf "  - halaman lain (tag/kategori)      : %d\n", other
    print ""
    print "PENTING: angka \"halaman lain\" sering didominasi crawler yang menelusuri"
    print "direktori tag/kategori, bukan pembaca. Angka pembaca manusia sesungguhnya"
    print "hanya bisa dilihat di GA4 (JS aktif), bukan di log server."
    print ""
    if (article > 0) {
      print "Artikel paling banyak dibaca (browser saja):"
      for (p in art) printf "  %3d  %s\n", art[p], p
    }
  }
' "$LOG" | sort -k1,1nr | head -40
