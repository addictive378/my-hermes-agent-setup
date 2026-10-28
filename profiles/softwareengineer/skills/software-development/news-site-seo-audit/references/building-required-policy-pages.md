# Building the Required Policy Pages

Use when an SEO audit has found the site's own footer/header linking to
`/tentang`, `/kontak`, `/privasi`, `/syarat`, `/pedoman` (or About/Contact/Privacy/Terms/
Editorial-policy) and those routes return 404. Reporting the 404s is only half the job — these
pages are a Google News requirement, so they have to exist.

## Why it matters more than it looks

These links render on **every** page, so every reader and every crawl sees the broken state. A
news site cannot be approved for Google News without working About, Contact, and editorial-policy
pages, no matter how good the articles are. Fixing them is usually the single highest-impact
change available — it can drop an audit's blocker count substantially in one commit.

## Read the nav config to get the real route list

Do not infer routes from the rendered footer alone, and do not guess at English paths. The nav
config is the authoritative list, and the slugs are whatever the config actually uses
(Indonesian here: `/tentang`, `/kontak`, `/privasi`, `/syarat`, `/pedoman` — not `/about`,
`/contact`, `/privacy`).

```bash
grep -n 'footerNav' -A 30 src/lib/config.ts
```

Probing the wrong slugs (`/privacy`) returns 404 and manufactures a finding that the route is
missing when only the path name differs. Probe the exact hrefs the config emits.

## Required sections per page

Each page needs real substance — Google News reviewers read them. Minimum viable content:

| Page | Must contain |
|---|---|
| About | Who publishes it; editorial principles (accuracy, balance, transparency, accountability); how articles are produced; **policy on AI assistance**; corrections stance; publisher block (owner, responsible editor, email) |
| Contact | Official email; a subject-line convention (`[KOREKSI]`, `[HAK JAWAB]`, `[TIPS]`, `[KERJA SAMA]`); response-time target; right-of-reply procedure; source-confidentiality note |
| Privacy | What is collected (server logs, analytics, email, newsletter); explicit *what we do not do* (no selling data, never asks for passwords/card data); cookies; reader rights and how to exercise them |
| Terms | Permitted use (quoting with attribution); prohibited use (full copying, scraping, misrepresenting); IP ownership; limitation of liability; third-party services; governing law |
| Editorial policy | Verification before publishing; confirming with subjects of negative coverage; source protection; separating fact from opinion; ad/sponsored labelling; **AI-use policy**; tiered corrections policy (typo → correction note → prominent correction); how to submit a correction |

Two sections are load-bearing for approval and are easy to omit: the **AI-use disclosure**
(if any automation touches production) and the **corrections policy** (state plainly that articles
are corrected rather than quietly deleted).

## Single-source the publisher identity

Put every identity value in one config object and read it from all pages. Editing the same email
or editor name in five files guarantees drift.

```ts
export const publisherConfig = {
  owner: "<from owner>",
  legalEntity: null as string | null,   // null if no registered entity exists
  email: "<from owner>",
  address: null as string | null,       // null if owner has not supplied one
  editorInChief: "<from owner>",
  foundedYear: <year>,
} as const;
```

Have the Contact page render the address conditionally (`{address && <li>…</li>}`) so supplying
the value later needs no page edits.

## When the owner has not supplied a required field

Two fields routinely go missing: a registered legal entity, and a physical editorial address.
**Never invent them.** A fabricated publisher entity or address carries legal weight — it is
misrepresentation on a page whose whole purpose is accountability — and it is grounds for a
Google News rejection.

Model the absence, do not paper over it:

- Keep the field `null` in `publisherConfig`.
- On Contact, state the situation honestly: correspondence is handled by email while no physical
  editorial address is established, and the address will be published here once it exists.
- Omit the entity block entirely rather than claiming a PT/yayasan that is not registered.

This satisfies the reviewer (the page is complete and truthful) without asserting anything
untrue. Ask the owner for the two values in the same message that delivers the finished pages, so
filling them later is a one-line change.

## Verify against the crawler UA, then reconcile the sitemap

Add the new routes to the sitemap generator (a hardcoded list of the static paths alongside the
article entries) and confirm both:

```bash
UA="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
for p in /tentang /kontak /privasi /syarat /pedoman; do
  printf "%-14s " "$p"; curl -s -o /dev/null -w "%{http_code}\n" -A "$UA" "https://<site>$p"
done
curl -s https://<site>/sitemap.xml | grep -oE 'site/(tentang|kontak|privasi|syarat|pedoman)' | sort -u
```

Success condition: every footer href returns 200 **and** appears in the sitemap. Then re-run the
full audit — the blocker count should drop and the remaining findings should all be the
per-article ones (missing author, over-length title/description).

## Pitfalls

- **Fabricating the address or legal entity to reach a green checklist.** The checklist exists to
  ensure accountability pages are real; inventing the content defeats it and risks rejection.
  Leave `null`, say so on the page, and ask.
- **Building the pages but forgetting the sitemap.** The routes work for readers but search
  engines only learn about them from the sitemap or an internal link crawl. Add them explicitly.
- **Guessing English slugs.** Use the hrefs the nav config emits; a 404 on `/privacy` when the
  site links `/privasi` is a self-inflicted finding.
- **Hardcoding the "last updated" date inside each page and then editing the text later.** Either
  centralise it or remember to bump it — a stale date on a policy page is a credibility tell.
- **Skipping the AI-use and corrections sections** because they seem optional. Both are directly
  in scope for news-publisher review and are the most commonly missing sections.
