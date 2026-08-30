/* Chay THAT app.js cua dashboard trong Node voi DOM gia.
   Muc tieu: mot trang phai phuc vu duoc CA HAI tram (field map khac han nhau)
   va suy bien tu te tren mot kenh khong phai cua minh.

   Test nay GOI API ThingSpeak THAT, nen can mang. That bai vi mang la that bai
   that - dung bien no thanh skip, vi "kenh tra ve gi" chinh la thu dang kiem.

   Chay:  node tests/test_dashboard.mjs                                */
import vm from "node:vm";
import { boot } from "./harness.mjs";

let ok = 0; const fail = [];
const check = (n, c, d = "") => { c ? ok++ : fail.push(`${n}  ${d}`); };
const R = (ctx, expr) => vm.runInContext(expr, ctx);

// ================= 1. BAO LOC =================
const bl = boot(3448221);
check("Bao Loc: STATION_MODE bat", R(bl.ctx, "STATION_MODE") === true);
// Moc chot 2026-08-30: entry 141 la ban ghi dau tien do THAT tai Bao Loc
// (ap suat 90,1 kPa). Entry 1-53 sai field map, 54-140 la chay thu o Sai Gon.
check("Bao Loc: DATA_START dung epoch entry 141",
  R(bl.ctx, "DATA_START") === Date.parse("2026-08-09T04:41:28Z"),
  String(R(bl.ctx, "DATA_START")));

// ================= 2. SAI GON =================
const sg = boot(3428136);
check("Sai Gon: DATA_START dung epoch rieng",
  R(sg.ctx, "DATA_START") === Date.parse("2026-07-21T17:17:02Z"),
  String(R(sg.ctx, "DATA_START")));

// Moi kenh phai co LY DO cat cua rieng no, va hai ly do phai KHAC nhau - neu
// giong nhau thi mot trong hai dang bi ke chuyen cua tram kia.
for (const [name, c] of [["Bao Loc", bl.ctx], ["Sai Gon", sg.ctx]])
  check(`${name}: epoch co ly do rieng`, R(c, "EPOCH_REASON").length > 20,
    R(c, "EPOCH_REASON"));
check("hai tram co ly do cat KHAC nhau",
  R(bl.ctx, "EPOCH_REASON") !== R(sg.ctx, "EPOCH_REASON"));

// ---- cho chon tram: co san hai tram + mot loi vao kenh bat ky ----
const options = (ctx) =>
  R(ctx, "JSON.stringify(document.querySelector('#channelSelect').children.map(o=>o.value))");
check("cho chon tram co du 2 tram + muc 'kenh khac'",
  options(bl.ctx) === JSON.stringify(["3448221", "3428136", "__other__"]),
  options(bl.ctx));
check("dang mo Bao Loc -> o chon dung Bao Loc",
  R(bl.ctx, "document.querySelector('#channelSelect').value") === "3448221");
check("dang mo tram co san -> ô go ID an di",
  R(bl.ctx, "document.querySelector('#customChannel').hidden") === true);
// Muc chon phai lay tu knownChannels, khong duoc go cung trong JavaScript.
check("danh sach tram lay tu config, khong nam trong JS",
  R(bl.ctx, "C.knownChannels.length") === 2);

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
// Cot kenh KHONG khai bao phai bien mat han. Truoc day chung thua ke nhan cua
// Bao Loc: field5..8 hien ra "Wind direction °", "PM2.5 µg/m³", "PM10 µg/m³",
// "Pressure kPa" - so bia, co don vi, co dai hop ly, va vao thang header CSV.
check("kenh la: chi giu dung 4 field kenh co khai bao",
  R(bl.ctx, "Object.keys(F).join(',')") === "field1,field2,field3,field4",
  R(bl.ctx, "Object.keys(F).join(',')"));
check("kenh la: bang suc khoe chi con 4 dong",
  R(bl.ctx, "sensorHealth().length") === 4,
  String(R(bl.ctx, "sensorHealth().length")));
check("kenh la: header CSV khong con cot bia",
  !R(bl.ctx, "csvParts(rows)[0]").includes("Wind speed"),
  R(bl.ctx, "csvParts(rows)[0]").slice(0, 120));
check("kenh la: verdict khong noi 'all 8 sensors'",
  !/all 8 sensors/.test(R(bl.ctx, "verdict()").detail || ""),
  R(bl.ctx, "verdict()").detail);
// Cho chon bam theo CHANNEL ID dang mo, khong phai theo metadata - nen phai thu
// bang mot context rieng mo thang mot ID khong co trong danh sach. offline:true
// de khong danh vao mang cho mot kenh khong ton tai.
const stranger = boot(999999999, { offline: true });
check("kenh ngoai danh sach: o chon nhay sang 'kenh khac'",
  R(stranger.ctx, "document.querySelector('#channelSelect').value") === "__other__",
  R(stranger.ctx, "document.querySelector('#channelSelect').value"));
check("kenh ngoai danh sach: hien o go Channel ID",
  R(stranger.ctx, "document.querySelector('#customChannel').hidden") === false);
check("kenh ngoai danh sach: khong muon ten tram nao",
  R(stranger.ctx, "C.channel.name") === "",
  R(stranger.ctx, "C.channel.name"));
check("kenh la: report noi ro station mode off",
  R(bl.ctx, "diagnosticReport()").includes("station mode    off"));
console.log(`\n  [kenh la] ${vLa.title}`);

console.log(`\n${ok} PASS, ${fail.length} FAIL`);
fail.forEach((f) => console.log("  FAIL:", f));
process.exit(fail.length ? 1 : 0);
