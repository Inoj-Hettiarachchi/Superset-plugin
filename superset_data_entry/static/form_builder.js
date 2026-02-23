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
                    '<div class="field-options-wrap mt-2" style="display:none">' +
                        '<label class="small text-muted">Select options (value shown in dropdown)</label>' +
                        '<div class="field-options-list"></div>' +
                        '<button type="button" class="btn btn-sm btn-outline-secondary add-option-btn">' +
                            '<i class="fa fa-plus"></i> Add option' +
                        '</button>' +
                    '</div>' +
                '</div>' +
            '</div>';
            document.getElementById('fieldsContainer').insertAdjacentHTML('beforeend', fieldHtml);
        });
    }

    function getOptionRowHtml() {
        return '<div class="input-group input-group-sm mb-1 option-row">' +
            '<input type="text" class="form-control option-value" placeholder="Value">' +
            '<input type="text" class="form-control option-label" placeholder="Label (optional)">' +
            '<div class="input-group-append">' +
                '<button type="button" class="btn btn-outline-danger remove-option"><i class="fa fa-times"></i></button>' +
            '</div>' +
        '</div>';
    }

    // Toggle options UI when field type changes to/from Select
    document.addEventListener('change', function(e) {
        var typeSelect = e.target && e.target.classList && e.target.classList.contains('field-type');
        if (typeSelect) {
            var wrap = typeSelect.closest('.field-card').querySelector('.field-options-wrap');
            if (wrap) wrap.style.display = typeSelect.value === 'select' ? 'block' : 'none';
        }
    });

    // Add option row (for Select fields)
    document.addEventListener('click', function(e) {
        if (e.target.closest('.add-option-btn')) {
            var btn = e.target.closest('.add-option-btn');
            var list = btn.previousElementSibling;
            if (list && list.classList.contains('field-options-list')) list.insertAdjacentHTML('beforeend', getOptionRowHtml());
        }
        if (e.target.closest('.remove-option')) {
            e.target.closest('.option-row').remove();
        }
    });

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
                var fieldType = card.querySelector('.field-type').value;
                var fieldData = {
                    id: (fieldId && fieldId.indexOf('new-') === 0) ? null : fieldId,
                    field_name: card.querySelector('.field-name').value,
                    field_label: card.querySelector('.field-label').value,
                    field_type: fieldType,
                    field_order: parseInt(card.querySelector('.field-order').value),
                    is_required: card.querySelector('.field-required').checked
                };
                if (fieldType === 'select') {
                    var options = [];
                    var optionsList = card.querySelector('.field-options-list');
                    if (optionsList) {
                        optionsList.querySelectorAll('.option-row').forEach(function(row) {
                            var val = row.querySelector('.option-value');
                            var lbl = row.querySelector('.option-label');
                            var v = val ? val.value.trim() : '';
                            if (v !== '') {
                                options.push({ value: v, label: (lbl && lbl.value.trim()) ? lbl.value.trim() : v });
                            }
                        });
                    }
                    fieldData.options = options;
                }
                fields.push(fieldData);
            });
            
            var formData = {
                id: document.getElementById('formId').value || null,
                name: document.getElementById('formName').value,
                title: document.getElementById('formTitle').value,
                description: document.getElementById('formDescription').value,
                table_name: document.getElementById('tableName').value,
                location_id: document.getElementById('locationId') ? (document.getElementById('locationId').value.trim() || null) : null,
                is_active: document.getElementById('isActive').checked,
                allow_edit: document.getElementById('allowEdit').checked,
                allow_delete: document.getElementById('allowDelete').checked,
                auto_create_table: !document.getElementById('formId').value,
                fields: fields
            };
            
            fetch('/data-entry/forms/builder/save', {
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
