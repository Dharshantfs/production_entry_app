import os

path = r'c:\Users\Admin\Planning\production_scheduler\production_scheduler\public\js\ColorChart.vue'
if not os.path.exists(path):
    print(f"Error: {path} not found")
    exit(1)

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Original file has {len(lines)} lines")

# Based on latest view_file (Step 1210)
# line 877 is the end of initSortable: "}"
# line 1024 is the start of getUnitEntries: "function getUnitEntries(unit) {"

# Validate markers
if not lines[876].strip() == "}":
    print(f"Warning: Unexpected content at line 877: {lines[876].strip()}")
if not "function getUnitEntries(unit) {" in lines[1023]:
    print(f"Warning: Unexpected content at line 1024: {lines[1023].strip()}")

prefix = lines[:877]
suffix = lines[1023:]

new_middle = [
    "\n",
    "async function handleMoveSuccess(res, newUnit) {\n",
    "    if (res.message && res.message.status === 'success') {\n",
    "        const movedTo = res.message.moved_to || { unit: newUnit, date: filterOrderDate.value };\n",
    "        if (movedTo.date !== filterOrderDate.value) {\n",
    "             frappe.msgprint(`Moved to ${movedTo.date}`);\n",
    "        } else if (movedTo.unit !== newUnit) {\n",
    "             frappe.msgprint(`Placed in ${movedTo.unit} (Capacity Full in ${newUnit})`);\n",
    "        } else {\n",
    "             frappe.show_alert({ message: \"Moved successfully\", indicator: \"green\" });\n",
    "        }\n",
    "        unitSortConfig[movedTo.unit].mode = 'manual';\n",
    "        await fetchData(); \n",
    "    }\n",
    "}\n",
    "\n",
    "function getUnitSortConfig(unit) {\n",
    "  if (!unitSortConfig[unit]) {\n",
    "    unitSortConfig[unit] = { mode: 'auto', color: 'asc', gsm: 'desc', priority: 'color' };\n",
    "  }\n",
    "  return unitSortConfig[unit];\n",
    "}\n",
    "\n",
    "function toggleUnitColor(unit) {\n",
    "  const config = getUnitSortConfig(unit);\n",
    "  config.mode = 'auto'; \n",
    "  if (config.priority !== 'color') {\n",
    "      config.priority = 'color';\n",
    "      config.color = 'asc';\n",
    "  } else {\n",
    "      config.color = config.color === 'asc' ? 'desc' : 'asc';\n",
    "  }\n",
    "}\n",
    "\n",
    "function toggleUnitGsm(unit) {\n",
    "  const config = getUnitSortConfig(unit);\n",
    "  config.mode = 'auto';\n",
    "  if (config.priority !== 'gsm') {\n",
    "      config.priority = 'gsm';\n",
    "      config.gsm = 'asc';\n",
    "  } else {\n",
    "      config.gsm = config.gsm === 'asc' ? 'desc' : 'asc';\n",
    "  }\n",
    "}\n",
    "\n",
    "function toggleUnitPriority(unit) {\n",
    "  const config = getUnitSortConfig(unit);\n",
    "  config.mode = 'auto';\n",
    "  config.priority = config.priority === 'color' ? 'gsm' : 'color';\n",
    "}\n",
    "\n",
    "function sortItems(unit, items) {\n",
    "  const config = getUnitSortConfig(unit);\n",
    "  if (config.mode === 'manual') {\n",
    "      return [...items].sort((a, b) => (a.idx || 0) - (b.idx || 0));\n",
    "  }\n",
    "  return [...items].sort((a, b) => {\n",
    "      let diff = 0;\n",
    "      if (config.priority === 'color') {\n",
    "          diff = compareColor(a, b, config.color);\n",
    "          if (diff === 0) diff = compareGsm(a, b, config.gsm);\n",
    "      } else {\n",
    "          diff = compareGsm(a, b, config.gsm);\n",
    "          if (diff === 0) diff = compareColor(a, b, config.color);\n",
    "      }\n",
    "      if (diff === 0) diff = (a.idx || 0) - (b.idx || 0);\n",
    "      return diff;\n",
    "  });\n",
    "}\n",
    "\n"
]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(prefix + new_middle + suffix)

print(f"Successfully updated file. New line count: {len(prefix) + len(new_middle) + len(suffix)}")
