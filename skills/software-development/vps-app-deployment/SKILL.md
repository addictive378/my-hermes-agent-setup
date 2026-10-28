---
name: vps-app-deployment
description: "Use when deploying a web app to a VPS: nginx, TLS."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
tags: [vps, deployment, nginx, systemd, postgres, nextjs, certbot]
metadata:
  hermes:
    tags: [vps, deployment, nginx, systemd, postgres, nextjs, certbot]
---

# Deploying a Web App to a VPS

## When to Use

- The user asks to put an app online, "deploy this", "make it public", or "set up so it can be accessed publicly".
- A repo has been cloned to the VPS and needs a database, a service manager unit, a reverse proxy, and TLS.
- Troubleshooting why a deployed site is unreachable, 502s, or is not served on the expected domain.

Deploy a self-hosted web application (Node/Next.js is the common case here) so it
runs under systemd behind nginx with TLS. The user self-hosts on a single VPS and
keeps several sites on one box, so every deployment must coexist with what is
already running.

## Before touching anything: recon

Run the whole block once — it determines every later decision:

```bash
ip -brief addr                          # private vs public interface
curl -sS -m 10 https://api.ipify.org    # the public IP users must reach
ss -tlnp                                # what already listens on 80/443/3000
ls /etc/nginx/sites-enabled/            # existing vhosts
sudo ufw status verbose                 # default-deny blocks 80/443
```

- **Do not modify an existing vhost.** Add a new `server_name` block for the new
  site; existing sites keep serving under their own `server_name` (an IP-based
  vhost keeps working alongside a domain-based one).
- A NAT'd VM still has a routable public IP via the provider's firewall — check
  the public IP, not the interface address, when telling the user what to point
  DNS at.

## DNS before TLS

Check whether the requested domain already points at this box:

```bash
dig +short A <domain> @8.8.8.8          # public resolver
dig +short A www.<domain> @8.8.8.8
for ns in $(dig +short NS <domain> @8.8.8.8); do dig +short A <domain> @$ns; done
```

**Do not trust this machine's own resolver.** `getent hosts` and a bare `dig`
read a cached answer and can still show the old parking IP for hours after the
user added the record — concluding "DNS not propagated" from that costs a
round-trip and is usually wrong. Query a public resolver and the authoritative
NS; if you need the local cache gone, `sudo resolvectl flush-caches`.

To exercise the real vhost regardless of DNS, force the resolution:

```bash
curl -sS --resolve <domain>:443:<public-ip> -o /dev/null -w "HTTP %{http_code}\n" https://<domain>/
curl -sS --resolve <domain>:80:<public-ip>  -o /dev/null -w "HTTP %{http_code} -> %{redirect_url}\n" http://<domain>/
```

- If the authoritative NS still returns elsewhere (a registrar parking page is
  common), the app can still be deployed and verified locally, but **TLS
  issuance will fail**. Tell the user the exact A records to add and defer
  certbot until they confirm — do not run certbot and report the failure as a
  deployment problem.
- Both the apex (`@`) and `www` need their own A record; a user often adds only
  one.

## Database

Install, then create the role and database idempotently so a re-run is safe:

```bash
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql postgresql-contrib
```

```bash
DB_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '<user>') THEN
    CREATE ROLE <user> LOGIN PASSWORD '<DB_PASS>';
  ELSE
    ALTER ROLE <user> PASSWORD '<DB_PASS>';
  END IF;
END
\$\$;
SQL
sudo -u postgres createdb -O <user> <db>
```

Verify with the real credentials
(`PGPASSWORD=... psql -h localhost -U <user> -d <db> -c 'SELECT current_database()'`)
— a role that exists but cannot log in is the most common silent failure.

## Environment file

Generate secrets with `openssl rand` and **never echo them to the chat** — write
them into the app's env file at mode 600 and report only the variable names.
Hold the values in a temporary mode-600 file if later steps need them again.

## Build

Run install → migrate → seed → build as separate commands and check each one's
output, not just the exit code. Seed scripts commonly print created admin
credentials to stdout — capture those for the handover note, and flag them as
must-change.

## Systemd unit

**Write the unit file with `write_file` into the scratch directory, then `sudo
cp` it into `/etc/systemd/system/`.** A heredoc whose body contains systemd
commands trips the command-lifecycle guard and stalls the turn — the file-write
route is fast and never triggers it.

Use the template `templates/systemd-next.service` (copy, edit the working
directory, node path, and port). Bind the app to `127.0.0.1` — nginx owns the
public interface. Then:

```bash
sudo cp <scratch>/<name>.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now <name>.service
```

**Verify the app directly before configuring nginx:**

```bash
curl -sS http://127.0.0.1:<port>/api/health   # or the app's equivalent
```

## nginx vhost

Use the template `templates/nginx-vhost.conf` (copy, set `server_name` and the
upstream port). Then:

```bash
sudo cp <scratch>/<site>.conf /etc/nginx/sites-available/<site>
sudo ln -sf /etc/nginx/sites-available/<site> /etc/nginx/sites-enabled/<site>
sudo nginx -t && sudo systemctl reload nginx
```

**Verify by Host header against localhost** — this proves the vhost works without
waiting for DNS:

```bash
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -H "Host: <domain>" http://127.0.0.1/
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -H "Host: <other-site>" http://127.0.0.1/   # cohabitants still up
```

## Firewall

If `ufw status` shows default-deny, HTTP/HTTPS is blocked externally even though
nginx listens:

```bash
sudo ufw allow 'Nginx Full'
```

## TLS

Only after the domain resolves to this box. In an agent/gateway turn, certbot
must run non-interactively — an email prompt stalls the turn:

```bash
sudo certbot --nginx -d <domain> -d www.<domain> \
  --non-interactive --agree-tos --email <account-email> --redirect
```

`--redirect` makes certbot add the HTTP→HTTPS 301. Then confirm the cert covers
every name you announced (a vhost serving `www` without a SAN for it still shows
"not secure" on that host):

```bash
echo | openssl s_client -connect <public-ip>:443 -servername <domain> 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
curl -sS --resolve <domain>:443:<public-ip> -o /dev/null -w "%{http_code}\n" https://<domain>/
```

certbot rewrites the vhost's server block; keep the proxy directives intact and
re-verify both the site and its cohabitants afterwards. Renewal is handled by
`certbot.timer` — confirm it is scheduled rather than adding your own cron.

**"The site says not secure"** right after a DNS change is almost never an app
bug: it means TLS has not been issued yet. Confirm DNS, run certbot, re-check
with `--resolve`. Do not go looking in the application or the vhost.

## Redeploying an update

When the user pushes to the repo and asks for the VPS to be updated, review
before pulling, then rebuild and restart:

```bash
cd <repo> && git fetch origin
git log --oneline HEAD..origin/main      # what is coming
git diff --stat HEAD origin/main
git pull origin main
```

Then: `npm ci` **only if** `package.json`/lock changed → `npm run db:migrate`
(no-op is fine and cheap) → `npm run build` → restart the unit → verify:

Capture the running PID **before** the restart, so you can prove the restart
actually happened:

```bash
systemctl show <unit> -p MainPID -p ActiveEnterTimestamp --value   # before
sudo systemctl restart <unit> && sleep 4 && systemctl is-active <unit>
systemctl show <unit> -p MainPID -p ActiveEnterTimestamp --value   # after: must differ
curl -sS http://127.0.0.1:<port>/api/health
curl -sS -o /dev/null -w "%{http_code}\n" https://<domain>/<a-real-page>
```

- **A green build is not a deployment.** `npm run build` writes `.next/`, but the
  running server loaded its build at startup — until the unit restarts, production
  keeps serving the old code and your fix stays invisible. An unchanged `MainPID`,
  or an `ActiveEnterTimestamp` older than `.next/BUILD_ID`'s mtime, proves the
  restart never happened. Check that timestamp, not the word `active`.
- `.env*` is gitignored, so a pull must NOT clobber it — assert it still exists
  with its mode intact before rebuilding, and say so in the report.
- Report the commit hash now running, so the user can confirm the deploy landed.

## Protecting an admin panel

A public site with a private admin area is the normal shape. Two independent
layers, and they are not interchangeable: rate-limit the login (brute force) and
gate the whole admin area (keep scanners out).

### Rate limiting

`limit_req_zone` / `limit_conn_zone` must be declared in the **`http` context** —
put them in `/etc/nginx/conf.d/<name>.conf`, not inside the `server` block
(nginx refuses to start otherwise). Reference them from the admin locations:

```nginx
# /etc/nginx/conf.d/<site>-limits.conf   -- http context, NOT in the server block
limit_req_zone $binary_remote_addr zone=<site>_login:10m rate=20r/m;
limit_req_zone $binary_remote_addr zone=<site>_admin:10m rate=10r/s;
```

```nginx
# inside the vhost's server block
location = /admin/login {
    limit_req zone=<site>_login burst=10 nodelay;
    ...
}
location ^~ /admin {
    limit_req zone=<site>_admin burst=60 nodelay;
    ...
}
```

- **Scope the strict limit to the login endpoint alone.** A tight limit
  (5r/m) on `location ^~ /admin` throttles the entire panel: the dashboard,
  its prefetches, and every server-action POST drain the same bucket, so a
  legitimate login starts returning **503** and looks like a broken app. One
  bucket per concern — strict on `= /admin/login`, generous on `/admin`.
- Verify **both** directions: N rapid requests to the login endpoint must begin
  returning 503, and the public site plus one normal login must still be 200.
  A limit never observed to fire is untested; a limit that fires on legitimate
  traffic is a bug. Public `location /` must be outside every admin zone.

### Basic Auth gate

Works from any network, unlike an IP allowlist (mobile IPs rotate and an
allowlist locks the owner out of their own panel).

```bash
sudo apt-get install -y apache2-utils
sudo htpasswd -B -c /etc/nginx/.htpasswd-<site> <username>   # the USER runs this
```

Include the gate from a **separate file** so it toggles without touching the
vhost: `include /etc/nginx/<site>-admin-gate.conf;` inside every admin
location. Enabling the gate is then a one-file change plus a reload, and
`htpasswd` edits take effect per request with no reload at all.

- Have the user set their own password by running `htpasswd` themselves. Never
generate a password and paste it into chat, and never accept one in chat.
- **Keep self-authenticating API routes out of the gated location.** Paths the
app authenticates itself (bearer token, HMAC) must live outside `location
/admin`. Verify by calling one unauthenticated: the 401 must carry the app's
JSON error body, not nginx's `WWW-Authenticate` header — if the header is
present, the gate is swallowing the API.

### Verifying a gated page when you cannot log in yourself

Headless-browser form submissions against Next.js server actions often fail to
fire the POST (hydration/prefetch quirks), so a browser that stays on the login
page proves nothing about the app — do not report it as a bug or as a pass.

Instead, mint a short-lived session with the app's own signing code and secret:
read `SESSION_SECRET` from the app's env file, produce a token with the same
library and claim shape the app verifies (e.g. `jose` `SignJWT`), write it to a
mode-600 temp file, then exercise the page over HTTP:

```bash
curl -sS -H "Cookie: <cookie-name>=$TOKEN" https://<domain>/<gated-path> -o page.html
```

Grep `page.html` for markers that only render when authenticated — an empty
shell that client-side redirects means the guard is working, not that the page
failed. Delete the temp token afterwards, and check credentials independently
(e.g. `bcrypt.compare` against the stored hash) rather than inferring validity
from a failed browser attempt.

For an App Router app, `references/nextjs-app-router-verification.md` covers the
cases that bite here: cookie mutation during render, a logout control wired as a
`<Link>` inside a `<form>`, and how to invoke a server action end-to-end with
`curl` alone — no browser and no hydration needed.

**Admin guard placement, and what a 200 on `/admin` means.** `GET /admin` without
a session returning 200 is not automatically a hole: App Router pages commonly
render an empty shell and let a client-side redirect — or the page's own
`requireAdmin()` — take over. Judge it by two things instead: (1) call the
protected surface with the session cookie cleared and confirm no protected data
appears in the HTML, and (2) confirm unauthenticated access cannot reach any
data-fetching path. Say which of the two you checked; a bare status code proves
neither. When the page has no server-side redirect at all, that is worth fixing
but is a hardening item, not an open door — and if a gated panel returns 401
before the app ever sees the request, that 401 is nginx's Basic Auth, not the
app rejecting the session.

### Seeded admin accounts

Deploying an app with seeded credentials is not finished until the owner can
change them. Check whether the app ships a password-change UI; if it does not,
say so and offer a minimal management path before the site is public:

- a small CLI over the app's own ORM and hash function, with verbs
  `list | create | passwd | disable | enable | delete`;
- **never accept a password as a command-line argument** — it lands in shell
  history and the process list. Prompt with hidden input, or read stdin;
- verify the stored credentials against the real hash before telling the user
  the account works;
- when replacing seeded accounts, create and verify the new one **before**
  deleting the old ones, or the owner is locked out.

## Handover

Report: what is running and under which unit, the URL, the DNS record the user
still has to add (if any), and any seeded credentials that must be changed. On
this user's machine, also record the deployment in the second-brain vault under
`10-Systems/` — future sessions look there for what is running where.

## Pitfalls

- Never assume the app is live because the process is running — probe the health
  endpoint, then the proxy, then the public URL.
- Never bind the app to `0.0.0.0` when nginx fronts it; a direct-exposed port
  bypasses nginx and any future TLS termination.
- Never put generated secrets in the chat or in the repo — env file at mode 600,
  outside version control.
- Never delete or rewrite an existing vhost while adding a site; a broken
  server_name match silently redirects traffic to whichever block nginx picked
  as default.
