# Scrape mode

Scrape mode runs an HTTP server that exposes the current sprint metrics for
collection by Prometheus or any compatible scraper. The cards file is re-read
on every request, so board changes are reflected without a restart.

BEGIN:scrape
Start an HTTP server that serves the current sprint metrics at /metrics.

The cards file is re-read on every request so that changes to the board are
reflected without a restart. Returns the port the server is listening on.

Endpoints:
- `/metrics` — Prometheus text exposition format
- `/json` — JSON API response
END:scrape

## Running the scrape server

The `--scrape` flag starts an HTTP server instead of printing a report to stdout.
Use `--port 0` to let the OS assign an ephemeral port; the actual port is printed
at startup.

Given a cards file (`cards.json`) with one completed card:

```json
[{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}]
```

Start the scrape server:

```
sprint-metrics cards.json --scrape --port 0
```

The startup message is printed to stdout (the port is ephemeral):

```
sprint-metrics: serving metrics at http://127.0.0.1:45678/metrics
```

### /metrics

An HTTP GET to `/metrics` returns the Prometheus text exposition format:

```
sprint_cycle_time_days 4
sprint_lead_time_days 6
sprint_throughput_cards 1
sprint_wip_violations 0
sprint_blocked_aging_days 0
sprint_escalation_rate_percent 0
sprint_first_attempt_rate_percent 100
```

### /json

An HTTP GET to `/json` returns the JSON API response:

```json
{"api_version": "1", "cycle_time_days": 4, "lead_time_days": 6, "throughput": 1, "wip_violations": 0, "blocked_aging_days": 0, "escalation_rate_percent": 0, "first_attempt_rate_percent": 100, "failure_breakdown": [], "top_failure_causes": {}, "flags": {"cycle_time_days": false, "lead_time_days": false, "throughput": false, "wip_violations": false, "blocked_aging_days": false, "escalation_rate_percent": false, "first_attempt_rate_percent": false}}
```

### Error handling

If the cards file is deleted while the server is running, subsequent requests to
`/metrics` return HTTP 500 with a body containing `sprint-metrics:`.
