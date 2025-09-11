// Stock Management System JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Confirm delete actions
    document.addEventListener('click', function(e) {
        if (e.target.matches('.btn-delete, .btn-danger[data-confirm]')) {
            if (!confirm('Are you sure you want to delete this item? This action cannot be undone.')) {
                e.preventDefault();
                return false;
            }
        }
    });

    // Form validation
    var forms = document.querySelectorAll('.needs-validation');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Stock quantity validation
    var quantityInputs = document.querySelectorAll('input[name="requested_quantity"]');
    quantityInputs.forEach(function(input) {
        input.addEventListener('change', function() {
            var maxQuantity = parseInt(this.getAttribute('max'));
            var currentValue = parseInt(this.value);
            
            if (currentValue > maxQuantity) {
                this.setCustomValidity(`Maximum available quantity is ${maxQuantity}`);
                this.classList.add('is-invalid');
            } else {
                this.setCustomValidity('');
                this.classList.remove('is-invalid');
                this.classList.add('is-valid');
            }
        });
    });

    // Real-time search functionality
    var searchInputs = document.querySelectorAll('input[name="search"]');
    searchInputs.forEach(function(input) {
        var timeoutId;
        input.addEventListener('input', function() {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(function() {
                if (input.value.length >= 2 || input.value.length === 0) {
                    input.form.submit();
                }
            }, 500);
        });
    });

    // Dynamic status badges
    function updateStatusBadges() {
        var statusElements = document.querySelectorAll('[data-status]');
        statusElements.forEach(function(element) {
            var status = element.getAttribute('data-status');
            element.className = element.className.replace(/badge bg-\w+/g, '');
            
            switch(status) {
                case 'Pending':
                    element.classList.add('badge', 'bg-warning');
                    break;
                case 'Approved':
                    element.classList.add('badge', 'bg-success');
                    break;
                case 'Denied':
                    element.classList.add('badge', 'bg-danger');
                    break;
                case 'In Transit':
                    element.classList.add('badge', 'bg-info');
                    break;
                case 'Received':
                    element.classList.add('badge', 'bg-success');
                    break;
                default:
                    element.classList.add('badge', 'bg-secondary');
            }
        });
    }

    // Call on page load
    updateStatusBadges();

    // Table row highlighting
    var tableRows = document.querySelectorAll('table tbody tr');
    tableRows.forEach(function(row) {
        row.addEventListener('click', function() {
            // Remove highlight from other rows
            tableRows.forEach(function(r) {
                r.classList.remove('table-active');
            });
            
            // Add highlight to clicked row
            this.classList.add('table-active');
        });
    });

    // Loading states for forms
    var submitButtons = document.querySelectorAll('button[type="submit"]');
    submitButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            var form = this.closest('form');
            if (form && form.checkValidity()) {
                this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';
                this.disabled = true;
                
                // Re-enable after 5 seconds as fallback
                setTimeout(function() {
                    button.disabled = false;
                    button.innerHTML = button.getAttribute('data-original-text') || 'Submit';
                }, 5000);
            }
        });
    });

    // Password strength indicator
    var passwordFields = document.querySelectorAll('input[type="password"]');
    passwordFields.forEach(function(field) {
        if (field.name === 'password') {
            field.addEventListener('input', function() {
                var password = this.value;
                var strength = calculatePasswordStrength(password);
                showPasswordStrength(this, strength);
            });
        }
    });

    function calculatePasswordStrength(password) {
        var score = 0;
        if (!password) return score;
        
        // Award points
        if (password.length >= 8) score += 1;
        if (/[a-z]/.test(password)) score += 1;
        if (/[A-Z]/.test(password)) score += 1;
        if (/[0-9]/.test(password)) score += 1;
        if (/[^A-Za-z0-9]/.test(password)) score += 1;
        
        return score;
    }

    function showPasswordStrength(input, strength) {
        var strengthMeter = input.parentNode.querySelector('.password-strength');
        if (!strengthMeter) {
            strengthMeter = document.createElement('div');
            strengthMeter.className = 'password-strength mt-1';
            input.parentNode.appendChild(strengthMeter);
        }

        var strengthText = ['Very Weak', 'Weak', 'Fair', 'Good', 'Strong'];
        var strengthClass = ['text-danger', 'text-warning', 'text-info', 'text-success', 'text-success'];
        
        if (input.value.length === 0) {
            strengthMeter.innerHTML = '';
            return;
        }
        
        strengthMeter.innerHTML = `<small class="${strengthClass[strength]}">Password strength: ${strengthText[strength]}</small>`;
    }

    // Auto-refresh functionality for dashboards
    if (window.location.pathname.includes('dashboard')) {
        // Refresh every 5 minutes
        setTimeout(function() {
            window.location.reload();
        }, 300000);
    }

    // Print functionality
    window.printTable = function(tableId) {
        var printWindow = window.open('', '_blank');
        var table = document.getElementById(tableId);
        
        if (table) {
            printWindow.document.write(`
                <html>
                    <head>
                        <title>Stock Management Report</title>
                        <style>
                            body { font-family: Arial, sans-serif; }
                            table { border-collapse: collapse; width: 100%; }
                            th, td { border: 1px solid #000; padding: 8px; text-align: left; }
                            th { background-color: #f2f2f2; }
                        </style>
                    </head>
                    <body>
                        <h2>Stock Management Report</h2>
                        <p>Generated on: ${new Date().toLocaleString()}</p>
                        ${table.outerHTML}
                    </body>
                </html>
            `);
            printWindow.document.close();
            printWindow.print();
        }
    };

    // Export to CSV functionality
    window.exportToCSV = function(tableId, filename) {
        var csv = [];
        var table = document.getElementById(tableId);
        
        if (!table) return;
        
        var rows = table.querySelectorAll('tr');
        
        for (var i = 0; i < rows.length; i++) {
            var row = [];
            var cols = rows[i].querySelectorAll('td, th');
            
            for (var j = 0; j < cols.length; j++) {
                var cellText = cols[j].innerText.replace(/"/g, '""');
                row.push('"' + cellText + '"');
            }
            
            csv.push(row.join(','));
        }
        
        // Create download
        var csvContent = csv.join('\n');
        var blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        var link = document.createElement('a');
        
        if (link.download !== undefined) {
            var url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', filename);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    };
});

// Utility functions
function formatDate(dateString) {
    var date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

// Global error handler
window.addEventListener('error', function(e) {
    console.error('Error:', e.error);
    // Optionally show user-friendly error message
});

// API helper functions
async function makeRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('Request failed:', error);
        throw error;
    }
}