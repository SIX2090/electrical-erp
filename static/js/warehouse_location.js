// 出入库单据 仓库/库位 联动助手
// 规则：仓库在 locations 表有库位记录→库位必填且可选；无库位记录→库位灰显、非必填。
// 用法：仓库 <select> 加 class "js-wh-loc-warehouse"，配对的库位 <select> 加 class "js-wh-loc-location"
// （同一行 <tr> 内就近配对；表头字段同样适用）。
(function () {
    'use strict';
    var ERP = window.ERP || (window.ERP = {});
    var ENDPOINT = '/api/lookup/warehouse_locations';

    function toInt(v) {
        var n = parseInt(v, 10);
        return isNaN(n) ? 0 : n;
    }

    function placeholderOption(text) {
        var o = document.createElement('option');
        o.value = '';
        o.textContent = text;
        return o;
    }

    function syncSearchInput(locationSelect, placeholder) {
        var wrapper = locationSelect.closest('.select-search');
        var input = wrapper ? wrapper.querySelector('.select-search-input') : null;
        if (!input) return;
        input.disabled = !!locationSelect.disabled;
        input.required = !!locationSelect.required;
        if (placeholder) input.placeholder = placeholder;
        var selected = locationSelect.options[locationSelect.selectedIndex];
        input.value = selected && selected.value ? (selected.textContent || '').trim() : '';
    }

    // 用返回的库位列表重建库位下拉，并按 has_locations 切换灰显/必填
    function applyState(locationSelect, data, keepValue) {
        if (!locationSelect) return;
        var prev = keepValue ? (locationSelect.value || locationSelect.dataset.selected || '') : '';
        locationSelect.innerHTML = '';
        if (data && data.has_locations) {
            locationSelect.appendChild(placeholderOption('请选择库位'));
            (data.locations || []).forEach(function (loc) {
                var o = document.createElement('option');
                o.value = String(loc.id);
                o.textContent = loc.name || '';
                o.dataset.warehouseId = String(loc.warehouse_id || loc.warehouseId || '');
                if (String(loc.id) === String(prev)) o.selected = true;
                locationSelect.appendChild(o);
            });
            locationSelect.disabled = false;
            locationSelect.required = true;
            syncSearchInput(locationSelect, locationSelect.options[0] ? locationSelect.options[0].textContent : '');
        } else {
            locationSelect.appendChild(placeholderOption('未启用库位'));
            locationSelect.value = '';
            locationSelect.disabled = true;
            locationSelect.required = false;
            syncSearchInput(locationSelect, locationSelect.options[0] ? locationSelect.options[0].textContent : '');
        }
        locationSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function fetchAndApply(warehouseSelect, locationSelect) {
        if (!warehouseSelect || !locationSelect) return;
        var wid = toInt(warehouseSelect.value);
        if (wid <= 0) {
            applyState(locationSelect, { has_locations: false, locations: [] }, false);
            return;
        }
        fetch(ENDPOINT + '?warehouse_id=' + encodeURIComponent(wid), { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : { has_locations: false, locations: [] }; })
            .then(function (data) { applyState(locationSelect, data, true); })
            .catch(function () { applyState(locationSelect, { has_locations: false, locations: [] }, false); });
    }

    // 查找配对的库位下拉：优先用仓库下拉上的 data-wh-loc-target 指定选择器；
    // #id 全局定位；.class 仅在当前行/容器内定位（适配调拨明细同行的调出/调入两对字段）。
    // 否则在同一行（<tr> 或最近祖先容器）内就近查找。
    function findPairedLocation(warehouseSelect) {
        if (!warehouseSelect) return null;
        var target = warehouseSelect.getAttribute('data-wh-loc-target');
        if (target) {
            if (target.charAt(0) === '#') {
                var byId = document.querySelector(target);
                if (byId && byId.tagName === 'SELECT') return byId;
            } else {
                var row = warehouseSelect.closest('tr') || warehouseSelect.closest('.document-entry-grid') || warehouseSelect.parentElement;
                if (row) {
                    var byClass = row.querySelector('select' + target);
                    if (byClass) return byClass;
                }
            }
        }
        var fallbackRow = warehouseSelect.closest('tr') || warehouseSelect.closest('.document-entry-grid') || warehouseSelect.parentElement;
        if (!fallbackRow) return null;
        return fallbackRow.querySelector('select.js-wh-loc-location');
    }

    function headerWarehouseValueFor(lineName) {
        // 行仓库字段名 → 对应表头仓库字段名
        var headerName = 'warehouse_id';
        if (lineName.indexOf('from_warehouse') >= 0) headerName = 'from_warehouse_id';
        else if (lineName.indexOf('to_warehouse') >= 0) headerName = 'to_warehouse_id';
        var hdr = document.querySelector('select.js-wh-loc-warehouse[name="' + headerName + '"]')
            || document.querySelector('select.js-wh-loc-warehouse[name="warehouse_id"]')
            || document.querySelector('select.js-wh-loc-warehouse[name="from_warehouse_id"]');
        return hdr ? hdr.value : '';
    }

    function bindPair(warehouseSelect) {
        if (!warehouseSelect || warehouseSelect.dataset.whLocBound === '1') return;
        warehouseSelect.dataset.whLocBound = '1';
        warehouseSelect.addEventListener('change', function () {
            var loc = findPairedLocation(warehouseSelect);
            if (loc) {
                // 仓库切换后清掉既选库位，避免脏值
                loc.dataset.selected = '';
                fetchAndApply(warehouseSelect, loc);
            }
        });
        // 行仓库为空时继承表头仓库（等价于“留空使用表头”），再判定库位
        var name = warehouseSelect.getAttribute('name') || '';
        if (name.indexOf('[]') >= 0 && !warehouseSelect.value) {
            var inherited = headerWarehouseValueFor(name);
            if (inherited) warehouseSelect.value = inherited;
        }
        // 初始进入（含编辑态回填）：以当前库位值为保留值
        var loc = findPairedLocation(warehouseSelect);
        if (loc) {
            loc.dataset.selected = loc.value || loc.dataset.selected || '';
            fetchAndApply(warehouseSelect, loc);
        }
    }

    function scanAll(root) {
        var scope = root || document;
        var nodes = scope.querySelectorAll ? scope.querySelectorAll('select.js-wh-loc-warehouse:not([data-wh-loc-bound])') : [];
        Array.prototype.forEach.call(nodes, bindPair);
    }

    // 新行默认带表头仓库：行仓库为空时用表头仓库填充，再触发联动
    ERP.syncLineWarehouseFromHeader = function (headerWarehouseSelector) {
        var header = document.querySelector(headerWarehouseSelector || 'select.js-wh-loc-warehouse[name="warehouse_id"], select.js-wh-loc-warehouse[name="from_warehouse_id"]');
        if (!header) return;
        var hwid = header.value;
        if (!hwid) return;
        document.querySelectorAll('select.js-wh-loc-warehouse[name^="line_"]').forEach(function (lineWh) {
            if (!lineWh.value) {
                lineWh.value = hwid;
                var loc = findPairedLocation(lineWh);
                if (loc) { loc.dataset.selected = ''; fetchAndApply(lineWh, loc); }
            }
        });
    };

    ERP.WarehouseLocation = {
        bind: bindPair,
        scan: scanAll,
        apply: fetchAndApply
    };

    function init() {
        scanAll(document);
        // 监听动态增行
        var grid = document.querySelector('.document-entry-grid, [data-document-grid]');
        if (grid && typeof MutationObserver !== 'undefined') {
            var obs = new MutationObserver(function (mutations) {
                mutations.forEach(function (m) {
                    m.addedNodes.forEach(function (n) {
                        if (n.nodeType === 1) scanAll(n);
                    });
                });
            });
            obs.observe(grid, { childList: true, subtree: true });
        }
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
