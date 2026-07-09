/**
 * Excel风格可编辑表格组件
 * 提供类似Excel的编辑体验：键盘导航、快速编辑、批量操作
 */

class ExcelTable {
    constructor(tableId, options = {}) {
        this.table = document.getElementById(tableId);
        if (!this.table) {
            console.error('Table not found:', tableId);
            return;
        }

        this.options = {
            editableFields: options.editableFields || ['quantity', 'price'],
            onSave: options.onSave || null,
            onError: options.onError || null,
            autoSave: options.autoSave !== false,
            enableKeyboard: options.enableKeyboard !== false,
            enableCopyPaste: options.enableCopyPaste !== false,
            ...options
        };

        this.currentCell = null;
        this.isEditing = false;
        this.editHistory = [];

        this.init();
    }

    init() {
        this.setupEditableCells();
        if (this.options.enableKeyboard) {
            this.setupKeyboardNavigation();
        }
        if (this.options.enableCopyPaste) {
            this.setupCopyPaste();
        }
        this.setupCellSelection();
    }

    /**
     * 设置可编辑单元格
     */
    setupEditableCells() {
        const cells = this.table.querySelectorAll('.editable-cell');
        cells.forEach(cell => {
            // 移除旧的事件监听器
            const newCell = cell.cloneNode(true);
            cell.parentNode.replaceChild(newCell, cell);

            // 双击编辑
            newCell.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                this.startEdit(newCell);
            });

            // 单击选中
            newCell.addEventListener('click', (e) => {
                e.stopPropagation();
                this.selectCell(newCell);
            });

            // 直接输入开始编辑（数字键）
            newCell.addEventListener('keydown', (e) => {
                if (!this.isEditing && this.isNumberKey(e.key)) {
                    this.startEdit(newCell, e.key);
                    e.preventDefault();
                }
            });
        });
    }

    /**
     * 判断是否为数字键
     */
    isNumberKey(key) {
        return /^[0-9.]$/.test(key);
    }

    /**
     * 选中单元格
     */
    selectCell(cell) {
        // 移除之前的选中状态
        const prevSelected = this.table.querySelector('.cell-selected');
        if (prevSelected) {
            prevSelected.classList.remove('cell-selected');
        }

        // 添加选中状态
        cell.classList.add('cell-selected');
        this.currentCell = cell;
        cell.focus();
    }

    /**
     * 开始编辑
     */
    startEdit(cell, initialValue = null) {
        if (this.isEditing) return;
        if (cell.querySelector('input')) return;

        const field = cell.dataset.field;
        const value = cell.dataset.value || cell.textContent.replace(/[¥,]/g, '').trim();
        const itemId = cell.closest('tr').dataset.id;

        // 创建输入框
        const input = document.createElement('input');
        input.type = 'number';
        input.step = '0.01';
        input.className = 'excel-edit-input';
        input.value = initialValue !== null ? initialValue : value;

        // 保存原始内容
        const originalContent = cell.innerHTML;
        const originalValue = value;

        // 替换为输入框
        cell.innerHTML = '';
        cell.appendChild(input);
        cell.classList.add('cell-editing');
        this.isEditing = true;
        this.currentCell = cell;

        // 聚焦并选中
        input.focus();
        if (initialValue === null) {
            input.select();
        }

        // 保存函数
        const saveEdit = () => {
            const newValue = parseFloat(input.value);

            // 验证
            if (isNaN(newValue) || newValue < 0) {
                this.showError('请输入有效的数值');
                this.cancelEdit(cell, originalContent, originalValue);
                return;
            }

            // 如果值没变，直接取消
            if (newValue === parseFloat(originalValue)) {
                this.cancelEdit(cell, originalContent, originalValue);
                return;
            }

            // 保存
            this.saveCell(cell, itemId, field, newValue, originalContent, originalValue);
        };

        // 取消函数
        const cancelEdit = () => {
            this.cancelEdit(cell, originalContent, originalValue);
        };

        // 事件监听
        input.addEventListener('blur', saveEdit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                input.blur(); // 触发保存
                // Enter后移动到下一行同列
                setTimeout(() => {
                    if (!this.isEditing) {
                        this.moveToNextRow(cell);
                    }
                }, 100);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                cancelEdit();
            } else if (e.key === 'Tab') {
                e.preventDefault();
                input.blur(); // 触发保存
                // Tab后移动到下一列
                setTimeout(() => {
                    if (!this.isEditing) {
                        if (e.shiftKey) {
                            this.moveToPrevCell(cell);
                        } else {
                            this.moveToNextCell(cell);
                        }
                    }
                }, 100);
            }
        });
    }

    /**
     * 取消编辑
     */
    cancelEdit(cell, originalContent, originalValue) {
        cell.innerHTML = originalContent;
        cell.dataset.value = originalValue;
        cell.classList.remove('cell-editing');
        this.isEditing = false;
        this.selectCell(cell);
    }

    /**
     * 保存单元格
     */
    saveCell(cell, itemId, field, newValue, originalContent, originalValue) {
        const row = cell.closest('tr');
        const quantityCell = row.querySelector('[data-field="quantity"]');
        const priceCell = row.querySelector('[data-field="price"]');

        const formData = new FormData();
        formData.append('id', itemId);
        formData.append('quantity', field === 'quantity' ? newValue : (quantityCell?.dataset.value || 0));
        formData.append('price', field === 'price' ? newValue : (priceCell?.dataset.value || 0));

        // 显示保存中状态
        cell.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

        // 调用保存回调或默认保存
        const savePromise = this.options.onSave
            ? this.options.onSave(itemId, field, newValue, formData)
            : this.defaultSave(formData);

        savePromise
            .then(res => {
                if (res.status === 'success') {
                    this.showSuccess('保存成功');
                    // 更新显示
                    cell.dataset.value = newValue;
                    const displayValue = field === 'price' ? '¥' + newValue.toFixed(2) : newValue.toFixed(2);
                    cell.innerHTML = displayValue;
                    cell.classList.remove('cell-editing');
                    this.isEditing = false;

                    // 更新金额列
                    this.updateAmount(row);

                    // 重新选中单元格
                    this.selectCell(cell);
                } else {
                    throw new Error(res.msg || '保存失败');
                }
            })
            .catch(err => {
                this.showError(err.message || '保存失败');
                this.cancelEdit(cell, originalContent, originalValue);
                if (this.options.onError) {
                    this.options.onError(err);
                }
            });
    }

    /**
     * 默认保存方法
     */
    defaultSave(formData) {
        return Promise.reject(new Error('未配置表格保存地址'));
    }

    /**
     * 更新金额列
     */
    updateAmount(row) {
        const quantityCell = row.querySelector('[data-field="quantity"]');
        const priceCell = row.querySelector('[data-field="price"]');
        const amountCell = row.querySelector('.text-end.fw-bold');

        if (quantityCell && priceCell && amountCell) {
            const quantity = parseFloat(quantityCell.dataset.value || 0);
            const price = parseFloat(priceCell.dataset.value || 0);
            const amount = quantity * price;
            amountCell.textContent = '¥' + amount.toFixed(2);
        }

        // 更新合计
        this.updateTotal();
    }

    /**
     * 更新合计行
     */
    updateTotal() {
        const tbody = this.table.querySelector('tbody');
        const rows = tbody.querySelectorAll('tr[data-id]');
        let totalQty = 0;
        let totalAmount = 0;

        rows.forEach(row => {
            const qtyCell = row.querySelector('[data-field="quantity"]');
            const priceCell = row.querySelector('[data-field="price"]');
            if (qtyCell && priceCell) {
                const qty = parseFloat(qtyCell.dataset.value || 0);
                const price = parseFloat(priceCell.dataset.value || 0);
                totalQty += qty;
                totalAmount += qty * price;
            }
        });

        // 更新合计行
        const tfoot = this.table.querySelector('tfoot');
        if (tfoot) {
            const qtyTotal = tfoot.querySelector('td:nth-last-child(3)');
            const amountTotal = tfoot.querySelector('td:nth-last-child(2)');
            if (qtyTotal) qtyTotal.textContent = totalQty.toFixed(2);
            if (amountTotal) amountTotal.textContent = '¥' + totalAmount.toFixed(2);
        }
    }

    /**
     * 键盘导航
     */
    setupKeyboardNavigation() {
        this.table.addEventListener('keydown', (e) => {
            if (this.isEditing) return;
            if (!this.currentCell) return;

            switch(e.key) {
                case 'ArrowRight':
                    e.preventDefault();
                    this.moveToNextCell(this.currentCell);
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    this.moveToPrevCell(this.currentCell);
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    this.moveToNextRow(this.currentCell);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this.moveToPrevRow(this.currentCell);
                    break;
                case 'Enter':
                    e.preventDefault();
                    this.startEdit(this.currentCell);
                    break;
                case 'F2':
                    e.preventDefault();
                    this.startEdit(this.currentCell);
                    break;
            }
        });
    }

    /**
     * 移动到下一个单元格
     */
    moveToNextCell(cell) {
        const row = cell.closest('tr');
        const cells = Array.from(row.querySelectorAll('.editable-cell'));
        const currentIndex = cells.indexOf(cell);

        if (currentIndex < cells.length - 1) {
            this.selectCell(cells[currentIndex + 1]);
        } else {
            // 移动到下一行第一个可编辑单元格
            this.moveToNextRow(cell, true);
        }
    }

    /**
     * 移动到上一个单元格
     */
    moveToPrevCell(cell) {
        const row = cell.closest('tr');
        const cells = Array.from(row.querySelectorAll('.editable-cell'));
        const currentIndex = cells.indexOf(cell);

        if (currentIndex > 0) {
            this.selectCell(cells[currentIndex - 1]);
        } else {
            // 移动到上一行最后一个可编辑单元格
            this.moveToPrevRow(cell, true);
        }
    }

    /**
     * 移动到下一行
     */
    moveToNextRow(cell, toFirst = false) {
        const row = cell.closest('tr');
        const nextRow = row.nextElementSibling;

        if (nextRow && nextRow.dataset.id) {
            const cells = Array.from(nextRow.querySelectorAll('.editable-cell'));
            if (cells.length > 0) {
                if (toFirst) {
                    this.selectCell(cells[0]);
                } else {
                    // 移动到同列
                    const currentIndex = Array.from(row.querySelectorAll('.editable-cell')).indexOf(cell);
                    this.selectCell(cells[Math.min(currentIndex, cells.length - 1)]);
                }
            }
        }
    }

    /**
     * 移动到上一行
     */
    moveToPrevRow(cell, toLast = false) {
        const row = cell.closest('tr');
        const prevRow = row.previousElementSibling;

        if (prevRow && prevRow.dataset.id) {
            const cells = Array.from(prevRow.querySelectorAll('.editable-cell'));
            if (cells.length > 0) {
                if (toLast) {
                    this.selectCell(cells[cells.length - 1]);
                } else {
                    // 移动到同列
                    const currentIndex = Array.from(row.querySelectorAll('.editable-cell')).indexOf(cell);
                    this.selectCell(cells[Math.min(currentIndex, cells.length - 1)]);
                }
            }
        }
    }

    /**
     * 设置单元格选择
     */
    setupCellSelection() {
        // 点击表格外取消选中
        document.addEventListener('click', (e) => {
            if (!this.table.contains(e.target)) {
                const selected = this.table.querySelector('.cell-selected');
                if (selected) {
                    selected.classList.remove('cell-selected');
                }
                this.currentCell = null;
            }
        });
    }

    /**
     * 复制粘贴支持
     */
    setupCopyPaste() {
        this.table.addEventListener('keydown', (e) => {
            if (this.isEditing) return;

            // Ctrl+C 复制
            if (e.ctrlKey && e.key === 'c' && this.currentCell) {
                e.preventDefault();
                const value = this.currentCell.dataset.value || this.currentCell.textContent.replace(/[¥,]/g, '').trim();
                navigator.clipboard.writeText(value);
                this.showSuccess('已复制');
            }

            // Ctrl+V 粘贴
            if (e.ctrlKey && e.key === 'v' && this.currentCell) {
                e.preventDefault();
                navigator.clipboard.readText().then(text => {
                    const value = parseFloat(text);
                    if (!isNaN(value) && value >= 0) {
                        this.startEdit(this.currentCell, value.toString());
                    } else {
                        this.showError('粘贴内容无效');
                    }
                });
            }
        });
    }

    /**
     * 显示成功消息
     */
    showSuccess(msg) {
        if (typeof showToast === 'function') {
            showToast(msg, 'success');
        } else {
            // Success toast is optional on pages without the toast helper.
        }
    }

    /**
     * 显示错误消息
     */
    showError(msg) {
        if (typeof showToast === 'function') {
            showToast(msg, 'danger');
        } else {
            console.error('Error:', msg);
        }
    }

    /**
     * 刷新表格
     */
    refresh() {
        this.setupEditableCells();
    }

    /**
     * 销毁实例
     */
    destroy() {
        // 清理事件监听器
        this.currentCell = null;
        this.isEditing = false;
    }
}

// 导出到全局
window.ExcelTable = ExcelTable;
