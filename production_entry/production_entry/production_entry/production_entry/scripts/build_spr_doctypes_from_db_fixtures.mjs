/**
 * Build Shaft Production Run / Item / Job DocType JSON from
 * production_entry/fixtures/from_db_20260401/tabDocField__*.json (Apr 1 SQL export).
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(__dirname, "..", "production_entry", "fixtures", "from_db_20260401");
const DT = path.join(__dirname, "..", "production_entry", "production_planning", "doctype");

function loadJson(name) {
  return JSON.parse(fs.readFileSync(path.join(FIX, name), "utf8"));
}

function escOptions(s) {
  if (s == null || s === "") return null;
  return String(s).replace(/\\n/g, "\n");
}

function rowToField(r) {
  const o = {
    fieldname: r.fieldname,
    fieldtype: r.fieldtype,
  };
  if (r.label) o.label = r.label;
  const opt = escOptions(r.options);
  if (opt) o.options = opt;
  if (r.in_list_view) o.in_list_view = 1;
  if (r.reqd) o.reqd = 1;
  if (r.read_only) o.read_only = 1;
  if (r.fetch_from) o.fetch_from = r.fetch_from;
  if (r.width) o.width = r.width;
  if (r.columns) o.columns = r.columns;
  return o;
}

function buildDocType(name, rows, extraFields = [], meta = {}) {
  rows = [...rows].sort((a, b) => (Number(a.idx) || 0) - (Number(b.idx) || 0));
  const fields = rows.map(rowToField);
  for (const f of extraFields) {
    const i = fields.findIndex((x) => x.fieldname === f.after);
    if (i >= 0) fields.splice(i + 1, 0, f.field);
    else fields.push(f.field);
  }
  const field_order = fields.map((f) => f.fieldname);
  const base = {
    actions: [],
    creation: meta.creation ?? "2026-04-01 15:52:00.000000",
    doctype: "DocType",
    editable_grid: 1,
    engine: "InnoDB",
    field_order,
    fields,
    index_web_pages_for_search: 1,
    is_submittable: meta.is_submittable ?? 1,
    links: [],
    modified: meta.modified ?? "2026-04-01 15:52:00.000000",
    module: "Production Planning",
    name,
    owner: "Administrator",
    permissions: meta.permissions ?? [],
    sort_field: "modified",
    sort_order: "DESC",
    states: [],
    track_changes: 1,
  };
  if (meta.istable) {
    base.istable = 1;
    return base;
  }
  base.allow_rename = meta.allow_rename ?? 1;
  base.autoname = meta.autoname ?? "naming_series:";
  base.naming_series = meta.naming_series ?? "SPR-.YYYY.-.#####";
  return base;
}

const permShaft = [
  {
    amend: 1,
    cancel: 1,
    create: 1,
    delete: 1,
    email: 1,
    export: 1,
    print: 1,
    read: 1,
    report: 1,
    role: "System Manager",
    share: 1,
    submit: 1,
    write: 1,
  },
  {
    create: 1,
    email: 1,
    export: 1,
    print: 1,
    read: 1,
    report: 1,
    role: "Manufacturing User",
    share: 1,
    submit: 1,
    write: 1,
  },
];

function main() {
  const sprRows = loadJson("tabDocField__Shaft_Production_Run.json");
  const itemRows = loadJson("tabDocField__Shaft_Production_Run_Item.json");
  const jobRows = loadJson("tabDocField__Shaft_Production_Run_Job.json");

  const ns = sprRows.find((r) => r.fieldname === "naming_series");
  if (ns && !ns.options) {
    ns.options = "SPR-.YYYY.-.#####";
  }

  const customerExtra = {
    after: "production_plan",
    field: {
      fieldname: "customer",
      fieldtype: "Link",
      label: "Customer",
      options: "Customer",
      in_list_view: 1,
    },
  };

  const mfgExtra = [
    {
      after: "bundle_stickers",
      field: {
        fieldname: "section_manufacturing",
        fieldtype: "Section Break",
        label: "Manufacturing Stock Entries",
      },
    },
    {
      after: "section_manufacturing",
      field: {
        fieldname: "manufacturing_entries",
        fieldtype: "Small Text",
        label: "Manufacturing Entries",
        read_only: 1,
      },
    },
  ];

  const spr = buildDocType("Shaft Production Run", sprRows, [customerExtra, ...mfgExtra], {
    permissions: permShaft,
  });

  const itemExtra = {
    after: "item_code",
    field: {
      fieldname: "item_name",
      fieldtype: "Data",
      label: "Item Name",
      read_only: 1,
      in_list_view: 1,
    },
  };

  const item = buildDocType("Shaft Production Run Item", itemRows, [itemExtra], {
    is_submittable: 0,
    istable: 1,
  });

  const job = buildDocType("Shaft Production Run Job", jobRows, [], {
    is_submittable: 0,
    istable: 1,
  });

  const w = (sub, file) =>
    fs.writeFileSync(file, JSON.stringify(sub, null, 1) + "\n", "utf8");

  w(spr, path.join(DT, "shaft_production_run", "shaft_production_run.json"));
  w(item, path.join(DT, "shaft_production_run_item", "shaft_production_run_item.json"));
  w(job, path.join(DT, "shaft_production_run_job", "shaft_production_run_job.json"));

  console.log("Wrote SPR DocTypes from DB fixtures + customer + manufacturing + item_name.");
}

main();
