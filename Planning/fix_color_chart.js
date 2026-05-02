const fs = require('fs');
const path = require('path');

const filePath = 'c:\\Users\\Admin\\Planning\\production_scheduler\\production_scheduler\\public\\js\\ColorChart.vue';

if (!fs.existsSync(filePath)) {
    console.error(`Error: ${filePath} not found`);
    process.exit(1);
}

const content = fs.readFileSync(filePath, 'utf8');
const lines = content.split('\n');

console.log(`Original file has ${lines.length} lines`);

// Based on latest view_file (Step 1210)
// line 877 is the end of initSortable: "}"
// line 1024 is the start of getUnitEntries: "function getUnitEntries(unit) {"

// Adjust for 0-indexing
const endOfInitSortable = 877;
const startOfGetUnitEntries = 1024;

const prefix = lines.slice(0, endOfInitSortable);
const suffix = lines.slice(startOfGetUnitEntries - 1);

const newMiddle = [
    "",
    "async function handleMoveSuccess(res, newUnit) {",
    "    if (res.message && res.message.status === 'success') {",
    "        const movedTo = res.message.moved_to || { unit: newUnit, date: filterOrderDate.value };",
    "        if (movedTo.date !== filterOrderDate.value) {",
    "             frappe.msgprint(`Moved to ${movedTo.date}`);",
    "        } else if (movedTo.unit !== newUnit) {",
    "             frappe.msgprint(`Placed in ${movedTo.unit} (Capacity Full in ${newUnit})`);",
    "        } else {",
    "             frappe.show_alert({ message: \"Moved successfully\", indicator: \"green\" });",
    "        }",
    "        unitSortConfig[movedTo.unit].mode = 'manual';",
    "        await fetchData(); ",
    "    }",
    "}",
    "",
    "function getUnitSortConfig(unit) {",
    "  if (!unitSortConfig[unit]) {",
    "    unitSortConfig[unit] = { mode: 'auto', color: 'asc', gsm: 'desc', priority: 'color' };",
    "  }",
    "  return unitSortConfig[unit];",
    "}",
    "",
    "function toggleUnitColor(unit) {",
    "  const config = getUnitSortConfig(unit);",
    "  config.mode = 'auto'; ",
    "  if (config.priority !== 'color') {",
    "      config.priority = 'color';",
    "      config.color = 'asc';",
    "  } else {",
    "      config.color = config.color === 'asc' ? 'desc' : 'asc';",
    "  }",
    "}",
    "",
    "function toggleUnitGsm(unit) {",
    "  const config = getUnitSortConfig(unit);",
    "  config.mode = 'auto';",
    "  if (config.priority !== 'gsm') {",
    "      config.priority = 'gsm';",
    "      config.gsm = 'asc';",
    "  } else {",
    "      config.gsm = config.gsm === 'asc' ? 'desc' : 'asc';",
    "  }",
    "}",
    "",
    "function toggleUnitPriority(unit) {",
    "  const config = getUnitSortConfig(unit);",
    "  config.mode = 'auto';",
    "  config.priority = config.priority === 'color' ? 'gsm' : 'color';",
    "}",
    "",
    "function sortItems(unit, items) {",
    "  const config = getUnitSortConfig(unit);",
    "  if (config.mode === 'manual') {",
    "      return [...items].sort((a, b) => (a.idx || 0) - (b.idx || 0));",
    "  }",
    "  return [...items].sort((a, b) => {",
    "      let diff = 0;",
    "      if (config.priority === 'color') {",
    "          diff = compareColor(a, b, config.color);",
    "          if (diff === 0) diff = compareGsm(a, b, config.gsm);",
    "      } else {",
    "          diff = compareGsm(a, b, config.gsm);",
    "          if (diff === 0) diff = compareColor(a, b, config.color);",
    "      }",
    "      if (diff === 0) diff = (a.idx || 0) - (b.idx || 0);",
    "      return diff;",
    "  });",
    "}",
    ""
];

const newContent = [...prefix, ...newMiddle, ...suffix].join('\n');
fs.writeFileSync(filePath, newContent, 'utf8');

console.log(`Successfully updated file. New line count: ${prefix.length + newMiddle.length + suffix.length}`);
