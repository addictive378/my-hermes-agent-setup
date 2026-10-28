---
name: news-site-seo-audit
description: "Audit technical SEO on a live news/content site."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [SEO, Google News, structured-data, sitemap, RSS, indexing, audit]
    related_skills: [systematic-debugging, production-data-changes, obsidian]
---

# News Site SEO Audit

## When to Use

Use when asked to improve traffic, "get to the top of Google", get indexed, get into Google
News/Discover, or audit SEO on a live content site. Also use before recommending any
traffic-dependent monetization (ad network, sponsored placement).

Do NOT answer these questions with generic SEO advice from memory. Every recommendation must be
anchored to a probe you actually ran against the deployment. Report measured state first, then
suggestions clearly labelled as suggestions.

**State your limits honestly.** If you are an engineering agent and not an SEO specialist, say
so. What you CAN do is verify what search engines require technically — and that is where most
real blockers live.

## Non-negotiables

1. **Audit the live deployment, not the source.** A route that exists in the repo can still 404
   in production (missing build step, wrong matcher, dynamic segment swallowing it). Every claim
   comes from a `curl` against the running site.
2. **Report measured state before advice.** Lead with the table of what you probed and what came
   back. Advice without a preceding measurement is exactly the generic answer the user can get
   anywhere.
3. **Separate fact from suggestion.** Mark your own suggestions as suggestions. Never imply a
   ranking guarantee — no one can promise a position in Google.
4. **Never invent editorial or legal data.** Publisher name, contact email, editorial address,
   responsible editor, author names — these come from the owner. Fabricated About/Contact details
   are a legal problem and a Google News rejection. Draft with an explicit `[ISI]` placeholder and
   ask.
5. **Warn about what can deindex the site.** Buying backlinks, copying other outlets, clickbait
   titles, mass AI filler — these can remove the site from Google entirely and undo all other
   work. Say so unprompted.
6. **Never recommend ad monetization on traffic you have not measured.** See the section below.

## Procedure

### 1. Probe the crawl surface first

Start with what search engines actually fetch, using a crawler UA so nothing is user-agent gated:

```bash
UA="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
curl -s -A "$UA" https://<site>/robots.txt
curl -s -o /dev/null -w "sitemap.xml: %{http_code}\n" -A "$UA" https://<site>/sitemap.xml
curl -s -o /dev/null -w "news-sitemap: %{http_code}\n" -A "$UA" https://<site>/news-sitemap.xml
curl -s -o /dev/null -w "rss: %{http_code}\n" -A "$UA" https://<site>/rss.xml
```

Check: robots.txt allows crawling and names every sitemap; `/admin`, `/api`, build internals
disallowed; public media (`/uploads/`) NOT disallowed (Discover and Images need it crawlable).

### 2. Reconcile the sitemap against the source of truth — both directions

```bash
curl -s https://<site>/sitemap.xml | grep -o '<loc>[^<]*</loc>' | sed 's/<[^>]*>//g' | sort -u
psql "$DATABASE_URL" -tAc "select slug from articles where status='published' order by published_at desc"
```

A set difference in EITHER direction is a finding:

- artifact lists something not published → it will send crawlers to 404s;
- published record missing from artifact → it may never be indexed.

Do not compare against a list you typed by hand. See the pitfalls.

### 3. Validate structured data on a real article page

```bash
curl -s -A "$UA" https://<site>/<category>/<slug> \
  | grep -oE '"(datePublished|dateModified)":"[^"]*"'
curl -s -A "$UA" https://<site>/<category>/<slug> \
  | grep -oE '"@type":"NewsArticle"|"author":[^,]*|"@type":"BreadcrumbList"'
```

Requirements for a valid `NewsArticle`:

| Field | Requirement |
|---|---|
| `headline` | non-empty |
| `image` | absolute URL(s) |
| `author` | **required for news** — a `Person` with a name at minimum |
| `publisher` | `NewsMediaOrganization` with logo |
| `datePublished` / `dateModified` | **ISO 8601** — `2026-10-25T05:24:56.605Z` |
| `mainEntityOfPage` | absolute canonical URL |
| `BreadcrumbList` | present |

Also check canonical (absolute, matches the path), OpenGraph, and the **rendered** `<title>`
length (≤ ~60 chars — after the layout's title template appends the site name) and meta
description 120–160 chars.

Length findings are usually bulk, not one-off. Fixing them has a trap: the stored title is not the
rendered one, and naive truncation silently changes meaning. See
`references/shortening-titles-and-descriptions.md` for the suffix-aware budget, the
`seo_title`/`seo_description`-only rule, and the tail-cleanup that keeps truncated titles readable.

Run the packaged auditor instead of retyping these curls — see `scripts/audit-seo.ts`
(it exits non-zero on blockers, so it can gate a deploy).

### 4. Hunt broken links, especially the policy pages

Sweep every link the site emits about itself — footer, header, and any nav config:

```bash
for p in /tentang /about /kontak /contact /redaksi /privasi /syarat /pedoman \
         /kebijakan-editorial /pedoman-media-siber; do
  printf "%-28s " "$p"; curl -s -o /dev/null -w "%{http_code}\n" -A "$UA" "https://<site>$p"
done
```

**A footer linking to routes that were never built is the highest-impact finding on a news
site.** Every visitor and every crawl sees those 404s on every page. Google News requires
working About / Contact / editorial-policy pages; without them the site will not be approved
regardless of how good the articles are.

Reporting the 404s is only half the job — these pages have to be **built**. See
`references/building-required-policy-pages.md` for the required sections per page, the
single-source publisher-config pattern, and the rule for fields the owner has not supplied
(model the absence honestly; never invent an address or legal entity).

Read the nav config, not the rendered page — the config is the full list:

```bash
grep -n 'footerNav' -A 30 src/lib/config.ts
```

### 5. Cross-check the published/unpublished boundary

```bash
psql "$DATABASE_URL" -c "select status, count(*) from articles group by status"
psql "$DATABASE_URL" -tAc "select slug, status, published_at from articles order by published_at desc"
```

**Unpublished records 404 on purpose — that is correct behaviour, not a bug.** Before reporting
"articles are broken", confirm the ones failing are actually `published`. A publish-mode default
holding every ingest in `draft` looks identical from the outside to a broken renderer, and it is
an editorial decision, not a technical fault. Report it as workflow state, not as an error.

### 6. Audit repeatedly — package it as a script

SEO regressions return with every content/publish change. Ship the checks as a re-runnable
script (`scripts/audit-seo.ts`, `scripts/audit-content.ts`, `scripts/traffic-summary.sh`) and
reference them in the report so the owner can re-check without you.

### 7. Register with the search engines (owner action, you assist)

**Google Search Console is the highest-leverage step and the most commonly skipped.** Without
it there is no visibility into which pages are indexed, which queries bring visitors, or what
crawl errors exist. Adding it is not optional for a news site.

1. Owner adds a Domain property and verifies via DNS TXT (most robust).
2. If the app already reads a verification env var, ask for the token and wire it — do not ask
   for account credentials.
3. Submit `sitemap.xml` and `news-sitemap.xml` in the Sitemaps section.
4. Review the Pages report for indexed vs excluded.

Google News Publisher needs, beyond the above: About/Contact/editorial-policy pages, authors with
real identities and profile pages, a written corrections policy, and original content.

**A missing `author` is often a CMS gap, not a data-entry lapse.** If the audit reports articles
published without an author, check whether the admin form can even express one — a dropdown fed by
a fixed author table means an ingest-driven site can only attribute people already in that table,
so new writers silently publish unattributed. The durable fix is an editable author field that
resolves a typed name case-insensitively against existing records and creates a new one only when
none matches (unique-slug collision handled with a numeric suffix). That keeps the author table
from filling with near-duplicates of the same person. Ship it before asking the owner to work
through the backlog, then have them fill the articles — attribution is an editorial decision.

**Once authors exist, check the profile pages are in the sitemap — not just live.**
`/penulis/<slug>` (or `/author/<slug>`) routinely renders fine while never appearing in
`sitemap.xml`, because the generator was written for articles and categories. Author identity is
exactly what News/Discover reviewers weigh, so a live-but-unlisted profile is invisible to the
crawl that would count it. Verify both, in one pass:

```bash
UA="Mozilla/5.0 (compatible; Googlebot/2.1)"
curl -s "https://<site>/sitemap.xml" | grep -c "penulis"     # 0 = never advertised
for s in $(psql "$DATABASE_URL" -tAc "select slug from authors where is_active='true'"); do
  printf '%-20s ' "/penulis/$s"; curl -s -o /dev/null -w "%{http_code}\n" -A "$UA" "https://<site>/penulis/$s"
done
```

Add them to the generator joined against published articles, so only profiles that actually have
content are listed — an empty author page in the sitemap is a soft-404 that wastes crawl budget.

## Traffic Before Monetization

**Never green-light an ad network on reported traffic you have not cleaned and measured.**

Raw access logs are dominated by bots and scanners. Measuring "pageviews" from an unfiltered log
produces a number that is both wrong and dangerous: ad networks pay per impression and forbid bot
traffic, so buying into that traffic risks account suspension.

Order of operations — it cannot be reversed:

```
fix SEO → Search Console → Google News → publish consistently
        → real readers → THEN ads
```

Measure a clean baseline first (filter the log, exclude crawlers, separate article pages from tag
directory sprawl), state it as a literal number, and only then discuss CPM. Be explicit about
which figure is a server-log request count and which is genuine human readership; only GA4 (or
equivalent) shows the latter.

`scripts/traffic-summary.sh` produces that clean baseline from an nginx access log — run it
before quoting any traffic figure. It prints article vs homepage vs tag-directory split and
warns that the tag-directory count is usually crawler sprawl, not readers.

Note that the nginx bot filter should be active before measuring; see the
`nginx-log-cleaning-and-bot-filtering` reference in the **systematic-debugging** skill
(`skill_view('systematic-debugging', 'references/nginx-log-cleaning-and-bot-filtering.md')`),
and `references/csp-blocked-analytics-beacons.md` in that same skill. The second one covers the
analytics install that looks healthy but reports zero, which is what you will be reading the
numbers from.

When the user asks to install ads at a traffic level that makes the revenue meaningless, say so
plainly with the measured numbers, give the risk (account suspension), and offer to proceed if
they still want it — the decision is theirs, but they must have the number.

## Pitfalls

- **Never report an unverified fix as done.** Compiling and restarting proves the build works,
  nothing about runtime output. Fetch the live page and quote the literal before/after value.
- **`db.execute()` returns database-native values, not JS types — timestamp columns come back as
  strings, not `Date`.** A date mapper that only handles `Date` (e.g.
  `raw instanceof Date ? raw.toISOString() : raw`) passes the raw PostgreSQL text
  `2026-10-25 12:24:56.605+07` straight through. That string is not ISO 8601, and **Google
  silently drops `datePublished`/`dateModified` it cannot parse**, costing News/Discover
  eligibility. It also leaks into sitemap `<lastmod>` as a mix of valid and invalid formats.
  Fix the mapper to parse strings through `new Date(...)` and emit `toISOString()`, guarding for
  `NaN`, and note that one shared mapper fixes JSON-LD and sitemap at once. Reading the DB via
  `psql` shows the same text format — do not mistake it for the wire format.
- **Do not build a probe list by hand, then call the artifact wrong.** Derive URLs from the live
  artifact itself (`curl sitemap.xml | grep -o '<loc>…'`) and probe exactly those. Probing slugs
  you typed from a stack of articles — including ones never published — manufactures failures
  that look like breakage. Reconcile in both directions and check the generator's own filter
  (`status='published'`) before editing it.
- **A 404 on an article is not automatically a rendering bug.** Check the record's status first.
  Drafts are supposed to 404; a publish-mode default quietly holding ingest in draft produces the
  same symptom and is the more likely cause on an ingest-driven site.
- **Trusting `curl` output over the rendered DOM for analytics/JS.** Presence of a tag in HTML does
  not prove the script ran. Drive a real browser and confirm the network beacon. See the reference
  `references/csp-blocked-analytics-beacons.md` inside the **systematic-debugging** skill.
- **Skipping Search Console because "the sitemap is fine".** A correct sitemap does not mean pages
  are indexed. They are separate systems; without Console you are guessing about the one that
  decides visibility.
- **Auditing only the entity types you thought of.** A sitemap that lists every article but no
  author profiles, no static policy pages, passes an article-focused check while omitting the URLs
  Google News actually weighs. Enumerate the site's *own* entity kinds (articles, categories,
  authors, static pages) and reconcile each against the artifact, rather than reconciling
  `articles` alone.
- **Fabricating policy-page content to satisfy the checklist.** About/Contact/editorial-policy
  text carries legal weight (who is responsible for published content). Draft the structure, mark
  unknown fields `[ISI]`, and ask the owner. Never invent a publisher entity, address, or editor
  name — and when the owner supplies some fields but not others, publish the pages with the missing
  ones `null` and an honest sentence explaining the absence rather than leaving the page broken or
  filling the gap with something plausible. Once the owner does supply them, state the real
  arrangement explicitly on the page — e.g. a site run by an individual with no registered
  legal entity should say so, since reviewers and readers both want to know who is accountable.
  See `references/building-required-policy-pages.md`.
- **Truncating titles by naive word count.** A title cut to fit the character budget can end on a
  dangling preposition or lose the unit of a number (`…Terbuka 2` from `2,8T`), which reads as a
  typo and damages trust on exactly the pages you are trying to rank. Prefer a clause boundary,
  then strip dangling tail tokens. See `references/shortening-titles-and-descriptions.md`.

## Reporting

Lead with the measured findings table, then order the work by impact:

1. Blockers (broken policy-page links, invalid structured data, missing sitemap entries)
2. Owner-action items (Search Console, News Publisher, editorial data only they can supply)
3. Candidate improvements (title/description lengths, missing author attribution)
4. Long-game items (publishing cadence) — labelled as not the engineer's to drive

Close with what you can start now versus what needs their input, and say which decisions are
editorial rather than technical. Bullets or labeled lines for chat output — no tables there.

Record the audit and the strategic plan in the vault (`20-Research/` for strategy,
`10-Systems/` for operational notes, `90-Log/` for what was changed) and push.
