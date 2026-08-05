---
name: progress-summary
description: Writes a dated progress summary (tech stack, what was built, what is left next week, open items) into the Summarization/ folder, auto-incrementing the session counter. Use when asked to summarize progress, write a session summary, record what was done this session, or wrap up for the day.
---

# Write a progress summary

Produces the next numbered summary in `Summarization/`, recording the current state of
the Ingredient-to-Recipe Chatbot project. Each file is a snapshot; together they form a
running ledger that feeds the Week 11–12 report writing and the Week 6 workload sync
with Person 1.

**This skill only writes the summary file.** It never edits project source.

## Step 1 — work out the next number

List `Summarization/`. Every file is named `YYYY-MM-DD_HHMM_N.md`. Take the trailing
`_N` from each, find the highest, add 1. If the folder is missing or empty, N = 1.

Derive the number from the filenames rather than from a stored counter — that way the
sequence can never drift out of step with what is actually on disk.

## Step 2 — get the real timestamp

Read the system clock (`date "+%Y-%m-%d %H%M (%A)"`). Do not infer the date from
conversation context, and do not reuse a date seen earlier in the session.

Filename: `Summarization/YYYY-MM-DD_HHMM_N.md`

## Step 3 — observe the real state, do not recall it

You may be invoked in a fresh session with no memory of the work. Even when you do have
that context, check anyway — the point of these files is that they are trustworthy.

- Run `python -m pytest tests/ -q` and record the **actual** output
- Read `requirements.txt` for the declared stack
- List the source tree to see which files exist
- If a git repo exists, `git log --oneline -10` for recent work

**Never copy a test result forward from the previous summary.** A stale "19 passed" in a
file dated three weeks later is worse than writing nothing.

## Step 4 — locate the roadmap week

Read PART B of `Claude.md` for the week-by-week plan. Work out which week the project is
currently in by comparing what exists on disk against the checklists, and read the
*next* week's section for the "what's left" content. Cite specific line numbers
(`Claude.md:374-394`) so the claims are checkable.

## Step 5 — read the previous summary

Read the previous file (N-1). Two reasons: match its structure so the sequence stays
consistent, and pick up its open-items table for Step 6.

Skip this on N = 1.

## Step 6 — write the file

Use these sections in this order:

1. **Header table** — date, session number, roadmap week, role, one-line status
2. **Tech stack** — table of Layer / Choice / Status. Status must honestly separate
   `✅ in use` from `⏳ declared, unused until Week N`. A stack list implying a library
   is working when it is only listed in `requirements.txt` misleads the future reader
   who has to fix it. Note anything needed but not yet installed
3. **What was built** — each file, its contract, and whether it is mock or real. Include
   frozen function signatures, since those are what Person 1 codes against
4. **Verification** — quote the real test output from Step 3
5. **Issues found and fixed** — especially anything environment-specific that will
   recur on a teammate's machine
6. **Next week** — checkboxes from the following week's roadmap section, with the
   reasoning behind any non-obvious constraint, not just the instruction
7. **Open items** — table of unresolved decisions, with why each matters and who owns it

## Step 7 — carry the open items forward

For each open item in the previous summary, check whether it is now resolved:

- **Still open** → copy it into the new table
- **Resolved** → note it as closed in the "What was built" section, and drop it
- **New** → add it

This is what turns a pile of snapshots into a ledger. An open item that quietly vanishes
between summaries is the failure mode to avoid — nothing should drop off without being
explicitly marked closed.

## Rules

- **Never overwrite an existing summary.** Always a new file with the next number. The
  history is the value.
- **Never claim a test passed without running it** in this session.
- **Record uncertainty as uncertainty.** "PyThaiNLP untested on 3.13" is useful.
  Silently omitting it is not.
- **Prefer specifics over adjectives.** "19 passed in 0.08s" beats "tests are working".
  "cp874 codepage cannot encode emoji" beats "fixed an encoding bug".
- Explain *why*, not just *what*. A future reader needs the reasoning to decide whether
  a decision still holds.
