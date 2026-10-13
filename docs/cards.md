# Card input format

Each card is a JSON object describing one card on the sprint board. The top-level
value in the cards file must be a JSON array (list) of card objects.

Only `created` is required; all other fields are optional. An empty array `[]` is
valid input and produces a report in which every metric is zero.

BEGIN:input-format
| Field | Required | Type | Description |
|---|---|---|---|
| `created` | Yes | ISO-8601 date | When the card was created |
| `started` | No | ISO-8601 date | When work started on the card |
| `completed` | No | ISO-8601 date | When the card was completed |
| `created_at` | No | ISO-8601 datetime | When the card was created (sub-day precision) |
| `started_at` | No | ISO-8601 datetime | When work started on the card (sub-day precision) |
| `completed_at` | No | ISO-8601 datetime | When the card was completed (sub-day precision) |
| `blocked_since` | No | ISO-8601 date | When the card was blocked |
| `attempts` | No | integer | Number of attempts (default: 1) |
| `failure_class` | No | string | Classification of the failure |
| `failure_role` | No | string | Role responsible for the failure |

```json
[
  {
    "created": "2024-01-03",
    "started": "2024-01-05",
    "completed": "2024-01-10",
    "blocked_since": "2024-01-06"
  },
  {
    "created": "2024-01-04"
  }
]
```
END:input-format

The datetime fields `created_at`, `started_at`, and `completed_at` are optional
ISO-8601 datetime strings (with timezone offset) that enable sub-day precision.
They are distinct from the date-only fields `created`, `started`, and `completed`,
which carry no time-of-day information. When only the date-only fields are
provided (without the corresponding `_at` datetime fields), the minute-level
metrics (`cycle_time_minutes` and `lead_time_minutes`) report null.
