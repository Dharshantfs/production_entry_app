import frappe
import json

def get_psi_fields():
    # Since I can't run this directly on Frappe Cloud, 
    # I'll create a script that users can run in the Console to tell me the fields.
    print("Run this in Console and paste the output:")
    print("fields = [f.fieldname for f in frappe.get_meta('Planning Sheet Item').fields]")
    print("print(fields)")

if __name__ == "__main__":
    get_psi_fields()
