import fs from "fs";
import path from "path";
import readline from "readline";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SQL = path.join(
  "c:",
  "Users",
  "Admin",
  "Downloads",
  "20260401_155243-jayashreespunbond-1zt_frappe_cloud-database.sql",
  "20260401_155243-jayashreespunbond-1zt_frappe_cloud-database.sql"
);
const OUT = path.join(__dirname, "..", "production_entry", "fixtures", "from_db_20260401");
const TARGETS = new Set([
  "Shaft Production Run",
  "Shaft Production Run Item",
  "Shaft Production Run Job",
  "Roll Production Entry",
  "Roll Production Entry Item",
]);

function splitTuples(body) {
  const tuples = [];
  let depth = 0,
    start = null;
  let i = 0,
    inStr = false,
    strQ = null,
    esc = false;
  while (i < body.length) {
    const c = body[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === "\\" && (strQ === "'" || strQ === '"')) esc = true;
      else if (c === strQ) {
        inStr = false;
        strQ = null;
      }
      i++;
      continue;
    }
    if (c === "'" || c === '"') {
      inStr = true;
      strQ = c;
      i++;
      continue;
    }
    if (c === "(") {
      if (depth === 0) start = i + 1;
      depth++;
    } else if (c === ")") {
      depth--;
      if (depth === 0 && start != null) {
        tuples.push(body.slice(start, i));
        start = null;
      }
    }
    i++;
  }
  return tuples;
}

function parseTuple(t) {
  const parts = [];
  let cur = [];
  let inStr = false,
    q = null,
    esc = false;
  for (const ch of t) {
    if (inStr) {
      cur.push(ch);
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === q) {
        inStr = false;
        q = null;
      }
      continue;
    }
    if (ch === "'" || ch === '"') {
      inStr = true;
      q = ch;
      cur.push(ch);
      continue;
    }
    if (ch === ",") {
      parts.push(cur.join("").trim());
      cur = [];
      continue;
    }
    cur.push(ch);
  }
  parts.push(cur.join("").trim());
  return parts;
}

function unquote(s) {
  if (s == null) return null;
  s = String(s).trim();
  if (s === "NULL") return null;
  if (s.length >= 2 && s[0] === "'" && s[s.length - 1] === "'") {
    return s.slice(1, -1).replace(/''/g, "'").replace(/\\'/g, "'");
  }
  const n = Number(s);
  if (!Number.isNaN(n) && s !== "") return n;
  return s;
}

/** Frappe tabDocField row indices (validated against mysqldump). */
function docFieldRow(parts) {
  return {
    name: unquote(parts[0]),
    parent: unquote(parts[6]),
    parentfield: unquote(parts[7]),
    parenttype: unquote(parts[8]),
    idx: unquote(parts[9]),
    fieldname: unquote(parts[10]),
    label: unquote(parts[11]),
    fieldtype: unquote(parts[13]),
    options: unquote(parts[15]),
    fetch_from: unquote(parts[39]),
    in_list_view: unquote(parts[40]),
    reqd: unquote(parts[42]),
    read_only: unquote(parts[43]),
    columns: unquote(parts[47]),
    width: unquote(parts[32]),
  };
}

async function eachInsertLine(filePath, table, cb) {
  const rl = readline.createInterface({
    input: fs.createReadStream(filePath, { encoding: "utf8" }),
    crlfDelay: Infinity,
  });
  const prefix = `INSERT INTO \`${table}\` VALUES `;
  for await (const line of rl) {
    if (!line.startsWith(prefix)) continue;
    const rest = line.slice(prefix.length);
    if (!rest.endsWith(";")) continue;
    const body = rest.slice(0, -1);
    cb(body);
  }
}

async function main() {
  if (!fs.existsSync(SQL)) {
    console.error("Missing", SQL);
    process.exit(1);
  }
  fs.mkdirSync(OUT, { recursive: true });
  const byParent = {};
  for (const p of TARGETS) byParent[p] = [];

  await eachInsertLine(SQL, "tabDocField", (body) => {
    for (const tup of splitTuples(body)) {
      const parts = parseTuple(tup);
      if (parts.length < 45) continue;
      if (unquote(parts[7]) !== "fields" || unquote(parts[8]) !== "DocType") continue;
      const parent = unquote(parts[6]);
      if (!TARGETS.has(parent)) continue;
      const row = docFieldRow(parts);
      delete row.parentfield;
      delete row.parenttype;
      byParent[parent].push(row);
    }
  });

  for (const [parent, rows] of Object.entries(byParent)) {
    rows.sort((a, b) => (Number(a.idx) || 0) - (Number(b.idx) || 0));
    const fn = path.join(
      OUT,
      `tabDocField__${parent.replace(/ /g, "_")}.json`
    );
    fs.writeFileSync(fn, JSON.stringify(rows, null, 1), "utf8");
    console.log(fn, rows.length);
  }

  const psOut = [];
  await eachInsertLine(SQL, "tabProperty Setter", (body) => {
    for (const tup of splitTuples(body)) {
      const parts = parseTuple(tup);
      if (parts.length < 14) continue;
      const docType = unquote(parts[10]);
      const fieldName = unquote(parts[11]);
      const property = unquote(parts[14]);
      const value = unquote(parts[16]);
      if (typeof docType !== "string") continue;
      if (
        !docType.includes("Shaft Production Run") &&
        !docType.includes("Roll Production Entry") &&
        !docType.includes("Bundle Stickers")
      )
        continue;
      psOut.push({
        name: unquote(parts[0]),
        doctype_or_field: unquote(parts[9]),
        doc_type: docType,
        field_name: fieldName,
        property,
        value,
      });
    }
  });
  psOut.sort((a, b) => (a.doc_type + a.field_name).localeCompare(b.doc_type + b.field_name));
  fs.writeFileSync(
    path.join(OUT, "tabPropertySetter_SPR_RPE.json"),
    JSON.stringify(psOut, null, 1),
    "utf8"
  );
  console.log("property setters", psOut.length);

  const csOut = [];
  await eachInsertLine(SQL, "tabClient Script", (body) => {
    for (const tup of splitTuples(body)) {
      const parts = parseTuple(tup);
      if (parts.length < 11) continue;
      const dt = unquote(parts[6]);
      const view = unquote(parts[7]);
      if (!TARGETS.has(dt) || view !== "Form") continue;
      csOut.push({
        name: unquote(parts[0]),
        dt,
        script: unquote(parts[10]),
      });
    }
  });
  fs.writeFileSync(
    path.join(OUT, "tabClientScript_Form_SPR_RPE.json"),
    JSON.stringify(csOut, null, 1),
    "utf8"
  );
  console.log("client scripts form", csOut.length);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
