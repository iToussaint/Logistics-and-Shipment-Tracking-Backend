import psycopg2
import pytest

from tracking import connection_pool, process_tracking_scan

PACKAGE_ID = 1


@pytest.fixture
def cursor():
    conn = connection_pool.getconn()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT current_status FROM packages WHERE package_id = %s", (PACKAGE_ID,))
    original_status = cur.fetchone()[0]
    cur.execute("SELECT max(event_id) FROM tracking_events")
    last_event_id = cur.fetchone()[0]

    yield cur

    # Undo what the test wrote so the seed data stays unchanged.
    cur.execute("DELETE FROM tracking_events WHERE event_id > %s", (last_event_id,))
    cur.execute(
        "UPDATE packages SET current_status = %s WHERE package_id = %s",
        (original_status, PACKAGE_ID),
    )
    cur.close()
    conn.autocommit = False
    connection_pool.putconn(conn)


def event_count(cur):
    cur.execute("SELECT count(*) FROM tracking_events WHERE package_id = %s", (PACKAGE_ID,))
    return cur.fetchone()[0]


def current_status(cur):
    cur.execute("SELECT current_status FROM packages WHERE package_id = %s", (PACKAGE_ID,))
    return cur.fetchone()[0]


def test_scan_inserts_event_and_updates_status(cursor):
    events_before = event_count(cursor)

    process_tracking_scan(PACKAGE_ID, 3, "In Transit")

    assert event_count(cursor) == events_before + 1
    assert current_status(cursor) == "In Transit"


def test_failed_scan_rolls_back_status_update(cursor):
    events_before = event_count(cursor)
    status_before = current_status(cursor)

    # The UPDATE succeeds, then the INSERT fails on the unknown location.
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        process_tracking_scan(PACKAGE_ID, 9999, "Exception")

    assert event_count(cursor) == events_before
    assert current_status(cursor) == status_before
