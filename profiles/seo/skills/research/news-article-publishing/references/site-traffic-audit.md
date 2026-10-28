# Reading the site's real traffic from nginx logs

Use when the owner asks for visits, pageviews, readers, or "insight kunjungan" for
`https://wartanusaku.site`. There is no GA4, no Search Console, and no analytics table —
`NEXT_PUBLIC_GA` is empty and the DB holds only editorial tables (`articles`, `tags`,
`editorial_activity`, `newsletter_subscribers`, …). The only source of truth is the nginx
access log, and **it is mostly bots**. Reporting raw counts is misleading; filter first.

## Logs to read

The vhost writes `wartanusaku.access.log` (rotated daily, current file small). The host-wide
`/var/log/nginx/access.log*` carries the same requests plus other vhosts, so parsing it gives
history the vhost file no longer has (compressed `*.gz` rotations reach back weeks). Reading
them requires root: `sudo -n python3 <script>`.

```
/var/log/nginx/wartanusaku.access.log        # this vhost, current period
/var/log/nginx/access.log, access.log.N.gz   # host-wide, history
```

Wildcard-zone and CDN request mirrors land in both, so the same hit can appear twice —
dedupe by (ip, day) when estimating sessions.

## Filtering, in this order

1. **Drop status != 200.** The `301`s are http→https and wildcard noise.
2. **Drop static assets**: `\.(css|js|png|jpe?g|svg|ico|webp|woff2?|ttf|map|xml|txt|json)$`,
   `/_next/`, `/api/`. These are 60–70% of all lines on this site.
3. **Drop scanner probes — the big one.** Roughly 45% of all 200s are vulnerability crawlers,
   not readers. Exclude: `\.(env|git|aws|php|asp|sql|bak|old|ini|yml|log|htaccess)`,
   `/wp-`, `/vendor/`, `/phpunit`, `/graphql`, `/api-docs`, `/swagger`, `/phpinfo`,
   `/_profiler`, `/solr`, `/kibana`, `/server-status`, `/containers`, `/Jenkinsfile`,
   `/actuator`, `/webui`, `/v1/models`, `/login`, `/env`, `/error_log`, `/graphiql`, `/.`.
4. **Drop non-browser UAs**: `curl|go-http|python|wget|scrapy|okhttp|java/|libwww`, plus
   `bot|crawler|spider|slurp|preview|headless|semrush|ahrefs`.
5. Only then count: clean pageviews, unique IPs, ip×day (≈sessions, upper bound), and views on
   content pages (`/<category>/…`, `/tag/…`, `/penulis/…`, `/cari`).

## Signals that a number is fake

- One IP with hundreds of `/` requests and a `curl/8.x` UA → scanner, not a reader.
- Adjacent IPs sharing a /24 each loading `/` 100+ times → crawler pool, not popularity.
- Many distinct IPs all sending the identical `iPhone OS 13_2_3` UA string → UA spoofing;
  **device-split statistics from this log are not reportable.**
- A single day 5–10× the baseline and concentrated in three IPs → not an audience.
- Category pages with hits but almost no article pages → people reach the homepage and never
  click through; that is a navigation/content problem, not a traffic win.

## What to report

Lead with the honest headline, then raw counts, then cleaned numbers, then caveats, then a
ranked fix list. Chain to state every time: raw log lines → scanner share → clean pageviews →
unique IPs → content-page views. Name the missing instrumentation (no GA4, no Search Console)
as a gap, not an excuse, and propose the order: fix rendering/indexing first, install analytics
second, filter bots at nginx third, submit the sitemap fourth.

## Known audit script

`scripts/audit_traffic.py` runs the whole pipeline (parses vhost + rotated host-wide logs,
filters, aggregates, prints JSON). Run it as `sudo -n python3 scripts/audit_traffic.py`. Extend
the `SCAN`/`BOT`/`ASSET` regexes there when a new noise pattern appears; keep the script
returning raw numbers and write the narrative yourself.
