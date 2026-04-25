// BROWSER CONSOLE DEBUG SCRIPT - Run this in browser F12 console to check data

// 1. CHECK WHAT'S IN THE GRID (locals object)
console.log("=== CHECKING GRID DATA ===");
if (cur_frm && cur_frm.fields_dict && cur_frm.fields_dict.items && cur_frm.fields_dict.items.grid) {
    const grid = cur_frm.fields_dict.items.grid;
    const rows = grid.grid_rows;
    
    if (rows && rows.length > 0) {
        rows.forEach((row, idx) => {
            const rowData = locals[row.doctype][row.name];
            console.log(`Row ${idx}:`, {
                name: row.name,
                gross_weight: rowData?.gross_weight,
                net_weight: rowData?.net_weight,
                produced_gsm: rowData?.produced_gsm,
                width_inch: rowData?.width_inch,
                meter_roll: rowData?.meter_roll,
                sticker_gsm: rowData?.sticker_gsm
            });
        });
    }
} else {
    console.log("No grid found!");
}

// 2. CHECK WHAT FRAPPE HAS IN DOC
console.log("\n=== CHECKING DOC DATA ===");
if (cur_frm && cur_frm.doc && cur_frm.doc.items) {
    cur_frm.doc.items.forEach((item, idx) => {
        console.log(`Item ${idx}:`, {
            idx: item.idx,
            gross_weight: item.gross_weight,
            net_weight: item.net_weight,
            produced_gsm: item.produced_gsm,
            width_inch: item.width_inch,
            meter_roll: item.meter_roll,
            sticker_gsm: item.sticker_gsm
        });
    });
}

// 3. CHECK LAST SAVE - What was actually sent to backend?
console.log("\n=== CHECKING LAST API CALL ===");
frappe.call({
    method: 'frappe.client.get',
    args: {
        doctype: cur_frm.doctype,
        name: cur_frm.doc.name
    },
    callback: function(r) {
        console.log("\n=== DATABASE STATE (LAST SAVED) ===");
        if (r.message && r.message.items) {
            r.message.items.forEach((item, idx) => {
                console.log(`DB Item ${idx}:`, {
                    idx: item.idx,
                    gross_weight: item.gross_weight,
                    net_weight: item.net_weight,
                    produced_gsm: item.produced_gsm,
                    width_inch: item.width_inch,
                    meter_roll: item.meter_roll,
                    sticker_gsm: item.sticker_gsm
                });
            });
        }
    }
});

console.log("\n✓ Check output above. If net_weight and produced_gsm are 0 in all three sections:");
console.log("   - Grid = 0 AND DB = 0 → Backend NOT calculating/setting values");
console.log("   - Grid = 0 BUT DB ≠ 0 → Frontend NOT refreshing grid");
console.log("   - Grid ≠ 0 BUT DB = 0 → NOT saving to database");
