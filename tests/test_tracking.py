import json
from datetime import timedelta

import psycopg2
import pytest

from tracking import (
    connection_pool,
    get_package_history,
    get_package_status,
    process_tracking_scan,
    redis_client,
    scan_logs,
)

PACKAGE_ID = 1
TRACKING_ID = "TRK00000001"
REDIS_KEY = f"package:{TRACKING_ID}:status"
SCANNER_ID = "TEST-SCANNER"


@pytest.fixture
def cursor():
    conn = connection_pool.getconn()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT current_status FROM packages WHERE package_id = %s", (PACKAGE_ID,))
    original_status = cur.fetchone()[0]
    cur.execute("SELECT max(event_id) FROM tracking_events")
    last_event_id = cur.fetchone()[0]
    redis_client.delete(REDIS_KEY)

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
    redis_client.delete(REDIS_KEY)
    scan_logs.delete_many({"scanner_id": SCANNER_ID})


def event_count(cur):
    cur.execute("SELECT count(*) FROM tracking_events WHERE package_id = %s", (PACKAGE_ID,))
    return cur.fetchone()[0]


def current_status(cur):
    cur.execute("SELECT current_status FROM packages WHERE package_id = %s", (PACKAGE_ID,))
    return cur.fetchone()[0]


def test_scan_updates_postgres_redis_and_mongo(cursor):
    events_before = event_count(cursor)

    process_tracking_scan(PACKAGE_ID, 3, "In Transit", SCANNER_ID)

    assert event_count(cursor) == events_before + 1
    assert current_status(cursor) == "In Transit"
    assert json.loads(redis_client.get(REDIS_KEY)) == {"status": "In Transit", "location": "Atlanta, GA"}
    log = scan_logs.find_one({"scanner_id": SCANNER_ID})
    assert log["result"] == "success"
    assert log["package_id"] == PACKAGE_ID


def test_failed_scan_rolls_back_and_is_logged(cursor):
    events_before = event_count(cursor)
    status_before = current_status(cursor)

    # The UPDATE succeeds, then the INSERT fails on the unknown location.
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        process_tracking_scan(PACKAGE_ID, 9999, "Exception", SCANNER_ID)

    assert event_count(cursor) == events_before
    assert current_status(cursor) == status_before
    assert redis_client.get(REDIS_KEY) is None
    assert scan_logs.find_one({"scanner_id": SCANNER_ID})["result"] == "failed"


def test_cache_miss_falls_back_to_postgres(cursor):
    status = get_package_status(TRACKING_ID)

    assert status == {"status": current_status(cursor), "location": "Houston, TX"}
    assert json.loads(redis_client.get(REDIS_KEY)) == status


def test_history_is_ordered_with_time_between_events():
    history = get_package_history("TRK00000004")

    statuses = [status for _, status, _, _ in history]
    gaps = [gap for _, _, _, gap in history]
    assert statuses == ["Created", "Picked Up", "In Transit", "Out for Delivery", "Delivered"]
    assert gaps == [None] + [timedelta(hours=10)] * 4
