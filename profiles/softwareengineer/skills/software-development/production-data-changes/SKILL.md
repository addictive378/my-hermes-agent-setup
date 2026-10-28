---
name: production-data-changes
description: "Safely clean or delete rows in a live database."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [PostgreSQL, Production, Data, Safety, Deployment]
    related_skills: [obsidian]
---

# Production Data Changes

## When to Use

Use when the user asks to clean, reset, delete, migrate, or bulk-edit data in a live database — "bersihkan konten", "kosongkan", "hapus semua", "reset dulu". A loose request against production is a data-loss request in disguise: recon, confirm, back up, execute in a transaction, then verify through the running app.

## Non-negotiables

1. **Never delete production rows on an ambiguous request.** "Bersihkan" could mean delete, unpublish, or archive. Enumerate the concrete rows you found, then ask via `clarify` with choices (delete / partial delete / unpublish), recommended option first. This is the one case where a round-trip beats guessing.
2. **Dump before you delete.** `pg_dump -Fc` to a dated file in the workspace backup dir, confirm the file size, and only then touch data. A backup you never verified exists is not a backup.
3. **Choose the minimum blast radius.** Keep lookup/seed tables downstream automation depends on (authors, categories, tags, settings, admin accounts) unless expressly asked. Deleting a lookup table breaks the import/API path that references it by slug — that failure surfaces later as an ingest job that cannot post.
4. **Delete inside one transaction with `ON_ERROR_STOP=1`**, FK children before parents. Partial cleanup leaves orphan links and half-empty pages.
5. **Verify through the live surface.** HTTP status, the rendered empty state, zero leftover links in the HTML, and the sitemap. A DB count of 0 does not prove the site stopped serving the old content — cached pages and stale sitemap entries still return 200 to crawlers.
6. **Record it in the vault** (`90-Log/`) and push — a production data change is exactly what the next agent needs to know about.
7. **After a bulk delete, audit the routes that READ the deleted data for cached negative results.** Emptying tables does not empty the framework's cache. A detail route that cached `null`/404 while the table was empty will keep soft-404ing every new record inserted afterwards — see the pitfall below.
8. **Invalidation is a code change that needs its own proof.** Every mutation path that writes content back (admin create/update/autosave, ingest API) must invalidate the exact routes that read it. Fix all of them in one pass, not just the one the user reported: a missing invalidate on autosave or on the ingest API surfaces later as "edits do not show up" or "published but 404".

## Procedure

### 1. Recon before touching anything

Load the connection string into the shell, never into the transcript:

```bash
cd ~/news-web
set -a && . ./.env.local && set +a
psql "$DATABASE_URL" -c "\dt"
psql "$DATABASE_URL" -c "select * from articles limit 20"
```

If a URL is ever printed, redact the password (`sed 's/:[^:@]*@/:***@/'`). Env files with secrets stay mode 600; never copy them elsewhere.

Then count every table in one pass so lookup data can be told apart from content data:

```bash
for t in $(psql "$DATABASE_URL" -tAc "select tablename from pg_tables where schemaname='public'"); do
  echo "$t: $(psql "$DATABASE_URL" -tAc "select count(*) from $t")"
done
```

Classify before proposing: content rows (what the user wants gone), join/link rows (cascade or delete explicitly), lookup/seed rows (authors, categories, tags, settings, users — usually keep). Detect fixture data by markers the project's seed script writes into titles/descriptions.

### 2. Confirm the scope with the user

Report findings as concrete numbers and titles, state which tables you will keep and why, then ask. Put alternatives in `clarify` choices (recommended first), not in prose the user has to parse.

Tie the recommendation to a real code path: "writer/ingest posts drafts with `authorSlug` + `category`, so emptying those tables breaks the next import." Not to aesthetics.

### 3. Back up

```bash
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p ~/workspace/softwareengineer/backups
pg_dump "$DATABASE_URL" -Fc -f ~/workspace/softwareengineer/backups/<db>_pre-<change>-$TS.dump
ls -lh ~/workspace/softwareengineer/backups/<db>_pre-<change>-$TS.dump
```

`-Fc` (custom format) so a single table can be restored later with `pg_restore -t`. Print the size — a 0-byte dump means you are about to be the incident.

### 4. Execute in one transaction

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
DELETE FROM child_links;
DELETE FROM other_children;
DELETE FROM main_table;
COMMIT;
SQL
```

Order: join tables → dependent rows → parent rows → now-unreferenced lookup rows (only if asked). Re-count every table afterwards and show before/after in the report.

Expect an approval prompt on `DELETE` without `WHERE`; that gate is correct — do not route around it with `TRUNCATE` or a `WHERE true` clause.

### 5. Verify through the live app

```bash
curl -s -o /dev/null -w "home: %{http_code}\n" https://<site>/
curl -s -o /dev/null -w "admin: %{http_code}\n" https://<site>/admin
curl -s https://<site>/ | grep -o 'href="/artikel/[a-z0-9-]*"' | sort -u | wc -l   # expect 0
curl -s https://<site>/ | grep -ci 'marker-of-deleted-content'                     # expect 0
curl -s https://<site>/sitemap.xml | grep -c '<url>'                               # crawled URLs left
```

An authenticated admin route returning 401/403 is the correct result — it proves the auth layer still works. Treat a 200 there as a red flag worth reporting.

Data-only changes need no restart; say so explicitly instead of rebuilding the app "to make the change visible". Rebuild only if the live page still serves stale content after the DB is clean.

### 6. Log to the vault and push

The log note (`90-Log/YYYY-MM-DD - <what changed>.md`) must cover: the instruction and who asked, the option chosen and why, backup path with the exact restore command, a before/after table of every affected table, what was deliberately kept and why, the verification commands with literal results, and remaining follow-ups. Commit and push that single note — the vault is the team's source of truth, so an unpushed note does not exist.

Never run the app's `db:seed` against a database that now holds real content; seed scripts re-insert the fixtures just deleted. Say so in the log when the project has one.

## Reporting to the user

Short structured summary: what was deleted (counts), what was kept (counts), literal verification results, backup path, vault note path and commit. Bullets or labeled lines — no tables in Telegram output, no restated reasoning. Close with the one thing they may want next ("tag seed rows still there — say the word if you want those gone too").

## Pitfalls

- **Do not audit a surface with a list you assembled by hand.** When checking "is the sitemap complete / are all published items readable", pull the URLs *from the live artifact* (`curl sitemap.xml | grep -o '<loc>[^<]*'`) and probe exactly those. Probing a list you typed from a database query instead proves something nobody asked about, and its failures look like real breakage. Reconcile both directions: live artifact → DB, and DB (published only) → live artifact. A set difference in either direction is the bug report.
- **Before calling a live artifact wrong, dump its contents and diff them against the source of truth — do not trust your own probe list.** Two failure modes look identical from the outside and have opposite fixes: the artifact emits records it should not, or the artifact is correct and your comparison list was wrong. A mixed probe ("I requested ten slugs and six 404'd") tells you nothing, because the six may be unpublished drafts that were never meant to be in the artifact. Confirm with one command — `curl sitemap.xml | grep -o '<loc>[^<]*'` diffed against the published rows — then check what the artifact's own filter (`status='published'`) actually selects. Getting this backwards sends you debugging a correct generator while the real cause sits upstream: content that was never published, or a publish-mode default quietly holding every ingest in draft.
- **"Fixed" is a claim about a write path you exercised, not about code you just wrote.** Adding the invalidation call, compiling, and restarting proves the build works — nothing more. Before reporting a cache/visibility fix, mutate a field through the real write path, fetch the public URL, and quote the before/after values. If you cannot exercise it end-to-end, say the fix is unverified instead of implying it works.
- `psql` exits 0 on a failed statement unless `ON_ERROR_STOP=1` is set — without it a partially applied cleanup looks successful.
- `DELETE FROM articles` does not remove rows in join tables lacking `ON DELETE CASCADE`; count those tables before and after, not just the parent.
- Lookup rows can look like content rows in a count listing. Read a few titles first; the seed `tags`/`authors` table is what breaks the ingest API, not the articles table.
- A sitemap still listing deleted URLs keeps sending crawlers to 404s long after the DB is clean — check it as part of verification every time.
- Deleting rows does not clear an app-level cache or static props. If the live page still shows old rows, look at revalidation/ISR config before concluding the delete failed.
- **A bulk delete poisons cached not-found results, and the damage shows up days later as "new content does not load".** Framework caches that store per-key results (Next.js `"use cache"` + `cacheLife`, ISR pages, query-result caches) happily cache the `null` from a lookup performed against an emptied table. Every record created afterwards resolves to that stale 404 until its TTL expires or the path is revalidated. When you clean a table, immediately audit the ingest/create paths that write back into it: they must call `revalidatePath`/`revalidateTag` (or the framework equivalent) on insert, not only the admin UI. Tell the user this explicitly — the follow-up bug looks unrelated to the cleanup and burns an hour of debugging otherwise.
- **An audit/log column is not a public column — check what the reader query selects, not just what the writer writes.** Mutation paths often record a generic internal note on every save (`changeNote: "Revision before update by <name>"`). If a public query selects the latest such note unfiltered and a component renders it when non-null, that memo is shown to readers on every edited record — it looks like a published correction banner. Fix it by filtering the internal marker in the query (keep the audit rows intact), not by deleting the component: the legitimate correction feature must survive, and UI-level hiding leaves the leak in other consumers (feeds, JSON-LD, API). A string marker shared between writer and reader is an implicit contract — changing the text in one place silently re-enables the leak, so comment it at both ends. After changing content rows for any reason, re-check the public pages of a few edited records for internal fields that leaked.
- **Verification leaves artifacts. Sweep them in the same pass that proves the fix.** Testing a write path end-to-end against production means you *created* production data: a draft article, a row you inserted to check rendering, an uploaded file now sitting in the media directory, a test slug that may have been published and cached. A probe that passes and then stays behind is a self-inflicted incident — the user's content list grows a record they did not write, and a crawler may index it. Before reporting done: delete the rows you created, delete the media files you uploaded, re-count the tables you touched, and say the counts match the pre-test baseline. Do not assume deleting the row cleans up its files — media directories are not foreign-keyed and the orphan survives the delete. Also revert any status transition you triggered (a test article left `published` is live content, not a fixture).
- **Removing a row does not clear the public surface it populated.** Cached listing pages, the sitemap, and the RSS feed can keep advertising a record you just deleted, so the cleanup looks incomplete to anyone checking the live site. Re-check sitemap/feed/listing counts after the delete, and revalidate those paths rather than concluding the DB delete failed.
- **A `revalidatePath` call is not proof of invalidation — verify the path exists as a real route.** Writing `revalidatePath` and declaring the cache bug fixed is the trap: revalidating a path the app does not serve clears nothing and fails silently (no error, no warning), while the page keeps serving stale HTML. Worse, a plausible-looking wrong path can still *render* through a catch-all/slug segment (`/artikel/<slug>` catching `[category]/[slug]`), so a manual click looks fine and hides the bug. Derive the path from the record's own fields (`categorySlug` + `slug`) and confirm the template that actually serves it — for a route like `app/[category]/[slug]/page.tsx` there is no `/artikel/` route, and revalidating one does not clear the other's cache entry. Prove it with a write, not with reasoning: change a field, fetch the public URL, and assert the new value appears; if the call runs outside a request context (a plain script) `revalidatePath` throws `Invariant: static generation store missing`, so test through the real server action/route, not a side script.
