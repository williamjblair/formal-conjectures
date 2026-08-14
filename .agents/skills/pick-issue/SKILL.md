---
name: pick-issue
description: Choose an issue in this repository that is genuinely unclaimed and within reach, before any formalisation work starts. Use when asked to find something to work on, to check whether an issue is taken, or before claiming an issue.
license: Apache-2.0
---

# Pick an issue

The expensive failure this prevents is finished work that collides with someone
else's open pull request. Assignees and issue comments do not tell you whether an
issue is taken. People open pull requests without commenting on the issue, and
issues stay assigned to people who stopped working months ago.

## Step 1: collect candidates

```
gh issue list --repo google-deepmind/formal-conjectures --state open --limit 100 \
  --json number,title,labels,assignees,updatedAt
```

Prefer issues that name a concrete file or problem number. An issue that names
nothing concrete needs scoping before it needs an owner, which is a comment, not
a claim.

## Step 2: the claimed check, which is the point of this skill

An issue is claimed if **any open pull request touches the file it concerns**,
whatever the issue page says. Check by path, not by conversation:

```
gh pr list --repo google-deepmind/formal-conjectures --state open --limit 400 \
  --json number,title,files \
  --jq '.[] | select(.files[]?.path | test("<the file>")) | "#\(.number) \(.title)"'
```

Run this with the *full path* of every file the issue concerns. Then check the
issue page too, for a claim that has no pull request yet:

- an assignee whose activity is recent
- a comment claiming it within the last two weeks
- a linked draft pull request

A stale assignee with no pull request and no recent activity is not a claim, but
say so in your comment when you take the issue, so the earlier claimant can
object.

An explicit stand-down comment releases an issue no matter what the assignee
field says. The reverse also holds: silence is not a release.

## Step 3: is it within reach

Read the issue's file at current `main` and the source it cites before deciding.
Three questions, in order:

1. **Is the issue still true?** Issues outlive their defects. Check the file on
   `main` for the thing the issue describes before planning anything; a merged
   fix does not always close its issue.
2. **Is the mathematics within your reach?** A statement-fidelity fix (wrong
   bound, wrong quantifier, missing hypothesis) needs source reading. A new
   formalisation needs the source *and* Mathlib vocabulary. A proof needs the
   most. Take the smallest kind you can finish.
3. **Does it need a decision you cannot make?** Issues that hinge on repository
   policy, on a maintainer's preference between two faithful readings, or on
   upstream (erdosproblems.com, Mathlib) belong in a comment thread, not a
   working branch.

## Step 4: claim it

Comment once, briefly, saying what you will do. Then branch off current `main`
and do it. Do not claim more than one issue at a time, and release with a
comment if you stop.

## Output

Report the chosen issue with: the path check you ran and its result, the staleness
evidence if you are overriding an assignee, and the kind of work it needs. If
nothing qualifies, say what you checked and why each near-miss failed; that
report is the deliverable, not a failure.
