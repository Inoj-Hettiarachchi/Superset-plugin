document.addEventListener('DOMContentLoaded', function() {
    var gridEl = document.getElementById('dataGrid');
    if (!gridEl) return;

    var formId = gridEl.getAttribute('data-form-id');

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
});

