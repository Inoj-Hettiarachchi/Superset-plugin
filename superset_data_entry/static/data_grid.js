document.addEventListener('DOMContentLoaded', function() {
    var gridEl = document.getElementById('dataGrid');
    if (!gridEl) return;

    var formId = gridEl.getAttribute('data-form-id');

    // ------------------------------------------------------------------ //
    // Delete record                                                        //
    // ------------------------------------------------------------------ //
    document.addEventListener('click', function(e) {
        var deleteBtn = e.target.closest('.delete-record-btn');
        if (!deleteBtn) return;

        var recordId = deleteBtn.getAttribute('data-record-id');
        var row = deleteBtn.closest('tr');

        DataEntryUtils.confirmAction(
            'Are you sure you want to delete this record?',
            function() {
                fetch('/data-entry/data/' + formId + '/delete/' + recordId, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': DataEntryUtils.getCsrfToken()
                    }
                })
                .then(function(response) { return response.json(); })
                .then(function(data) {
                    if (data.success) {
                        if (row) { row.remove(); }
                        DataEntryUtils.showToast('Record deleted.', 'success');
                    } else {
                        DataEntryUtils.showToast('Error: ' + (data.error || 'Unknown error'), 'danger');
                    }
                })
                .catch(function(error) {
                    DataEntryUtils.showToast('Network error: ' + error, 'danger');
                });
            },
            'Delete',
            'btn-danger'
        );
    });

    // ------------------------------------------------------------------ //
    // SharePoint upload                                                    //
    // ------------------------------------------------------------------ //
    function doSharePointUpload(force) {
        var btnId = force ? 'spForceReuploadBtn' : 'sharepointUploadBtn';
        var btn = document.getElementById(btnId);
        var originalHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Uploading\u2026';
        }

        fetch('/data-entry/data/' + formId + '/sharepoint-upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': DataEntryUtils.getCsrfToken()
            },
            body: JSON.stringify({ force: force })
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (btn) { btn.disabled = false; btn.innerHTML = originalHtml; }

            if (!data.success) {
                DataEntryUtils.showToast('SharePoint upload failed: ' + (data.error || 'Unknown error'), 'danger');
                return;
            }

            if (data.mode === 'no_new_rows') {
                DataEntryUtils.showToast(
                    'All entries are already uploaded to SharePoint \u2014 no new entries found.',
                    'info'
                );
                return;
            }

            // Success: seed or incremental
            var modeLabel = data.mode === 'seed' ? 'Full upload' : 'Incremental upload';
            DataEntryUtils.showToast(
                modeLabel + ' complete \u2014 ' + data.rows_uploaded + ' row(s) sent to SharePoint.',
                'success'
            );

            // Show truncation warning if present (e.g. "Exported 50,000 of 63,000 rows")
            if (data.warning) {
                DataEntryUtils.showToast('\u26a0\ufe0f ' + data.warning, 'warning');
            }

            // Update the last-uploaded badge
            var badge = document.getElementById('spLastUploadedBadge');
            if (badge && data.last_uploaded_at) {
                var dt = data.last_uploaded_at.replace('T', ' ').substring(0, 16);
                badge.innerHTML = '<i class="fa fa-clock-o"></i> Last uploaded: ' + dt;
            }

            // After a seed upload, relabel the main button as incremental
            // and show the Force Re-upload button (page reload is simplest)
            if (data.mode === 'seed') {
                var uploadBtn = document.getElementById('sharepointUploadBtn');
                if (uploadBtn) {
                    uploadBtn.innerHTML = '<i class="fa fa-cloud-upload"></i> Upload New Entries to SharePoint';
                }
                // Reload once so the admin Force Re-upload button appears
                setTimeout(function() { window.location.reload(); }, 1800);
            }
        })
        .catch(function(error) {
            if (btn) { btn.disabled = false; btn.innerHTML = originalHtml; }
            DataEntryUtils.showToast('Network error: ' + error, 'danger');
        });
    }

    var spUploadBtn = document.getElementById('sharepointUploadBtn');
    if (spUploadBtn) {
        spUploadBtn.addEventListener('click', function() {
            doSharePointUpload(false);
        });
    }

    var spForceBtn = document.getElementById('spForceReuploadBtn');
    if (spForceBtn) {
        spForceBtn.addEventListener('click', function() {
            DataEntryUtils.confirmAction(
                'This will re-upload ALL records to SharePoint, replacing the existing file. Continue?',
                function() { doSharePointUpload(true); },
                'Force Re-upload',
                'btn-warning'
            );
        });
    }
});


