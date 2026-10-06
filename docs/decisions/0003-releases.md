# 3. A release is a pull request

- **Date:** 2026-09-28
- **Status:** Accepted

## Context

Releases were cut by hand, and nothing checked that one had really published.

## Decision

A release is a pull request with the version bump and a dated changelog entry. On merge: a tag, a GitHub Release and the image on GHCR.

## Consequences

The release is reviewed like any change. What it publishes can be checked against the tag.

## Source

mqucifer/sprint-metrics#186 ([issue](https://github.com/mqucifer/sprint-metrics/issues/186)); the service Goal's decision D5 ([Goal](https://github.com/mqucifer/sprint-metrics/issues/174)).
