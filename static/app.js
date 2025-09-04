class BTCOptionsScanner {
    constructor() {
        this.dataTable = null;
        this.lastScanParams = null;
        this.initializeEventListeners();
    }

    initializeEventListeners() {
        // Form submission
        document.getElementById('scannerForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.performScan();
        });

        // Export button
        document.getElementById('exportBtn').addEventListener('click', () => {
            this.exportResults();
        });

        // Clear button
        document.getElementById('clearBtn').addEventListener('click', () => {
            this.clearForm();
        });

        // DTE and Expiry mutual exclusion
        document.getElementById('dteMax').addEventListener('input', () => {
            if (document.getElementById('dteMax').value) {
                document.getElementById('expiry').value = '';
            }
        });

        document.getElementById('expiry').addEventListener('change', () => {
            if (document.getElementById('expiry').value) {
                document.getElementById('dteMax').value = '';
            }
        });
    }

    collectFormData() {
        const formData = {
            side: document.querySelector('input[name="side"]:checked').value,
            premium_in_btc: document.getElementById('premiumInBtc').checked,
            sort: document.getElementById('sortBy').value,
            desc: document.getElementById('sortDesc').checked,
            limit: parseInt(document.getElementById('limitResults').value) || 200
        };

        // Optional fields
        const dteMax = document.getElementById('dteMax').value;
        if (dteMax) formData.dte_max = parseInt(dteMax);

        const expiry = document.getElementById('expiry').value;
        if (expiry) formData.expiry = expiry;

        const deltaMin = document.getElementById('deltaMin').value;
        const deltaMax = document.getElementById('deltaMax').value;
        if (deltaMin && deltaMax) {
            formData.delta_band = [parseFloat(deltaMin), parseFloat(deltaMax)];
        }

        const premMin = document.getElementById('premMin').value;
        if (premMin) formData.prem_min = parseFloat(premMin);

        const premMax = document.getElementById('premMax').value;
        if (premMax) formData.prem_max = parseFloat(premMax);

        return formData;
    }

    async performScan() {
        try {
            this.showLoading();
            this.hideError();
            this.hideResults();

            const formData = this.collectFormData();
            this.lastScanParams = formData;

            const response = await fetch('/scan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });

            const result = await response.json();

            if (!result.success) {
                throw new Error(result.error || 'Unknown error occurred');
            }

            this.displayResults(result);
            document.getElementById('exportBtn').disabled = false;

        } catch (error) {
            this.showError(error.message);
            console.error('Scan error:', error);
        } finally {
            this.hideLoading();
        }
    }

    displayResults(result) {
        const { data, btc_spot, total_count } = result;

        // Update info
        const resultsInfo = document.getElementById('resultsInfo');
        resultsInfo.textContent = `BTC Spot: $${btc_spot.toFixed(2)} | Showing ${data.length} of ${total_count} options`;

        // Destroy existing DataTable if exists
        if (this.dataTable) {
            this.dataTable.destroy();
        }

        // Clear table body
        const tbody = document.querySelector('#resultsTable tbody');
        tbody.innerHTML = '';

        // Populate table
        data.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${row.instrument}</code></td>
                <td><span class="badge bg-${row.type === 'C' ? 'success' : 'danger'}">${row.type}</span></td>
                <td>${row.expiry}</td>
                <td>${row.dte}</td>
                <td>$${this.formatNumber(row.spot, 2)}</td>
                <td>$${this.formatNumber(row.strike, 0)}</td>
                <td>${this.formatPercentage(row.iv)}</td>
                <td>${this.formatNumber(row.delta, 3)}</td>
                <td>${this.formatNumber(row.premium_native, 8)}</td>
                <td>$${this.formatNumber(row.premium_usd, 2)}</td>
                <td>$${this.formatNumber(row.breakeven, 2)}</td>
                <td>${this.formatPercentage(row.pop_delta)}</td>
                <td>${this.formatPercentage(row.pop_logN)}</td>
            `;
            tbody.appendChild(tr);
        });

        // Initialize DataTable
        this.dataTable = new DataTable('#resultsTable', {
            pageLength: 25,
            lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]],
            order: [], // Maintain server-side ordering
            columnDefs: [
                { targets: [4, 5, 8, 9, 10], className: 'text-end' }, // Right-align numeric columns
                { targets: [6, 11, 12], className: 'text-end' } // Right-align percentage columns
            ],
            language: {
                search: "Filter results:",
                lengthMenu: "Show _MENU_ entries",
                info: "Showing _START_ to _END_ of _TOTAL_ entries",
                paginate: {
                    previous: "Previous",
                    next: "Next"
                }
            }
        });

        this.showResults();
    }

    async exportResults() {
        if (!this.lastScanParams) {
            this.showError('No scan data to export. Please run a scan first.');
            return;
        }

        try {
            const response = await fetch('/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(this.lastScanParams)
            });

            if (!response.ok) {
                throw new Error('Export failed');
            }

            // Create download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `btc_options_scan_${new Date().toISOString().slice(0, 10)}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

        } catch (error) {
            this.showError(`Export failed: ${error.message}`);
        }
    }

    clearForm() {
        document.getElementById('scannerForm').reset();
        document.getElementById('sideBoth').checked = true;
        document.getElementById('sortDesc').checked = true;
        document.getElementById('limitResults').value = 200;
        this.hideResults();
        this.hideError();
        document.getElementById('exportBtn').disabled = true;
    }

    formatNumber(value, decimals = 2) {
        if (value === null || value === undefined || isNaN(value)) {
            return 'N/A';
        }
        return value.toFixed(decimals);
    }

    formatPercentage(value) {
        if (value === null || value === undefined || isNaN(value)) {
            return 'N/A';
        }
        return (value * 100).toFixed(2) + '%';
    }

    showLoading() {
        document.getElementById('loadingSpinner').style.display = 'block';
    }

    hideLoading() {
        document.getElementById('loadingSpinner').style.display = 'none';
    }

    showResults() {
        document.getElementById('resultsContainer').style.display = 'block';
    }

    hideResults() {
        document.getElementById('resultsContainer').style.display = 'none';
    }

    showError(message) {
        document.getElementById('errorMessage').textContent = message;
        document.getElementById('errorContainer').style.display = 'block';
    }

    hideError() {
        document.getElementById('errorContainer').style.display = 'none';
    }
}

// Initialize the scanner when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new BTCOptionsScanner();
});
