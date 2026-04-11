// Initialize production_scheduler namespace
frappe.provide("production_scheduler");

// Simple controller that initializes the Confirmed Order page
// This uses Frappe's built-in async load mechanism
production_scheduler.ConfirmedOrderController = class {
    constructor(wrapper) {
        if (!wrapper) return;
        
        try {
            // Show loading message
            wrapper.innerHTML = '<div style="padding:16px;color:#111827;font-weight:600;">Loading confirmed orders...</div>';
            
            // Fetch data via API
            frappe.call({
                method: "production_scheduler.api.get_confirmed_orders_kanban",
                args: { order_date: frappe.datetime.get_today() },
                callback: (r) => {
                    if (r.message) {
                        // Data loaded successfully, now load the Vue component
                        loadConfirmedOrderPage(wrapper, r.message);
                    } else {
                        wrapper.innerHTML = '<div style="padding:16px;color:#b91c1c;font-weight:700;">No confirmed orders found.</div>';
                    }
                },
                error: (err) => {
                    console.error("Confirmed Order API Error:", err);
                    wrapper.innerHTML = '<div style="padding:16px;color:#b91c1c;font-weight:700;">Failed to load confirmed orders. Check server logs.</div>';
                }
            });
        } catch (e) {
            console.error("ConfirmedOrderController initialization failed:", e);
            wrapper.innerHTML = '<div style="padding:16px;color:#b91c1c;font-weight:700;">Failed to initialize. Error: ' + e.message + '</div>';
        }
    }
};

function loadConfirmedOrderPage(wrapper, initialData) {
    // This is a placeholder for actual Vue component initialization
    // For now, display the data in a simple table format
    try {
        let html = '<div style="padding:16px;"><h3>Confirmed Orders</h3>';
        html += '<p>Total Orders: ' + (initialData.length || 0) + '</p>';
        
        if (initialData && initialData.length > 0) {
            html += '<table style="width:100%;border-collapse:collapse;">';
            html += '<tr style="background-color:#f3f4f6;"><th style="padding:8px;border:1px solid #e5e7eb;text-align:left;">Item</th><th style="padding:8px;border:1px solid #e5e7eb;">Qty</th><th style="padding:8px;border:1px solid #e5e7eb;">Color</th><th style="padding:8px;border:1px solid #e5e7eb;">Unit</th></tr>';
            
            for (let item of initialData) {
                html += '<tr>';
                html += '<td style="padding:8px;border:1px solid #e5e7eb;">' + (item.itemName || item.name || '-') + '</td>';
                html += '<td style="padding:8px;border:1px solid #e5e7eb;">' + (item.qty || 0) + '</td>';
                html += '<td style="padding:8px;border:1px solid #e5e7eb;">' + (item.color || '-') + '</td>';
                html += '<td style="padding:8px;border:1px solid #e5e7eb;">' + (item.unit || 'Mixed') + '</td>';
                html += '</tr>';
            }
            
            html += '</table>';
        } else {
            html += '<p>No confirmed orders for today.</p>';
        }
        
        html += '</div>';
        wrapper.innerHTML = html;
    } catch (e) {
        console.error("Error rendering confirmed orders:", e);
        wrapper.innerHTML = '<div style="padding:16px;color:#b91c1c;font-weight:700;">Error rendering data: ' + e.message + '</div>';
    }
}
