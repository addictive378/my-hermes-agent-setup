# Analytics Beacons Silently Dropped by CSP

## When this applies

You installed an analytics/tag script (GA4, Plausible, Umami, Meta Pixel, Hotjar) and the
provider dashboard shows **zero data**, but the page looks correct: the `<script>` tag is in the
HTML, the network tab shows the script downloading fine, and there are no errors a user would
notice.

This is the opposite failure mode from a missing tag. A missing tag is obvious on inspection;
this one passes every shallow check and only fails on the step that actually matters — the
**beacon POST that carries the data**.

## Why it happens: two separate origins, only one allowed

A tag-based analytics install touches at least two different hosts, and a `Content-Security-Policy`
must allowlist both under **different directives**:

| Purpose | Directive | Typical host |
|---|---|---|
| Fetch the loader script | `script-src` | `www.googletagmanager.com` |
| POST the hit/beacon | `connect-src` | `www.google-analytics.com`, `region1.google-analytics.com`, `*.analytics.google.com` |
| Fallback pixel (noscript/imgs) | `img-src` | same analytics hosts |

A CSP that allowlists only the loader — the common hand-written case — lets the script run and
then **blocks every beacon**. The browser reports it only as a console CSP violation, which nobody
reads on production.

The trap is sharper with regional routing: GA4 sends hits to a **regional** subdomain
(`region1.google-analytics.com`), not only the apex `www.google-analytics.com`. Allowlisting the
apex host alone passes local testing and drops real traffic.

## Diagnose: never accept "the tag is in the HTML" as evidence

Three probes, in order. Each rules out a different layer.

```bash
# 1. Is the ID actually in the served HTML? (a NEXT_PUBLIC_* / build-time value)
curl -s https://<site>/ | grep -o 'gtag/js?id=G-[A-Z0-9]*' | head -1

# 2. What does the CSP actually allow?
curl -sI https://<site>/ | grep -o 'script-src[^;]*'
curl -sI https://<site>/ | grep -o 'connect-src[^;]*'

# 3. Can the beacon endpoint be reached at all?
curl -s -o /dev/null -w "%{http_code}\n" "https://www.google-analytics.com/g/collect?v=2&tid=G-XXXX"
```

Then close the loop in a **real browser**, because only a browser enforces CSP. A script that
loads the page, waits for the beacon, and reports whether a `/g/collect` request was actually sent
is the tight loop for this class:

```ts
// intercept requests; a blocked beacon shows up in requestfailed, not request
page.on("request",       r => /\/g\/collect/.test(r.url()) && hits.push(r.url()));
page.on("requestfailed", r => blocked.push(r.url() + " :: " + r.failure()?.errorText));
page.on("console",       m => m.type() === "error" && consoleErrors.push(m.text()));
```

Assert on the `tid` query parameter of the sent hit equalling the expected ID, and on the absence
of a `Content Security Policy` console error. That combination is the only proof the whole chain
works — ID embedded, CSP permitting, beacon transmitted.

## Fix

Widen `connect-src` (and `img-src` if a pixel fallback exists) to the analytics hosts, including
wildcards for regional subdomains:

```
connect-src 'self' https://www.google-analytics.com https://*.google-analytics.com
             https://*.analytics.google.com https://www.googletagmanager.com
```

Keep `script-src` as tight as before — the loader host alone is enough there.

## Pitfalls

- **`NEXT_PUBLIC_*` (and any framework's build-time public var) is baked in at build time, not
  read at runtime.** Setting it in the env file and restarting the service changes nothing; the
  ID must be rebuilt in. Symptom: you "configured" analytics and the HTML still has no ID. Always
  `build` then `restart`, and verify by grepping the served HTML for the ID.
- **A near-miss env var name fails silently.** A pre-existing `NEXT_PUBLIC_GA` alongside the
  expected `NEXT_PUBLIC_GA4_ID` reads as "already configured" while the code reads a different
  key. Confirm the exact key the config module reads rather than trusting `grep` for a prefix.
- **The provider dashboard lag is not a bug.** Realtime appears within seconds; standard reports
  take 24–48 hours. Do not "fix" a working install because yesterday's report is empty. Say this
  to the user up front — it prevents a second round of debugging on a healthy system.
- **Analytics counts humans, the server log counts requests.** Analytics will always read lower
  than nginx/Apache logs, because it only counts clients that executed JavaScript. The smaller
  number is the more truthful one for editorial decisions; do not present the gap as data loss.
- **Never weaken a security control to make tracking work.** Do not add `'unsafe-eval'`, drop the
  CSP, or disable `nosniff` to fix a beacon. Allowlist the specific hosts instead.
- **One ID, one stream.** Two IDs on one site splits the data and makes both streams look partly
  broken.

## Handing this to a non-technical owner

The account/property/stream creation happens in a browser the agent does not control. Write the
steps as a numbered walkthrough with the exact field values (timezone **and** currency, which are
easy to get wrong and corrupt every daily report), and state plainly that only the public
Measurement ID is needed — never a password, 2FA code, or account recovery. Finish with a
verification step the owner can run themselves (open the provider's Realtime view) so they are not
waiting on the agent to confirm it works.
