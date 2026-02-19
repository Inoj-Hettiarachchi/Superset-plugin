document.addEventListener('DOMContentLoaded', function() {
    var formEl = document.getElementById('dataEntryForm');
    if (!formEl) return;

    var formId = formEl.getAttribute('data-form-id');

    formEl.addEventListener('submit', function(e) {
        e.preventDefault();
        
        var submitBtn = document.getElementById('dataEntrySubmitBtn');
        var originalHtml = submitBtn ? submitBtn.innerHTML : '';
        if (submitBtn) {
            submitBtn.classList.add('data-entry-btn-loading');
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Submitting...';
        }
        
        // Clear previous errors
        document.querySelectorAll('.invalid-feedback').forEach(function(el) {
            el.textContent = '';
            if (el.previousElementSibling) {
                el.previousElementSibling.classList.remove('is-invalid');
            }
        });
        
        // Collect form data
        var formData = {};
        var formElements = formEl.elements;
        
        for (var i = 0; i < formElements.length; i++) {
            var element = formElements[i];
            if (element.name) {
                if (element.type === 'checkbox') {
                    formData[element.name] = element.checked;
                } else if (element.type === 'number') {
                    formData[element.name] = element.value ? parseFloat(element.value) : null;
                } else {
                    formData[element.name] = element.value || null;
                }
            }
        }
        
        function resetSubmitBtn() {
            if (submitBtn) {
                submitBtn.classList.remove('data-entry-btn-loading');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalHtml;
            }
        }
        
        fetch('/data-entry/entry/' + formId + '/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            resetSubmitBtn();
            if (data.success) {
                alert(data.message);
                formEl.reset();
            } else if (data.errors) {
                for (var fieldName in data.errors) {
                    var errorDiv = document.getElementById('error_' + fieldName);
                    var inputField = document.getElementById('field_' + fieldName);
                    if (errorDiv && inputField) {
                        errorDiv.textContent = data.errors[fieldName].join(', ');
                        inputField.classList.add('is-invalid');
                    }
                }
                alert('Please fix the validation errors');
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(function(error) {
            resetSubmitBtn();
            alert('Error: ' + error);
        });
    });
});
