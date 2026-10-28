#!/usr/bin/env bash
# SEO probe suite for Next.js news sites.
# Usage: bash probe.sh <base_url>
set -euo pipefail
BASE="${1:-https://wartanusaku.site}"

echo "=== 1. LIVENESS ==="
for p in / /sitemap.xml /robots.txt /rss.xml /news-sitemap.xml; do
  printf "%-25s " "$p"
  curl -s -o /dev/null -w "%{http_code} ttfb=%{time_starttransfer}s size=%{size_download}\n" "${BASE}${p}"
done

echo "\n=== 2. E-E-A-T PAGES ==="
for p in /tentang /kontak /pedoman /kebijakan-editorial /privasi /syarat; do
  printf "%-25s " "$p"
  STATUS=$(curl -s -o /tmp/seo_probe.html -w "%{http_code}" "${BASE}${p}")
  ROBOTS=$(grep -oE '<meta name="robots" content="[^"]*"' /tmp/seo_probe.html | head -1 || true)
  echo "$STATUS ${ROBOTS:-'(no robots meta)'}"
done

echo "\n=== 3. GLOBAL METADATA (homepage) ==="
curl -s "${BASE}/" | grep -oE '<meta name="robots"[^>]*>|max-image-preview|max-snippet|max-video-preview' | sort -u || echo "(none found)"

echo "\n=== 4. CATEGORY INDEXABILITY ==="
for cat in teknologi politik bisnis indonesia olahraga; do
  printf "%-15s " "$cat"
  curl -s "${BASE}/${cat}" | grep -oE '<meta name="robots" content="[^"]*"' | head -1 || echo "(default/indexable)"
done

echo "\n=== 5. ARTICLE SAMPLE ==="
ARTICLE=$(curl -s "${BASE}/sitemap.xml" | grep -oE '<loc>[^<]+</loc>' | sed 's/<[^>]*>//g' | grep -E '/[a-z]+/[a-z0-9-]{10,}' | head -1)
echo "URL: $ARTICLE"
if [ -n "$ARTICLE" ]; then
  curl -s "$ARTICLE" > /tmp/seo_article.html
  echo "H1: $(grep -oE '<h1[^>]*>[^<]{0,120}' /tmp/seo_article.html | head -1)"
  echo "Canonical: $(grep -oE '<link rel="canonical" href="[^"]*"' /tmp/seo_article.html | head -1)"
  echo "JSON-LD types: $(grep -oE '"@type":"[A-Za-z]+"' /tmp/seo_article.html | sort -u | tr '\n' ' ')"
  TEXT_LEN=$(python3 -c "import re; h=open('/tmp/seo_article.html').read(); t=re.sub(r'<script.*?</script>','',h,flags=re.S); t=re.sub(r'<[^>]+>',' ',t); print(len(t))")
  echo "Body text length: $TEXT_LEN chars (>1000 = SSR OK)"
  echo "Internal article links: $(grep -oE 'href="/[a-z]+/[a-z0-9-]{10,}"' /tmp/seo_article.html | sort -u | wc -l)"
  OG_IMG=$(grep -oE 'og:image" content="[^"]*"' /tmp/seo_article.html | head -1 | sed 's/.*content="//;s/"$//')
  if [ -n "$OG_IMG" ]; then
    IMG_SIZE=$(curl -sI "$OG_IMG" | grep -i content-length | awk '{print $2}' | tr -d '\r' || true)
    echo "og:image size: ${IMG_SIZE:-unknown} bytes (<50000 = likely sub-1200px)"
  fi
fi

echo "\n=== 6. FOOTER E-E-A-T LINKS ==="
curl -s "${BASE}/" | grep -oE 'href="/(tentang|kontak|pedoman|privasi|syarat|redaksi|kebijakan[a-z-]*)"' | sort -u

echo "\nDone. DB check is separate (needs DATABASE_URL)."
