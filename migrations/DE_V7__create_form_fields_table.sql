-- Create form_fields table for storing field definitions

CREATE TABLE IF NOT EXISTS form_fields (
    id SERIAL PRIMARY KEY,
    form_id INT NOT NULL REFERENCES form_configurations(id) ON DELETE CASCADE,
    field_name VARCHAR(100) NOT NULL,
    field_label VARCHAR(255) NOT NULL,
    field_type VARCHAR(50) NOT NULL,
    field_order INT NOT NULL,
    is_required BOOLEAN DEFAULT FALSE,
    default_value TEXT,
    placeholder VARCHAR(255),
    help_text TEXT,
    validation_rules JSONB,
    options JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_form_field UNIQUE(form_id, field_name)
);

CREATE INDEX IF NOT EXISTS idx_form_fields_form_id ON form_fields(form_id);
CREATE INDEX IF NOT EXISTS idx_form_fields_order ON form_fields(form_id, field_order);

COMMENT ON TABLE form_fields IS 'Stores field definitions for data entry forms';
