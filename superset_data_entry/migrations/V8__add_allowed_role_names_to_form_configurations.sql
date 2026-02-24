-- Add allowed_role_names for creator + role-allowlist access model
-- JSONB array of role names. Only owner or users with a role in this list can enter data

ALTER TABLE form_configurations
ADD COLUMN IF NOT EXISTS allowed_role_names JSONB DEFAULT '[]'::jsonb;

COMMENT ON COLUMN form_configurations.allowed_role_names IS 'Role names allowed to enter data. Owner always has access';
