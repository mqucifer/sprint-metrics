# sprint-metrics

Reports how the crew is performing: cycle time, lead time, throughput per
sprint, WIP-limit violations, blocked-card aging, and escalation rate — as a
table, as JSON, and as markdown for the standup issue.

**This repository is built by agents.** The Sponsor sets the goal; the crew
proposes the epics, writes the stories, implements them, reviews, and merges.
See [mqucifer/crew](https://github.com/mqucifer/crew) for the organization
that builds it, and its `docs/ways-of-working.md` for the rules those agents
follow.

Only the scaffolding here was written by hand — enough that CI is green and the
crew has something to branch from.

## Installation

Requires Python 3.12. No third-party runtime packages are needed — the tool
uses only the standard library.

```
uv pip install git+https://github.com/mqucifer/sprint-metrics.git@v0.1.0
```

After installation the `sprint-metrics` command is available on the PATH.

## Basic usage

```
sprint-metrics cards.json
```

`cards.json` is a JSON file of sprint cards. When no file argument is given,
the tool reads the JSON from standard input and prints the default table.
