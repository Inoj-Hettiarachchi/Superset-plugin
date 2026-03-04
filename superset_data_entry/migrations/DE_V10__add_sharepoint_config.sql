-- V10: Add SharePoint export configuration columns to form_configurations
-- Each form can optionally be configured to export submissions to a SharePoint folder.

ALTER TABLE form_configurations
    ADD COLUMN IF NOT EXISTS sharepoint_enabled       BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS sharepoint_tenant_id     TEXT,
    ADD COLUMN IF NOT EXISTS sharepoint_client_id     TEXT,
    ADD COLUMN IF NOT EXISTS sharepoint_client_secret TEXT,
    ADD COLUMN IF NOT EXISTS sharepoint_site_url      TEXT,
    ADD COLUMN IF NOT EXISTS sharepoint_folder_path   TEXT;
