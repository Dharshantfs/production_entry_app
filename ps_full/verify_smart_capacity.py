import frappe
from frappe.utils import getdate, add_days, nowdate

def verify_smart_allocation():
    frappe.db.rollback() # Start fresh or safe
    
    # 1. Setup Test Data
    unit = "Unit 1"
    limit = 4.4 # Tons
    today = nowdate()
    
    print(f"\n--- Testing Smart Allocation on {today} ---")
    
    # Clear existing orders for Unit 1 today to have predictable state
    frappe.db.sql("DELETE FROM `tabPlanning Sheet Item` WHERE unit=%s AND parent IN (SELECT name FROM `tabPlanning sheet` WHERE ordered_date=%s)", (unit, today))
    
    # Create Dummy "Full" Load (4.0 Tons)
    # create_dummy_order(qty_tons=4.0, unit=unit, date=today)
    # We can just manually insert to save time/complexity
    ps = frappe.new_doc("Planning sheet")
    ps.customer = "Test Customer Content"
    ps.ordered_date = today
    ps.append("items", {
        "item_code": "TEST-FULL",
        "qty": 4000, # 4T
        "unit": unit,
        "quality": "SUPER PLATINUM" # Valid for Unit 1
    })
    ps.insert()
    print("Created 4T Load in Unit 1.")
    
    # 2. Test Updates (Moving a new order to this full unit)
    # Create a new small order (1T) - Should fit? 4+1 = 5 > 4.4. FAIL.
    # Should move to Neighbor (Unit 2? 3?) or Next Day.
    
    ps_new = frappe.new_doc("Planning sheet")
    ps_new.customer = "Test Overflow"
    ps_new.ordered_date = today # Initially wants today
    ps_new.append("items", {
        "item_code": "TEST-OVERFLOW",
        "qty": 1000, # 1T
        "unit": unit, # Wants Unit 1
        "quality": "SUPER PLATINUM"
    })
    ps_new.insert()
    
    print(f"Update Attempt: Moving 1T order to {unit} on {today} (Current Load: ~4T)...")
    
    try:
        from production_scheduler.production_scheduler.api import update_schedule
        result = update_schedule(ps_new.name, unit, today)
        
        print(f"Result: {result}")
        
        moved_to = result.get("moved_to", {})
        if moved_to.get("unit") != unit:
            print(f"✅ Auto-moved to Neighbor Unit: {moved_to.get('unit')}")
        elif str(moved_to.get("date")) != str(today):
            print(f"✅ Auto-moved to Next Day: {moved_to.get('date')}")
        else:
            print("❌ Remained in target? This suggests validation failed or limits ignored.")
            
    except Exception as e:
        print(f"❌ Error: {e}")

    frappe.db.rollback() # Cleanup

verify_smart_allocation()
