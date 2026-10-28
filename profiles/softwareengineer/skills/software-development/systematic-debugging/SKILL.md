---
name: systematic-debugging
description: "4-phase root cause debugging: understand bugs before fixing."
version: 1.1.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [debugging, troubleshooting, problem-solving, root-cause, investigation]
    related_skills: [test-driven-development, subagent-driven-development]
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## The Feedback Loop Rule

The feedback loop is the debugging work. Before reading code to build a theory, create or identify a **tight** command that can go red on the user's exact symptom and green when the bug is fixed. A tight loop is fast, deterministic, agent-runnable, and specific enough to catch this bug — not merely "doesn't crash".

When a clean repro is hard, spend disproportionate effort building the loop. Guessing without a red-capable loop is the failure mode this skill exists to prevent.

## When to Use

Use for ANY technical issue:
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:**
- Issue seems simple (simple bugs have root causes too)
- You're in a hurry (rushing guarantees rework)
- Someone wants it fixed NOW (systematic is faster than thrashing)

## The Four Phases

You MUST complete each phase before proceeding to the next.

---

## Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

### 1. Read Error Messages Carefully

- Don't skip past errors or warnings
- They often contain the exact solution
- Read stack traces completely
- Note line numbers, file paths, error codes

**Action:** Use `read_file` on the relevant source files. Use `search_files` to find the error string in the codebase. For framework-produced error strings (Next.js, Django, Rails middleware), grep the framework's own `dist`/`site-packages` source for the message — it lands you on the exact guard clause and its condition in one step, which beats guessing at the cause.

### 2. Build a Tight Feedback Loop

- Can you trigger the user's exact symptom with one command?
- Does the command fail for this bug and only pass once the bug is fixed?
- Is it fast enough to run repeatedly?
- Is it deterministic? For flaky bugs, can you raise the reproduction rate high enough to debug?
- If not reproducible → gather more data, don't guess.

**Ways to construct a loop — try in roughly this order:**

1. **Failing test** at the seam that reaches the bug: unit, integration, or end-to-end.
2. **HTTP script / curl** against a running dev server.
3. **CLI invocation** with fixture input, diffing stdout/stderr against expected output.
4. **Headless browser script** (Playwright/Puppeteer) asserting on DOM, console, or network.
5. **Replay a captured trace**: HAR, request payload, event log, queue message, or webhook body.
6. **Throwaway harness** that boots the smallest useful slice of the system and calls the failing path.
7. **Property / fuzz loop** when the bug is intermittent wrong output over a broad input space.
8. **Bisection harness** suitable for `git bisect run` when the bug appeared between two known states.
9. **Differential loop** comparing old vs new version, two configs, two providers, or two datasets.
10. **Human-in-the-loop script** only as a last resort: script the human steps and capture their result so the loop stays structured.

**Tighten the loop once it exists:**

- Make it faster: cache setup, narrow scope, skip unrelated initialization.
- Make the signal sharper: assert the exact symptom, not generic success.
- Make it more deterministic: pin time, seed randomness, isolate filesystem, freeze network.

For non-deterministic bugs, the immediate goal is a higher reproduction rate, not perfection. Run the trigger 100x, parallelize, add stress, narrow timing windows, or inject sleeps. A 50% flake is debuggable; a 1% flake usually is not.

**Action:** Use the `terminal` tool to run the tight loop:

```bash
# Run a specific failing test
pytest tests/test_module.py::test_name -v

# Or run a scripted repro
python scripts/repro_bug.py

# Or run a high-repetition flaky repro
for i in {1..100}; do pytest tests/test_flake.py::test_name -q || break; done
```

### 3. Check Recent Changes

- What changed that could cause this?
- Git diff, recent commits
- New dependencies, config changes

**Action:**

```bash
# Recent commits
git log --oneline -10

# Uncommitted changes
git diff

# Changes in specific file
git log -p --follow src/problematic_file.py | head -100
```

### 4. Gather Evidence in Multi-Component Systems

**WHEN system has multiple components (API → service → database, CI → build → deploy):**

**BEFORE proposing fixes, add diagnostic instrumentation:**

For EACH component boundary:
- Log what data enters the component
- Log what data exits the component
- Verify environment/config propagation
- Check state at each layer

Run once to gather evidence showing WHERE it breaks.
THEN analyze evidence to identify the failing component.
THEN investigate that specific component.

### 5. Trace Data Flow

**WHEN error is deep in the call stack:**

- Where does the bad value originate?
- What called this function with the bad value?
- Keep tracing upstream until you find the source
- Fix at the source, not at the symptom

**Action:** Use `search_files` to trace references:

```python
# Find where the function is called
search_files("function_name(", path="src/", file_glob="*.py")

# Find where the variable is set
search_files("variable_name\\s*=", path="src/", file_glob="*.py")
```

### Phase 1 Completion Checklist

- [ ] Error messages fully read and understood
- [ ] A tight loop command exists and has been run at least once
- [ ] Loop is red-capable: it asserts the user's exact symptom, not a nearby failure
- [ ] Loop is deterministic, or a flaky bug has a high enough reproduction rate to debug
- [ ] Recent changes identified and reviewed
- [ ] Evidence gathered (logs, state, data flow)
- [ ] Problem isolated to specific component/code
- [ ] Root cause hypotheses can be stated and tested

**STOP:** Do not proceed to Phase 2 until you understand WHY it's happening.

---

## Phase 2: Pattern Analysis

**Find the pattern before fixing:**

### 0. Minimize the Reproduction

Once the loop is red, shrink the repro to the smallest scenario that still goes red. Cut inputs, callers, config, data, and steps **one at a time**, re-running the loop after each cut. Keep only what is load-bearing for the failure.

Done when removing any remaining element makes the loop go green. A minimal repro narrows the hypothesis space and often becomes the cleanest regression test.

### 1. Find Working Examples

- Locate similar working code in the same codebase
- What works that's similar to what's broken?

**Action:** Use `search_files` to find comparable patterns:

```python
search_files("similar_pattern", path="src/", file_glob="*.py")
```

### 2. Compare Against References

- If implementing a pattern, read the reference implementation COMPLETELY
- Don't skim — read every line
- Understand the pattern fully before applying

### 3. Identify Differences

- What's different between working and broken?
- List every difference, however small
- Don't assume "that can't matter"

### 4. Understand Dependencies

- What other components does this need?
- What settings, config, environment?
- What assumptions does it make?

---

## Phase 3: Hypothesis and Testing

**Scientific method:**

### 1. Form Ranked Falsifiable Hypotheses

- Generate 3–5 plausible hypotheses before testing any single one.
- Rank them by likelihood and cheapness to falsify.
- State the prediction each hypothesis makes: "If X is the cause, then changing or observing Y should make Z happen."
- Discard or sharpen any hypothesis that does not make a testable prediction.

If the user is present, show the ranked list before testing. They may have domain knowledge that instantly re-ranks it. If the user is AFK, proceed with your ranking.

### 2. Test Minimally

- Test the highest-ranked hypothesis with the smallest possible probe.
- Change one variable at a time.
- Don't fix multiple things at once.
- Prefer debugger/REPL inspection when available; one breakpoint beats ten logs.
- If you add logs, tag every temporary line with a unique prefix such as `[DEBUG-a4f2]` so cleanup is a single search.

### 3. Verify Before Continuing

- Did it work? → Phase 4
- Didn't work? → Form NEW hypothesis
- DON'T add more fixes on top

### 4. When You Don't Know

- Say "I don't understand X"
- Don't pretend to know
- Ask the user for help
- Research more

---

## Phase 4: Implementation

**Fix the root cause, not the symptom:**

### 1. Create Failing Test Case

- Simplest possible reproduction
- Automated test if possible
- MUST have before fixing
- Use the `test-driven-development` skill

### 2. Implement Single Fix

- Address the root cause identified
- ONE change at a time
- No "while I'm here" improvements
- No bundled refactoring

### 3. Verify Fix

```bash
# Run the specific regression test
pytest tests/test_module.py::test_regression -v

# Run full suite — no regressions
pytest tests/ -q
```

### 4. If Fix Doesn't Work — The Rule of Three

- **STOP.**
- Count: How many fixes have you tried?
- If < 3: Return to Phase 1, re-analyze with new information
- **If ≥ 3: STOP and question the architecture (step 5 below)**
- DON'T attempt Fix #4 without architectural discussion

### 5. If 3+ Fixes Failed: Question Architecture

**Pattern indicating an architectural problem:**
- Each fix reveals new shared state/coupling in a different place
- Fixes require "massive refactoring" to implement
- Each fix creates new symptoms elsewhere

**STOP and question fundamentals:**
- Is this pattern fundamentally sound?
- Are we "sticking with it through sheer inertia"?
- Should we refactor the architecture vs. continue fixing symptoms?

**Discuss with the user before attempting more fixes.**

This is NOT a failed hypothesis — this is a wrong architecture.

---

## Red Flags — STOP and Follow Process

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "Pattern says X but I'll adapt it differently"
- "Here are the main problems: [lists fixes without investigation]"
- Proposing solutions before tracing data flow
- **"One more fix attempt" (when already tried 2+)**
- **Each fix reveals a new problem in a different place**

**ALL of these mean: STOP. Return to Phase 1.**

**If 3+ fixes failed:** Question the architecture (Phase 4 step 5).

## Domain Playbooks

Some bug classes have a known signature and a known probe. Read the matching reference before
building a loop from scratch:

- `references/nextjs-image-and-cache-bugs.md` — Next.js production: images served via
  `/_next/image` that come back blank (SSRF guard rejecting own-host absolute URLs); new records
  soft-404ing while their list page shows them (`"use cache"` holding a cached `null`);
  **newly uploaded files serving the HTML 404 page** because anything written into `public/`
  after `next start` is missing from the boot-time static manifest; and **internal editorial
  notes rendering as public correction banners** because a public query reads an audit column
  unfiltered. Opens with a direct-vs-optimizer probe table that separates the classes in two curls.
- `references/csp-blocked-analytics-beacons.md` — an analytics install that reports **zero traffic**
  although the tag is in the HTML: `Content-Security-Policy` allowing the loader host but not the
  beacon hosts (including regional subdomains), plus the build-time-env and dashboard-lag traps
  that make a healthy install look broken.
- `references/nginx-log-cleaning-and-bot-filtering.md` — making server logs usable for decisions:
  measure the log for scanner signatures before writing any blocklist, block by `map` + a single
  `return 444` gate, and **route `access_log` through a `map` so blocked requests are not
  journaled at all** (a 444 from an `if` gate is still logged — the common wrong assumption).
  Covers matching scanner *stems* rather than variant names, dropping `^` anchors from
  generic-client patterns, re-measuring after the first pass because a blocklist never converges,
  the client matrix (readers, Googlebot, curl, scanners) that proves the filter broke neither
  monitoring nor SEO, and why to measure the clean reader baseline before recommending anything
  traffic-dependent such as ad networks that forbid bot impressions.

## Repro Behind an Auth Gate

Admin-only bugs (upload, save, publish) still need a tight loop. Never ask the user for a
password and never type one: mint a short-lived session token locally from the app's own
signing secret, then drive the real UI.

1. Sign a token with the app's own library and secret, short expiry, and write it `0600` outside
the repo — do not echo it:

```bash
node -e "
require('dotenv').config({path:'.env.local'});
const {SignJWT}=require('jose');
new SignJWT({userId:'<id>',email:'<email>',name:'Diag Probe',role:'super_admin'})
  .setProtectedHeader({alg:'HS256'}).setIssuedAt().setExpirationTime('20m')
  .sign(new TextEncoder().encode(process.env.SESSION_SECRET))
  .then(t=>require('fs').writeFileSync('/tmp/.probe_token',t,{mode:0o600}));
"
```

2. Set it as the session cookie in the browser via CDP before navigating, using the **host you
   will actually drive** — a cookie set for one host is not sent to another:

```python
cdp('Network.setCookie', name='<session-cookie>', value=open('/tmp/.probe_token').read().strip(),
    domain='127.0.0.1', path='/', httpOnly=True)
```

3. Drive the real flow (fill, upload, save, publish) and assert on what the UI reports about
   itself — `naturalWidth`/`naturalHeight` on an `<img>`, the URL field's value, presence of the
   success string — not on a screenshot.
4. Delete the token file when done.

Prefer this over the server-action + `Next-Action` header route when the bug is in the browser
layer (preview rendering, file input, client state); that route proves the server mutation, and
will happily pass while the UI stays broken.

If HTTPS from the browser tool fails but `127.0.0.1` works, drive the local instance of the same
production build — identical code and process type, without the TLS/proxy layer in the way. Do not
treat it as "the browser tool is broken".

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question the pattern, don't fix again. |

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **1. Root Cause** | Read errors, reproduce, check changes, gather evidence, trace data flow | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare, identify differences | Know what's different |
| **3. Hypothesis** | Form theory, test minimally, one variable at a time | Confirmed or new hypothesis |
| **4. Implementation** | Create regression test, fix root cause, verify | Bug resolved, all tests pass |

## Hermes Agent Integration

### Investigation Tools

Use these Hermes tools during Phase 1:

- **`search_files`** — Find error strings, trace function calls, locate patterns
- **`read_file`** — Read source code with line numbers for precise analysis
- **`terminal`** — Run tests, check git history, reproduce bugs
- **`web_search`/`web_extract`** — Research error messages, library docs

### With delegate_task

For complex multi-component debugging, dispatch investigation subagents:

```python
delegate_task(
    goal="Investigate why [specific test/behavior] fails",
    context="""
    Follow systematic-debugging skill:
    1. Read the error message carefully
    2. Reproduce the issue
    3. Trace the data flow to find root cause
    4. Report findings — do NOT fix yet

    Error: [paste full error]
    File: [path to failing code]
    Test command: [exact command]
    """,
    toolsets=['terminal', 'file']
)
```

### With test-driven-development

When fixing bugs:
1. Write a test that reproduces the bug (RED)
2. Debug systematically to find root cause
3. Fix the root cause (GREEN)
4. The test proves the fix and prevents regression

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common

**No shortcuts. No guessing. Systematic always wins.**
