import frappe
import json

def execute():
    """Rescue Patch: Restores Planning Sheet DocTypes from Deleted Documents bin.
    
    If the DocType was deleted during the last deploy, this patch finds the latest
    backup in the recycle bin and re-inserts it as a CUSTOM DocType in the 
    Manufacturing module.
    """
    for doctype_name in ["Planning Sheet", "Planning Sheet Item"]:
        if not frappe.db.exists("DocType", doctype_name):
            # 1. Find the latest backup in Deleted Document
            deleted_entry = frappe.db.get_value("Deleted Document", 
                {"deleted_doctype": "DocType", "deleted_name": doctype_name}, 
                ["name", "data"], as_dict=True, order_by="creation desc")
            
            if deleted_entry:
                try:
                    # 2. Parse the backup data
                    doc_dict = json.loads(deleted_entry.data)
                    
                    # 3. Clean up the data for re-insertion
                    doc_dict.update({
                        "doctype": "DocType",
                        "module": "Manufacturing",
                        "custom": 1, # Make it permanent
                        "__islocal": 1
                    })
                    
                    # Remove system fields that shouldn't be manually inserted
                    for field in ["creation", "modified", "modified_by", "owner", "docstatus"]:
                        doc_dict.pop(field, None)
                    
                    # 4. Create and insert the DocType
                    new_doc = frappe.get_doc(doc_dict)
                    new_doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
                    
                    frappe.logger().info(f"✅ Successfully rescued {doctype_name} from recycle bin")
                except Exception as e:
                    frappe.logger().error(f"❌ Failed to rescue {doctype_name}: {str(e)}")
            else:
                frappe.logger().warning(f"⚠️ No backup found for {doctype_name} in Deleted Documents")
        else:
            # 5. If it exists but has wrong module, fix it
            frappe.db.sql("UPDATE `tabDocType` SET module='Manufacturing', custom=1 WHERE name=%s", doctype_name)
            frappe.logger().info(f"✅ Fixed existing {doctype_name} module to Manufacturing")

    # Final cleanup
    frappe.db.commit()
    frappe.clear_cache()
