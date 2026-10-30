DROP TABLE IF EXISTS tracking_events, packages, shipments, locations, customers;

CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE,
    phone       VARCHAR(20)
);

CREATE TABLE locations (
    location_id SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    city        VARCHAR(100) NOT NULL,
    state       CHAR(2)      NOT NULL
);

CREATE TABLE shipments (
    shipment_id             SERIAL PRIMARY KEY,
    sender_id               INT NOT NULL REFERENCES customers (customer_id),
    recipient_id            INT NOT NULL REFERENCES customers (customer_id),
    origin_location_id      INT NOT NULL REFERENCES locations (location_id),
    destination_location_id INT NOT NULL REFERENCES locations (location_id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- current_status mirrors the latest tracking event so it can be read without
-- scanning the event history; process_tracking_scan keeps the two in sync.
CREATE TABLE packages (
    package_id       SERIAL PRIMARY KEY,
    tracking_id      VARCHAR(20)  NOT NULL UNIQUE,
    shipment_id      INT          NOT NULL REFERENCES shipments (shipment_id),
    weight_kg        NUMERIC(8, 2) NOT NULL CHECK (weight_kg > 0),
    current_status   VARCHAR(20)  NOT NULL DEFAULT 'Created'
        CHECK (current_status IN ('Created', 'Picked Up', 'In Transit',
                                  'Out for Delivery', 'Delivered', 'Exception')),
    package_metadata JSONB        NOT NULL DEFAULT '{}'
);

CREATE TABLE tracking_events (
    event_id        BIGSERIAL PRIMARY KEY,
    package_id      INT         NOT NULL REFERENCES packages (package_id),
    location_id     INT         NOT NULL REFERENCES locations (location_id),
    status          VARCHAR(20) NOT NULL
        CHECK (status IN ('Created', 'Picked Up', 'In Transit',
                          'Out for Delivery', 'Delivered', 'Exception')),
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Speeds up rebuilding one package's history in time order (see benchmark.sql).
CREATE INDEX idx_tracking_events_package_time ON tracking_events (package_id, event_timestamp);
