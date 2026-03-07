import frappe
import json

def test_api():
    from production_entry.production_entry.doctype.shaft_production_run.shaft_production_run import get_job_roll_details

    res = get_job_roll_details(
        production_plan="MFG-PP-2026-00203", 
        job_id="1", 
        combination='46" + 42" + 26" / 66"', 
        no_of_shafts=1
    )

    print(json.dumps(res, indent=2, default=str))

test_api()
