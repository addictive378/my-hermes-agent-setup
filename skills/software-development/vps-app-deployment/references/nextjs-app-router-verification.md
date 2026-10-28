# Verifying Next.js App Router Apps and Their Auth Flows

Depth notes for an App Router app whose auth flow must be inspected or proven
fixed without a logged-in browser.

## Cookie mutation belongs in an action, never in render

`sessions().delete()`, `cookies().set()`, and any helper wrapping them
(`clearSessionCookie()`, `setSessionCookie()`) throw during a Server Component
render:

```
Error: Cookies can only be modified in a Server Action or Route Handler.
```

A page that calls them in its body turns every visit into an error page — Next
renders its generic client screen ("This page couldn't load / Reload to try
again") while the server still answers **HTTP 200** with an error digest in the
body. Symptom and status code look nothing like a 500, so the browser shows a
mystery failure and the network tab looks fine. The only reliable signal is the
server log (`journalctl -u <unit>`), not the page.

Move the mutation into a Server Action or Route Handler. Logout:

```ts
// src/app/**/actions/auth.ts
"use server";
export async function logoutAction() {
  await clearSessionCookie();
  redirect("/admin/login");
}
```

and render a control that actually submits:

```jsx
<form action={logoutAction}>
  <button type="submit">Keluar</button>
</form>
```

**Never put a `<Link>` inside a `<form>` as the control.** `<Link>` renders an
anchor and only navigates; the form never submits, so the "logout" silently does
nothing while looking wired up. `redirect()` is likewise legal only inside an
action or route handler, never during render.

## Invoke a server action from curl — no browser, no hydration

The action id is embedded in the rendered HTML of any page carrying the form:

```bash
curl -sS -H "Cookie: <cookie>=$TOKEN" http://127.0.0.1:<port>/<page> -o page.html
grep -oE '\$ACTION_ID_[a-f0-9]+' page.html | head -1
```

Submit it the way a no-JS browser would — form-encoded, with `Origin`/`Referer`
set and the action id as the field name:

```bash
curl -sS -X POST "http://127.0.0.1:<port>/<page>" \
  -H "Cookie: <cookie>=$TOKEN" \
  -H "Origin: http://127.0.0.1:<port>" \
  -H "Referer: http://127.0.0.1:<port>/<page>" \
  -F '$ACTION_ID_<id>=' -D - -o /dev/null
```

A working action answers `303 See Other` with both headers that prove it:

```
Set-Cookie: <cookie>=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT
Location: /<redirect-target>
```

Skip the `Next-Action: <id>` header with a `text/plain` body — it is rejected as
`Invalid Server Action request.` (400) unless the full RSC request shape is
reproduced. The form-encoded POST is the one that works.

## Minting a session without the password

Read the signing secret from the app's env file and the user row from the DB, then
sign the same claim shape the app verifies:

```bash
node -e "
const {SignJWT}=require('jose');const {Client}=require('pg');
require('dotenv').config({path:'.env.local'});
(async()=>{const c=new Client({connectionString:process.env.DATABASE_URL});await c.connect();
const r=await c.query(\"SELECT id,email,name,role FROM admin_users WHERE role='super_admin' LIMIT 1\");
const u=r.rows[0];
const t=await new SignJWT({userId:u.id,email:u.email,name:u.name,role:u.role})
 .setProtectedHeader({alg:'HS256'}).setIssuedAt().setExpirationTime('15m')
 .sign(new TextEncoder().encode(process.env.SESSION_SECRET));
require('fs').writeFileSync('/tmp/tk.txt',t,{mode:0o600});await c.end();})();"
```

Write the token to a mode-600 temp file, read it back with `TOK=$(cat ...)`, and
delete it when the probe is done. **Never echo a session token into chat.**

## Testing around the edge layers

- Test the app at `http://127.0.0.1:<port>` to bypass an nginx Basic Auth gate,
  and prove the gate separately by expecting `401` on `https://<domain>/admin`.
- A cookie the app sets with `secure: true` cannot be exercised over plain
  `http://127.0.0.1` in a browser. Use `curl` for the probe, or inject the cookie
  through CDP with `secure` off.
- Rate limits live in nginx, so localhost probes are never throttled — never
  conclude "the rate limit works" from localhost traffic.

## Status codes lie about auth state

A gated App Router path can answer `200` carrying only the public shell when no
session is present: the layout renders its unauthenticated branch instead of
redirecting. Assert on a marker that renders **only** when authenticated (the
admin nav labels, the signed-in email), never on the status code. Report the
missing redirect as its own finding — it is a different bug from the one you set
out to fix, and folding them together hides whichever one you did not verify.
