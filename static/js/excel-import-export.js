/**
 * Excel导入导出组件
 * 支持单据明细的批量导入和导出
 */

class ExcelImportExport {
    constructor(options = {}) {
        this.options = {
            tableId: options.tableId || 'itemTable',
            exportUrl: options.exportUrl || null,
            importUrl: options.importUrl || null,
            templateUrl: options.templateUrl || null,
            fileName: options.fileName || '单据明细',
            columns: options.columns || [],
            onImportSuccess: options.onImportSuccess || null,
            onImportError: options.onImportError || null
        };

        this.init();
    }

    init() {
        // 创建导入导出按钮
        this.createButtons();
        // 创建导入模态框
        this.createImportModal();
    }

    createButtons() {
        // 查找表格容器内的工具栏（更精确的定位）
        const tableContainer = document.querySelector('.order-table-container');
        if (!tableContainer) {
            console.error('ExcelImportExport: 找不到 .order-table-container');
            return;
        }

        let toolbar = tableContainer.querySelector('.order-toolbar');

        // 如果没有 order-toolbar，尝试查找 table-header-custom
        if (!toolbar) {
            const header = tableContainer.querySelector('.table-header-custom');
            if (header && header.parentElement) {
                // 如果父元素不是 order-toolbar，创建一个
                if (!header.parentElement.classList.contains('order-toolbar')) {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'order-toolbar';
                    header.parentElement.insertBefore(wrapper, header);
                    wrapper.appendChild(header);
                    toolbar = wrapper;
                } else {
                    toolbar = header.parentElement;
                }
            }
        }

        if (!toolbar) {
            console.error('ExcelImportExport: 找不到工具栏容器');
            return;
        }


        // 查找或创建按钮组
        let btnGroup = toolbar.querySelector('.btn-group');
        if (!btnGroup) {
            btnGroup = document.createElement('div');
            btnGroup.className = 'btn-group';
            toolbar.appendChild(btnGroup);
        }


        // 导出按钮
        const exportBtn = document.createElement('button');
        exportBtn.className = 'btn-order btn-order-success btn-order-sm';
        exportBtn.innerHTML = '<i class="bi bi-file-earmark-excel"></i> 导出Excel';
        exportBtn.onclick = () => this.exportToExcel();
        btnGroup.appendChild(exportBtn);

        // 导入按钮
        const importBtn = document.createElement('button');
        importBtn.className = 'btn-order btn-order-primary btn-order-sm';
        importBtn.innerHTML = '<i class="bi bi-upload"></i> 导入Excel';
        importBtn.onclick = () => this.showImportModal();
        btnGroup.appendChild(importBtn);

        // 下载模板按钮
        if (this.options.templateUrl) {
            const templateBtn = document.createElement('button');
            templateBtn.className = 'btn-order btn-order-secondary btn-order-sm';
            templateBtn.innerHTML = '<i class="bi bi-download"></i> 下载模板';
            templateBtn.onclick = () => this.downloadTemplate();
            btnGroup.appendChild(templateBtn);
        }
    }

    createImportModal() {
        const modalHtml = `
        <div class="modal fade" id="excelImportModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5><i class="bi bi-upload"></i> 导入Excel</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-info d-flex align-items-start">
                            <i class="bi bi-info-circle me-2 mt-1"></i>
                            <div>
                                <strong>导入说明：</strong>
                                <ul class="mb-0 mt-2">
                                    <li>支持 .xlsx 和 .xls 格式</li>
                                    <li>第一行为表头，从第二行开始为数据</li>
                                    <li>必填列：${this.getRequiredColumns()}</li>
                                    <li>建议先下载模板，按模板格式填写数据</li>
                                </ul>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-medium">选择Excel文件</label>
                            <input type="file" class="form-control" id="excelFileInput"
                                   accept=".xlsx,.xls" />
                        </div>
                        <div id="importPreview" class="d-none">
                            <label class="form-label fw-medium">数据预览</label>
                            <div class="table-responsive" style="max-height: 300px;">
                                <table class="table table-sm table-bordered" id="previewTable">
                                    <thead></thead>
                                    <tbody></tbody>
                                </table>
                            </div>
                            <div class="mt-2">
                                <span class="badge bg-primary" id="previewCount">0</span> 条数据待导入
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button class="btn btn-primary" id="confirmImportBtn" disabled>
                            <i class="bi bi-check"></i> 确认导入
                        </button>
                    </div>
                </div>
            </div>
        </div>`;

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // 绑定文件选择事件
        document.getElementById('excelFileInput').addEventListener('change', (e) => {
            this.handleFileSelect(e);
        });

        // 绑定确认导入事件
        document.getElementById('confirmImportBtn').addEventListener('click', () => {
            this.confirmImport();
        });
    }

    getRequiredColumns() {
        const required = this.options.columns.filter(col => col.required);
        return required.map(col => col.label).join('、') || '物料编码、数量';
    }

    showImportModal() {
        const modal = new bootstrap.Modal(document.getElementById('excelImportModal'));
        modal.show();
        // 重置
        document.getElementById('excelFileInput').value = '';
        document.getElementById('importPreview').classList.add('d-none');
        document.getElementById('confirmImportBtn').disabled = true;
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        // 使用SheetJS读取Excel
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const data = new Uint8Array(e.target.result);
                const workbook = XLSX.read(data, { type: 'array' });
                const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
                const jsonData = XLSX.utils.sheet_to_json(firstSheet);

                if (jsonData.length === 0) {
                    this.showToast('Excel文件为空', 'warning');
                    return;
                }

                this.previewData = jsonData;
                this.showPreview(jsonData);
                document.getElementById('confirmImportBtn').disabled = false;
            } catch (error) {
                this.showToast('读取Excel文件失败：' + error.message, 'danger');
            }
        };
        reader.readAsArrayBuffer(file);
    }

    showPreview(data) {
        const preview = document.getElementById('importPreview');
        const table = document.getElementById('previewTable');
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');

        // 清空
        thead.innerHTML = '';
        tbody.innerHTML = '';

        if (data.length === 0) return;

        // 表头
        const headers = Object.keys(data[0]);
        const headerRow = document.createElement('tr');
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);

        // 数据（最多显示10行）
        const displayData = data.slice(0, 10);
        displayData.forEach(row => {
            const tr = document.createElement('tr');
            headers.forEach(header => {
                const td = document.createElement('td');
                td.textContent = row[header] || '';
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });

        document.getElementById('previewCount').textContent = data.length;
        preview.classList.remove('d-none');
    }

    confirmImport() {
        if (!this.previewData || this.previewData.length === 0) {
            this.showToast('没有可导入的数据', 'warning');
            return;
        }

        if (!this.options.importUrl) {
            this.showToast('未配置导入接口', 'danger');
            return;
        }

        const btn = document.getElementById('confirmImportBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> 导入中...';

        fetch(this.options.importUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || ''
            },
            body: JSON.stringify({ data: this.previewData })
        })
        .then(r => r.json())
        .then(res => {
            if (res.status === 'success') {
                this.showToast(`成功导入 ${res.count || this.previewData.length} 条数据`, 'success');
                bootstrap.Modal.getInstance(document.getElementById('excelImportModal')).hide();
                if (this.options.onImportSuccess) {
                    this.options.onImportSuccess(res);
                } else {
                    setTimeout(() => location.reload(), 800);
                }
            } else {
                this.showToast('导入失败：' + (res.msg || '未知错误'), 'danger');
                if (this.options.onImportError) {
                    this.options.onImportError(res);
                }
            }
        })
        .catch(err => {
            this.showToast('导入失败：' + err.message, 'danger');
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-check"></i> 确认导入';
        });
    }

    exportToExcel() {
        if (this.options.exportUrl) {
            // 使用服务器端导出
            window.open(this.options.exportUrl, '_blank');
        } else {
            // 使用客户端导出
            this.clientExport();
        }
    }

    clientExport() {
        const table = document.getElementById(this.options.tableId);
        if (!table) {
            this.showToast('未找到表格', 'warning');
            return;
        }

        // 获取表格数据
        const data = [];
        const headers = [];

        // 表头
        const headerCells = table.querySelectorAll('thead th');
        headerCells.forEach(th => {
            const text = th.textContent.trim();
            if (text && text !== '序' && text !== '操作' && !th.querySelector('input[type="checkbox"]')) {
                headers.push(text);
            }
        });

        // 数据行
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(tr => {
            if (tr.querySelector('.empty-state')) return;

            const rowData = {};
            const cells = tr.querySelectorAll('td');
            let headerIndex = 0;

            cells.forEach((td, index) => {
                // 跳过序号、复选框、操作列
                if (index === 0 || td.querySelector('input[type="checkbox"]') || td.querySelector('.btn')) {
                    return;
                }

                if (headerIndex < headers.length) {
                    let value = td.textContent.trim();
                    // 移除货币符号
                    value = value.replace(/¥|￥/g, '');
                    rowData[headers[headerIndex]] = value;
                    headerIndex++;
                }
            });

            if (Object.keys(rowData).length > 0) {
                data.push(rowData);
            }
        });

        if (data.length === 0) {
            this.showToast('没有可导出的数据', 'warning');
            return;
        }

        // 创建工作簿
        const ws = XLSX.utils.json_to_sheet(data);
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, '明细');

        // 下载
        const fileName = `${this.options.fileName}_${this.formatDate(new Date())}.xlsx`;
        XLSX.writeFile(wb, fileName);

        this.showToast('导出成功', 'success');
    }

    downloadTemplate() {
        if (this.options.templateUrl) {
            window.open(this.options.templateUrl, '_blank');
        } else {
            // 生成模板
            this.generateTemplate();
        }
    }

    generateTemplate() {
        const headers = this.options.columns.map(col => col.label);
        const example = {};
        this.options.columns.forEach(col => {
            example[col.label] = col.example || '';
        });

        const ws = XLSX.utils.json_to_sheet([example]);
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, '模板');

        XLSX.writeFile(wb, `${this.options.fileName}_导入模板.xlsx`);
        this.showToast('模板下载成功', 'success');
    }

    formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hour = String(date.getHours()).padStart(2, '0');
        const minute = String(date.getMinutes()).padStart(2, '0');
        return `${year}${month}${day}_${hour}${minute}`;
    }

    showToast(message, type = 'info') {
        if (typeof showToast === 'function') {
            showToast(message, type);
        } else {
            alert(message);
        }
    }
}

// 导出到全局
window.ExcelImportExport = ExcelImportExport;
