"""The /range and /trend responses' api_version (mqucifer/crew#1019).

It moves once, in the release that changes what the responses offer, with
`declared-changes.json`'s, and never in a story. It has its own file so that the
release, which may change a version file and not the code, can move it.
"""

API_VERSION = "16"
