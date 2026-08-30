/* SO CAI - cac phat hien cua ban ra soat 2026-08-30, viet thanh test.
   Xem docs/AUDIT-2026-08-30.md de biet chi tiet tung muc.

   BO TEST NAY DO CO CHU Y. Moi muc con OPEN la mot loi CHUA sua. Sua xong thi
   no tu chuyen sang FIXED. Khi tat ca FIXED, file nay xanh va tro thanh test
   chong tai phat - dung xoa no di sau khi sua.

   KHONG can mang: tat ca deu chay tren ham thuan hoac tren van ban nguon.

   Chay:  node tests/test_audit_regressions.mjs                              */
import { boot, bodyMarkup, appJs } from "./harness.mjs";

/* Ten field cua tram Sai Gon. Dung de kiem tra cac cho con gan cung theo SO
   FIELD: Sai Gon dat nhiet do o field3, Bao Loc dat o field1. */
const SAIGON_FIELDS = {
  name: "MakerLab Station",
  field1: "Wind speed", field2: "Wind direction", field3: "Temperature",
  field4: "Pressure", field5: "Light", field6: "Humidity",
  field7: "Noise", field8: "PM2.5",
};

const findings = [];
const finding = (id, title, probe) => findings.push({ id, title, probe });

/* -------------------------------------------------------------------------
   A1 - Trang bia ten/don vi/dai hop ly cho field mot kenh la KHONG he co.
   ------------------------------------------------------------------------- */
finding("A1", "Kenh la khong duoc bia ten + don vi cho field no khong co", () => {
  const { run } = boot(3448221, { offline: true });
  run(`applyChannelMetadata({name:"Solar Inverter Log",field1:"Voltage",field2:"Current",field3:"Battery"})`);
  const invented = JSON.parse(run(
    `JSON.stringify(Object.entries(F).filter(([k])=>['field4','field5','field6','field7','field8'].includes(k))
       .filter(([,c])=>c.unit||c.range).map(([k,c])=>k+'='+c.name+' '+(c.unit||'')))`,
  ));
  return {
    open: invented.length > 0,
    evidence: invented.length
      ? `kenh chi khai bao 3 field, trang van gan: ${invented.join(" | ")}`
      : "field khong khai bao -> khong ten, khong don vi, khong dai",
  };
});

/* -------------------------------------------------------------------------
   A2 - ZERO_SIGNATURE con gan cung field1/2/3, tuc la doc SAI o Sai Gon.
   ------------------------------------------------------------------------- */
finding("A2", "Dau hieu 'cam bien vua khoi dong lai' phai theo VAI TRO, khong theo so field", () => {
  const { run } = boot(3448221, { offline: true });
  run(`applyChannelMetadata(${JSON.stringify(SAIGON_FIELDS)})`);

  /* Tren Sai Gon, so 0 khi cam bien chua am la o nhiet do (field3),
     do am (field6) va anh sang (field5). */
  const realWarmup = run(`bootReason({status:'ALL_OK',field3:0,field6:0,field5:0})`);
  /* Con field1/field2/field3 = 0 tren Sai Gon la: lang gio, huong 0, 0 do C.
     Lang gio la chuyen binh thuong hang dem - khong phai cam bien reboot. */
  const calmNight = run(`bootReason({status:'ALL_OK',field1:0,field2:0,field3:0})`);

  const misses = realWarmup !== "sensor";
  const falsePositive = calmNight === "sensor";
  return {
    open: misses || falsePositive,
    evidence: [
      misses ? "BO SOT: warm-up that (temp/hum/light = 0) -> " + JSON.stringify(realWarmup) : null,
      falsePositive ? "BAO NHAM: dem lang gio (wind/dir/temp = 0) -> 'sensor'" : null,
    ].filter(Boolean).join("; ") || "theo vai tro, dung ca hai chieu",
  };
});

/* -------------------------------------------------------------------------
   A3 - Chu tren trang gan cung con so 8, trong khi trang nhan MOI kenh.
   ------------------------------------------------------------------------- */
finding("A3", "Chu hien tren trang khong duoc gan cung 'eight' khi kenh la co the it field hon", () => {
  const inMarkup = (bodyMarkup.match(/\beight\b/gi) || []).length;
  /* Chuoi verdict nam trong JS, khong nam trong markup, nen dem rieng. */
  const inVerdict = (appJs.match(/all eight sensors/gi) || []).length;
  return {
    open: inMarkup + inVerdict > 0,
    evidence: inMarkup + inVerdict
      ? `markup: ${inMarkup} cho, chuoi verdict: ${inVerdict} cho`
      : "so field lay tu chinh kenh",
  };
});

/* -------------------------------------------------------------------------
   A4 - Ghi chu moc du lieu ke rieng cau chuyen cua Sai Gon cho MOI kenh.
   ------------------------------------------------------------------------- */
finding("A4", "Ghi chu 'data epoch' khong duoc ke ly do cua rieng mot tram", () => {
  const hard = /station reinstall and firmware update|different wind scaling/.test(appJs);
  return {
    open: hard,
    evidence: hard
      ? "chuoi epochNote gan cung 'station reinstall'/'different wind scaling' - "
        + "sai ngay khi Bao Loc duoc chot moc (ly do la field map khac, khong phai thang do gio)"
      : "ly do moc lay theo tung kenh",
  };
});

/* -------------------------------------------------------------------------
   A5 - Lan ve dau tien hien ten cua kenh TRUOC do, chong len id kenh moi.
   ------------------------------------------------------------------------- */
finding("A5", "Lan ve dau tien khong duoc dan ten tram nay len id cua tram kia", () => {
  const { document, el } = boot(3428136, { offline: true });
  const title = document.title;
  const shownName = el("#channelName").textContent;
  const wrong = /Bao Loc/i.test(title) || /Bao Loc/i.test(shownName);
  return {
    open: wrong,
    evidence: wrong
      ? `?channel=3428136 nhung title="${title}", #channelName="${shownName}"`
      : `title="${title}"`,
  };
});

/* ------------------------------- chay ------------------------------------ */
let open = 0;
console.log("SO CAI DASHBOARD - ban ra soat 2026-08-30\n");
for (const f of findings) {
  let r;
  try {
    r = f.probe();
  } catch (error) {
    r = { open: true, evidence: "probe nem loi: " + (error && error.message) };
  }
  if (r.open) open++;
  console.log(`  [${r.open ? "OPEN " : "FIXED"}] ${f.id}  ${f.title}`);
  console.log(`           ${r.evidence}\n`);
}
console.log(`${findings.length - open} FIXED, ${open} OPEN`);
if (open) console.log("\nBo test nay do la DUNG cho toi khi cac muc tren duoc sua.");
process.exit(open ? 1 : 0);
