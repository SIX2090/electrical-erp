/* Clean ERP shared UI helpers. Keep this file free of retired WMS route maps. */
(function () {
    'use strict';

    function onReady(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback);
        } else {
            callback();
        }
    }

    function bindConfirmations() {
        document.querySelectorAll('[data-confirm]').forEach(function (el) {
            if (el.dataset.confirmBound === '1') return;
            el.dataset.confirmBound = '1';
            el.addEventListener('click', function (event) {
                var message = el.getAttribute('data-confirm') || '确认执行该操作？';
                if (!window.confirm(message)) {
                    event.preventDefault();
                    event.stopPropagation();
                }
            });
        });
    }

    function bindCheckAll() {
        document.querySelectorAll('#checkAll').forEach(function (master) {
            if (master.dataset.checkAllBound === '1') return;
            master.dataset.checkAllBound = '1';
            var table = master.closest('table') || document;
            var items = Array.prototype.slice.call(table.querySelectorAll('.check-item'));
            if (!items.length) return;

            master.addEventListener('change', function () {
                items.forEach(function (item) {
                    if (!item.disabled) item.checked = master.checked;
                });
            });

            items.forEach(function (item) {
                item.addEventListener('change', function () {
                    var enabled = items.filter(function (candidate) { return !candidate.disabled; });
                    var checked = enabled.filter(function (candidate) { return candidate.checked; });
                    master.checked = enabled.length > 0 && checked.length === enabled.length;
                    master.indeterminate = checked.length > 0 && checked.length < enabled.length;
                });
            });
        });
    }

    function initColumnSettings() {
        if (!window.localStorage || !window.MutationObserver) return;
        var tables = Array.prototype.slice.call(document.querySelectorAll('table.table'));
        var tableIndex = 0;
        tables.forEach(function (table) {
            if (table.dataset.columnSettingsReady === '1') return;
            if (table.dataset.columnSettings === 'off') return;
            if (table.hasAttribute('data-document-grid')) return;
            if (table.closest('.document-grid-column-panel')) return;
            var headRow = table.querySelector('thead tr');
            if (!headRow || headRow.children.length < 2) return;
            var body = table.tBodies && table.tBodies[0];
            if (!body) return;
            var hasActionColumn = Array.prototype.slice.call(headRow.children).some(function (cell) {
                var label = String(cell.textContent || '').replace(/\s+/g, '').trim().toLowerCase();
                return cell.dataset.columnSystem === 'actions' ||
                    cell.dataset.columnKey === 'actions' ||
                    label === 'actions' ||
                    label === '\u64cd\u4f5c' ||
                    label === '\u64cd\u4f5c\u83dc\u5355';
            });
            if (hasActionColumn) {
                table.dataset.columnSettingsReady = '1';
                return;
            }

            table.dataset.columnSettingsReady = '1';
            Array.prototype.slice.call(headRow.children).forEach(function (cell, index) {
                if (!cell.dataset.columnOriginalIndex) {
                    cell.dataset.columnOriginalIndex = String(index);
                }
                if (!cell.dataset.columnSettingsBaseId) {
                    cell.dataset.columnSettingsBaseId = cell.dataset.columnKey || cell.dataset.sortable || ('col' + index);
                }
            });
            var key = 'wms1.columnSettings.' + window.location.pathname + '.' + (table.id || ('table' + tableIndex++));
            var wrapper = table.closest('.table-responsive, .table-responsive-wrapper, .wms-mobile-table-scroll') || table.parentElement;
            if (wrapper && !wrapper.classList.contains('erp-column-settings-wrap')) {
                wrapper.classList.add('erp-column-settings-wrap');
            }

            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'erp-column-settings-btn';
            button.title = '栏目设置';
            button.setAttribute('aria-label', '栏目设置');
            button.innerHTML = '<i class="bi bi-gear"></i>';
            if (wrapper) wrapper.insertBefore(button, wrapper.firstChild);

            function readState() {
                try {
                    return JSON.parse(localStorage.getItem(key) || '{}') || {};
                } catch (err) {
                    return {};
                }
            }

            function saveState(state) {
                localStorage.setItem(key, JSON.stringify(state || {}));
            }

            function cleanColumnLabel(value, fallback) {
                var label = String(value || '').replace(/\s+/g, ' ').trim();
                label = label.replace(/[\s*＊]+$/g, '').trim();
                return label || fallback || '';
            }

            function defaultColumnName(index) {
                return '\u7b2c' + (index + 1) + '\u5217';
            }

            function labelFromHeaderCell(cell, index) {
                var fallback = defaultColumnName(index);
                if (cell.dataset.columnSystem === 'selection') {
                    return cleanColumnLabel(cell.dataset.columnLabel, '选择');
                }
                if (cell.dataset.columnSettingsDefaultLabel) {
                    return cleanColumnLabel(cell.dataset.columnSettingsDefaultLabel, fallback);
                }
                if (cell.dataset.columnLabel) {
                    cell.dataset.columnSettingsDefaultLabel = cleanColumnLabel(cell.dataset.columnLabel, fallback);
                    return cell.dataset.columnSettingsDefaultLabel;
                }
                var clone = cell.cloneNode(true);
                clone.querySelectorAll('.text-danger, .required-label, .sort-marker, i, button, input, select, textarea').forEach(function (node) {
                    node.remove();
                });
                var label = cleanColumnLabel(clone.textContent, fallback);
                cell.dataset.columnSettingsDefaultLabel = label;
                return label;
            }

            function defaultColumns() {
                return Array.prototype.slice.call(headRow.children).map(function (cell, index) {
                    var label = labelFromHeaderCell(cell, index);
                    var originalIndex = Number(cell.dataset.columnOriginalIndex || index);
                    var isSystemColumn = !!cell.dataset.columnSystem;
                    var isSystemSelection = cell.dataset.columnSystem === 'selection';
                    return {
                        id: cell.dataset.columnSettingsBaseId,
                        index: originalIndex,
                        originalLabel: label || defaultColumnName(index),
                        label: label || defaultColumnName(index),
                        locked: isSystemColumn || (index === 0 && !!cell.querySelector('input[type="checkbox"]')),
                        systemSelection: isSystemSelection
                    };
                });
            }

            function normalizedColumns() {
                var base = defaultColumns();
                var state = readState();
                var saved = Array.isArray(state.columns) ? state.columns : [];
                var byId = {};
                saved.forEach(function (column) { byId[column.id] = column; });
                var merged = base.map(function (column) {
                    var existing = byId[column.id] || {};
                    return {
                        id: column.id,
                        index: column.index,
                        originalLabel: column.originalLabel,
                        label: cleanColumnLabel(existing.label, column.originalLabel),
                        visible: existing.visible !== false,
                        locked: column.locked,
                        systemSelection: column.systemSelection
                    };
                });
                var ordered = [];
                saved.forEach(function (savedColumn) {
                    var found = merged.find(function (column) { return column.id === savedColumn.id; });
                    if (found && ordered.indexOf(found) === -1) ordered.push(found);
                });
                merged.forEach(function (column) {
                    if (ordered.indexOf(column) === -1) ordered.push(column);
                });
                return ordered;
            }

            function reorderCells(row, order) {
                if (!row || row.children.length !== order.length) return;
                var cells = Array.prototype.slice.call(row.children);
                var byOriginalIndex = {};
                cells.forEach(function (cell, currentIndex) {
                    var originalIndex = cell.dataset.columnOriginalIndex;
                    if (originalIndex === undefined) {
                        originalIndex = String(currentIndex);
                        cell.dataset.columnOriginalIndex = originalIndex;
                    }
                    byOriginalIndex[originalIndex] = cell;
                });
                var fragment = document.createDocumentFragment();
                order.forEach(function (column) {
                    if (byOriginalIndex[String(column.index)]) {
                        fragment.appendChild(byOriginalIndex[String(column.index)]);
                    }
                });
                row.appendChild(fragment);
            }

            function applyState() {
                var columns = normalizedColumns();
                var rowOrder = columns.map(function (column) {
                    return {
                        id: column.id,
                        index: column.index,
                        label: column.label,
                        visible: column.visible,
                        locked: column.locked,
                        systemSelection: column.systemSelection
                    };
                });

                [headRow].concat(Array.prototype.slice.call(table.querySelectorAll('tbody tr, tfoot tr'))).forEach(function (row) {
                    reorderCells(row, rowOrder);
                });

                var headers = Array.prototype.slice.call(headRow.children);
                headers.forEach(function (cell, displayIndex) {
                    var column = columns[displayIndex];
                    if (!column) return;
                    cell.dataset.columnSettingsId = column.id;
                    if (!cell.dataset.originalColumnLabel) cell.dataset.originalColumnLabel = column.originalLabel;
                    if (column.systemSelection) return;
                    if (column.label) {
                        var textTarget = cell.querySelector('.grid-header-text, .sort-label');
                        if (textTarget) textTarget.textContent = column.label;
                        else cell.childNodes.forEach(function (node) {
                            if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) node.textContent = column.label + ' ';
                        });
                        if (!cell.childNodes.length || !cell.textContent.trim()) cell.textContent = column.label;
                    }
                });

                Array.prototype.slice.call(table.querySelectorAll('tr')).forEach(function (row) {
                    Array.prototype.slice.call(row.children).forEach(function (cell, displayIndex) {
                        var column = columns[displayIndex];
                        if (!column) return;
                        cell.classList.toggle('erp-column-hidden', column.visible === false);
                    });
                });
            }

            function openDialog() {
                var old = document.querySelector('.erp-column-modal-backdrop');
                if (old) old.remove();
                var columns = normalizedColumns();
                var backdrop = document.createElement('div');
                backdrop.className = 'erp-column-modal-backdrop';
                backdrop.innerHTML =
                    '<div class="erp-column-modal" role="dialog" aria-modal="true" aria-label="栏目设置">' +
                    '<div class="erp-column-modal-head"><strong>栏目设置</strong><button type="button" class="erp-column-modal-close" aria-label="关闭"><i class="bi bi-x-lg"></i></button></div>' +
                    '<div class="erp-column-modal-body">' +
                    '<div class="erp-column-setting-hint">勾选显示栏目，可修改显示名称，并用上下按钮调整顺序。设置仅保存当前用户浏览器。</div>' +
                    '<div class="erp-column-setting-list"></div>' +
                    '</div>' +
                    '<div class="erp-column-modal-foot">' +
                    '<button type="button" class="btn btn-outline-secondary btn-sm" data-column-reset>恢复默认</button>' +
                    '<button type="button" class="btn btn-primary btn-sm" data-column-save>确定</button>' +
                    '</div>' +
                    '</div>';
                document.body.appendChild(backdrop);
                var list = backdrop.querySelector('.erp-column-setting-list');

                function renderRows() {
                    list.innerHTML = columns.map(function (column, index) {
                        return '<div class="erp-column-setting-row" data-column-id="' + escapeAttribute(column.id) + '">' +
                            '<span class="erp-column-setting-index">' + (index + 1) + '</span>' +
                            '<label class="erp-column-setting-check"><input type="checkbox" ' + (column.visible === false ? '' : 'checked') + (column.locked ? ' disabled' : '') + '> 显示</label>' +
                            '<input class="form-control form-control-sm" value="' + escapeAttribute(column.label) + '" aria-label="显示名称">' +
                            '<div class="erp-column-setting-move">' +
                            '<button type="button" class="btn btn-light btn-sm" data-move="-1" title="上移"><i class="bi bi-chevron-up"></i></button>' +
                            '<button type="button" class="btn btn-light btn-sm" data-move="1" title="下移"><i class="bi bi-chevron-down"></i></button>' +
                            '</div>' +
                            '</div>';
                    }).join('');
                }

                function collectRows() {
                    Array.prototype.slice.call(list.querySelectorAll('.erp-column-setting-row')).forEach(function (row, index) {
                        var column = columns[index];
                        if (!column) return;
                        var checkbox = row.querySelector('input[type="checkbox"]');
                        var input = row.querySelector('input.form-control');
                        column.visible = column.locked || checkbox.checked;
                        column.label = column.systemSelection ? column.originalLabel : cleanColumnLabel(input.value, column.originalLabel);
                    });
                }

                renderRows();
                list.addEventListener('click', function (event) {
                    var moveButton = event.target.closest('[data-move]');
                    if (!moveButton) return;
                    collectRows();
                    var row = moveButton.closest('.erp-column-setting-row');
                    var from = Array.prototype.indexOf.call(list.children, row);
                    var to = from + Number(moveButton.dataset.move);
                    if (to < 0 || to >= columns.length) return;
                    var moved = columns.splice(from, 1)[0];
                    columns.splice(to, 0, moved);
                    renderRows();
                });
                backdrop.querySelector('.erp-column-modal-close').addEventListener('click', function () {
                    backdrop.remove();
                });
                backdrop.addEventListener('click', function (event) {
                    if (event.target === backdrop) backdrop.remove();
                });
                backdrop.querySelector('[data-column-reset]').addEventListener('click', function () {
                    localStorage.removeItem(key);
                    backdrop.remove();
                    window.location.reload();
                });
                backdrop.querySelector('[data-column-save]').addEventListener('click', function () {
                    collectRows();
                    saveState({columns: columns});
                    backdrop.remove();
                    window.location.reload();
                });
            }

            function escapeAttribute(value) {
                return String(value || '').replace(/[&<>"']/g, function (ch) {
                    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];
                });
            }

            button.addEventListener('click', openDialog);
            applyState();

            var observer = new MutationObserver(function () {
                if (table.dataset.columnSettingsApplying === '1') return;
                table.dataset.columnSettingsApplying = '1';
                window.requestAnimationFrame(function () {
                    applyState();
                    table.dataset.columnSettingsApplying = '0';
                });
            });
            observer.observe(table, {childList: true, subtree: true});
        });
    }

    function bindListFilterToggle() {
        document.querySelectorAll('[data-toggle="list-filter"]').forEach(function (btn) {
            if (btn.dataset.filterToggleBound === '1') return;
            btn.dataset.filterToggleBound = '1';
            btn.addEventListener('click', function () {
                var card = btn.closest('.page-card') || btn.closest('.card') || document;
                var form = card.querySelector('[data-list-filter-form]');
                if (!form) return;
                var expanded = form.classList.toggle('d-none') === false;
                btn.setAttribute('aria-expanded', String(expanded));
                btn.classList.toggle('btn-secondary', expanded);
                btn.classList.toggle('btn-outline-secondary', !expanded);
                if (expanded) {
                    var firstInput = form.querySelector('input:not([type="hidden"]), select');
                    if (firstInput) firstInput.focus();
                }
            });
            // Reflect active filter state on page load
            var card = btn.closest('.page-card') || btn.closest('.card') || document;
            var form = card && card.querySelector('[data-list-filter-form]');
            if (form && !form.classList.contains('d-none')) {
                btn.classList.remove('btn-outline-secondary');
                btn.classList.add('btn-secondary');
                btn.setAttribute('aria-expanded', 'true');
            }
        });
    }

    window.initCheckAll = function () {
        bindCheckAll();
    };

    window.showToast = function (message, type, delay) {
        type = type || 'info';
        delay = delay || 2400;
        var container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1080';
            document.body.appendChild(container);
        }
        var el = document.createElement('div');
        el.className = 'toast align-items-center text-bg-' + type + ' border-0';
        el.setAttribute('role', 'alert');
        el.innerHTML = '<div class="d-flex"><div class="toast-body"></div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
        el.querySelector('.toast-body').textContent = message || '';
        container.appendChild(el);
        var toast = bootstrap.Toast.getOrCreateInstance(el, { delay: delay });
        el.addEventListener('hidden.bs.toast', function () { el.remove(); });
        toast.show();
    };

    window.showConfirm = function (message, options) {
        options = options || {};
        return Promise.resolve(window.confirm((options.title ? options.title + '\n' : '') + (message || '确认执行该操作？')));
    };

    window.deleteItem = async function (url, id) {
        var confirmed = await window.showConfirm('确定删除该记录吗？', { title: '删除确认' });
        if (!confirmed) return;
        var csrf = document.querySelector('meta[name="csrf-token"]');
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf ? csrf.getAttribute('content') : ''
            },
            body: JSON.stringify({ id: id })
        })
        .then(function (r) { return r.json(); })
        .then(function (res) {
            if (res.status === 'success' || res.ok) {
                window.showToast(res.msg || '删除成功', 'success');
                setTimeout(function () { location.reload(); }, 650);
            } else {
                window.showToast(res.msg || res.error || '删除失败', 'danger', 3600);
            }
        })
        .catch(function (err) { window.showToast('删除失败：' + err.message, 'danger', 3600); });
    };

    window.batchDelete = async function (url, tableId) {
        var table = document.getElementById(tableId);
        var checked = Array.prototype.slice.call((table || document).querySelectorAll('.check-item:checked'));
        var ids = checked.map(function (item) { return item.value; });
        if (!ids.length) {
            window.showToast('请先选择要删除的记录', 'warning');
            return;
        }
        var confirmed = await window.showConfirm('确定删除选中的 ' + ids.length + ' 条记录吗？', { title: '批量删除确认' });
        if (!confirmed) return;
        var csrf = document.querySelector('meta[name="csrf-token"]');
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf ? csrf.getAttribute('content') : ''
            },
            body: JSON.stringify({ ids: ids })
        })
        .then(function (r) { return r.json(); })
        .then(function (res) {
            if (res.status === 'success' || res.ok) {
                window.showToast(res.msg || '删除成功', 'success');
                setTimeout(function () { location.reload(); }, 650);
            } else {
                window.showToast(res.msg || res.error || '删除失败', 'danger', 3600);
            }
        })
        .catch(function (err) { window.showToast('删除失败：' + err.message, 'danger', 3600); });
    };

    function markActiveNav() {
        var path = window.location.pathname.replace(/\/+$/, '') || '/';
        document.querySelectorAll('[data-nav-link]').forEach(function (link) {
            var href = (link.getAttribute('href') || '').replace(/\/+$/, '') || '/';
            if (href === path) {
                link.classList.add('active');
            }
        });
    }

    function initTopbarTools() {
        var root = document.querySelector('[data-topbar-tools]');
        if (!root) return;

        function closeMenus() {
            root.querySelectorAll('[data-topbar-menu]').forEach(function (menu) {
                menu.classList.remove('is-open');
            });
            root.querySelectorAll('[data-topbar-toggle]').forEach(function (button) {
                button.classList.remove('is-open');
                button.setAttribute('aria-expanded', 'false');
            });
        }

        root.querySelectorAll('[data-topbar-toggle]').forEach(function (button) {
            button.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                var key = button.getAttribute('data-topbar-toggle');
                var menu = root.querySelector('[data-topbar-menu="' + key + '"]');
                var shouldOpen = menu && !menu.classList.contains('is-open');
                closeMenus();
                if (shouldOpen) {
                    menu.classList.add('is-open');
                    button.classList.add('is-open');
                    button.setAttribute('aria-expanded', 'true');
                }
            });
        });

        document.addEventListener('click', function (event) {
            if (!root.contains(event.target)) {
                closeMenus();
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeMenus();
            }
        });
    }

    function initAiAssistantPanel() {
        var panel = document.querySelector('[data-ai-assistant-panel]');
        if (!panel) return;
        var answer = panel.querySelector('[data-ai-answer]');
        var question = panel.querySelector('[data-ai-question]');
        var submit = panel.querySelector('[data-ai-submit]');

        function escapeHtml(value) {
            return String(value || '').replace(/[&<>"']/g, function (ch) {
                return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];
            });
        }

        function escapeAttribute(value) {
            return String(value || '').replace(/[&<>"']/g, function (ch) {
                return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];
            });
        }

        panel.querySelectorAll('[data-ai-example]').forEach(function (button) {
            button.addEventListener('click', function () {
                if (question) question.value = button.getAttribute('data-ai-example') || '';
                if (question) question.focus();
            });
        });

        if (submit) {
            submit.addEventListener('click', function () {
                var text = question ? question.value.trim() : '';
                if (!text) {
                    if (answer) answer.textContent = '请先输入要说明的问题。';
                    return;
                }
                submit.disabled = true;
                if (answer) answer.textContent = '正在生成说明...';
                var csrf = document.querySelector('meta[name="csrf-token"]');
                fetch('/api/ai-assistant/help', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrf ? csrf.getAttribute('content') : ''
                    },
                    body: JSON.stringify({mode: 'operation', question: text})
                })
                .then(function (res) {
                    return res.json().then(function (data) {
                        if (!res.ok && !data.reply) {
                            throw new Error(data.msg || '生成失败');
                        }
                        return data;
                    });
                })
                .then(function (data) {
                    if (!answer) return;
                    var html = escapeHtml(data.reply || data.msg || '没有返回说明。');
                    if (data.links && data.links.length) {
                        html += '<div class="erp-ai-link-list">';
                        data.links.forEach(function (link) {
                            html += '<a href="' + escapeAttribute(link.href || '#') + '">' + escapeHtml(link.label || link.href || '手册入口') + '</a>';
                        });
                        html += '</div>';
                    }
                    if (data.sections && data.sections.length) {
                        html += '<div class="erp-ai-link-list">';
                        data.sections.forEach(function (section) {
                            html += '<a href="' + escapeAttribute(section.href || '#') + '">' + escapeHtml(section.title || '手册章节') + '</a>';
                        });
                        html += '</div>';
                    }
                    answer.innerHTML = html;
                })
                .catch(function (err) {
                    if (answer) answer.textContent = '生成失败：' + err.message;
                })
                .finally(function () {
                    submit.disabled = false;
                });
            });
        }
    }

    function bindClientPagination() {
        document.querySelectorAll('table.client-paginate').forEach(function (table) {
            if (table.dataset.clientPaginate === '1') return;
            table.dataset.clientPaginate = '1';
            var tbody = table.tBodies && table.tBodies[0];
            if (!tbody) return;
            var allRows = Array.prototype.slice.call(tbody.rows);
            var total = allRows.length;
            var pageSize = parseInt(table.dataset.pageSize || '50', 10) || 50;
            var currentPage = 1;
            var totalPages = Math.max(1, Math.ceil(total / pageSize));
            if (total <= pageSize) return;

            var wrapper = document.createElement('div');
            wrapper.className = 'd-flex justify-content-between align-items-center mt-2 flex-wrap gap-2 client-pagination-bar';
            table.parentNode.insertBefore(wrapper, table.nextSibling);

            var info = document.createElement('div');
            info.className = 'text-muted small';
            wrapper.appendChild(info);

            var nav = document.createElement('div');
            nav.className = 'd-flex align-items-center gap-2';
            wrapper.appendChild(nav);

            var btnGroup = document.createElement('div');
            btnGroup.className = 'btn-group btn-group-sm';
            nav.appendChild(btnGroup);

            function btn(label, disabled, onClick) {
                var b = document.createElement('a');
                b.className = 'btn btn-outline-secondary' + (disabled ? ' disabled' : '');
                b.href = 'javascript:void(0)';
                b.textContent = label;
                if (!disabled) b.addEventListener('click', onClick);
                btnGroup.appendChild(b);
                return b;
            }

            var pageSpan = document.createElement('span');
            pageSpan.className = 'small text-muted mx-1';
            nav.appendChild(pageSpan);

            function render() {
                var start = (currentPage - 1) * pageSize;
                var end = Math.min(start + pageSize, total);
                allRows.forEach(function (row, idx) {
                    row.style.display = (idx >= start && idx < end) ? '' : 'none';
                });
                info.textContent = '\u5171 ' + total + ' \u6761\u8bb0\u5f55\uff0c\u5f53\u524d\u7b2c ' + (start + 1) + '-' + end + ' \u6761';
                btnGroup.innerHTML = '';
                btn('\u9996\u9875', currentPage <= 1, function () { currentPage = 1; render(); });
                btn('\u4e0a\u4e00\u9875', currentPage <= 1, function () { currentPage = Math.max(1, currentPage - 1); render(); });
                var s = Math.max(1, currentPage - 2);
                var e = Math.min(totalPages, currentPage + 2);
                for (var p = s; p <= e; p++) {
                    (function (pn) {
                        var b = btn(String(pn), false, function () { currentPage = pn; render(); });
                        if (pn === currentPage) { b.classList.remove('btn-outline-secondary'); b.classList.add('btn-primary'); }
                    })(p);
                }
                btn('\u4e0b\u4e00\u9875', currentPage >= totalPages, function () { currentPage = Math.min(totalPages, currentPage + 1); render(); });
                btn('\u672b\u9875', currentPage >= totalPages, function () { currentPage = totalPages; render(); });
                pageSpan.textContent = currentPage + ' / ' + totalPages;
            }
            render();
        });
    }

    function initDocumentDetailTables() {
        var content = document.querySelector('.content');
        if (!content || !content.querySelector('.document-menu-bar')) return;

        content.querySelectorAll('table.table').forEach(function (table) {
            if (table.dataset.documentDetailStyled === '1') return;
            if (table.closest('.document-grid-column-panel')) return;
            var thead = table.tHead;
            var tbody = table.tBodies && table.tBodies[0];
            if (!thead || !thead.rows.length || !tbody) return;
            var headers = Array.prototype.slice.call(thead.rows[0].cells);
            if (headers.length < 3) return;

            table.dataset.documentDetailStyled = '1';
            table.classList.add('erp-detail-grid');
            if (table.hasAttribute('data-document-grid')) {
                table.classList.add('erp-detail-grid-managed');
            }

            var wrapper = table.closest('.table-responsive, .table-responsive-wrapper, .wms-mobile-table-scroll, .document-grid-scroll') || table.parentElement;
            if (wrapper) wrapper.classList.add('erp-detail-grid-scroll');

            function normalizedText(node) {
                return String(node ? (node.innerText || node.textContent || '') : '').replace(/\s+/g, '').trim();
            }

            function columnKind(label) {
                if (!label) return 'text';
                if (/^(行号|序号|行|No\.?|#)$/i.test(label)) return 'rowno';
                if (/操作|动作/.test(label)) return 'action';
                if (/数量|数|金额|单价|成本|税额|税率|余额|应收|应付|已收|已付|未入库|已入库|已发|合格|报废|账存|实盘|差异|用量|损耗|需求|库存|领料|发料|收料/.test(label)) return 'number';
                if (/日期|时间/.test(label)) return 'date';
                if (/编码|编号|单号|批号|项目号|柜号|来源行|BOM|版本|科目编码/.test(label)) return 'code';
                if (/名称|物料|客户|供应商|摘要|备注|原因|说明|地址/.test(label)) return 'name';
                if (/规格|型号|仓库|库位|单位|状态|管控|分类/.test(label)) return 'medium';
                return 'text';
            }

            var widthMap = {
                rowno: 54,
                action: 86,
                number: 92,
                date: 112,
                code: 128,
                name: 168,
                medium: 118,
                text: 120
            };
            var totalWidth = 0;
            headers.forEach(function (th, index) {
                var label = normalizedText(th);
                var kind = th.dataset.erpColumnKind || columnKind(label);
                th.dataset.erpColumnKind = kind;
                th.classList.add('erp-detail-col-' + kind);
                var width = Number(th.dataset.erpColumnWidth || widthMap[kind] || 120);
                totalWidth += width;
                th.style.width = width + 'px';
                th.style.minWidth = width + 'px';
                th.style.maxWidth = width + 'px';

                Array.prototype.slice.call(tbody.rows).forEach(function (row) {
                    var cell = row.cells[index];
                    if (!cell) return;
                    cell.classList.add('erp-detail-col-' + kind);
                    cell.style.width = width + 'px';
                    cell.style.minWidth = width + 'px';
                    cell.style.maxWidth = width + 'px';
                    if (!cell.title) {
                        var title = String(cell.innerText || cell.textContent || '').replace(/\s+/g, ' ').trim();
                        if (title) cell.title = title;
                    }
                });
            });

            var minWidth = Math.max(totalWidth, wrapper ? wrapper.clientWidth : 0);
            table.style.minWidth = minWidth + 'px';
            table.style.width = minWidth + 'px';
        });
    }

    function initErpTableTools() {
        document.querySelectorAll('.content table.table').forEach(function (table, tableIndex) {
            if (table.dataset.erpTableTools === '1') return;
            if (table.closest('[data-no-table-tools]')) return;
            var thead = table.tHead;
            var tbody = table.tBodies && table.tBodies[0];
            if (!thead || !tbody || !thead.rows.length) return;
            var headerRow = thead.rows[0];
            var headers = Array.prototype.slice.call(headerRow.cells);
            if (!headers.length) return;
            table.dataset.erpTableTools = '1';
            table.dataset.tableIndex = String(tableIndex);

            function cellText(row, index) {
                var cell = row.cells[index];
                return cell ? (cell.innerText || cell.textContent || '').replace(/\s+/g, ' ').trim() : '';
            }

            function comparable(value) {
                var text = String(value || '').trim();
                var normalized = text.replace(/,/g, '');
                if (/^-?\d+(\.\d+)?$/.test(normalized)) return {type: 'number', value: Number(normalized)};
                var timestamp = Date.parse(text);
                if (!Number.isNaN(timestamp) && /\d{4}[-/]\d{1,2}[-/]\d{1,2}/.test(text)) {
                    return {type: 'date', value: timestamp};
                }
                return {type: 'text', value: text.toLowerCase()};
            }

            function sortRows(index) {
                var direction = table.dataset.sortIndex === String(index) && table.dataset.sortDirection === 'asc' ? 'desc' : 'asc';
                var rows = Array.prototype.slice.call(tbody.rows);
                rows.sort(function (a, b) {
                    var av = comparable(cellText(a, index));
                    var bv = comparable(cellText(b, index));
                    var result = 0;
                    if (av.type === bv.type && av.type !== 'text') {
                        result = av.value === bv.value ? 0 : (av.value > bv.value ? 1 : -1);
                    } else {
                        result = String(av.value).localeCompare(String(bv.value), 'zh-CN', {numeric: true, sensitivity: 'base'});
                    }
                    return direction === 'asc' ? result : -result;
                });
                rows.forEach(function (row) { tbody.appendChild(row); });
                table.dataset.sortIndex = String(index);
                table.dataset.sortDirection = direction;
                headers.forEach(function (th) {
                    th.classList.remove('table-sort-asc', 'table-sort-desc');
                    th.removeAttribute('aria-sort');
                    var marker = th.querySelector('.erp-client-sort-marker');
                    if (marker) marker.remove();
                });
                var active = headers[index];
                if (active) {
                    active.classList.add(direction === 'asc' ? 'table-sort-asc' : 'table-sort-desc');
                    active.setAttribute('aria-sort', direction === 'asc' ? 'ascending' : 'descending');
                    var markerNode = document.createElement('span');
                    markerNode.className = 'erp-client-sort-marker ms-1';
                    markerNode.textContent = direction === 'asc' ? '\u2191' : '\u2193';
                    active.appendChild(markerNode);
                }
            }

            headers.forEach(function (th, index) {
                if (th.dataset.columnSystem) return;
                if (th.querySelector('input, button, select, textarea')) return;
                th.style.cursor = 'pointer';
                th.title = th.title || '\u70b9\u51fb\u6392\u5e8f';
                th.addEventListener('click', function (event) {
                    if (event.target.closest('a, button, input, select, textarea')) return;
                    sortRows(index);
                });
            });
        });
    }

    function bindFormGuard() {
        document.querySelectorAll('form[method="post"], form[method="POST"]').forEach(function (form) {
            if (form.dataset.formGuardBound === '1') return;
            form.dataset.formGuardBound = '1';
            form.addEventListener('submit', function (event) {
                if (form.dataset.submitting === '1') {
                    event.preventDefault();
                    return;
                }
                form.dataset.submitting = '1';
                var submitter = event.submitter;
                if (!submitter || !form.contains(submitter)) {
                    var active = document.activeElement;
                    submitter = active && form.contains(active) && active.matches('button[type="submit"], input[type="submit"]') ? active : null;
                }
                form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(function (btn) {
                    if (btn.disabled) return;
                    btn.dataset._origDisabled = btn.disabled;
                    btn.disabled = true;
                    if (btn !== submitter) return;
                    if (btn.tagName === 'INPUT') {
                        btn.dataset._origValue = btn.value;
                        btn.value = '处理中...';
                    } else {
                        btn.dataset._origHtml = btn.innerHTML;
                        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 处理中...';
                    }
                });
            });
        });
    }

    function hideGlobalToolbarWhenPageHasActions() {
        // Unified toolbar architecture: global toolbar is always shown.
        // Local document-menu-bar elements are removed by base.html JS.
        // No need to hide global toolbar based on page actions.
        return;
    }

    function groupExportActionsIntoMore() {
        var exportPattern = /(\u5bfc\u51fa|\u5f15\u51fa|excel|xlsx|csv|pdf)/i;
        var candidates = Array.prototype.slice.call(document.querySelectorAll('.content a.btn, .content button.btn'));
        var byContainer = [];

        function isExportAction(el) {
            if (el.closest('.dropdown-menu, .document-menu-bar')) return false;
            var text = String(el.textContent || '').replace(/\s+/g, '').trim();
            var href = String(el.getAttribute('href') || '');
            var onclick = String(el.getAttribute('onclick') || '');
            return exportPattern.test(text) ||
                /export=(csv|xlsx|excel|pdf)/i.test(href) ||
                /format=(csv|xlsx|excel|pdf)/i.test(href) ||
                /export.*table|export.*report/i.test(onclick);
        }

        candidates.filter(isExportAction).forEach(function (el) {
            var container = el.parentElement;
            if (!container || container.closest('td, th, .dropdown-menu')) return;
            if (!container.matches('.d-flex, .btn-group, .section-title > div, .text-lg-end, .text-end, div')) return;
            var entry = byContainer.find(function (item) { return item.container === container; });
            if (!entry) {
                entry = { container: container, items: [] };
                byContainer.push(entry);
            }
            entry.items.push(el);
        });

        byContainer.forEach(function (entry) {
            if (!entry.items.length || entry.container.dataset.exportMoreGrouped === '1') return;
            entry.container.dataset.exportMoreGrouped = '1';
            var first = entry.items[0];
            var small = entry.items.some(function (item) { return item.classList.contains('btn-sm'); });
            var dropdown = document.createElement('div');
            dropdown.className = 'dropdown d-inline-block erp-export-more';
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-outline-secondary' + (small ? ' btn-sm' : '') + ' dropdown-toggle';
            btn.setAttribute('data-bs-toggle', 'dropdown');
            btn.setAttribute('aria-expanded', 'false');
            btn.innerHTML = '<i class="bi bi-three-dots"></i> \u66f4\u591a';
            var menu = document.createElement('ul');
            menu.className = 'dropdown-menu dropdown-menu-end';
            dropdown.appendChild(btn);
            dropdown.appendChild(menu);
            first.parentNode.insertBefore(dropdown, first);

            entry.items.forEach(function (item) {
                var li = document.createElement('li');
                item.classList.remove('btn', 'btn-primary', 'btn-secondary', 'btn-success', 'btn-outline-primary', 'btn-outline-secondary', 'btn-outline-success', 'btn-sm', 'btn-lg', 'me-2', 'ms-2', 'flex-fill');
                item.classList.add('dropdown-item');
                if (item.tagName === 'BUTTON' && !item.getAttribute('type')) {
                    item.type = 'button';
                }
                li.appendChild(item);
                menu.appendChild(li);
            });
        });
    }

    onReady(function () {
        bindConfirmations();
        bindCheckAll();
        bindListFilterToggle();
        bindFormGuard();
        markActiveNav();
        initTopbarTools();
        groupExportActionsIntoMore();
        hideGlobalToolbarWhenPageHasActions();
        initAiAssistantPanel();
        initDocumentDetailTables();
        initColumnSettings();
        initErpTableTools();
        bindClientPagination();
    });
})();
