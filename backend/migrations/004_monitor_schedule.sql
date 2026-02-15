-- Schedule config for automated page monitor crawls
CREATE TABLE IF NOT EXISTS monitor_schedule_config (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  enabled BOOLEAN DEFAULT false,
  hour_utc INT DEFAULT 14,       -- 6 AM Pacific (14:00 UTC)
  minute_utc INT DEFAULT 0,
  runs_per_day INT DEFAULT 2,    -- 2 = twice daily (12h apart)
  auto_ingest BOOLEAN DEFAULT true,
  project_id UUID REFERENCES projects(id),
  last_run_at TIMESTAMPTZ,
  last_run_status TEXT,
  last_run_changes INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Insert default config row (disabled by default, twice daily)
INSERT INTO monitor_schedule_config (enabled, hour_utc, minute_utc, runs_per_day, auto_ingest)
VALUES (false, 14, 0, 2, true)
ON CONFLICT DO NOTHING;
