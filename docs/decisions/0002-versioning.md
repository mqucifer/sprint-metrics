# 2. The package version and the API version are separate

- **Date:** 2026-09-28
- **Status:** Accepted

## Context

The tool is released as a package and an image, and its JSON answers carry their own `api_version`.

## Decision

The package follows SemVer, separately from `api_version`. A new API version is a MINOR release; removing one is MAJOR; fixes and docs are PATCH. The first release is 1.0.0, and API v1 is already a promised contract.

## Consequences

A change that adds an accepted or returned format is MINOR. Nothing an existing API version accepts or returns changes in a release.

## Source

The container epic's Sponsor decisions, mqucifer/sprint-metrics#186 ([issue](https://github.com/mqucifer/sprint-metrics/issues/186)); the service Goal's decision D4 ([Goal](https://github.com/mqucifer/sprint-metrics/issues/174)).
