(() => {
    'use strict';

    const selectors = {
        table: '#bomItemsTable',
        addButton: '#addBomRow',
        product: '.item-product',
        code: '.item-code',
        name: '.item-name',
        specification: '.item-specification',
        optional: '.item-optional',
        removeButton: '.remove-row',
        unit: '[name="item_unit"]',
    };

    const events = {
        addRow: 'bom:add-row',
        copySelectedRow: 'bom:copy-selected-row',
        deleteEmptyRows: 'bom:delete-empty-rows',
        clearItems: 'bom:clear-items',
        refreshProductFields: 'bom:refresh-product-fields',
    };

    const getTable = () => document.querySelector(selectors.table);
    const getBody = (table = getTable()) => table?.tBodies?.[0] || null;
    const getRows = (table = getTable()) => Array.from(getBody(table)?.rows || []);

    const isTextInput = (input) => {
        const type = (input.getAttribute('type') || 'text').toLowerCase();
        return !['button', 'submit', 'reset', 'hidden'].includes(type);
    };

    const refreshOptionalValues = (table = getTable()) => {
        getRows(table).forEach((row, index) => {
            row.querySelectorAll(selectors.optional).forEach((input) => {
                input.value = String(index);
            });
        });
    };

    const fillProductFields = (row) => {
        const product = row?.querySelector(selectors.product);
        const option = product?.selectedOptions?.[0];
        const selected = option && option.value ? option : null;
        const codeInput = row?.querySelector(selectors.code);
        const nameInput = row?.querySelector(selectors.name);
        const specInput = row?.querySelector(selectors.specification);
        const unitInput = row?.querySelector(selectors.unit);

        if (codeInput) codeInput.value = selected?.dataset.code || '';
        if (nameInput) nameInput.value = selected?.dataset.name || '';
        if (specInput) specInput.value = selected?.dataset.specification || '';
        if (unitInput) unitInput.value = selected?.dataset.unit || '';
    };

    const refreshProductFields = (target) => {
        const table = getTable();
        if (!table) return;

        const row = target?.closest?.('tr');
        const rows = row && table.contains(row) ? [row] : getRows(table);
        rows.forEach(fillProductFields);
    };

    const resetRow = (row) => {
        row.querySelectorAll('input').forEach((input) => {
            if (input.matches(selectors.code) || input.matches(selectors.name) || input.matches(selectors.specification)) {
                input.value = '';
            } else if (input.type === 'checkbox' || input.type === 'radio') {
                input.checked = false;
            } else if (input.name === 'item_loss_rate') {
                input.value = '0';
            } else if (isTextInput(input)) {
                input.value = '';
            }
        });

        row.querySelectorAll('textarea').forEach((textarea) => {
            textarea.value = '';
        });

        row.querySelectorAll('select').forEach((select) => {
            select.value = '';
        });
    };

    const copyFormState = (sourceRow, targetRow) => {
        const sourceFields = Array.from(sourceRow.querySelectorAll('input, select, textarea'));
        const targetFields = Array.from(targetRow.querySelectorAll('input, select, textarea'));

        sourceFields.forEach((source, index) => {
            const target = targetFields[index];
            if (!target) return;

            if (target.type === 'checkbox' || target.type === 'radio') {
                target.checked = source.checked;
            } else {
                target.value = source.value;
            }
        });
    };

    const resetSelectSearchEnhancement = (row) => {
        row.querySelectorAll('.select-search').forEach((wrapper) => {
            const select = wrapper.querySelector('select');
            if (!select) {
                wrapper.remove();
                return;
            }
            select.removeAttribute('data-select-search-enhanced');
            select.classList.remove('select-search-source');
            select.removeAttribute('tabindex');
            wrapper.parentNode.insertBefore(select, wrapper);
            wrapper.remove();
        });

        row.querySelectorAll('select[data-select-search-enhanced="true"]').forEach((select) => {
            select.removeAttribute('data-select-search-enhanced');
            select.classList.remove('select-search-source');
            select.removeAttribute('tabindex');
        });
    };

    const enhanceSelects = (root) => {
        if (typeof window.enhanceSelectSearch === 'function') {
            window.enhanceSelectSearch(root);
        }
    };

    const cloneRow = (sourceRow, options = {}) => {
        const clone = sourceRow.cloneNode(true);
        clone.removeAttribute('data-bom-actions-wired');
        resetSelectSearchEnhancement(clone);

        if (options.copyValues) {
            copyFormState(sourceRow, clone);
            fillProductFields(clone);
        } else {
            resetRow(clone);
        }

        return clone;
    };

    const appendRow = (options = {}) => {
        const table = getTable();
        const body = getBody(table);
        const rows = getRows(table);
        const sourceRow = options.sourceRow || rows[0];
        if (!body || !sourceRow) return null;

        const row = cloneRow(sourceRow, { copyValues: Boolean(options.copyValues) });
        body.appendChild(row);
        enhanceSelects(row);
        refreshOptionalValues(table);
        return row;
    };

    const getActiveRow = () => {
        const table = getTable();
        const active = document.activeElement;
        const row = active?.closest?.('tr');
        if (row && table?.contains(row)) return row;

        const rows = getRows(table);
        return rows[rows.length - 1] || null;
    };

    const isEmptyRow = (row) => {
        const product = row.querySelector(selectors.product);
        if (product?.value) return false;

        return Array.from(row.querySelectorAll('input, textarea, select')).every((field) => {
            if (field.matches(selectors.code) || field.matches(selectors.name) || field.matches(selectors.specification)) {
                return true;
            }
            if (field.matches(selectors.product)) return !field.value;
            if (field.type === 'checkbox' || field.type === 'radio') return !field.checked;
            if (field.name === 'item_loss_rate') return !field.value || field.value === '0';
            return !String(field.value || '').trim();
        });
    };

    const removeRow = (row) => {
        const table = getTable();
        if (!row || getRows(table).length <= 1) return;

        row.remove();
        refreshOptionalValues(table);
    };

    const deleteEmptyRows = () => {
        const table = getTable();
        const rows = getRows(table);
        let remaining = rows.length;

        rows.forEach((row) => {
            if (remaining > 1 && isEmptyRow(row)) {
                row.remove();
                remaining -= 1;
            }
        });

        refreshOptionalValues(table);
    };

    const clearItems = () => {
        const table = getTable();
        const body = getBody(table);
        const rows = getRows(table);
        const sourceRow = rows[0];
        if (!body || !sourceRow) return;

        body.replaceChildren();
        for (let index = 0; index < 3; index += 1) {
            const row = cloneRow(sourceRow);
            body.appendChild(row);
            enhanceSelects(row);
        }
        refreshOptionalValues(table);
    };

    const copySelectedRow = () => {
        const sourceRow = getActiveRow();
        if (!sourceRow) return null;

        return appendRow({ sourceRow, copyValues: true });
    };

    const init = () => {
        const table = getTable();
        const addButton = document.querySelector(selectors.addButton);
        if (!table || table.dataset.bomActionsReady === '1') return;

        table.dataset.bomActionsReady = '1';

        table.addEventListener('change', (event) => {
            if (event.target.matches(selectors.product)) {
                fillProductFields(event.target.closest('tr'));
            }
        });

        table.addEventListener('click', (event) => {
            const button = event.target.closest(selectors.removeButton);
            if (button && table.contains(button)) {
                event.preventDefault();
                event.stopImmediatePropagation();
                removeRow(button.closest('tr'));
            }
        }, true);

        addButton?.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopImmediatePropagation();
            appendRow();
        }, true);

        document.addEventListener('click', (event) => {
            const trigger = event.target.closest('[data-menu-event]');
            if (!trigger) return;
            const eventName = trigger.getAttribute('data-menu-event');
            if (!eventName || !eventName.startsWith('bom:')) return;
            event.preventDefault();
            document.dispatchEvent(new CustomEvent(eventName, { detail: { source: trigger } }));
        });

        document.addEventListener(events.addRow, (event) => {
            appendRow(event.detail || {});
        });

        document.addEventListener(events.copySelectedRow, () => {
            copySelectedRow();
        });

        document.addEventListener(events.deleteEmptyRows, () => {
            deleteEmptyRows();
        });

        document.addEventListener(events.clearItems, () => {
            clearItems();
        });

        document.addEventListener(events.refreshProductFields, (event) => {
            refreshProductFields(event.detail?.target);
        });

        refreshProductFields();
        refreshOptionalValues(table);
    };

    window.BomFormActions = {
        addRow: appendRow,
        clearItems,
        copySelectedRow,
        deleteEmptyRows,
        fillProductFields,
        refreshOptionalValues,
        refreshProductFields,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
