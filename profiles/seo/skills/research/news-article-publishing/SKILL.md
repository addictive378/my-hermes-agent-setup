---
name: news-article-publishing
description: "Research news, write the article, upload to news-web."
version: 1.0.0
author: Hermes Writer (writer profile)
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Writing, News, SEO, Publishing, Indonesia, WartaNusantara]
    category: research
    related_skills: [agent-reach, grounded-citations, obsidian]
---

# News Article Publishing (Warta Nusantara)

Use when asked to research news and publish articles to the site — e.g. "lakukan riset lalu
tulis artikel dan upload di news-web", "cari berita viral lalu tulis artikel". Covers sourcing
with the read-only `agent-reach` CLI, viral-topic selection, drafting to house style, and
uploading to the Next.js CMS as **drafts**.

Deliverable = articles actually created in the CMS (verified in Postgres), plus an archive
note in the Obsidian vault. Not a description of what you would write.

## When to Use

Use when the owner asks for news/blog articles that end up on the production site —
"lakukan riset lalu tulis artikel dan upload di news-web", "cari berita viral, tulis
artikelnya", "tulis artikel dari berita ini lalu kirim ke CMS". Also for revising or
re-uploading an existing draft, and for checking what a previous batch actually published.

Not for: standalone research briefs with no upload, video scripts (videomaker owns those), or
quick chat answers about the news. Traffic/visitor questions about the site itself are a
different job — see `references/site-traffic-audit.md`.

## Where things live

| Thing | Path / value |
|---|---|
| Site repo | `~/news-web` (Next.js + PostgreSQL), live at `https://wartanusaku.site` |
| Secrets + integration config | `~/news-web/.env.local` (`DATABASE_URL`, `HERMES_API_KEY`, `NEXT_PUBLIC_SITE_URL`, `HERMES_DEFAULT_PUBLISH_MODE`, `HERMES_PERMISSIONS`) |
| Integration contract | `~/news-web/docs/HERMES_INTEGRATION.md` — read before any schema change |
| Upload endpoint | `POST /api/integrations/hermes/articles` (Bearer key, schema_version `1.0`) |
| Obsidian vault | `~/.hermes/obsidian` — `20-Research/` candidate map, `40-Drafts/` sent-package note |

Load `docs/HERMES_INTEGRATION.md` and `src/lib/hermes-validation.ts` for the exact field list.
Never paste the API key or `DATABASE_URL` into chat.

## Procedure

① **Intake.** Take the topic scope from the owner's message (e.g. "berita berpotensi viral").
State the assumptions you are making (Indonesian audience, `indonesia` category, batch size) in
the final report; do not stall on questions for a routine batch.

② **Sweep sources with Agent Reach.** Say "using the agent-reach skill (channel web)" first.
Fan out rather than trusting one tag page:

```bash
agent-reach web search "berita viral Indonesia hari ini" --limit 5
agent-reach web search "<specific event keywords>" --limit 4   # one query per candidate
```

Tag pages of detik / Antara / CNN Indonesia / Liputan6 / tvOne are good coverage maps
(they show what is trending), but a tag page's summary list is not an article. For every
candidate you intend to write, `agent-reach read <article-url>` the actual page.

③ **Select for viral potential** using all four gates:
1. Emotional or public-reaction hook (outrage, sympathy, absurdity, contrast).
2. An official or named source who can be quoted — heat without attribution is not writable.
3. Already covered by several outlets → evidence of search demand, and a cross-check corpus.
4. Fresher than about a week.

Prefer **angle over recap**: what is the second-order question the other outlets skip? (The
legal risk of the mob, the effect on honest vendors nearby, the contrast between two outbreaks
of the same behaviour.) A chronology rewrite is not a publishable article.

Write the selection map to `20-Research/<date> Peta Berita Viral - Kandidat Artikel.md`
**before** drafting, so the ranking is inspectable.

④ **Draft.** One article = H1 → 2-paragraph lead → kronologi / `Yang perlu diketahui` → 2–3
analysis H2s → `Yang belum jelas` → closing → sources. House rules:
- Bahasa Indonesia, baku-santai, active voice, short paragraphs.
- Quote officials verbatim in `<blockquote>` with attribution in the surrounding sentence.
- Anything not confirmed by a source goes under `Yang belum jelas` and is labelled a claim,
  not a fact (e.g. a single Instagram post's price).
- Crime/legal pieces: "diduga", "menurut polisi", plus a short note that the explanation is
  general and not legal advice.
- Meta title ≤70, meta description ≤160 — the API returns 422 if these overflow.

⑤ **Upload as draft.** Read `HERMES_API_KEY` / `NEXT_PUBLIC_SITE_URL` from `.env.local` inside
a Python script (never on the shell command line, never in chat) and POST JSON with curl
`--data-binary @-`. Helper pattern in `references/news-web-upload.md`.
Always `requested_status: "draft"`, a unique `idempotency_key`, `category_slug` / `author_slug`
that exist in the DB, `sources[]` for every claim, `editorial_notes` + `research_warnings` for
what a human editor must check, and `disclosure_text` stating AI-assisted research.

⑥ **Verify against the database, not the response body.**

```bash
DBURL=$(grep -m1 '^DATABASE_URL=' ~/news-web/.env.local | cut -d= -f2- | tr -d '"')
psql "$DBURL" -c "select a.slug,a.status,length(a.body),c.slug,
  (select count(*) from article_sources s join articles_to_sources ats on ats.source_id=s.id where ats.article_id=a.id) srcs,
  (select count(*) from articles_to_tags t where t.article_id=a.id) tags
  from articles a left join categories c on c.id=a.category_id order by a.created_at desc limit 10;"
psql "$DBURL" -c "select seo_title,length(seo_title),length(seo_description) from articles order by created_at desc limit 10;"
```

Also check the live site (`curl -sS -o /dev/null -w '%{http_code}' https://wartanusaku.site/`
and `/api/health`) before reporting success.

⑦ **Archive to the vault.** `40-Drafts/<date> Paket Artikel Viral - Terkirim ke news-web.md`:
slug + article id per piece, sources, angle, warnings, what the editor must still do (featured
image, confirm unverified numbers), and the follow-up CTA. The owner checks the vault and repo
for progress — a chat reply alone is not a deliverable.

## Pitfalls

- **Retrying a timed-out POST destroys the work.** The idempotency hash covers the whole
  payload including `publication_context_time`, so a retry with a fresh timestamp returns
  `409 IDEMPOTENCY_CONFLICT` for an article that was in fact created. After any timeout or
  non-2xx, **query the DB for the slug first**; only retry (new `idempotency_key`) if the row
  is genuinely absent.
- **Trusting the HTTP client's failure over the server's state.** curl exiting non-zero or
  timing out does not mean the insert failed. The DB row is the source of truth.
- **Assuming upload = published.** Default integration is draft-only
  (`HERMES_DEFAULT_PUBLISH_MODE=draft`, permissions `articles:create,articles:read`).
  Publishing needs publish mode **and** `articles:publish`; never flip those unless the owner asks.
- **An empty read result is not proof the page lacks a body.** `agent-reach read` can return
  `ok:true` with zero items on some detik regional pages (jabar/sumut). Switch to the same
  story on another domain (news.detik.com, merdeka.com, cnnindonesia.com) instead of
  concluding the story is thin. When `items` is non-empty but `text` opens with menus and
  links, skip past the chrome to the first real paragraph — printing the whole page wastes
  context and buries the facts.
- **A tag/aggregator page is a coverage map, not evidence.** Headline lists from the viral tag
  pages tell you what is trending; every claim you write must come from `agent-reach read` on
  the article page itself.
- **Inventing category or author slugs.** They must already exist; an unknown slug silently
  inserts a NULL relation and the article renders uncategorised. Query `categories` /
  `authors` first.
- **Writing one article per trending headline.** Two adjacent events can make one comparative
  piece that is stronger than either recap; also check the DB for an existing near-duplicate slug.
- **Pasting `.env.local` values into the report or chat.** Read them in-process only.
- **Double-appending the endpoint path.** In cron runs `NEWS_WEB_API_URL` already holds the
  *complete* endpoint (`https://wartanusaku.site/api/integrations/hermes/articles`). POST to
  `"$NEWS_WEB_API_URL"` as-is; adding `/api/integrations/hermes/articles` again returns a
  `404` HTML page that looks like a missing route but is just a wrong URL.
- **Omitting `idempotency_key`.** The cron integration rejects the payload with
  `422 VALIDATION_ERROR` ("expected string, received undefined"); the key must be present on
  every POST, not only on retries.
- **Drafting long, then trimming in a loop.** Scheduled political articles carry a hard
  400–700 word brief. In cron there is no `python -c`/heredoc, so every trim is a separate
  written `.py` file — drafting straight to ~650 words saves many cycles. Write the draft to
  hit the range the first time, then build the payload and POST.
- **A `200` on `/uploads/<file>` does not mean the image is served.** Under `next start`, files
  added to `public/uploads/` after the last build are NOT served; the catch-all route answers
  with an HTML page that still returns `200`. Always check `%{content_type}` (want `image/jpeg`),
  not the status code. Fix = `npm run build` + `sudo -n systemctl restart news-web` (service
  `news-web.service`, port 3000). Do that build once per batch at a quiet moment, never per upload.
- **Re-POSTing to attach a featured image.** The endpoint accepts `featured_image_url` only on
  create; for an existing draft, `UPDATE articles SET featured_image_url=..., alt=... WHERE
  slug=...` via psql is the correct route (the integration has no update verb).
- **Draft articles 404 on the public page but still render a shell.**
  `/<category>/<slug>` returns `200` with `<title>Artikel Tidak Ditemukan</title>` for drafts —
  that is expected, not a broken image or a broken slug.
- **The same 404 on a `published` row is a real rendering bug, not a draft.** Run
  `select slug,status,published_at from articles where status='published'` before you conclude
  anything about traffic. If published rows 404 on `/<category>/<slug>`, stop and report it;
  writing more articles cannot help until the article pages render.

## Cover images when no stock photo exists

There is no licensed stock library and no image-gen API on this box, and scraping news photos
is a copyright violation. Generate an original editorial cover instead:

```bash
python3 -m venv /tmp/imgenv && /tmp/imgenv/bin/pip install pillow
# script draws a 1200x675 JPEG into ~/news-web/public/uploads/, then rebuild+restart
```

House look that passed review: 1200×675 (16:9), dark gradient background, short accent bar +
uppercase kicker (`KATEGORI · LOKASI`) in amber/teal, serif bold headline, one sans subtitle
line with the 2–3 key facts, one flat vector motif per article. Then `finish()` the JPEG at
quality 86 (~50 KB).

Layout rules learned the hard way:
- Wrap with an orphan guard: if the last line holds a single word, pull one word down from the
  line above; if the whole headline fits one line, centre the text block vertically instead of
  leaving a huge empty band.
- Keep ≥30 px between the last text baseline and the canvas edge, and measure badge width with
  `draw.textlength()` before drawing — text silently overflows a `rounded_rectangle`.
- Verify with `vision_analyze` on the rendered JPEG (ask specifically about clipping and
  overlap); a second pass usually finds an overflow.
- Write alt text 80–120 chars describing the illustration *as an illustration*, not as a photo
  of the event — these are not real photographs.

## Verification

Do not report a batch as delivered until: each slug is present in `articles` with the expected
`status`, non-trivial `body` length, correct `category_id`, source count ≥ 2 and tag count ≥ 3;
`length(seo_title) ≤ 70` and `length(seo_description) ≤ 160`; site and `/api/health` return 200;
and the vault notes exist on disk.

Deeper recipes (upload helper, payload field reference, DB inspection queries) are in
`references/news-web-upload.md`. When the owner asks how many people read the site, follow
`references/site-traffic-audit.md` — raw nginx request counts overstate traffic by roughly an
order of magnitude on this box, so they must be filtered before any number reaches the owner.
