#!/usr/bin/env python3
"""Audit real traffic for wartanusaku.site from nginx logs.

Usage:  sudo -n python3 audit_traffic.py

Prints one JSON object: raw line count, scanner share, clean pageviews, unique IPs,
ipxday session estimate, per-day series, top real paths, top content paths, device split.
Filters are ordered and documented in ../references/site-traffic-audit.md.
"""
import collections
import datetime
import glob
import gzip
import json
import re

VHOST_LOG = "/var/log/nginx/wartanusaku.access.log"
HOST_GLOB = "/var/log/nginx/access.log*"

LINE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<req>[^"]*)" '
    r'(?P<status>\d{3}) \S+ "[^"]*" "(?P<ua>[^"]*)"'
)
ASSET = re.compile(
    r'\.(css|js|png|jpe?g|svg|ico|webp|woff2?|ttf|map|xml|txt|json|webmanifest)(\?|$)'
    r'|/_next/|/api/|/favicon', re.I
)
SCAN = re.compile(
    r'\.(env|git|aws|php|asp|aspx|jsp|cgi|sql|bak|old|ini|yml|yaml|log|htaccess|DS_Store)'
    r'|/wp-|/vendor/|/phpunit|/graphql|/api-docs|/swagger|/phpinfo|/_profiler|/solr'
    r'|/kibana|/server-status|/containers|/Jenkinsfile|/actuator|/webui|/v1/models'
    r'|/login|/env|/error_log|/graphiql|/cgi-bin|/config|/xmlrpc|/owa/|/developmentserver'
    r'|/index\.html|/api/json|/\.', re.I
)
BOT = re.compile(
    r'bot|crawler|spider|slurp|preview|headless|semrush|ahrefs|dataprovider|bytespider'
    r'|gptbot|claudebot|perplexity|monitor|uptime|pingdom', re.I
)
NONBROWSER = re.compile(r'curl|go-http|python|wget|scrapy|okhttp|java/|libwww', re.I)
CONTENT = re.compile(r'^/(?:[a-z-]+/[^/]+|tag/|penulis/|cari)')


def read_lines():
    out = []
    paths = [VHOST_LOG] + sorted(glob.glob(HOST_GLOB))
    for p in dict.fromkeys(paths):
        try:
            if p.endswith(".gz"):
                out += gzip.open(p, "rt", errors="replace").read().splitlines()
            else:
                out += open(p, errors="replace").read().splitlines()
        except OSError:
            continue
    return out


def path_of(r):
    parts = r["req"].split(" ")
    return parts[1].split("?")[0] if len(parts) > 1 else ""


def main():
    rows = []
    for line in read_lines():
        m = LINE.match(line)
        if not m:
            continue
        d = m.groupdict()
        try:
            d["ts"] = datetime.datetime.strptime(d["ts"], "%d/%b/%Y:%H:%M:%S %z")
        except ValueError:
            continue
        d["status"] = int(d["status"])
        rows.append(d)

    ok = [r for r in rows if r["status"] == 200 and path_of(r) and not ASSET.search(path_of(r))]
    scanners = [r for r in ok if SCAN.search(path_of(r))]
    clean = [r for r in ok if r not in scanners and not NONBROWSER.search(r["ua"])]

    ip_day = {(r["ip"], r["ts"].strftime("%Y-%m-%d")) for r in clean}
    per_day = collections.Counter(d for _, d in ip_day)
    content = [r for r in clean if CONTENT.match(path_of(r))]
    device = collections.Counter(
        next((k for k in ("iPhone", "Android", "Windows", "Macintosh", "Linux")
              if k.lower() in r["ua"].lower()), "other")
        for r in clean
    )

    result = {
        "window": [min(r["ts"] for r in rows).isoformat(), max(r["ts"] for r in rows).isoformat()] if rows else None,
        "total_log_lines": len(rows),
        "scanner_share_pct": round(100 * len(scanners) / len(ok), 1) if ok else 0.0,
        "clean_pageviews": len(clean),
        "unique_ips": len({r["ip"] for r in clean}),
        "approx_sessions_ip_day": len(ip_day),
        "sessions_per_day": dict(sorted(per_day.items())),
        "content_pageviews": len(content),
        "top_content_paths": collections.Counter(path_of(r) for r in content).most_common(15),
        "top_real_paths": collections.Counter(path_of(r) for r in clean).most_common(10),
        "device_split_unreliable_if_spoofed": dict(device),
        "top_ips": collections.Counter(r["ip"] for r in clean).most_common(5),
    }
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
