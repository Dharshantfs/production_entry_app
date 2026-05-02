import os
import re
from pathlib import Path


file_path = Path(__file__).resolve().parent / "production_entry" / "public" / "js" / "ProductionScheduler.vue"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix isLaminationBoard check
content = re.sub(
    r'isLaminationBoard\.value = Boolean\(r && r\[0\] === "lamination-board"\);',
    r'isLaminationBoard.value = Boolean(r && r[0] && r[0].toLowerCase().replace(/-/g, " ") === "lamination board");',
    content
)

# Fix goToPlan route
content = re.sub(
    r'frappe\.set_route\("lamination-order-table", query\);',
    r'frappe.set_route("Lamination Order Table", query);',
    content
)
content = re.sub(
    r'frappe\.set_route\("production-table", query\);',
    r'frappe.set_route("Production Table", query);',
    content
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched ProductionScheduler.vue")
