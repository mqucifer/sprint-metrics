# Running the service

Part of the [service reference](../service.md).

## Starting the service

The service reads its database connection string from the `SPRINT_METRICS_DB` environment variable. The Dockerfile sets no default; the variable must be provided at runtime. If `SPRINT_METRICS_DB` is not set or the database is unreachable at startup, the service exits with a non-zero code.

```
docker run -d -p 8080:8080 \
  -e SPRINT_METRICS_DB=postgresql://sprint:secret@db.internal:5432/sprint_metrics \
  ghcr.io/mqucifer/sprint-metrics:1.0.0
```

The service creates and migrates its schema at startup. It listens on port 8080 inside the container.

## Automatic recovery

If the Postgres server restarts (for example, when Docker Desktop restarts), the service reconnects to its database automatically. No container restart is required for the service to resume answering requests.

While the database is unavailable, all query endpoints return HTTP 503. Once the database is reachable again, the endpoints resume returning HTTP 200 without any operator intervention.
