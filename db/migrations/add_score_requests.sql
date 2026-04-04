CREATE TABLE IF NOT EXISTS score_requests (
  id SERIAL PRIMARY KEY,
  address TEXT NOT NULL,
  city TEXT,
  state TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  livability_score INTEGER,
  evidence_quality TEXT,
  strong_signal_count INTEGER,
  error TEXT,
  response_time_ms INTEGER,
  user_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_score_requests_created ON score_requests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_score_requests_city ON score_requests(city);
