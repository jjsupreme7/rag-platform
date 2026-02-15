-- Add review_status to change log for approval workflow
-- pending = awaiting user review, approved = ingested, dismissed = skipped
ALTER TABLE monitor_change_log
  ADD COLUMN IF NOT EXISTS review_status TEXT DEFAULT 'pending';

-- Add last_modified to store the server's Last-Modified date when available
ALTER TABLE monitor_change_log
  ADD COLUMN IF NOT EXISTS last_modified TEXT;
