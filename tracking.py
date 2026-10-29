from psycopg2 import pool

connection_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    host="localhost",
    port=5434,
    dbname="logistics",
    user="logistics",
    password="logistics",
)


def process_tracking_scan(package_id, location_id, status):
    conn = connection_pool.getconn()
    try:
        # "with conn" commits if both statements succeed and rolls back if either fails.
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE packages SET current_status = %s WHERE package_id = %s",
                    (status, package_id),
                )
                cur.execute(
                    "INSERT INTO tracking_events (package_id, location_id, status) VALUES (%s, %s, %s)",
                    (package_id, location_id, status),
                )
    finally:
        connection_pool.putconn(conn)
