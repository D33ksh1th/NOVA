CREATE TABLE observation (
  id            BIGSERIAL PRIMARY KEY,
  asset_uid     UUID NOT NULL,
  collector     TEXT NOT NULL,
  confidence    NUMERIC(3,2) NOT NULL,
  observed_at   TIMESTAMPTZ NOT NULL,
  attr_path     TEXT NOT NULL,
  attr_value    JSONB NOT NULL,
  evidence      JSONB
);
CREATE INDEX observation_asset_attr_ts_idx ON observation (asset_uid, attr_path, observed_at DESC);

CREATE TABLE asset (
  asset_uid     UUID PRIMARY KEY,
  zone          TEXT NOT NULL,
  purdue_level  SMALLINT,
  criticality   SMALLINT,
  first_seen    TIMESTAMPTZ,
  last_seen     TIMESTAMPTZ,
  current       JSONB
);

CREATE TABLE component (
  id            BIGSERIAL PRIMARY KEY,
  asset_uid     UUID REFERENCES asset,
  bom_type      TEXT NOT NULL,
  purl          TEXT,
  cpe           TEXT,
  name          TEXT NOT NULL,
  version       TEXT,
  props         JSONB,
  first_seen    TIMESTAMPTZ,
  last_seen     TIMESTAMPTZ
);
CREATE UNIQUE INDEX component_asset_unique_idx ON component (asset_uid, bom_type, name, COALESCE(version,''));
CREATE INDEX component_props_gin_idx ON component USING GIN (props jsonb_path_ops);

CREATE TABLE finding (
  id            BIGSERIAL PRIMARY KEY,
  asset_uid     UUID,
  component_id  BIGINT REFERENCES component,
  rule_id       TEXT NOT NULL,
  vuln_id       TEXT,
  severity      TEXT,
  epss          NUMERIC,
  kev           BOOLEAN,
  reachable     BOOLEAN,
  vex_status    TEXT,
  state         TEXT,
  dedupe_key    TEXT UNIQUE
);
