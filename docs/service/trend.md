# GET /trend

Part of the [service reference](../service.md).

GET /trend answers the question 'what was this metric in each of these sprints?' by returning a value for every sprint label in the requested calendar range, with null for a sprint that has no events, so a gap reads as no data rather than zero. The range is specified by explicit start and end labels consistent with /range: `GET /trend?metric=throughput&start=2024-01&end=2024-04`.
