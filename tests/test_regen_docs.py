"""Temporary helper to regenerate the marked docs and schema files in place."""


def test_regen():
    from sprint_metrics._docs_gen import generate_all

    generate_all()
