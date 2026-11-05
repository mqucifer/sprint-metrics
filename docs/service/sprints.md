# Sprint registration

Part of the [service reference](../service.md).

The service accepts sprint definitions via POST /sprints. Each sprint is registered by name before events that reference it are posted. The body carries the sprint's name, start date, end date, and timezone. If a sprint with the same name is already registered, its definition is updated in place.
