import frappe


def execute():
    required = {
        "parent": "VARCHAR(140)",
        "parenttype": "VARCHAR(140)",
        "parentfield": "VARCHAR(140)",
        "idx": "INT NOT NULL DEFAULT 0",
    }

    doctypes = frappe.get_all("DocType", filters={"istable": 1}, pluck="name") or []
    for dt in doctypes:
        try:
            existing = set(frappe.db.get_table_columns(dt) or [])
        except Exception:
            # Table may not physically exist yet during pre_model_sync.
            # Skip safely; this patch is best-effort hardening only.
            continue
        for col, ddl in required.items():
            if col not in existing:
                frappe.db.sql(f"ALTER TABLE `tab{dt}` ADD COLUMN `{col}` {ddl}")

    frappe.db.commit()
