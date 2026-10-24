import os

import pytest

# Every connection the tests open, the service's included, gives up on a lock
# after 10 s, so a session left holding one fails the test that waits on it
# instead of hanging the suite. libpq reads PGOPTIONS at connect time.
os.environ["PGOPTIONS"] = (os.environ.get("PGOPTIONS", "") + " -c lock_timeout=10s").strip()


@pytest.fixture(autouse=True)
def _close_leftover_sessions():
    """After each test, close the database sessions it left open.

    A service started by a test can open its own connection on reconnect, and
    the test has no handle on it to close.
    """
    yield
    db_url = os.environ.get("SPRINT_METRICS_DB")
    if db_url is None:
        return
    try:
        import psycopg

        with psycopg.connect(db_url, connect_timeout=5, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                "AND backend_type = 'client backend'"
            )
    except Exception:
        pass
