# Cleaning Server Logs and Blocking Scanners at the Proxy

## When this applies

Someone wants to make web-server logs usable for decisions ("which pages get traffic", editorial
planning) and the logs are dominated by vulnerability scanners. Or a site is drawing constant
traffic to paths it does not even have.

Do not start from a blocklist copied off the internet. Start from the site's own log — the
blocklist should be a measurement, not a guess.

## Measure first: the log tells you what to block

```bash
sudo wc -l /var/log/nginx/<site>.access.log

# top user agents
sudo awk -F'"' '{print $6}' /var/log/nginx/<site>.access.log | sort | uniq -c | sort -rn | head -15

# top request paths
sudo awk -F'"' '{print $2}' /var/log/nginx/<site>.access.log | awk '{print $2}' \
  | sort | uniq -c | sort -rn | head -20

# paths that only a scanner asks for
sudo awk -F'"' '{print $2}' /var/log/nginx/<site>.access.log \
  | grep -oiE "/(wp-admin|wp-login|wp-content|xmlrpc|\.env|\.git|phpmyadmin|admin\.php|config\.php|\.aws|vendor/)" \
  | sort | uniq -c | sort -rn
```

Interpret by stack: a Next.js/Django/Rails site has **no** `wp-admin`, `xmlrpc.php`, `.env`, or
`.git` to serve. Every hit on those is scanning, no exceptions — that is what makes them safe to
block outright. A UA that is an empty string or `-` has no legitimate reader behind it either.

Classify every UA into one of three buckets before writing rules:

| Bucket | Examples | Action |
|---|---|---|
| Real readers | browser UA strings, mobile Safari, Instagram in-app | never block |
| Legitimate crawlers | Googlebot, Bingbot, Yandex, Applebot | never block — SEO depends on them |
| Scanners / junk | `l9explore`, `masscan`, `zgrab`, `nuclei`, `nikto`, `sqlmap`, `wpscan`, headless scrapers, empty UA | block |

## Implement with `map` + a single gate, not per-location `if`s

Two `map` blocks (UA and path) fold into one decision variable, and one `if` in the server block
enforces it. This keeps the rule in one place instead of scattered across locations.

```nginx
map $http_user_agent $site_bad_ua {
    default                 0;
    ""                      1;
    "-"                     1;

    # Scanner families: match the STEM, never one variant name.
    # `l9explore` alone misses `l9scan` and `l9tcpid` — all LeakIX variants.
    "~*l9"                  1;
    "~*leakix"              1;
    "~*masscan"             1;
    "~*zgrab"               1;
    "~*nuclei"              1;
    "~*nikto"               1;
    "~*sqlmap"              1;
    "~*wpscan"              1;

    # Backlink/SEO crawlers: high volume, no reader value.
    "~*serpstatbot"         1;
    "~*checkmarknetwork"    1;
    "~*internetmeasurement" 1;
    "~*heritrix"            1;

    "~*headlesschrome"      1;
    "~*phantomjs"           1;

    # Generic clients. NO leading anchor: the UA often arrives wrapped in a
    # prefix, so `^go-http-client` misses `Mozilla/5.0 ... Go-http-client/1.1`.
    "~*python-requests"     1;
    "~*python-urllib"       1;
    "~*go-http-client"      1;
    "~*java/"               1;
}

map $request_uri $site_bad_path {
    default                                 0;
    "~*^/\.env"                              1;
    "~*^/\.git"                              1;
    "~*^/\.aws"                              1;
    "~*^/wp-admin"                           1;
    "~*^/wp-login"                           1;
    "~*^/xmlrpc\.php"                        1;
    "~*^/phpmyadmin"                         1;
    "~*^/\.well-known/security\.txt$"        0;   # explicit allow wins
}

map "$site_bad_ua$site_bad_path" $site_block {
    default   0;
    "~*^1"    1;    # UA matched
    "~*1$"    1;    # path matched
}

# Route access logging through a map so blocked requests are NOT JOURNALED.
# An `if` block cannot contain `access_log` (nginx rejects it: "access_log
# directive is not allowed here"), so the file must be chosen via a variable.
map $site_block $site_loggable {
    0        /var/log/nginx/<site>.access.log;
    1        off;
}
```

```nginx
server {
    access_log $site_loggable;          # replaces the literal path
    error_log  /var/log/nginx/<site>.error.log;

    if ($site_block) { return 444; }
    # ... locations
}
```

`444` closes the connection with no response, but **a `return 444` from an `if` block is still
written to the access log.** The belief that 444 keeps the log clean is wrong, and trusting it is
how you end up with a supposedly-filtered log still full of 444 scanner lines (and with `444`
showing up as a status count that looks like real traffic). Only the `map`-selected `access_log`
above removes them. Prove it: send junk, then confirm the log's line count did not move.

### Pitfall: the `if` gate cannot hold `access_log`; `map` is the only way through

If nginx refuses a directive as "not allowed here", do not hunt for a syntax variant — the
configuration model is telling you to move the decision into a `map` (evaluated in the `http`
context) and reference the resulting variable from the `server` block.

## Pitfalls

- **Do not block `curl` and `wget`.** They are what legitimate monitoring, uptime checks, and
  your own probes use. Blocking the tool because scanners also use it takes down health checks
  and leaves you unable to verify anything. Block the *scanner UAs*, not the transport.
- **A first-generation blocklist is never complete — re-measure the log after deploying it.**
  Expected round-two fillers: a scanner whose sibling variant you did not list (`l9scan` when you
  wrote only `l9explore`), a crawler that had not appeared yet (`serpstatbot`), and any generic
  client pattern anchored with `^` while the UA arrives wrapped. Treat "filter installed" as the
  start of the audit, not the end, and report the rescan rather than implying the filter is final.
- **Prefer a loose stem over exhaustive variant names, and drop `^` anchors from generic-client
  patterns.** Exact-name blocklists never converge — state that plainly instead of letting the
  user believe the junk is now fully handled.
- **Characterise by what the stack can serve, not by a generic list.** `/.env` on a Node site is
  always an attack; on a PHP app it might be a config read. Decide per stack.
- **`map` values are strings; the combined key needs anchored regexes.** `"~*^1"` / `"~*1$"` on
  `"$a$b"` catches either side matching. An unanchored pattern will match unexpectedly.
- **Everything with `default 0` must be listed explicitly.** A path not in the map is allowed — so
  a typo in a regex silently disables that rule. Test the rules, do not assume.
- **This is not a substitute for rate limiting.** It drops known-junk signatures, not volumetric
  floods. Keep `limit_req`/`limit_conn` on sensitive locations, and an upstream WAF for real DDoS.
- **A bot filter does not give you reader counts.** After cleaning, logs still contain Googlebot
  and other legitimate crawlers. Say so instead of presenting log lines as pageviews — real
  reader analytics needs a client-side tool.
- **Measure the clean baseline before recommending any traffic-dependent decision.** Ad networks,
  sponsorship, and "is this site worth promoting" all hinge on real-reader volume, and after
  filtering the honest figure is usually far smaller than the raw log suggested. Break requests
  into article pages / homepage / tag+category pages, exclude crawler UAs from all three, and
  report the article-page count as the number that matters. On a mostly-uncrawled site the
  tag/category bucket is nearly all crawlers — a large "other" count is not readership.
- **Do not install ad code on top of bot-dominated traffic.** Ad networks that pay per impression
  forbid bot traffic, so a site whose impressions come from scanners risks the publisher account
  being suspended — the inverse of the intended outcome. Say plainly that the sequencing is
  content and indexing first, measured readers second, monetisation third, and that the ad
  integration itself is the easy part.
- **Removing the gate must be safe.** Keep the `map` file in place; deleting only the
  `if ($site_block) { return 444; }` line reverts behaviour without leaving a dangling include.

## Prove it with a client matrix, both directions

Test that the innocents still pass **and** that the junk still dies. A filter verified only in the
blocking direction will happily break your monitoring.

```bash
printf "%-30s %s\n" "desktop reader:" "$(curl -s -o /dev/null -w '%{http_code}' \
  -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36' https://<site>/)"
printf "%-30s %s\n" "Googlebot:"      "$(curl -s -o /dev/null -w '%{http_code}' \
  -A 'Mozilla/5.0 (compatible; Googlebot/2.1)' https://<site>/)"
printf "%-30s %s\n" "curl (monitoring):" "$(curl -s -o /dev/null -w '%{http_code}' https://<site>/)"
printf "%-30s %s\n" "scanner -> /.env:"  "$(curl -s -o /dev/null -w '%{http_code}' \
  -A 'l9explore/1.2.2' https://<site>/.env)"
printf "%-30s %s\n" "wp-admin:"          "$(curl -s -o /dev/null -w '%{http_code}' \
  -A 'Mozilla/5.0 Chrome/89' https://<site>/wp-admin/install.php)"
printf "%-30s %s\n" "empty UA:"          "$(curl -s -o /dev/null -w '%{http_code}' -A '' https://<site>/)"
```

Expected: `200` for the first three, `000` (connection closed, curl exit 56) for the scanners.

## Procedure

1. Measure the log: counts per UA and per suspicious path.
2. Write `map` blocks into `/etc/nginx/conf.d/<site>-botfilter.conf` with the measured values.
3. Add `if ($site_block) { return 444; }` to the server block — **this is a change to a file
   under `/etc`, which needs explicit user approval.** Stage the file, run `nginx -t`, and get the
   go-ahead before overwriting. If the write is refused or times out, do not retry: leave the
   staged file and ask.
4. `sudo nginx -t && sudo systemctl reload nginx` — test before reload, always.
5. Run the client matrix above against production.
6. Verify the access log no longer grows from scanner traffic. Send junk deliberately, then
   confirm the log line count is unchanged — do not infer this from the 444 status, which is
   still logged when it comes from an `if` gate.
7. **Re-measure the log 24h later.** The first pass always leaves survivors; add the new stems
   and generic-client patterns found, and repeat until the junk count flattens.
8. Record the file locations, the measured counts that justified each rule, the test matrix
   results, and the one-line rollback in `10-Systems/`, then commit and push the vault.
