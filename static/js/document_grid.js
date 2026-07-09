(function () {
    function readJson(key, fallback) {
        try {
            var value = JSON.parse(localStorage.getItem(key) || "null");
            return value == null ? fallback : value;
        } catch (error) {
            return fallback;
        }
    }

    function writeJson(key, value) {
        localStorage.setItem(key, JSON.stringify(value));
    }

    function escapeHtml(value) {
        return String(value || "").replace(/[&<>"']/g, function (ch) {
            return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch];
        });
    }

    function cellText(cell) {
        if (!cell) return "";
        var field = cell.querySelector("input, select, textarea");
        if (!field) return cell.textContent.trim();
        if (field.tagName === "SELECT") {
            var selected = field.options[field.selectedIndex];
            return selected ? selected.textContent.trim() : "";
        }
        return field.value || "";
    }

    function syncDateEmptyState(scope) {
        if (scope && scope.matches && scope.matches('input[type="date"]')) {
            scope.classList.toggle("document-date-empty", !scope.value);
            return;
        }
        (scope || document).querySelectorAll('input[type="date"]').forEach(function (input) {
            input.classList.toggle("document-date-empty", !input.value);
        });
    }

    function numericValue(text) {
        var cleaned = String(text || "").replace(/,/g, "");
        var value = parseFloat(cleaned);
        return Number.isFinite(value) ? value : null;
    }

    function initDocumentGrid(table) {
        if (!table || table.dataset.documentGridReady === "true") return window.documentGridApi || null;
        table.dataset.documentGridReady = "true";
        table.classList.add("document-grid");
        table.classList.add("document-grid-spreadsheet");

        var gridKey = table.dataset.gridKey || table.id || window.location.pathname;
        var storagePrefix = "wms1.documentGrid." + gridKey + ".";
        var widthKey = storagePrefix + "widths";
        var orderKey = storagePrefix + "order";
        var hiddenKey = storagePrefix + "hidden";
        var alignKey = storagePrefix + "align";
        var customKey = storagePrefix + "customFields";
        var thead = table.querySelector("thead");
        var tbody = table.querySelector("tbody");
        var headerRow = thead && (thead.querySelector("tr[data-grid-header]") || thead.querySelector("tr"));
        if (headerRow && !headerRow.hasAttribute("data-grid-header")) {
            headerRow.setAttribute("data-grid-header", "");
        }
        var customJsonInput = document.querySelector('[name="custom_fields_json"]');
        if (!thead || !tbody || !headerRow) {
            return window.documentGridApi || null;
        }
        function isEmptyMessageRow(row) {
            if (!row || row.children.length !== 1) return false;
            var cell = row.children[0];
            return cell && cell.colSpan > 1 && !row.querySelector("input, select, textarea");
        }
        function isVisualRow(row) {
            return row && row.dataset.visualRow === "true";
        }
        function ensureRowNumberColumn() {
            var existingHeader = headerRow.querySelector('[data-column-key="row_no"]');
            if (!existingHeader) {
                var th = document.createElement("th");
                th.dataset.columnKey = "row_no";
                th.dataset.columnLabel = "序号";
                th.className = "document-grid-row-no";
                th.textContent = "序号";
                headerRow.insertBefore(th, headerRow.firstElementChild);
            } else {
                existingHeader.classList.add("document-grid-row-no");
            }
            tbody.querySelectorAll("tr").forEach(function (row) {
                if (isEmptyMessageRow(row)) return;
                var cell = row.querySelector('[data-column-key="row_no"]');
                if (!cell) {
                    cell = document.createElement("td");
                    cell.dataset.columnKey = "row_no";
                    cell.className = "document-grid-row-no";
                    row.insertBefore(cell, row.firstElementChild);
                } else {
                    cell.classList.add("document-grid-row-no");
                }
            });
            updateRowNumbers();
        }
        function updateRowNumbers() {
            var rowNo = 1;
            tbody.querySelectorAll("tr").forEach(function (row) {
                if (isEmptyMessageRow(row)) return;
                var cell = row.querySelector('[data-column-key="row_no"]');
                if (!cell) return;
                cell.textContent = String(rowNo);
                rowNo += 1;
            });
        }
        ensureRowNumberColumn();
        function resetFieldForBlankRow(field) {
            if (!field) return;
            if (field.type === "checkbox" || field.type === "radio") {
                field.checked = false;
                return;
            }
            if (field.tagName === "SELECT") {
                field.selectedIndex = 0;
                return;
            }
            field.value = "";
        }
        function ensureMinimumEntryRows() {
            if (!table.closest("form")) return;
            if (!table.dataset.minRows && !table.dataset.documentMinRows) return;
            var minRows = Number(table.dataset.minRows || table.dataset.documentMinRows);
            if (!Number.isFinite(minRows) || minRows <= 1) return;
            var rows = Array.from(tbody.querySelectorAll("tr"));
            if (!rows.length || rows.length >= minRows) return;
            var template = rows[rows.length - 1];
            if (isEmptyMessageRow(template) || !template.querySelector("input, select, textarea")) return;
            while (tbody.querySelectorAll("tr").length < minRows) {
                var clone = template.cloneNode(true);
                clone.querySelectorAll("input, select, textarea").forEach(resetFieldForBlankRow);
                clone.querySelectorAll("[id]").forEach(function (node) { node.removeAttribute("id"); });
                tbody.appendChild(clone);
            }
            ensureRowNumberColumn();
        }
        ensureMinimumEntryRows();
        var defaultOrder = Array.from(headerRow.querySelectorAll("[data-column-key]")).map(function (cell) {
            return cell.dataset.columnKey;
        });
        var locked = new Set(["row_no", "actions"]);
        var sortState = {key: "", direction: "asc"};
        var copiedRowValues = null;
        var selectedCell = null;

        function ensureHeaderChrome() {
            headerRow.querySelectorAll("th[data-column-key]").forEach(function (th) {
                if (!th.dataset.columnLabel) {
                    th.dataset.columnLabel = th.textContent.replace(/\*/g, "").trim();
                }
                if (!th.querySelector(".grid-header-text")) {
                    var nodes = Array.from(th.childNodes);
                    var span = document.createElement("span");
                    span.className = "grid-header-text";
                    nodes.forEach(function (node) {
                        if (node.nodeType === Node.ELEMENT_NODE && node.classList && node.classList.contains("grid-resize-handle")) return;
                        span.appendChild(node);
                    });
                    th.insertBefore(span, th.firstChild);
                }
                if (!locked.has(th.dataset.columnKey) && !th.querySelector(".grid-resize-handle")) {
                    var handle = document.createElement("span");
                    handle.className = "grid-resize-handle";
                    handle.setAttribute("aria-hidden", "true");
                    th.appendChild(handle);
                }
            });
        }

        function columns() {
            return Array.from(headerRow.querySelectorAll("[data-column-key]")).map(function (th) {
                return {
                    key: th.dataset.columnKey,
                    label: th.dataset.columnLabel || th.textContent.trim(),
                    th: th
                };
            });
        }

        function eachColumnCell(key, callback) {
            table.querySelectorAll('[data-column-key="' + CSS.escape(key) + '"]').forEach(callback);
        }

        function applyWidths() {
            var widths = readJson(widthKey, {});
            var alignments = readJson(alignKey, {});
            columns().forEach(function (column) {
                var width = parseFloat(widths[column.key]);
                if (Number.isFinite(width) && width > 0) {
                    eachColumnCell(column.key, function (cell) {
                        cell.style.width = width + "px";
                        cell.style.minWidth = width + "px";
                    });
                }
            });
        }

        function setColumnWidth(key, width) {
            var nextWidth = Math.max(72, Math.min(640, Math.round(width || 0)));
            if (!key || !Number.isFinite(nextWidth)) return;
            eachColumnCell(key, function (cell) {
                cell.style.width = nextWidth + "px";
                cell.style.minWidth = nextWidth + "px";
            });
            var widths = readJson(widthKey, {});
            widths[key] = nextWidth;
            writeJson(widthKey, widths);
        }

        function applyAlignments() {
            var alignments = readJson(alignKey, {});
            columns().forEach(function (column) {
                var align = alignments[column.key] || "";
                eachColumnCell(column.key, function (cell) {
                    cell.classList.remove("document-grid-align-left", "document-grid-align-center", "document-grid-align-right");
                    if (align) cell.classList.add("document-grid-align-" + align);
                    cell.querySelectorAll("input, select, textarea").forEach(function (field) {
                        field.classList.remove("document-grid-align-left", "document-grid-align-center", "document-grid-align-right");
                        if (align) field.classList.add("document-grid-align-" + align);
                    });
                });
            });
        }

        function setColumnAlignment(key, align) {
            if (!key || locked.has(key)) return;
            var value = ["left", "center", "right"].indexOf(align) !== -1 ? align : "";
            var alignments = readJson(alignKey, {});
            if (value) alignments[key] = value;
            else delete alignments[key];
            writeJson(alignKey, alignments);
            applyAlignments();
        }

        function reorderRow(row, order) {
            if (!row) return;
            var byKey = new Map();
            Array.from(row.children).forEach(function (cell) {
                if (cell.dataset.columnKey) byKey.set(cell.dataset.columnKey, cell);
            });
            if (!byKey.size) return;
            var frag = document.createDocumentFragment();
            order.forEach(function (key) {
                var cell = byKey.get(key);
                if (cell) frag.appendChild(cell);
            });
            Array.from(row.children).forEach(function (cell) {
                if (!cell.dataset.columnKey || order.indexOf(cell.dataset.columnKey) === -1) frag.appendChild(cell);
            });
            row.appendChild(frag);
        }

        function normalizedOrder() {
            var existing = columns().map(function (column) { return column.key; });
            var saved = readJson(orderKey, []);
            var result = [];
            if (existing.indexOf("row_no") !== -1) result.push("row_no");
            existing.forEach(function (key) {
                if (locked.has(key)) return;
                if (saved.indexOf(key) !== -1) return;
                saved.push(key);
            });
            saved.forEach(function (key) {
                if (existing.indexOf(key) !== -1 && result.indexOf(key) === -1 && !locked.has(key)) result.push(key);
            });
            if (existing.indexOf("actions") !== -1) result.push("actions");
            return result;
        }

        function applyOrder() {
            var order = normalizedOrder();
            reorderRow(headerRow, order);
            tbody.querySelectorAll("tr").forEach(function (row) { reorderRow(row, order); });
        }

        function applyHidden() {
            var hidden = new Set(readJson(hiddenKey, []));
            columns().forEach(function (column) {
                var hide = hidden.has(column.key) && !locked.has(column.key);
                eachColumnCell(column.key, function (cell) {
                    cell.classList.toggle("d-none", hide);
                });
            });
        }

        function collectCustomFields() {
            var definitions = readJson(customKey, []);
            var rows = Array.from(tbody.querySelectorAll("tr")).map(function (row, rowIndex) {
                var values = {};
                definitions.forEach(function (field) {
                    var input = row.querySelector('[data-custom-field-key="' + CSS.escape(field.key) + '"]');
                    values[field.key] = input ? input.value : "";
                });
                return {row: rowIndex + 1, values: values};
            });
            if (customJsonInput) {
                customJsonInput.value = JSON.stringify({fields: definitions, rows: rows});
            }
        }

        function addCustomFieldColumn(field) {
            if (headerRow.querySelector('[data-column-key="' + CSS.escape(field.key) + '"]')) return;
            var th = document.createElement("th");
            th.dataset.columnKey = field.key;
            th.dataset.columnLabel = field.label;
            th.innerHTML = '<span class="grid-header-text">' + escapeHtml(field.label) + '</span><span class="grid-resize-handle" aria-hidden="true"></span>';
            var actionTh = headerRow.querySelector('[data-column-key="actions"]');
            headerRow.insertBefore(th, actionTh || null);
            tbody.querySelectorAll("tr").forEach(function (row) {
                if (row.querySelector('[data-column-key="' + CSS.escape(field.key) + '"]')) return;
                var td = document.createElement("td");
                td.dataset.columnKey = field.key;
                td.innerHTML = '<input class="form-control form-control-sm" data-custom-field-key="' + escapeHtml(field.key) + '" name="' + escapeHtml(field.key) + '[]" value="">';
                var actionCell = row.querySelector('[data-column-key="actions"]');
                row.insertBefore(td, actionCell || null);
            });
        }

        function loadCustomFields() {
            readJson(customKey, []).forEach(addCustomFieldColumn);
        }

        function addCustomCellsToRow(row) {
            readJson(customKey, []).forEach(function (field) {
                if (row.querySelector('[data-column-key="' + CSS.escape(field.key) + '"]')) return;
                var td = document.createElement("td");
                td.dataset.columnKey = field.key;
                td.innerHTML = '<input class="form-control form-control-sm" data-custom-field-key="' + escapeHtml(field.key) + '" name="' + escapeHtml(field.key) + '[]" value="">';
                var actionCell = row.querySelector('[data-column-key="actions"]');
                row.insertBefore(td, actionCell || null);
            });
        }

        function rowFields(row) {
            return Array.from(row.querySelectorAll("input, select, textarea")).filter(function (field) {
                return field.type !== "hidden" && !field.disabled;
            });
        }

        function focusFirstEditable(row) {
            var field = row && row.querySelector("input:not([type=hidden]), select, textarea");
            if (field) field.focus();
        }

        function activeRow() {
            var active = document.activeElement && document.activeElement.closest && document.activeElement.closest("tbody tr");
            if (active && tbody.contains(active) && !isVisualRow(active) && !isEmptyMessageRow(active)) return active;
            return businessRows()[0] || null;
        }

        function businessRows() {
            return Array.from(tbody.querySelectorAll("tr")).filter(function (row) {
                return !isVisualRow(row) && !isEmptyMessageRow(row);
            });
        }

        function markSelectedCell(cell) {
            if (!cell || !tbody.contains(cell)) return;
            table.querySelectorAll(".document-grid-cell-active").forEach(function (node) {
                node.classList.remove("document-grid-cell-active");
            });
            table.querySelectorAll(".document-grid-row-active").forEach(function (node) {
                node.classList.remove("document-grid-row-active");
            });
            selectedCell = cell;
            cell.classList.add("document-grid-cell-active");
            var row = cell.closest("tr");
            if (row) row.classList.add("document-grid-row-active");
        }

        function editableCellForField(field) {
            return field && field.closest && field.closest("td[data-column-key]");
        }

        function editableFields(row) {
            return rowFields(row).filter(function (field) {
                return !field.readOnly && !field.closest('[data-column-key="row_no"]');
            });
        }

        function moveFocus(fromField, rowOffset, cellOffset) {
            var row = fromField && fromField.closest("tr");
            if (!row) return false;
            var rows = businessRows();
            var rowIndex = rows.indexOf(row);
            if (rowIndex < 0) return false;
            var fields = editableFields(row);
            var fieldIndex = fields.indexOf(fromField);
            if (fieldIndex < 0) return false;
            var targetRowIndex = Math.max(0, Math.min(rows.length - 1, rowIndex + rowOffset));
            var targetFields = editableFields(rows[targetRowIndex]);
            if (!targetFields.length) return false;
            var targetFieldIndex = Math.max(0, Math.min(targetFields.length - 1, fieldIndex + cellOffset));
            var target = targetFields[targetFieldIndex];
            if (!target) return false;
            target.focus();
            if (target.select && target.tagName !== "SELECT") target.select();
            markSelectedCell(editableCellForField(target));
            return true;
        }

        function applyPastedMatrix(startField, text) {
            if (!startField || !text || text.indexOf("\t") === -1 && text.indexOf("\n") === -1) return false;
            var row = startField.closest("tr");
            var rows = businessRows();
            var startRowIndex = rows.indexOf(row);
            if (startRowIndex < 0) return false;
            var startFields = editableFields(row);
            var startFieldIndex = startFields.indexOf(startField);
            if (startFieldIndex < 0) return false;
            var matrix = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
            if (matrix.length && matrix[matrix.length - 1] === "") matrix.pop();
            matrix.forEach(function (line, rowOffset) {
                var targetRow = rows[startRowIndex + rowOffset];
                if (!targetRow) return;
                var values = line.split("\t");
                var targetFields = editableFields(targetRow);
                values.forEach(function (value, colOffset) {
                    var target = targetFields[startFieldIndex + colOffset];
                    if (!target || target.readOnly || target.disabled) return;
                    target.value = value;
                    target.dispatchEvent(new Event("input", {bubbles: true}));
                    target.dispatchEvent(new Event("change", {bubbles: true}));
                });
            });
            collectCustomFields();
            return true;
        }

        function copyRowValues(row) {
            if (!row) return null;
            return rowFields(row).map(function (field) {
                return {
                    name: field.name || "",
                    key: field.dataset.customFieldKey || "",
                    value: field.value || ""
                };
            });
        }

        function pasteRowValues(row, values) {
            if (!row || !values) return;
            var fields = rowFields(row);
            values.forEach(function (item, index) {
                var target = null;
                if (item.key) target = row.querySelector('[data-custom-field-key="' + CSS.escape(item.key) + '"]');
                if (!target && item.name) {
                    target = fields.find(function (field) { return field.name === item.name; });
                }
                if (!target) target = fields[index];
                if (target) {
                    target.value = item.value;
                    target.dispatchEvent(new Event("change", {bubbles: true}));
                    target.dispatchEvent(new Event("input", {bubbles: true}));
                }
            });
            collectCustomFields();
        }

        function setupResize() {
            headerRow.querySelectorAll(".grid-resize-handle").forEach(function (handle) {
                if (handle.dataset.ready === "true") return;
                handle.dataset.ready = "true";
                handle.addEventListener("mousedown", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    var th = handle.closest("[data-column-key]");
                    var key = th && th.dataset.columnKey;
                    if (!key || locked.has(key)) return;
                    var startX = event.clientX;
                    var startWidth = th.getBoundingClientRect().width || th.offsetWidth || 100;
                    document.body.classList.add("document-grid-resizing");
                    function move(moveEvent) {
                        setColumnWidth(key, startWidth + moveEvent.clientX - startX);
                    }
                    function up() {
                        document.body.classList.remove("document-grid-resizing");
                        document.removeEventListener("mousemove", move);
                        document.removeEventListener("mouseup", up);
                    }
                    document.addEventListener("mousemove", move);
                    document.addEventListener("mouseup", up);
                });
            });
        }

        function setupDrag() {
            var draggedKey = "";
            headerRow.querySelectorAll("[data-column-key]").forEach(function (th) {
                var key = th.dataset.columnKey;
                if (locked.has(key)) return;
                th.draggable = true;
                th.addEventListener("dragstart", function (event) {
                    if (event.target.closest(".grid-resize-handle")) {
                        event.preventDefault();
                        return;
                    }
                    draggedKey = key;
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", key);
                });
                th.addEventListener("dragover", function (event) {
                    if (!draggedKey || draggedKey === key || locked.has(key)) return;
                    event.preventDefault();
                    th.classList.add("grid-drag-over");
                });
                th.addEventListener("dragleave", function () {
                    th.classList.remove("grid-drag-over");
                });
                th.addEventListener("drop", function (event) {
                    event.preventDefault();
                    th.classList.remove("grid-drag-over");
                    if (!draggedKey || draggedKey === key || locked.has(key)) return;
                    var order = normalizedOrder().filter(function (item) { return item !== draggedKey; });
                    var targetIndex = order.indexOf(key);
                    order.splice(targetIndex, 0, draggedKey);
                    writeJson(orderKey, order);
                    applyOrder();
                });
                th.addEventListener("dragend", function () {
                    draggedKey = "";
                    headerRow.querySelectorAll(".grid-drag-over").forEach(function (cell) {
                        cell.classList.remove("grid-drag-over");
                    });
                });
            });
        }

        function sortBy(key) {
            if (locked.has(key)) return;
            sortState.direction = sortState.key === key && sortState.direction === "asc" ? "desc" : "asc";
            sortState.key = key;
            var rows = Array.from(tbody.querySelectorAll("tr"));
            var visualRows = rows.filter(function (row) { return isVisualRow(row) || isEmptyMessageRow(row); });
            rows = rows.filter(function (row) { return !isVisualRow(row) && !isEmptyMessageRow(row); });
            rows.sort(function (a, b) {
                var aText = cellText(a.querySelector('[data-column-key="' + CSS.escape(key) + '"]'));
                var bText = cellText(b.querySelector('[data-column-key="' + CSS.escape(key) + '"]'));
                var aNum = numericValue(aText);
                var bNum = numericValue(bText);
                var result = aNum != null && bNum != null ? aNum - bNum : aText.localeCompare(bText, "zh-Hans-CN");
                return sortState.direction === "asc" ? result : -result;
            });
            rows.forEach(function (row) { tbody.appendChild(row); });
            visualRows.forEach(function (row) { tbody.appendChild(row); });
            updateRowNumbers();
            headerRow.querySelectorAll("th[data-column-key]").forEach(function (th) {
                th.classList.remove("document-grid-sort-asc", "document-grid-sort-desc");
                th.removeAttribute("aria-sort");
            });
            var activeHeader = headerRow.querySelector('[data-column-key="' + CSS.escape(key) + '"]');
            if (activeHeader) {
                activeHeader.classList.add(sortState.direction === "asc" ? "document-grid-sort-asc" : "document-grid-sort-desc");
                activeHeader.setAttribute("aria-sort", sortState.direction === "asc" ? "ascending" : "descending");
            }
        }

        function openColumnPanel(anchor) {
            var panel = document.querySelector(".document-grid-column-panel");
            if (panel) panel.remove();
            var hidden = new Set(readJson(hiddenKey, []));
            var widths = readJson(widthKey, {});
            var alignments = readJson(alignKey, {});
            panel = document.createElement("div");
            panel.className = "document-grid-column-panel";
            panel.innerHTML = columns().filter(function (column) { return !locked.has(column.key); }).map(function (column) {
                var currentWidth = parseInt(widths[column.key] || 0, 10) || "";
                return '<label class="document-grid-column-row"><span><input type="checkbox" value="' + escapeHtml(column.key) + '" ' + (hidden.has(column.key) ? "" : "checked") + '> ' + escapeHtml(column.label) + '</span><input class="document-grid-width-input" type="number" min="72" max="640" step="10" value="' + escapeHtml(currentWidth) + '" data-column-width-key="' + escapeHtml(column.key) + '" placeholder="宽度"></label>';
            }).join("");
            panel.querySelectorAll(".document-grid-column-row").forEach(function (row) {
                var widthInput = row.querySelector("[data-column-width-key]");
                var columnKey = widthInput && widthInput.dataset.columnWidthKey;
                if (!columnKey) return;
                var select = document.createElement("select");
                select.className = "document-grid-align-select";
                select.dataset.columnAlignKey = columnKey;
                [
                    ["", "默认"],
                    ["left", "左"],
                    ["center", "中"],
                    ["right", "右"]
                ].forEach(function (optionDef) {
                    var option = document.createElement("option");
                    option.value = optionDef[0];
                    option.textContent = optionDef[1];
                    if ((alignments[columnKey] || "") === option.value) option.selected = true;
                    select.appendChild(option);
                });
                row.appendChild(select);
            });
            document.body.appendChild(panel);
            var rect = anchor.getBoundingClientRect();
            panel.style.left = Math.min(rect.left, window.innerWidth - 240) + "px";
            panel.style.top = (rect.bottom + 6) + "px";
            panel.addEventListener("change", function () {
                var nextHidden = [];
                panel.querySelectorAll("input[type=checkbox]").forEach(function (input) {
                    if (!input.checked) nextHidden.push(input.value);
                });
                writeJson(hiddenKey, nextHidden);
                applyHidden();
            });
            panel.querySelectorAll("[data-column-width-key]").forEach(function (input) {
                input.addEventListener("input", function () {
                    var width = parseFloat(input.value);
                    if (Number.isFinite(width)) setColumnWidth(input.dataset.columnWidthKey, width);
                });
            });
            panel.querySelectorAll("[data-column-align-key]").forEach(function (select) {
                select.addEventListener("change", function () {
                    setColumnAlignment(select.dataset.columnAlignKey, select.value);
                });
            });
            setTimeout(function () {
                document.addEventListener("click", function close(event) {
                    if (panel.contains(event.target) || event.target === anchor) return;
                    panel.remove();
                    document.removeEventListener("click", close);
                });
            }, 0);
        }

        ensureHeaderChrome();
        loadCustomFields();
        setupResize();
        setupDrag();
        applyOrder();
        applyWidths();
        applyHidden();
        applyAlignments();
        syncDateEmptyState(table);
        collectCustomFields();

        table.addEventListener("click", function (event) {
            var th = event.target.closest("th[data-column-key]");
            if (!th || event.target.closest(".grid-resize-handle")) return;
            sortBy(th.dataset.columnKey);
        });
        table.addEventListener("input", function (event) {
            if (event.target.matches("[data-custom-field-key]")) collectCustomFields();
            if (event.target.matches('input[type="date"]')) syncDateEmptyState(event.target.closest("tr") || table);
        });
        table.addEventListener("change", function (event) {
            collectCustomFields();
            if (event.target.matches('input[type="date"]')) syncDateEmptyState(event.target.closest("tr") || table);
        });
        table.addEventListener("focusin", function (event) {
            var cell = editableCellForField(event.target);
            if (cell) markSelectedCell(cell);
        });
        table.addEventListener("click", function (event) {
            var cell = event.target.closest("td[data-column-key]");
            if (!cell || !tbody.contains(cell) || isVisualRow(cell.closest("tr")) || isEmptyMessageRow(cell.closest("tr"))) return;
            markSelectedCell(cell);
        });
        table.addEventListener("keydown", function (event) {
            var field = event.target.closest && event.target.closest("input, select, textarea");
            if (!field || field.type === "hidden") return;
            if (event.altKey || event.metaKey || event.ctrlKey) return;
            var moved = false;
            if (event.key === "Enter") moved = moveFocus(field, event.shiftKey ? -1 : 1, 0);
            if (event.key === "Tab") moved = moveFocus(field, 0, event.shiftKey ? -1 : 1);
            if (field.tagName !== "SELECT" && event.key === "ArrowUp") moved = moveFocus(field, -1, 0);
            if (field.tagName !== "SELECT" && event.key === "ArrowDown") moved = moveFocus(field, 1, 0);
            if (moved) event.preventDefault();
        });
        table.addEventListener("paste", function (event) {
            var field = event.target.closest && event.target.closest("input, select, textarea");
            if (!field || field.readOnly || field.disabled) return;
            var text = event.clipboardData && event.clipboardData.getData("text");
            if (applyPastedMatrix(field, text || "")) {
                event.preventDefault();
                if (typeof showToast === "function") showToast("已按电子表格区域粘贴。", "success");
            }
        });

        var api = {
            refresh: function () {
                ensureRowNumberColumn();
                tbody.querySelectorAll("tr").forEach(addCustomCellsToRow);
                setupResize();
                setupDrag();
                applyOrder();
                applyWidths();
                applyHidden();
                applyAlignments();
                syncDateEmptyState(table);
                collectCustomFields();
                updateRowNumbers();
            },
            openColumnPanel: openColumnPanel,
            addCustomField: function () {
                var label = window.prompt("自定义字段名称");
                if (!label) return;
                label = label.trim();
                if (!label) return;
                var definitions = readJson(customKey, []);
                var key = "custom_" + Date.now();
                var field = {key: key, label: label};
                definitions.push(field);
                writeJson(customKey, definitions);
                addCustomFieldColumn(field);
                setupResize();
                setupDrag();
                applyOrder();
                collectCustomFields();
            },
            reset: function () {
                localStorage.removeItem(widthKey);
                localStorage.removeItem(orderKey);
                localStorage.removeItem(hiddenKey);
                localStorage.removeItem(alignKey);
                localStorage.removeItem(customKey);
                window.location.reload();
            },
            currentRow: activeRow,
            insertRow: function (createRow, after) {
                if (typeof createRow !== "function") return null;
                var base = activeRow();
                var row = createRow();
                if (!row) return null;
                if (after) {
                    if (base && base.nextSibling) tbody.insertBefore(row, base.nextSibling);
                    else tbody.appendChild(row);
                } else if (base) {
                    tbody.insertBefore(row, base);
                } else {
                    tbody.appendChild(row);
                }
                this.refresh();
                focusFirstEditable(row);
                return row;
            },
            copyCurrentRow: function () {
                copiedRowValues = copyRowValues(activeRow());
                return copiedRowValues;
            },
            pasteToCurrentRow: function () {
                pasteRowValues(activeRow(), copiedRowValues);
            },
            duplicateCurrentRow: function (createRow) {
                var values = copyRowValues(activeRow());
                var row = this.insertRow(createRow, true);
                pasteRowValues(row, values);
                return row;
            },
            moveCurrentRow: function (direction) {
                var row = activeRow();
                if (!row) return;
                if (direction < 0 && row.previousElementSibling) {
                    tbody.insertBefore(row, row.previousElementSibling);
                }
                if (direction > 0 && row.nextElementSibling) {
                    tbody.insertBefore(row.nextElementSibling, row);
                }
                collectCustomFields();
                updateRowNumbers();
                focusFirstEditable(row);
            },
            deleteCurrentRow: function () {
                var row = activeRow();
                if (!row || businessRows().length <= 1) return;
                var next = row.nextElementSibling || row.previousElementSibling;
                row.remove();
                collectCustomFields();
                updateRowNumbers();
                focusFirstEditable(next);
            }
        };
        window.documentGridApi = api;
        return api;
    }

    window.initDocumentGrid = initDocumentGrid;
    document.addEventListener("DOMContentLoaded", function () {
        syncDateEmptyState(document);
        document.addEventListener("input", function (event) {
            if (event.target && event.target.matches('input[type="date"]')) syncDateEmptyState(event.target);
        });
        document.addEventListener("change", function (event) {
            if (event.target && event.target.matches('input[type="date"]')) syncDateEmptyState(event.target);
        });
        document.querySelectorAll("[data-document-grid]").forEach(initDocumentGrid);
    });
})();
