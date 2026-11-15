# Workshop: fixture - a workshop composed from scenario steps

## Introduction

A workshop page that follows the page contract: one scenario played twice, then its own rows.

## Personas

| Persona | Used for |
|---|---|
| **fixture-01** | Every block: no sign-in, no cluster. |

## Agenda

| Time | Block | Play | Transition to the next block |
|---|---|---|---|
| 0:00 | Opening | The message, then [the agenda](#agenda) on screen | "One scenario, played twice." |
| 0:02 | The scenario | [Fixture demo](../scenarios/fixture/fixture-demo.md#5-minute-version), 5-minute version | "Now one step of the longer version." |
| 0:07 | One more read | [Fixture demo, 15-minute version](../scenarios/fixture/fixture-demo.md#15-minute-version), only its pipe step (5:00) | "And the workshop's own rows." |
| 0:09 | Own rows | [The workshop's own table](#the-workshops-own-table), inline | |
| 0:12 | Close and questions | Repeat the message | |

## Presenter lifecycle

`make demo use fixture-workshop` selects this page.

### Status

Nothing to do. The scenario's status file runs, then the workshop's own.

### Check

Nothing to do.

### Install

The scenario's install writes the fixture add-on marker: one confirmation, the workshop's id.

### Start

Nothing to do.

### Stop

Nothing to do.

### Uninstall

The scenario's uninstall removes the fixture add-on marker.

## The workshop's own table

| Time | Do | Say | You should see |
|---|---|---|---|
| 0:00 | Terminal: `git log -1 --format=%s` | "The workshop's own read." | A commit subject. |
| 2:00 | Close the block | "Done." | |

## If something goes wrong

| Symptom | Fallback | Say |
|---|---|---|
| Anything | Read the log under ~/.cache/zuno/demo/logs. | "Let me check." |

## References

- The workshop lifecycle (WP-280).

## Page status

> **Status:** Test fixture of platform/demo/tests (WP-280). It needs no cluster.
