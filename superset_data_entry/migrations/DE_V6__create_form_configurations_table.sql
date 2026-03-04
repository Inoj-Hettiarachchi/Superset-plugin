-- Create form_configurations table for storing form metadata
-- This table defines the structure and properties of data entry forms

CREATE TABLE IF NOT EXISTS form_configurations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    table_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    allow_edit BOOLEAN DEFAULT TRUE,
    allow_delete BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_form_configurations_name ON form_configurations(name);
CREATE INDEX IF NOT EXISTS idx_form_configurations_active ON form_configurations(is_active);

COMMENT ON TABLE form_configurations IS 'Stores metadata for dynamic data entry forms';
