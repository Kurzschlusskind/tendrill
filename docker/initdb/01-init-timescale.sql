-- Tendrill Database Initialization
-- PostgreSQL + TimescaleDB

-- Enable TimescaleDB Extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- Schema
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS tendrill;

-- =============================================================================
-- Sensor Readings - Hypertable für Zeitreihen
-- =============================================================================

CREATE TABLE IF NOT EXISTS tendrill.sensor_readings (
    time            TIMESTAMPTZ         NOT NULL,
    device_id       UUID                NOT NULL,
    zone_id         UUID                NOT NULL,
    sensor_type     VARCHAR(50)         NOT NULL,
    value           DOUBLE PRECISION    NOT NULL,
    unit            VARCHAR(20)         NOT NULL,
    quality         SMALLINT            DEFAULT 100,
    metadata        JSONB               DEFAULT '{}'::jsonb
);

-- Convert to TimescaleDB Hypertable
SELECT create_hypertable(
    'tendrill.sensor_readings',
    by_range('time'),
    if_not_exists => TRUE
);

-- Compression Policy (nach 7 Tagen komprimieren)
ALTER TABLE tendrill.sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id, zone_id, sensor_type'
);

SELECT add_compression_policy(
    'tendrill.sensor_readings',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Retention Policy (Daten nach 1 Jahr löschen, optional aktivieren)
-- SELECT add_retention_policy('tendrill.sensor_readings', INTERVAL '1 year');

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_time
    ON tendrill.sensor_readings (device_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_zone_type_time
    ON tendrill.sensor_readings (zone_id, sensor_type, time DESC);

-- =============================================================================
-- Devices
-- =============================================================================

CREATE TABLE IF NOT EXISTS tendrill.devices (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(100)    NOT NULL,
    device_type     VARCHAR(50)     NOT NULL,
    zone_id         UUID,
    mqtt_topic      VARCHAR(255)    NOT NULL UNIQUE,
    config          JSONB           DEFAULT '{}'::jsonb,
    is_active       BOOLEAN         DEFAULT TRUE,
    last_seen       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devices_zone ON tendrill.devices (zone_id);
CREATE INDEX IF NOT EXISTS idx_devices_active ON tendrill.devices (is_active) WHERE is_active = TRUE;

-- =============================================================================
-- Zones (Grow-Bereiche)
-- =============================================================================

CREATE TABLE IF NOT EXISTS tendrill.zones (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(100)    NOT NULL,
    description     TEXT,
    zone_type       VARCHAR(50)     NOT NULL DEFAULT 'grow_room',
    current_phase   VARCHAR(50),
    phase_started   TIMESTAMPTZ,
    config          JSONB           DEFAULT '{}'::jsonb,
    is_active       BOOLEAN         DEFAULT TRUE,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- =============================================================================
-- Plants / Grows
-- =============================================================================

CREATE TABLE IF NOT EXISTS tendrill.grows (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(100)    NOT NULL,
    strain          VARCHAR(100),
    zone_id         UUID            REFERENCES tendrill.zones(id),
    plant_count     INTEGER         DEFAULT 1,
    current_phase   VARCHAR(50)     NOT NULL DEFAULT 'germination',
    phase_started   TIMESTAMPTZ     DEFAULT NOW(),
    grow_started    TIMESTAMPTZ     DEFAULT NOW(),
    grow_ended      TIMESTAMPTZ,
    notes           TEXT,
    config          JSONB           DEFAULT '{}'::jsonb,
    is_active       BOOLEAN         DEFAULT TRUE,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grows_zone ON tendrill.grows (zone_id);
CREATE INDEX IF NOT EXISTS idx_grows_active ON tendrill.grows (is_active) WHERE is_active = TRUE;

-- =============================================================================
-- Alerts
-- =============================================================================

CREATE TABLE IF NOT EXISTS tendrill.alerts (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    zone_id         UUID            REFERENCES tendrill.zones(id),
    device_id       UUID            REFERENCES tendrill.devices(id),
    alert_type      VARCHAR(50)     NOT NULL,
    severity        VARCHAR(20)     NOT NULL DEFAULT 'warning',
    message         TEXT            NOT NULL,
    sensor_type     VARCHAR(50),
    value           DOUBLE PRECISION,
    threshold_min   DOUBLE PRECISION,
    threshold_max   DOUBLE PRECISION,
    acknowledged    BOOLEAN         DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(100),
    resolved        BOOLEAN         DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_zone_unresolved
    ON tendrill.alerts (zone_id, created_at DESC)
    WHERE resolved = FALSE;

-- =============================================================================
-- Actuator Commands
-- =============================================================================

CREATE TABLE IF NOT EXISTS tendrill.actuator_commands (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id       UUID            REFERENCES tendrill.devices(id),
    command_type    VARCHAR(50)     NOT NULL,
    payload         JSONB           NOT NULL,
    source          VARCHAR(50)     NOT NULL DEFAULT 'manual',
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending',
    executed_at     TIMESTAMPTZ,
    result          JSONB,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- =============================================================================
-- Phase History
-- =============================================================================

CREATE TABLE IF NOT EXISTS tendrill.phase_history (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    grow_id         UUID            REFERENCES tendrill.grows(id),
    phase           VARCHAR(50)     NOT NULL,
    started_at      TIMESTAMPTZ     NOT NULL,
    ended_at        TIMESTAMPTZ,
    notes           TEXT,
    config_snapshot JSONB
);

CREATE INDEX IF NOT EXISTS idx_phase_history_grow
    ON tendrill.phase_history (grow_id, started_at DESC);

-- =============================================================================
-- Functions
-- =============================================================================

-- Automatische updated_at Aktualisierung
CREATE OR REPLACE FUNCTION tendrill.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers für updated_at
CREATE TRIGGER update_devices_updated_at
    BEFORE UPDATE ON tendrill.devices
    FOR EACH ROW EXECUTE FUNCTION tendrill.update_updated_at();

CREATE TRIGGER update_zones_updated_at
    BEFORE UPDATE ON tendrill.zones
    FOR EACH ROW EXECUTE FUNCTION tendrill.update_updated_at();

CREATE TRIGGER update_grows_updated_at
    BEFORE UPDATE ON tendrill.grows
    FOR EACH ROW EXECUTE FUNCTION tendrill.update_updated_at();

-- =============================================================================
-- Continuous Aggregates für Performance
-- =============================================================================

-- Stündliche Aggregation
CREATE MATERIALIZED VIEW IF NOT EXISTS tendrill.sensor_readings_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    device_id,
    zone_id,
    sensor_type,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS sample_count
FROM tendrill.sensor_readings
GROUP BY bucket, device_id, zone_id, sensor_type
WITH NO DATA;

-- Refresh Policy
SELECT add_continuous_aggregate_policy('tendrill.sensor_readings_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Tägliche Aggregation
CREATE MATERIALIZED VIEW IF NOT EXISTS tendrill.sensor_readings_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    device_id,
    zone_id,
    sensor_type,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS sample_count
FROM tendrill.sensor_readings
GROUP BY bucket, device_id, zone_id, sensor_type
WITH NO DATA;

SELECT add_continuous_aggregate_policy('tendrill.sensor_readings_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);
