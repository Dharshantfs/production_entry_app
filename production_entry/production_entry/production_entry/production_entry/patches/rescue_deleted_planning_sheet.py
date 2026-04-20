import frappe
import json

def execute():
    """Emergency Rescue: Restores Planning Sheet DocTypes from Deleted Documents bin.
    Uses a unique path to force execution during migrate.
    """
    for doctype_name in ["Planning Sheet", "Planning sheet", "Planning Sheet Item", "Planning sheet Item"]:
        # Find the latest backup in Deleted Document
        deleted_entry = frappe.db.get_value("Deleted Document", 
            {"deleted_doctype": "DocType", "deleted_name": doctype_name}, 
            ["name", "data"], as_dict=True, order_by="creation desc")
        
        if deleted_entry:
            try:
                # 1. Parse the backup data
                doc_dict = json.loads(deleted_entry.data)
                
                # 2. Force it to be a CUSTOM DocType in Manufacturing
                doc_dict.update({
                    "doctype": "DocType",
                    "module": "Manufacturing",
                    "custom": 1,
                    "__islocal": 1
                })
                
                # Remove system fields
                for field in ["creation", "modified", "modified_by", "owner", "docstatus"]:
                    doc_dict.pop(field, None)
                
                # 3. Check if already exists in DocType table (even if not in cache)
                if not frappe.db.exists("DocType", doc_dict['name']):
                    new_doc = frappe.get_doc(doc_dict)
                    new_doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
                    frappe.logger().info(f"✅ RESCUED {doctype_name}")
                else:
                    # Just update the existing record
                    frappe.db.sql("UPDATE `tabDocType` SET module='Manufacturing', custom=1 WHERE name=%s", doc_dict['name'])
                    frappe.logger().info(f"✅ UPDATED {doctype_name}")

            except Exception as e:
                frappe.logger().error(f"❌ Rescue failed for {doctype_name}: {str(e)}")

    # 4. Final Cleanup
    frappe.db.commit()
    frappe.clear_cache()
