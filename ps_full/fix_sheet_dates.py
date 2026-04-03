import frappe

def execute():
    frappe.init(site="1zt.frappe.cloud")
    frappe.connect()

    WHITE_COLORS = [
        "WHITE", "BRIGHT WHITE", "P. WHITE", "P.WHITE", "R.F.D", "RFD", 
        "BLEACHED", "B.WHITE", "SNOW WHITE", "MILKY WHITE", "SUPER WHITE", "SUNSHINE WHITE",
        "BLEACH WHITE", "BLEACH WHITE 1.0", "BLEACH WHITE 2.0"
    ]

    # Find sheets with custom_planned_date
    sheets = frappe.db.sql("""
        SELECT name, custom_planned_date 
        FROM `tabPlanning sheet` 
        WHERE custom_planned_date IS NOT NULL 
          AND custom_planned_date != ''
    """, as_dict=True)

    count = 0
    for sheet in sheets:
        # Check if the sheet contains a pure white item
        items = frappe.db.get_all("Planning Sheet Item", filters={"parent": sheet.name}, fields=["color"])
        has_white = False
        for item in items:
            c = (item.color or "").upper().strip()
            # The strict check correctly implemented in the backend:
            if c and not any(x in c for x in ["IVORY", "CREAM", "OFF WHITE", "/"]):
                if any(w in c for w in WHITE_COLORS):
                    has_white = True
                    break
        
        # If the sheet has a white item, clear its header date so the white item falls back to ordered_date.
        # The true "color" items that were pushed will still be safe via custom_item_planned_date.
        if has_white:
            frappe.db.set_value("Planning sheet", sheet.name, "custom_planned_date", None)
            count += 1

    frappe.db.commit()
    print(f"Fixed {count} Mixed Sheets. Old White orders will now safely fallback to their ordered_date.")

if __name__ == "__main__":
    execute()
