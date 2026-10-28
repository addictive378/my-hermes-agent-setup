# Shortening Titles and Meta Descriptions Safely

Use when the audit reports over-length `<title>` or meta description on many articles, and the
owner asks you to fix them in bulk.

## Measure the RENDERED title, not the stored field

This is the trap that makes a "fix" look pointless. The layout usually wraps article titles in a
template:

```ts
// src/app/layout.tsx
export const metadata: Metadata = {
  title: { default: siteConfig.name, template: `%s — ${siteConfig.name}` },
};
```

So a stored title of 55 characters becomes a 75-character `<title>`. Auditing the database column
(65 chars, "under control") while Google sees 84 is how you conclude the titles are fine when they
are not.

**Always compute the budget after subtracting the suffix:**

```
stored title budget = 60 - len(" — " + siteName)
```

With a 20-character suffix the real budget is 40. Measure the live tag to confirm:

```bash
UA="Mozilla/5.0 (compatible; Googlebot/2.1)"
T=$(curl -s -A "$UA" "https://<site>/<category>/<slug>" | grep -oE '<title>[^<]*</title>' | head -1 | sed 's/<[^>]*>//g')
printf '%3d  %s\n' "${#T}" "$T"
```

## Change `seo_title`/`seo_description`, never the article headline

The on-page headline is an editorial decision. Shortening it automatically damages the piece and
is not yours to make. Write the shortened value into the SEO override column so the page keeps
its voice and only the machine-facing metadata changes:

```ts
await db.update(articles).set({
  seoTitle: shortened,        // article.title untouched
  seoDescription: shortenedDesc,
  updatedAt: new Date(),
}).where(eq(articles.id, id));
```

Say this explicitly in the report — the owner will otherwise assume their headlines were cut.

## Automatic truncation breaks meaning — post-process the tail

Naive whole-word trimming produces titles that read as broken, and the owner will notice before
Google does:

| Naive result | Problem |
|---|---|
| `Kimi K3.1 Pro: Model AI Terbuka 2` | dropped the `,8T` unit — the number now means something else |
| `U-15 Indonesia 7-1 Fiji lalu 0-3 Wales di` | dangling preposition |
| `Tenggat Lewat, Timsel KPU-Bawaslu Belum` | dangling auxiliary, sentence incomplete |

Rules that fix this, applied in order:

1. **Prefer a clause boundary** (`:`, `—`, `-`, `,`, `;`) at or before the budget, keeping at
   least half the budget — a shorter complete clause beats a longer truncated one.
2. **Otherwise trim whole words** (never mid-word).
3. **Then strip a dangling tail** — a trailing preposition, conjunction, or auxiliary
   (`di ke dari dan atau untuk dengan pada dalam jadi agar lalu usai soal atas bagi oleh hingga
   sampai sejak antara terhadap kepada yang ini itu belum sudah telah akan masih bisa dapat
   harus perlu mulai bakal`), and a trailing bare number that lost its unit.
4. **Re-apply step 3 in a loop** until stable — removing one token can expose another.

For descriptions, split on sentence boundaries and keep whole sentences up to the cap; fall back
to whole-word trimming, then terminate the truncated text with a period so it does not read as
cut off. Target 120–160.

## Always dry-run before writing

Build the script with a `--apply` flag and print the before/after table on a bare run. The
broken-truncation table above is exactly the sort of thing a dry run surfaces cheaply, and it is
much easier to reject a bad transformation than to revert one across 16 rows.

```bash
npx tsx scripts/shorten-seo.ts           # preview
npx tsx scripts/shorten-seo.ts --apply   # write
```

Back up the database before `--apply` — the rewrite touches every published row.

## Bulk DB writes bypass the revalidation path

A script editing rows directly does **not** fire `revalidatePath`, so cached pages keep serving
the old metadata. After `--apply`: rebuild, restart, then re-run the auditor against the live
site and read actual title lengths back. Confirming the column changed is not the verification;
confirming the served `<title>` changed is.

## Close the loop with a zero state

Re-run `scripts/audit-seo.ts` and report the literal count — the goal is `Total masalah: 0`
across all published articles, not a smaller number. That is the only statement that tells the
owner the technician-facing work is finished.
