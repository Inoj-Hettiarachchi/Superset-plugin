document.addEventListener('DOMContentLoaded', function() {
    var fieldCounter = 0;

    var addFieldBtn = document.getElementById('addFieldBtn');
    
    if (addFieldBtn) {
        addFieldBtn.addEventListener('click', function() {
            fieldCounter++;
            var fieldHtml = '<div class="card mb-3 field-card data-entry-field-card" data-field-id="new-' + fieldCounter + '">' +
                '<div class="card-body">' +
                    '<div class="row">' +
                        '<div class="col-md-2">' +
                            '<label>Order</label>' +
                            '<input type="number" class="form-control form-control-sm field-order" value="' + fieldCounter + '" min="1">' +
                        '</div>' +
                        '<div class="col-md-3">' +
                            '<label>Field Name *</label>' +
                            '<input type="text" class="form-control form-control-sm field-name" placeholder="field_name">' +
                        '</div>' +
                        '<div class="col-md-3">' +
                            '<label>Label *</label>' +
                            '<input type="text" class="form-control form-control-sm field-label" placeholder="Field Label">' +
                        '</div>' +
                        '<div class="col-md-2">' +
                            '<label>Type *</label>' +
                            '<select class="form-control form-control-sm field-type">' +
                                '<option value="text">Text</option>' +
                                '<option value="integer">Integer</option>' +
                                '<option value="decimal">Decimal</option>' +
                                '<option value="date">Date</option>' +
                                '<option value="boolean">Boolean</option>' +
                                '<option value="select">Select</option>' +
                            '</select>' +
                        '</div>' +
                        '<div class="col-md-1">' +
                            '<label>Required</label>' +
                            '<div class="form-check">' +
                                '<input type="checkbox" class="form-check-input field-required">' +
                            '</div>' +
                        '</div>' +
                        '<div class="col-md-1">' +
                            '<label>&nbsp;</label>' +
                            '<button type="button" class="btn btn-sm btn-danger btn-block remove-field">' +
                                '<i class="fa fa-trash"></i>' +
                            '</button>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>';
            document.getElementById('fieldsContainer').insertAdjacentHTML('beforeend', fieldHtml);
        });
    }

    // Remove field
    document.addEventListener('click', function(e) {
        if (e.target.closest('.remove-field')) {
            if (confirm('Are you sure you want to remove this field?')) {
                e.target.closest('.field-card').remove();
            }
        }
    });

    // Save form with fields
    var formEl = document.getElementById('formBuilderForm');
    if (formEl) {
        formEl.addEventListener('submit', function(e) {
            e.preventDefault();
            
            var submitBtn = document.getElementById('formBuilderSubmitBtn');
            var originalHtml = submitBtn ? submitBtn.innerHTML : '';
            if (submitBtn) {
                submitBtn.classList.add('data-entry-btn-loading');
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Saving...';
            }
            
            var fields = [];
            document.querySelectorAll('.field-card').forEach(function(card) {
                var fieldId = card.getAttribute('data-field-id');
                fields.push({
                    id: (fieldId && fieldId.indexOf('new-') === 0) ? null : fieldId,
                    field_name: card.querySelector('.field-name').value,
                    field_label: card.querySelector('.field-label').value,
                    field_type: card.querySelector('.field-type').value,
                    field_order: parseInt(card.querySelector('.field-order').value),
                    is_required: card.querySelector('.field-required').checked
                });
            });
            
            var formData = {
                id: document.getElementById('formId').value || null,
                name: document.getElementById('formName').value,
                title: document.getElementById('formTitle').value,
                description: document.getElementById('formDescription').value,
                table_name: document.getElementById('tableName').value,
                is_active: document.getElementById('isActive').checked,
                allow_edit: document.getElementById('allowEdit').checked,
                allow_delete: document.getElementById('allowDelete').checked,
                auto_create_table: !document.getElementById('formId').value,
                fields: fields
            };
            
            fetch('/data-entry/builder/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (submitBtn) {
                    submitBtn.classList.remove('data-entry-btn-loading');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalHtml;
                }
                if (data.success) {
                    alert(data.message);
                    window.location.href = '/data-entry/forms/list/';
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(function(error) {
                if (submitBtn) {
                    submitBtn.classList.remove('data-entry-btn-loading');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalHtml;
                }
                alert('Error: ' + error);
            });
        });
    }
});
