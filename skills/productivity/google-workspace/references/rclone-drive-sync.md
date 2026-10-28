# rclone + Google Drive Two-Way Sync

Load this when the user wants a Drive folder synchronized to the local
filesystem (not just one-off uploads) — a "workspace on Drive", a shared asset
folder, or a backup destination. rclone's `bisync` is the right tool for two-way;
`mount` needs FUSE and is not necessary for a headless server.

## Configure the remote from the existing OAuth token

Reuse the token already obtained via this skill's setup — the user must not
authorize a second OAuth client for the same account:

- `rclone config create` is NOT reliably non-interactive for the `drive` type
  (it can hang waiting for input on a non-TTY and stall the turn). **Write
  `~/.config/rclone/rclone.conf` directly instead**, building the token JSON from
  `~/.hermes/google_token.json`:

If it does hang, kill it by PID (`ps -eo pid,args | grep rclone`, then
`kill <pid>`) — **never `pkill -f "rclone config"`**. `-f` matches the full
command line of the `bash -c "… pkill -f …"` shell running your cleanup, so the
pattern SIGTERMs your own turn instead of the hung process.

```bash
python3 - <<'PYEOF'
import json, os, pathlib
tok = json.load(open(os.path.expanduser('~/.hermes/google_token.json')))
rclone_token = {
    "access_token": tok.get("token"),
    "token_type": tok.get("token_type", "Bearer"),
    "refresh_token": tok.get("refresh_token"),
    "expiry": tok.get("expiry"),
}
conf = pathlib.Path(os.path.expanduser('~/.config/rclone/rclone.conf'))
conf.parent.mkdir(parents=True, exist_ok=True)
conf.write_text(
    "[gdrive]\ntype = drive\n"
    f"client_id = {tok['client_id']}\n"
    f"client_secret = {tok['client_secret']}\n"
    "scope = drive\n"
    f"token = {json.dumps(rclone_token)}\n"
)
os.chmod(conf, 0o600)
PYEOF
```

Never print the client_secret, access token, or refresh token — keep them inside
the script's variables and the config file.

Then verify: `rclone lsd gdrive: --max-depth 1`.

## Path addressing pitfall

A remote path of the form `gdrive:<folder-id>` fails with "directory not found"
— the drive backend does not treat a bare ID as a path. Address folders by
**name path** from the root (`gdrive:Hermes/writer-workspace`), or set
`root_folder_id` in the remote's config. Find the name path with
`rclone lsjson gdrive: --dirs-only`, or via the Drive API when the folder sits
under a shared parent.

## Bisync

First run must seed the pairing state, and it is one-directional in intent —
it makes Path2 (local) mirror Path1 (remote):

```bash
rclone bisync "gdrive:Hermes/<folder>" /local/path --resync
```

After that, run without `--resync` for true two-way. Wrap in a script with:

- `flock -n` on a lock file — two overlapping syncs corrupt state;
- `--max-depth` left alone, `--verbose` piped to `tail` to keep logs bounded;
- cron cadence 5–10 minutes with a distinct `# tag` comment so the entry is
  idempotent when re-installed via `(crontab -l | grep -v tag; echo line) | crontab -`.

**The "too many deletes" guard:** when many files disappear on one side between
runs (e.g. cleanup), bisync aborts rather than propagate the deletions — it
refuses to continue until state is rebuilt. A sync script must detect this and
log the exact remedy (`rclone bisync <path1> <path2> --resync`), not fail
silently. After any cleanup that removes several files at once, expect one
failed run and re-run with `--resync`.

## Testing a new pairing

1. `--resync` initial (empty folder: instant).
2. Create a file locally, run the sync, verify it appears with
   `rclone lsf "gdrive:<path>/"`.
3. Create a file on the remote side, run the sync, verify it lands locally.
4. Run the script once under a stripped cron environment
   (`env -i HOME=... PATH=/usr/bin:/bin ...`) — rclone lives in
   `/usr/local/bin`, which a minimal PATH does not always include.
5. Clean up test artifacts on BOTH sides and run `--resync` once more; deleting
   test files triggers the deletes guard otherwise.

## Per-profile access

rclone uses one remote config (`~/.config/rclone`) per OS user, not per Hermes
profile. If profiles need their own credentials, copy the token file to each
profile home and call this skill's `google_api.py` with
`HERMES_HOME=<profile home>` — the API wrapper resolves the token from there.
