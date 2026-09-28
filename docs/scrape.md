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
