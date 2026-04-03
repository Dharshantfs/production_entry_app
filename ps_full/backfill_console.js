// Paste this into browser console (F12 -> Console)
// Backfills Planning sheet.customer_name for existing records

(() => {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Planning sheet',
            fields: ['name', 'customer'],
            limit_page_length: 0
        },
        callback: function (r) {
            const sheets = (r && r.message) || [];
            if (!sheets.length) {
                console.log('No Planning Sheets found.');
                return;
            }

            const targets = sheets.filter((s) => s.customer);
            if (!targets.length) {
                console.log('No records with customer found.');
                return;
            }

            console.log(`Found ${sheets.length} Planning Sheets. Starting backfill for ${targets.length}.`);

            let done = 0;
            let updated = 0;
            let failed = 0;

            function finishOne() {
                done += 1;
                if (done % 25 === 0 || done === targets.length) {
                    console.log(`Progress ${done}/${targets.length} | Updated: ${updated} | Failed: ${failed}`);
                }

                if (done === targets.length) {
                    console.log(`Backfill finished. Updated: ${updated}, Failed: ${failed}`);
                    if (updated > 0) {
                        console.log('Reloading page in 2 seconds...');
                        setTimeout(() => location.reload(), 2000);
                    }
                }
            }

            targets.forEach((sheet) => {
                frappe.call({
                    method: 'frappe.client.get',
                    args: {
                        doctype: 'Customer',
                        name: sheet.customer
                    },
                    callback: function (cr) {
                        const customerName = cr && cr.message && cr.message.customer_name;
                        if (!customerName) {
                            failed += 1;
                            console.warn(`Customer name missing for ${sheet.customer} (${sheet.name})`);
                            finishOne();
                            return;
                        }

                        frappe.call({
                            method: 'frappe.client.set_value',
                            args: {
                                doctype: 'Planning sheet',
                                name: sheet.name,
                                fieldname: 'customer_name',
                                value: customerName
                            },
                            callback: function () {
                                updated += 1;
                                finishOne();
                            },
                            error: function () {
                                // Some sites use custom_customer_name instead of customer_name.
                                frappe.call({
                                    method: 'frappe.client.set_value',
                                    args: {
                                        doctype: 'Planning sheet',
                                        name: sheet.name,
                                        fieldname: 'custom_customer_name',
                                        value: customerName
                                    },
                                    callback: function () {
                                        updated += 1;
                                        finishOne();
                                    },
                                    error: function () {
                                        failed += 1;
                                        console.error(`Failed updating ${sheet.name}`);
                                        finishOne();
                                    }
                                });
                            }
                        });
                    },
                    error: function () {
                        failed += 1;
                        console.error(`Failed reading customer ${sheet.customer} (${sheet.name})`);
                        finishOne();
                    }
                });
            });
        },
        error: function () {
            console.error('Failed to read Planning Sheets list.');
        }
    });
})();
