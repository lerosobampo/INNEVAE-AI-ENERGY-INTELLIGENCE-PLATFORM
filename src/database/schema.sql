
-- ============================================================
-- INNEVA.E AI ENERGY INTELLIGENCE PLATFORM
-- SQLite Database Schema
-- ============================================================

-- 1. ELECTRICITY DEMAND
CREATE TABLE IF NOT EXISTS electricity_demand (
    interval_start_utc TEXT NOT NULL,
    interval_end_utc TEXT NOT NULL,
    area TEXT NOT NULL,
    actual_total_load_mw REAL,
    day_ahead_total_load_forecast_mw REAL,

    PRIMARY KEY (interval_start_utc, area),

    CHECK (interval_end_utc > interval_start_utc),

    CHECK (
        actual_total_load_mw IS NULL
        OR actual_total_load_mw >= 0
    )
);


-- 2. SOLAR GENERATION
CREATE TABLE IF NOT EXISTS solar_generation (
    valid_from_utc TEXT NOT NULL,
    valid_to_utc TEXT NOT NULL,
    point TEXT,
    type TEXT,
    granularity TEXT,
    timezone TEXT,
    activity TEXT,
    classification TEXT,
    capacity_kw REAL,
    volume_kwh REAL,
    percentage REAL,
    emission_kg_co2 REAL,
    emission_factor_kg_co2_per_kwh REAL
);


-- 3. ONSHORE WIND GENERATION
CREATE TABLE IF NOT EXISTS wind_onshore_generation (
    valid_from_utc TEXT NOT NULL,
    valid_to_utc TEXT NOT NULL,
    point TEXT,
    type TEXT,
    granularity TEXT,
    timezone TEXT,
    activity TEXT,
    classification TEXT,
    capacity_kw REAL,
    volume_kwh REAL,
    percentage REAL,
    emission_kg_co2 REAL,
    emission_factor_kg_co2_per_kwh REAL
);


-- 4. OFFSHORE WIND GENERATION
CREATE TABLE IF NOT EXISTS wind_offshore_generation (
    valid_from_utc TEXT NOT NULL,
    valid_to_utc TEXT NOT NULL,
    location TEXT,
    generation_type TEXT,
    granularity TEXT,
    timezone TEXT,
    activity TEXT,
    classification TEXT,
    capacity_kw REAL,
    volume_kwh REAL,
    percentage REAL,
    emission_kg_co2 REAL,
    emission_factor_kg_co2_per_kwh REAL
);


-- 5. WEATHER OBSERVATIONS
CREATE TABLE IF NOT EXISTS weather_observations (
    interval_start_utc TEXT NOT NULL,
    interval_end_utc TEXT,
    station_id INTEGER NOT NULL,
    observation_date TEXT,
    observation_hour_utc INTEGER,
    wind_direction_degrees REAL,
    hourly_mean_wind_speed_0_1_ms REAL,
    wind_speed_last_10min_0_1_ms REAL,
    maximum_wind_gust_0_1_ms REAL,
    air_temperature_0_1_c REAL,
    minimum_ground_temperature_0_1_c REAL,
    dew_point_temperature_0_1_c REAL,
    sunshine_duration_0_1_hours REAL,
    global_radiation_j_cm2 REAL,
    precipitation_duration_0_1_hours REAL,
    precipitation_amount_0_1_mm REAL,
    sea_level_pressure_0_1_hpa REAL,
    visibility_code TEXT,
    cloud_cover_oktas REAL,
    relative_humidity_pct REAL,
    present_weather_code TEXT,
    weather_code_indicator TEXT,
    fog_indicator INTEGER,
    rain_indicator INTEGER,
    snow_indicator INTEGER,
    thunder_indicator INTEGER,
    ice_formation_indicator INTEGER,

    PRIMARY KEY (interval_start_utc, station_id)
);


-- 6. WHOLESALE ELECTRICITY PRICES
CREATE TABLE IF NOT EXISTS wholesale_prices (
    country TEXT,
    iso3_code TEXT NOT NULL,
    interval_start_utc TEXT NOT NULL,
    datetime_local TEXT,
    wholesale_price_eur_mwh REAL,

    PRIMARY KEY (iso3_code, interval_start_utc)
);


-- 7. GRID CAPACITY
CREATE TABLE IF NOT EXISTS grid_capacity (
    supply_area_id TEXT,
    year INTEGER,
    existing_transport_capacity_injection REAL,
    existing_transport_capacity_consumption REAL,
    required_transport_capacity_injection REAL,
    required_transport_capacity_consumption REAL,
    unique_requests_injection REAL,
    unique_requests_consumption REAL,
    waiting_list_injection REAL,
    waiting_list_consumption REAL,
    forecast_capacity_injection REAL,
    forecast_capacity_consumption REAL,
    information TEXT,
    congestion_url TEXT,
    expected_resolution_year_injection INTEGER,
    expected_resolution_year_consumption INTEGER,
    start_date TEXT,
    end_date TEXT,
    quarter TEXT,
    regional_grid_operator TEXT,
    province TEXT
);
