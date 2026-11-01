import json
from datetime import UTC, datetime

import psycopg2
import redis
from psycopg2 import pool
from pymongo import MongoClient

connection_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    host="localhost",
    port=5434,
    dbname="logistics",
    user="logistics",
    password="logistics",
)
redis_client = redis.Redis(host="localhost", port=6380, decode_responses=True)
scan_logs = MongoClient("localhost", 27018).logistics.scan_logs


def process_tracking_scan(package_id, location_id, status, scanner_id):
    log_entry = {
        "scanner_id": scanner_id,
        "package_id": package_id,
        "location_id": location_id,
        "status": status,
        "scanned_at": datetime.now(UTC),
    }

    conn = connection_pool.getconn()
    try:
        # "with conn" commits if all statements succeed and rolls back if any fails.
        with conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE packages SET current_status = %s WHERE package_id = %s",
                (status, package_id),
            )
            cur.execute(
                "INSERT INTO tracking_events (package_id, location_id, status) VALUES (%s, %s, %s)",
                (package_id, location_id, status),
            )
            cur.execute(
                """
                SELECT p.tracking_id, l.city || ', ' || l.state
                FROM packages p
                JOIN locations l ON l.location_id = %s
                WHERE p.package_id = %s
                """,
                (location_id, package_id),
            )
            tracking_id, location = cur.fetchone()
    except psycopg2.Error as error:
        # Failed scans are still logged so the audit trail has every raw scan.
        scan_logs.insert_one({**log_entry, "result": "failed", "error": str(error)})
        raise
    finally:
        connection_pool.putconn(conn)

    scan_logs.insert_one({**log_entry, "result": "success"})
    cache_status(tracking_id, status, location)


def cache_status(tracking_id, status, location):
    redis_client.set(
        f"package:{tracking_id}:status",
        json.dumps({"status": status, "location": location}),
    )


def get_package_status(tracking_id):
    cached = redis_client.get(f"package:{tracking_id}:status")
    if cached:
        return json.loads(cached)

    # Cache miss: read the latest status from Postgres and cache it.
    conn = connection_pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.current_status, l.city || ', ' || l.state
                FROM packages p
                JOIN tracking_events e ON e.package_id = p.package_id
                JOIN locations l ON l.location_id = e.location_id
                WHERE p.tracking_id = %s
                ORDER BY e.event_timestamp DESC
                LIMIT 1
                """,
                (tracking_id,),
            )
            row = cur.fetchone()
    finally:
        connection_pool.putconn(conn)

    if row is None:
        return None
    status, location = row
    cache_status(tracking_id, status, location)
    return {"status": status, "location": location}


def get_package_history(tracking_id):
    conn = connection_pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                    WITH package_events AS (
                        SELECT e.event_timestamp, e.status, l.city || ', ' || l.state AS location
                        FROM tracking_events e
                        JOIN packages p ON p.package_id = e.package_id
                        JOIN locations l ON l.location_id = e.location_id
                        WHERE p.tracking_id = %s
                    )
                    SELECT event_timestamp,
                           status,
                           location,
                           event_timestamp - LAG(event_timestamp) OVER (ORDER BY event_timestamp)
                               AS time_since_previous
                    FROM package_events
                    ORDER BY event_timestamp
                    """,
                (tracking_id,),
            )
            return cur.fetchall()
    finally:
        connection_pool.putconn(conn)
