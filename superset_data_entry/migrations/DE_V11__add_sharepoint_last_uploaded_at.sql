-- V11: Track the last time form data was bulk-uploaded to SharePoint.
-- NULL means the form has never been uploaded (triggers a seed/full upload).

ALTER TABLE form_configurations
    ADD COLUMN IF NOT EXISTS sharepoint_last_uploaded_at TIMESTAMP NULL;
