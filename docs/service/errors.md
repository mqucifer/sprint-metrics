# Error responses

Part of the [service reference](../service.md).

When the database is unreachable, POST /events, GET /range, and GET /trend each return HTTP 503 with a JSON body identifying the condition as transient. The event or query was not processed; the client should retain the request and retry after a short delay. The 503 body is a JSON object containing an "error" field that names the database as the cause and a "retryable" field set to true, so the sender can safely retry without losing data.

When an internal service error occurs (not caused by the database), the service returns HTTP 500. The client should not retry a 500; it indicates a bug in the service and should be reported as an issue. The 500 body contains a description of the unexpected condition.

A request that fails validation (for example, a /range query whose start label is after its end label) returns HTTP 400 regardless of database state, because validation is performed before any database query is attempted. The client should not retry a 400.

GET /sprint returns HTTP 410 with a JSON body identifying the endpoint as removed. The endpoint is gone; a range spanning one sprint (GET /range) answers the same question. The 410 is distinct from a transient condition (503), a validation failure (400), and a service bug (500); the caller should switch to GET /range and not retry.

GET /metrics returns HTTP 410 with a JSON body identifying the endpoint as removed, with or without a query string and whether or not the database is reachable. The service no longer offers its stored metrics as Prometheus text; GET /range and GET /trend answer them.
