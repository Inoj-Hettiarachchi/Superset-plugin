-- DE_V12: SharePoint upload audit log
-- Tracks every manual upload attempt for diagnostics & compliance.

CREATE TABLE IF NOT EXISTS de_sharepoint_upload_log (
    id              SERIAL PRIMARY KEY,
    form_id         INTEGER NOT NULL REFERENCES form_configurations(id) ON DELETE CASCADE,
    uploaded_by     VARCHAR(256) NOT NULL,
    mode            VARCHAR(20)  NOT NULL,        -- 'seed', 'incremental', 'no_new_rows'
    rows_uploaded   INTEGER      NOT NULL DEFAULT 0,
    warning         TEXT,                          -- e.g. "Exported 50,000 of 63,000 rows (capped)"
    error           TEXT,                          -- NULL on success
    duration_ms     INTEGER,                       -- wall-clock time of the upload
    created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS ix_sp_upload_log_form_id
    ON de_sharepoint_upload_log(form_id);

CREATE INDEX IF NOT EXISTS ix_sp_upload_log_created_at
    ON de_sharepoint_upload_log(created_at);
