import frappe
import json
from production_scheduler.api import _find_best_unlocked_plan, _get_contextual_plan_name

def debug_plans():
    frappe.connect()
    try:
        raw_string = frappe.db.get_value("DefaultValue", {"defkey": "production_scheduler_color_chart_plans", "parent": "__default"}, "defvalue")
        print(f"RAW STRING: {raw_string}")
        
        if not raw_string:
            print("No plans found in global defaults.")
            return

        parsed = json.loads(raw_string)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
            
        print(f"PARSED PLANS: {json.dumps(parsed, indent=2)}")
        
        target_date = "2026-03-17"
        print(f"\nTesting with date: {target_date}")
        
        ctx_prefix = _get_contextual_plan_name("", target_date).strip()
        print(f"Contextual Prefix for {target_date}: '{ctx_prefix}'")
        
        matching_plan = _find_best_unlocked_plan(parsed, target_date)
        print(f"MATCHING PLAN RESULT: {matching_plan}")
        
        # Verify why it might be failing
        for plan in parsed:
            p_name = plan.get("name", "")
            p_locked = plan.get("locked")
            print(f"Checking Plan: '{p_name}', Locked: {p_locked} (type: {type(p_locked)})")
            
    finally:
        frappe.destroy()

if __name__ == "__main__":
    debug_plans()
