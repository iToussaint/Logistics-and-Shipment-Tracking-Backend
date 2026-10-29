-- Run after schema.sql (it relies on the fresh SERIAL ids starting at 1).

INSERT INTO locations (name, city, state) VALUES
    ('Dallas Hub',            'Dallas',      'TX'),
    ('Houston Warehouse',     'Houston',     'TX'),
    ('Atlanta Hub',           'Atlanta',     'GA'),
    ('Chicago Hub',           'Chicago',     'IL'),
    ('Denver Warehouse',      'Denver',      'CO'),
    ('Phoenix Warehouse',     'Phoenix',     'AZ'),
    ('Los Angeles Hub',       'Los Angeles', 'CA'),
    ('Seattle Warehouse',     'Seattle',     'WA'),
    ('New York Hub',          'New York',    'NY'),
    ('Miami Warehouse',       'Miami',       'FL');

INSERT INTO customers (name, email, phone)
SELECT 'Customer ' || i, 'customer' || i || '@example.com', '555-' || lpad(i::text, 4, '0')
FROM generate_series(1, 1000) AS i;

INSERT INTO shipments (sender_id, recipient_id, origin_location_id, destination_location_id, created_at)
SELECT i % 1000 + 1,
       (i + 500) % 1000 + 1,
       i % 10 + 1,
       (i + 5) % 10 + 1,
       timestamptz '2026-09-01' + i * interval '2 minutes'
FROM generate_series(1, 17000) AS i;

-- Two packages per shipment. Each package has progressed 1 to 5 steps along
-- the delivery route, which sets its current_status.
INSERT INTO packages (tracking_id, shipment_id, weight_kg, current_status, package_metadata)
SELECT 'TRK' || lpad(i::text, 8, '0'),
       (i + 1) / 2,
       round((0.5 + random() * 30)::numeric, 2),
       (ARRAY['Created', 'Picked Up', 'In Transit', 'Out for Delivery', 'Delivered'])[i % 5 + 1],
       jsonb_build_object('fragile', i % 3 = 0, 'requires_signature', i % 4 = 0)
FROM generate_series(1, 34000) AS i;

-- One event for every step a package has reached: the first two at the
-- origin, the middle one at a transit hub, the last two at the destination.
INSERT INTO tracking_events (package_id, location_id, status, event_timestamp)
SELECT p.package_id,
       CASE WHEN step <= 2 THEN s.origin_location_id
            WHEN step = 3  THEN (s.origin_location_id + 2) % 10 + 1
            ELSE s.destination_location_id END,
       (ARRAY['Created', 'Picked Up', 'In Transit', 'Out for Delivery', 'Delivered'])[step],
       s.created_at + (step - 1) * interval '10 hours'
FROM packages p
JOIN shipments s ON s.shipment_id = p.shipment_id
CROSS JOIN generate_series(1, 5) AS step
WHERE step <= array_position(
    ARRAY['Created', 'Picked Up', 'In Transit', 'Out for Delivery', 'Delivered'],
    p.current_status::text);
