-- Monitor page state: tracks each monitored URL and its content hash
CREATE TABLE IF NOT EXISTS monitor_page_state (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  url TEXT NOT NULL,
  category TEXT,
  title TEXT,
  content_hash TEXT,
  last_checked_at TIMESTAMPTZ,
  last_changed_at TIMESTAMPTZ,
  status TEXT DEFAULT 'active',
  error_message TEXT,
  project_id UUID REFERENCES projects(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(url, project_id)
);

-- Monitor change log: records each detected change
CREATE TABLE IF NOT EXISTS monitor_change_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  page_state_id UUID REFERENCES monitor_page_state(id),
  url TEXT NOT NULL,
  change_type TEXT NOT NULL,
  title TEXT,
  summary TEXT,
  is_substantive BOOLEAN DEFAULT true,
  diff_additions INT DEFAULT 0,
  diff_deletions INT DEFAULT 0,
  auto_ingested BOOLEAN DEFAULT false,
  detected_at TIMESTAMPTZ DEFAULT now(),
  project_id UUID REFERENCES projects(id)
);

-- Index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_monitor_page_state_project ON monitor_page_state(project_id);
CREATE INDEX IF NOT EXISTS idx_monitor_change_log_project ON monitor_change_log(project_id);
CREATE INDEX IF NOT EXISTS idx_monitor_change_log_detected ON monitor_change_log(detected_at DESC);
