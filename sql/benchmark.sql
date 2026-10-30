-- Compares the tracking history query with and without the composite index.
-- Run each step separately.

-- Step 1: remove the index to measure the "before" case.
DROP INDEX IF EXISTS idx_tracking_events_package_time;
ANALYZE tracking_events;

-- Step 2: before indexing.
EXPLAIN ANALYZE
WITH package_events AS (
    SELECT e.event_timestamp, e.status, l.city || ', ' || l.state AS location
    FROM tracking_events e
    JOIN packages p ON p.package_id = e.package_id
    JOIN locations l ON l.location_id = e.location_id
    WHERE p.tracking_id = 'TRK00000004'
)
SELECT event_timestamp,
       status,
       location,
       event_timestamp - LAG(event_timestamp) OVER (ORDER BY event_timestamp) AS time_since_previous
FROM package_events
ORDER BY event_timestamp;

-- Step 3: create the composite index.
CREATE INDEX idx_tracking_events_package_time ON tracking_events (package_id, event_timestamp);
ANALYZE tracking_events;

-- Step 4: after indexing (same query as step 2).
EXPLAIN ANALYZE
WITH package_events AS (
    SELECT e.event_timestamp, e.status, l.city || ', ' || l.state AS location
    FROM tracking_events e
    JOIN packages p ON p.package_id = e.package_id
    JOIN locations l ON l.location_id = e.location_id
    WHERE p.tracking_id = 'TRK00000004'
)
SELECT event_timestamp,
       status,
       location,
       event_timestamp - LAG(event_timestamp) OVER (ORDER BY event_timestamp) AS time_since_previous
FROM package_events
ORDER BY event_timestamp;
