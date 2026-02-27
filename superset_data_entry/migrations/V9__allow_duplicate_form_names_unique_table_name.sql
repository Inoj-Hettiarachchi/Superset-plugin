-- Allow duplicate form names; forms are tracked by id.
-- Ensure table_name stays unique so each form has its own data table.

ALTER TABLE form_configurations DROP CONSTRAINT IF EXISTS form_configurations_name_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'form_configurations'::regclass
        AND conname = 'form_configurations_table_name_key'
    ) THEN
        ALTER TABLE form_configurations
        ADD CONSTRAINT form_configurations_table_name_key UNIQUE (table_name);
    END IF;
END $$;
