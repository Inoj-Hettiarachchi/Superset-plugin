-- Add location_id to form_configurations for RLS (location-based filtering)
ALTER TABLE form_configurations ADD COLUMN IF NOT EXISTS location_id VARCHAR(100);
