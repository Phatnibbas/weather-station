/* DOM gia + sandbox dung chung cho cac test dashboard.
   Tach ra khoi test_dashboard.mjs de test_audit_regressions.mjs khong phai
   chep lai - hai ban chep se troi nhau, va luc do test do chinh thu no do. */
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";

export const HTML_PATH = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "public",
  "index.html",
);

export const html = readFileSync(HTML_PATH, "utf8");

export const configJson = html.match(
  /<script id="appConfig" type="application\/json">([\s\S]*?)<\/script>/,
)[1];

export const appJs = html.slice(
  html.lastIndexOf("<script>") + 8,
  html.lastIndexOf("</script>"),
);

/* Chi phan HTML co the nhin thay tren man hinh - dung cho cac assert ve CHU,
   de mot chuoi giong het nam trong comment JS khong lam test do nham. */
export const bodyMarkup = html.slice(
  html.indexOf("<body>"),
  html.lastIndexOf("<script>"),
);

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

/* Nap app.js that trong mot context sach.
   offline:true thay fetch bang mot ham khong bao gio tra loi, nen trang dung
   nguyen o trang thai VUA VE LAN DAU - dung cho cac assert ve first paint. */
export function boot(channelId, { offline = false } = {}) {
  const cache = new Map();
  const el = (s) => { if (!cache.has(s)) cache.set(s, new El(s)); return cache.get(s); };
  el("#zone").value = "Asia/Ho_Chi_Minh";
  el("#scale").value = "robust";
  const document = {
    documentElement: new El("html"), body: new El("body"), title: "",
    getElementById: (id) => (id === "appConfig" ? { textContent: configJson } : el("#" + id)),
    querySelector: (s) => el(s), querySelectorAll: () => [],
    createElement: () => new El(), addEventListener: () => {}, execCommand: () => true,
  };
  const sandbox = {
    document, console, Intl, URL, URLSearchParams, Blob, AbortController,
    fetch: offline ? () => new Promise(() => {}) : fetch,
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
  vm.runInContext(appJs, ctx, { filename: `app.js(${channelId})` });
  return { ctx, el, document, run: (expr) => vm.runInContext(expr, ctx) };
}
