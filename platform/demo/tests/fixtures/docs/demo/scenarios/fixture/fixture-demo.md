# Scenario: fixture - the presenter lifecycle end to end

## Introduction

A demo page that follows the page contract, used to prove the path action, runner playbook, results, page section.

## Personas

| Persona | Used for |
|---|---|
| **fixture-01** | Every step: no sign-in, no cluster. |

## Presenter lifecycle

`make demo use fixture-demo 5|15` selects this page.

### Status

Nothing to do. The file reads the last commit and whether the fixture add-on marker exists.

### Check

Nothing to do.

### Install

The file writes the fixture add-on marker. Check that `status` now reports it installed.

### Start

What only a person does:

- [ ] Open two terminals.
- [ ] Read the first step aloud.

### Stop

Nothing to do.

### Uninstall

The file removes the fixture add-on marker.

## 5-minute version

Profile 1, **fixture-01**.

| Time | Do | Say | You should see |
|---|---|---|---|
| 0:00 | Terminal: `git log -1 --format=%h` | "One read, no shell." | A short commit id. |
| 1:30 | Optional: `oc delete pod fixture -n fixture` | "This one changes the cluster: it is never run by the step." | |
| 4:00 | Close | "The page is the source of truth." | |

## 15-minute version

Run the 5-minute version, then:

| Time | Do | Say | You should see |
|---|---|---|---|
| 5:00 | Terminal: `git log -2 --oneline \| head -1` | "A pipe, still no shell." | One line. |
| 6:00 | Terminal: `git show zuno-fixture-no-such-ref` | "A read that fails on purpose." | An error, then the fallback below. |
| 14:00 | Close | Repeat the message. | |

## If something goes wrong

| Symptom | Fallback | Say |
|---|---|---|
| The 6:00 read fails | It always does: this row proves the failure path. | "Expected." |
| Anything else | Read the log under ~/.cache/zuno/demo/logs. | "Let me check." |

## Limits

- A fixture shows the engine, not a demo.

## Appendix A - HLD

The fixture has no platform map.

## Appendix B - LLD

The fixture has no internals.

## References

- ADR-0616: the presenter lifecycle (WP-270).

## Page status

> **Status:** Test fixture of platform/demo/tests (WP-270). It needs no cluster: its files read the local git history
> and write a marker under the test's HOME.
