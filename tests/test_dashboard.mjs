/* Chay THAT app.js cua dashboard trong Node voi DOM gia.
   Muc tieu: mot trang phai phuc vu duoc CA HAI tram (field map khac han nhau)
   va suy bien tu te tren mot kenh khong phai cua minh.

   Test nay GOI API ThingSpeak THAT, nen can mang. That bai vi mang la that bai
   that - dung bien no thanh skip, vi "kenh tra ve gi" chinh la thu dang kiem.

   Chay:  node tests/test_dashboard.mjs                                */
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HTML = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "public",
  "index.html",
);
const html = readFileSync(HTML, "utf8");
const cfg = html.match(
  /<script id="appConfig" type="application\/json">([\s\S]*?)<\/script>/,
)[1];
const js = html.slice(html.lastIndexOf("<script>") + 8, html.lastIndexOf("</script>"));

class El {
  constructor(sel = "") {
    this.sel = sel; this._text = ""; this.value = ""; this.innerHTML = "";
    this.dataset = {}; this.style = {}; this.hidden = false; this.disabled = false;
    this.checked = true; this.clientWidth = 900; this.clientHeight = 380;
    this.offsetWidth = 80; this.offsetHeight = 40;
    this.childNodes = [{ nodeValue: "" }];
    this.classList = { add() {}, remove() {}, toggle() {}, contains: () => false };
    this.children = [];
  }
  get textContent() { return this._text; }
  set textContent(v) { this._text = String(v); }
  setAttribute() {} getAttribute() { return null; } removeAttribute() {}
  addEventListener() {}
  append(c) { this.children.push(c); if (c && c.value !== undefined && !this.value) this.value = c.value; }
  remove() {} click() {} focus() {} select() {} contains() { return false; }
  querySelector() { return new El(); } querySelectorAll() { return []; }
  scrollIntoView() {} setPointerCapture() {}
  getBoundingClientRect() { return { width: 900, height: 380, left: 0, top: 0 }; }
}

function boot(channelId) {
  const cache = new Map();
  const el = (s) => { if (!cache.has(s)) cache.set(s, new El(s)); return cache.get(s); };
  el("#zone").value = "Asia/Ho_Chi_Minh";
  el("#scale").value = "robust";
  const document = {
    documentElement: new El("html"), body: new El("body"), title: "",
    getElementById: (id) => (id === "appConfig" ? { textContent: cfg } : el("#" + id)),
    querySelector: (s) => el(s), querySelectorAll: () => [],
    createElement: () => new El(), addEventListener: () => {}, execCommand: () => true,
  };
  const sandbox = {
    document, console, fetch, Intl, URL, URLSearchParams, Blob, AbortController,
    setTimeout, clearTimeout, setInterval, clearInterval,
    Date, Math, JSON, Number, String, Object, Array, Map, Set, Promise, Error, RegExp, isNaN,
    requestAnimationFrame: (f) => setTimeout(f, 0), cancelAnimationFrame: clearTimeout,
    addEventListener: () => {},
    navigator: { onLine: true, clipboard: { writeText: async () => {} } },
    location: { search: `?channel=${channelId}`, href: `https://x.invalid/?channel=${channelId}` },
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    matchMedia: () => ({ matches: false }),
  };
  sandbox.window = sandbox; sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);
  vm.runInContext(js, ctx, { filename: `app.js(${channelId})` });
  return { ctx, el };
}

let ok = 0; const fail = [];
const check = (n, c, d = "") => { c ? ok++ : fail.push(`${n}  ${d}`); };
const R = (ctx, expr) => vm.runInContext(expr, ctx);

// ================= 1. BAO LOC =================
const bl = boot(3448221);
check("Bao Loc: STATION_MODE bat", R(bl.ctx, "STATION_MODE") === true);
check("Bao Loc: DATA_START = 0 (chua chot epoch)", R(bl.ctx, "DATA_START") === 0);

// ================= 2. SAI GON =================
const sg = boot(3428136);
check("Sai Gon: DATA_START dung epoch rieng",
  R(sg.ctx, "DATA_START") === Date.parse("2026-07-21T17:17:02Z"),
  String(R(sg.ctx, "DATA_START")));

// cho ca hai nap xong metadata that
await new Promise((r) => setTimeout(r, 10000));

const groups = (ctx) => R(ctx, "JSON.stringify(MODBUS_GROUPS.map(g=>g.id+':'+g.fields.join('+')))");
const vol = (ctx) => R(ctx, "Object.keys(VOLATILE).sort().join(',')");
const roles = (ctx) => R(ctx, "Object.entries(F).map(([k,c])=>k+'='+c.role).join(' ')");

console.log("\n--- Bao Loc 3448221 ---");
console.log("  roles :", roles(bl.ctx));
console.log("  modbus:", groups(bl.ctx));
console.log("  volatile:", vol(bl.ctx));
console.log("--- Sai Gon 3428136 ---");
console.log("  roles :", roles(sg.ctx));
console.log("  modbus:", groups(sg.ctx));
console.log("  volatile:", vol(sg.ctx));

check("Bao Loc: nhom Modbus dung field",
  groups(bl.ctx) === JSON.stringify(["THN:field1+field2", "LUX:field3", "PM:field6+field7+field8", "WIND:field4+field5"]),
  groups(bl.ctx));
check("Sai Gon: nhom Modbus dung field (map KHAC HAN)",
  groups(sg.ctx) === JSON.stringify(["THN:field3+field6+field7", "LUX:field5", "PM:field8+field4", "WIND:field1+field2"]),
  groups(sg.ctx));
check("Sai Gon: STATION_MODE bat", R(sg.ctx, "STATION_MODE") === true);

// VOLATILE phai theo Y NGHIA, khong theo so field
check("Bao Loc: VOLATILE = temp,hum,wspd,pm25,pm10",
  vol(bl.ctx) === "field1,field2,field4,field6,field7", vol(bl.ctx));
check("Sai Gon: VOLATILE KHAC Bao Loc (khong con pm10, them noise)",
  vol(sg.ctx) === "field1,field3,field6,field7,field8", vol(sg.ctx));
check("hai tram co VOLATILE khac nhau", vol(bl.ctx) !== vol(sg.ctx));

// ca hai deu phai nap duoc du lieu that
for (const [name, c] of [["Bao Loc", bl.ctx], ["Sai Gon", sg.ctx]]) {
  const n = R(c, "rows.length");
  const v = R(c, "verdict()");
  check(`${name}: nap duoc du lieu that`, n > 0, `rows=${n}`);
  check(`${name}: verdict() day du`, !!(v && v.title && v.detail));
  check(`${name}: diagnosticReport() sinh duoc`,
    R(c, "diagnosticReport()").includes("STATION DIAGNOSTIC REPORT"));
  check(`${name}: bang suc khoe du 8 field`, R(c, "sensorHealth().length") === 8);
  console.log(`\n  [${name}] ${(v.level || "pending").toUpperCase()} — ${v.title}`);
  console.log(`     ${v.detail.slice(0, 160)}`);
}

// ================= 3. KENH LA: phai suy bien, khong duoc nem =================
const apply = R(bl.ctx, "applyChannelMetadata");
let threw = false;
try {
  apply({ name: "Some Random Channel", field1: "Voltage", field2: "Current",
    field3: "Battery", field4: "RSSI" });
} catch (e) { threw = true; }
check("kenh la: KHONG nem loi nua", !threw);
check("kenh la: STATION_MODE tat", R(bl.ctx, "STATION_MODE") === false);
check("kenh la: deadGroups tra ve rong", R(bl.ctx, "deadGroups(rows.at(-1)).length") === 0);
const vLa = R(bl.ctx, "verdict()");
check("kenh la: verdict KHONG bia 'all four Modbus reads'",
  !vLa.title.includes("sensor is not answering"), vLa.title);
check("kenh la: verdict van chay", !!(vLa && vLa.title));
check("kenh la: field la khong bi bia don vi",
  R(bl.ctx, "F.field1.unit") === "" && R(bl.ctx, "F.field1.range") === null,
  `unit=${R(bl.ctx, "F.field1.unit")}`);
check("kenh la: report noi ro station mode off",
  R(bl.ctx, "diagnosticReport()").includes("station mode    off"));
console.log(`\n  [kenh la] ${vLa.title}`);

console.log(`\n${ok} PASS, ${fail.length} FAIL`);
fail.forEach((f) => console.log("  FAIL:", f));
process.exit(fail.length ? 1 : 0);
