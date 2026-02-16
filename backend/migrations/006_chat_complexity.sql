-- Track which complexity tier the model router chose for each chat
ALTER TABLE chat_usage_log ADD COLUMN IF NOT EXISTS complexity TEXT;
