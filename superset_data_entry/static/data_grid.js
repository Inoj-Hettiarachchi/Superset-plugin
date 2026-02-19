document.addEventListener('DOMContentLoaded', function() {
    var gridEl = document.getElementById('dataGrid');
    if (!gridEl) return;

    var formId = gridEl.getAttribute('data-form-id');

    document.addEventListener('click', function(e) {
        var deleteBtn = e.target.closest('.delete-record-btn');
        if (deleteBtn) {
            var recordId = deleteBtn.getAttribute('data-record-id');
            if (!confirm('Are you sure you want to delete this record?')) {
                return;
            }
            
            fetch('/data-entry/data/' + formId + '/delete/' + recordId, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success) {
                    alert(data.message);
                    location.reload();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(function(error) {
                alert('Error: ' + error);
            });
        }
    });
});
