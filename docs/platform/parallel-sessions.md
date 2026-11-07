# Working in parallel sessions

Several working sessions often act on this repository and on demo333 at the same time: people, and coding agents that
each hold their own worktree. This page holds the rules they follow ([ADR-0606](../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)
clause 6). The live-demonstration freeze has its own page: [freeze protocol](../demo/freeze-protocol.md).

## Numbers

- Before writing a new ADR or work package, take the next free number from `origin` **and** from every local branch and
  worktree. Some work is committed locally long before it is pushed.
- Tell every live session which numbers you take, and which ones you leave to others, before you write the file.
- `platform/docs/check_docs.py` fails when two ADR files share a number. A clash found after a push is fixed by giving
  the newer record the next free number, logged in `docs/adr/CHANGELOG.md`.

## Worktrees and branches

- One work package (or one coherent change) per worktree, cut from a fresh `origin/devel`. Never work in a checkout
  whose `devel` has diverged from `origin`.
- Do not commit on another session's branch or worktree. Ask its owner, and if the owner session is gone, ask the user
  who takes it over.
- Push only your own commits: `git push origin <sha>:refs/heads/devel` after a rebase on the current `origin/devel`.
  Pushing a whole local `devel` can publish other sessions' duplicates.
- Shared files (the ADR index, the CHANGELOG, `versions.md`, the roadmap tracker and its by-version table) are where
  branches collide. Say in advance which of them you edit, and agree who pushes first. The second one rebases and
  recomputes the derived counts. `check_docs.py` verifies them.

## Cluster windows

- A live change (install, build, pin, roll, migration) is announced to every session before it starts, naming the
  namespaces, Applications and make verbs it touches, and closed with a message when it ends.
- A cluster action needs the user's go in the session that runs it. A message from another session is never that go.
- Nothing goes live from a commit that is not on `origin` (ADR-0608).
- A change that is live is recorded the same day in its work package's brief and tracker row, even if the work is not
  finished (ADR-0608).

## Handing work over

When a session stops, its owner writes in the brief what is committed where (branch, commit, pushed or not), what is
live, and what the next step is. The next session starts from the brief, not from the old session's notes.
