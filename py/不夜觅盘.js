const VERSION = "1.1.21";

// ==================== 版本更新说明 ====================
// 1.1.21  2026-10-25
//   - 全量验收修复: ①死分享判定补认"分享者用户封禁"(此前永远出"获取失败,可重试"占位,点一次错一次);
//     ②_detail 单条失败占位卡补拼分享链接(r 型条目解 data.u 并拼提取码,裸分享链接直接回填),
//     失败后也能从占位卡复制链接自取(SHOW_SHARE_URL 开关仍生效)。
// 1.1.20  2026-10-24
//   - 新增 百度分享匿名直连(照 omnibox觅盘 配方): 详情 loadShareVod 百度直连优先枚举(pbaidu: 自包含选集,
//     带文件大小前缀),容器百度"分享信息"偶发 -21 故障时不再落"解析失败"占位;死分享/提取码经
//     isPreciseShareError 直抛占位卡(百度文案不再被 123 分支误标成"123 提取码/该123分享");
//   - 播放 playShare/_play 走 pbaidu: 直连,容器选集ID也先试匿名直连(fs_id 直用/按分集名匹配,失败回退容器);
//   - 稳健性: verify 误报 -12 重试、新旧分享页双形态解析(window.yunData/转义 JSON AB灰度)、
//     randsk 兜底 BDCLND Cookie、会话600s/签名120s缓存、/share/streaming 出 M3U8 探活后交宿主。
// 1.1.19  2026-10-23
//   - 修复 P1: 补回 v1.1.17 更新说明正文(被 v1.1.18 编辑误删);
//   - 修复 P2a: loadShareVod 重抛闸门放宽(5103 死/提取码文案也冒泡到占位卡);
//   - 新增 123/UC 直连选集小标题显示文件大小(`[1.23G] 名`)。
// 1.1.18  2026-10-22
//   - 123 分享错误细化(真网复现"谍影重重"不能播根因): 
//     ① 空分享(code 0+InfoList[]) → "该 123 分享内容已被清空(分享记录有效但文件为空)"
//     ② 5103 此分享不存在 → "该 123 分享已失效"; 5103 提取码错误 → "123 提取码不正确(非失效)"
//     ③ loadShareVod/pan123DirectVod 抛出明确错误冒泡到 buildFailedShareVod,占位卡展示真实原因。
// 1.1.17  2026-10-22
//   - 新增 UC 分享匿名免转存直连(照 omnibox 同款 PowerList 配方): token -> detail -> /file/download,
//     不依赖后台 UC 会员 Cookie;详情优先直连枚举,播放识别 puc: 自包含选集并带 UC UA/魔法 Referer;
//     直连失败仍回退容器 drive,后台 UC 账号继续生效;补认"好友已取消了分享"为死分享。
// 1.1.16  2026-10-19
//   - 断网兜底(自动化测试发现): ①_search 站点不可用时回空列表,不再让整个搜索请求 500(覓盘/聚影同款);
//     ②_detail 单条失败出"获取失败,可重试"占位卡——热词卡详情在站点抖动时不再开天窗。
// 1.1.15  2026-10-19
//   - 播放加固("资源有效却播不出来"排查): ①loadShareVod 瞬时返回空时立刻重试一次(空结果不入缓存,
//     重试即新请求); ②报错顺序修正——先判"解析失败未获取到可播放内容"再判"未找到匹配的网盘",
//     网络/反爬导致的解析失败不再被误报成网盘未配置。
// 1.1.14  2026-10-19
//   - 死分享判定剔除"无法识别的分享链接":识别缺口≠死分享,误判会记死7天把活分享从搜索滤掉、
//     跳过本可成功的回退。覓盘 v1.6.13 根因修复(镜像域名 123685/123865 漏认)同款防护。
// 1.1.13  2026-10-17
//   - 123分享列表:匿名形态被反爬以 HTML/网络方式拒绝(非业务code),或误报"分享不存在"时,
//     不再短路直接抛,必兜底试一次 legacy 原形态(升级前一直可用)——修复形态回归导致的
//     活分享被误判死、详情只出失效占位的问题。
// 1.1.12  2026-10-17
//   - 123接入 power721/PowerList 免登录配方(三档取链):
//     a) 档①无限直链: share/get 列表项自带123服务端已签名 DownloadUrl(缩略图形态),剥掉变换后缀
//        _24_24 与 &trade_key=123pan-thumbnail 即原文件合法直链(字面量替换、不重排query),t= 约7天有效、
//        疑似不计下载额度——选集ID(p123:)携带该直链,命中则零请求直接播;
//     b) 档②匿名换直链: share/download/info 匿名(无 Bearer)优先、带账号兜底,补 driveId/FileName 字段;
//        5112 分享方流量耗尽时不再重试账号(同一后端无意义);
//     c) 档③分享无提取流量(5112,按 code 精确判定,不误伤"提取码不正确")且文件在自己盘里时,
//        改走本人网盘 /b/api/file/download_info(消耗普通下载流量,alist挂载同款);
//     d) 分享列表改官方 web 参数形态首选(ParentFileId 驼峰/next=-1/event 等)、原形态兜底;死分享跳过多余回退;
//        step2 探测不再携带 Bearer(令牌不发给解码后的任意域名);直链缺失/快过期时才重列目录换新签名。
// 1.1.11  2026-10-16
//   - 123大版本适配(123已改版,旧匿名/无签名接口全部失效):
//     a) API 固定 yun.123pan.com(候选 www.123pan.cn/.com),每个请求带 signPath 签名(照 alist drivers/123_share);
//     b) 下载接口需登录(匿名必拒"您需要注册登录或付费后下载"):sign_in 自动登录换token(401自动重登),
//        账密不写死在 JS 里,只配环境变量 PAN_123_USERNAME + PAN_123_PASSWORD(或已有token配 PAN_123_TOKEN);
//        "不夜后台添加123账号"功能已随123改版失效,不用管它,以环境变量为准;
//     c) 下载请求体改小驼峰;分享方无提取流量(免费号为0)且文件在自己盘里时,自动改走本人网盘
//        /b/api/file/download_info(消耗普通下载流量,alist挂载同款),自己的分享可完整播放;
//     d) 分页改Page制、step2支持302/JSON双分支、shareKey按白名单截断(防源数据粘"提取码:xxx")。
// 1.1.10  2026-10-15
//   - 修复123云盘不出分集(与不夜聚影.js同方法):
//     a) 镜像域名(123684/123685/123865/123912)统一改写成 www.123pan.cn——容器/SDK 的123 drive
//        只认含 "123pan" 的域名,域名不匹配 matchShare 就从不枚举分集;
//     b) 容器123 drive 枚举失败/为空时,直连123官方分享列表API递归收集视频(匿名可读,实测
//        新闻女王26集/伟大的长征13集);选集ID用 p123: 前缀自包含分享上下文(源站/shareKey/密码/
//        文件字段),播放直连下载API,不依赖容器drive;
//     c) 支持新旧分享路径:/s/{token} 与 /123pan/{token}(含 *.share.123pan.cn 子域)。
//     注:123 download API 需123账号登录/付费(5112),需登录的分享播放会明确报错。
//   - 新增本更新说明区,此后每次更新在此记录。
// 1.1.0~1.1.9  2026-10-07~09
//   - 由 omnibox 版 觅盘.js 移植为不夜容器插件:网盘分组、失效链接过滤(/api/check/links)、
//     行上"有效"标签、分享页二次校验、TMDB 补全、简介裸链接修复等(1.1.2~1.1.6 为版本跳号)。
const net = require("net");
const tls = require("tls");
const axios = require("axios");
const http = require("http");
const https = require("https");
const CryptoJS = require("crypto-js");

const DISABLE_WORDS = /^(off|false|none|no|0)$/i;

const BUILTIN_TMDB_PROXY = (() => {
  const raw = String(process.env.MIPAN_BUILTIN_PROXY || "").trim();
  const value = raw === "" ? "http://192.168.1.8:7890" : raw.replace(/\/+$/, "");
  return DISABLE_WORDS.test(value) ? "" : value;
})();

const splitConfigList = (value) =>
  String(value || "")
    .split(/[;,]/)
    .map((item) => item.trim())
    .filter(Boolean);

const envInt = (name, fallback, min = 0) => {
  const raw = process.env[name];
  const parsed = parseInt(raw === undefined || raw === "" ? String(fallback) : raw, 10);
  return Number.isFinite(parsed) && parsed >= min ? parsed : fallback;
};

const envBool = (name, fallback = true) => {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return fallback;
  return String(raw).toLowerCase() !== "false";
};

const envStr = (name, fallback = "") => {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return String(fallback);
  return String(raw).trim();
};

const SITE_CANDIDATES = (() => {
  const raw = splitConfigList(process.env.MIPAN_WEB_SITE || "");
  const list = (raw.length ? raw : ["https://www.mipan.so"]).map((item) =>
    String(item || "").trim().replace(/\/+$/, "")
  );
  const valid = list.filter((item) => /^https?:\/\//i.test(item));
  return valid.length ? valid : ["https://www.mipan.so"];
})();

const REQUEST_TIMEOUT = envInt("MIPAN_TIMEOUT", 20000, 3000);
const PAGE_SIZE = envInt("MIPAN_LIMIT", 20, 1);
const MAX_ITEMS_PER_GROUP = envInt("MIPAN_MAX_ITEMS", 50, 5);
const HOT_LIMIT = envInt("MIPAN_HOT_LIMIT", 24, 1);
const MIN_REQUEST_INTERVAL = envInt("MIPAN_MIN_INTERVAL", 120, 0);
const SEARCH_CACHE_EX = envInt("MIPAN_CACHE_EX_SECONDS", 1800, 60);
const DETAIL_CACHE_EX = envInt("MIPAN_DETAIL_CACHE_EX_SECONDS", 600, 30);
const HOT_CACHE_EX = envInt("MIPAN_HOT_CACHE_EX_SECONDS", 21600, 60);
const SHOW_SHARE_URL = envBool("MIPAN_SHOW_SHARE_URL", true);
const HIDE_TYPES = new Set(splitConfigList(process.env.MIPAN_HIDE_TYPES || "magnet;ed2k").map((item) => item.toLowerCase()));
const CHECK_ENABLED = envBool("MIPAN_CHECK", true);
const CHECK_LIMIT = envInt("MIPAN_CHECK_LIMIT", 1200, 10);
const CHECK_CHUNK = envInt("MIPAN_CHECK_CHUNK", 250, 10);
const CHECK_CONCURRENCY = envInt("MIPAN_CHECK_CONCURRENCY", 3, 1);
const CHECK_TIMEOUT = envInt("MIPAN_CHECK_TIMEOUT", 30000, 3000);
const VERIFY_ENABLED = envBool("MIPAN_VERIFY", true);
const VERIFY_LIMIT = envInt("MIPAN_VERIFY_LIMIT", 120, 0);
const VERIFY_CONCURRENCY = envInt("MIPAN_VERIFY_CONCURRENCY", 8, 1);
const VERIFY_TIMEOUT = envInt("MIPAN_VERIFY_TIMEOUT", 8000, 3000);
const TMDB_ENABLED = envBool("MIPAN_TMDB", true);
const TMDB_API_KEY = envStr("TMDB_API_KEY", "fe9ee1bf19dfa140736bd03fbce42a62");
const TMDB_MIRRORS = splitConfigList(envStr("TMDB_MIRROR", "http://tmdb.itv666.cc"))
  .map((item) => item.replace(/\/+$/, ""))
  .filter((item) => /^https?:\/\//i.test(item));
const TMDB_MIRROR = TMDB_MIRRORS[0] || "";
const TMDB_HOST = "api.themoviedb.org";
const TMDB_MIRROR_TIMEOUT = envInt("MIPAN_TMDB_MIRROR_TIMEOUT", 8000, 500);
const TMDB_TIMEOUT = envInt("MIPAN_TMDB_TIMEOUT", 4000, 500);
const TMDB_PROXY_TIMEOUT = envInt("MIPAN_TMDB_PROXY_TIMEOUT", 12000, 1000);
const BUILTIN_PROXY_DOWN = envInt("MIPAN_BUILTIN_PROXY_DOWN_SECONDS", 600, 5);
const BUILTIN_PROXY_FAILS = envInt("MIPAN_BUILTIN_PROXY_FAILS", 2, 1);
const TMDB_TOTAL = envInt("MIPAN_TMDB_TOTAL_TIMEOUT", 12000, 2000);
const TMDB_MIRROR_DOWN = envInt("MIPAN_TMDB_MIRROR_DOWN_SECONDS", 120, 5);
const TMDB_DOWN = envInt("MIPAN_TMDB_DOWN_SECONDS", 120, 10);
const TMDB_FAIL_STREAK = envInt("MIPAN_TMDB_FAIL_STREAK", 2, 1);
const TMDB_HIT_EX = envInt("MIPAN_TMDB_CACHE_EX_SECONDS", 604800, 60);
const TMDB_MISS_EX = envInt("MIPAN_TMDB_MISS_EX_SECONDS", 300, 30);
const TMDB_IMAGE_SIZE = envStr("MIPAN_TMDB_IMAGE_SIZE", "w500");
const TMDB_IMAGE_MIRROR = envStr("TMDB_IMAGE_MIRROR", "").replace(/\/+$/, "");
const CHECK_SKIP_TYPES = new Set(
  splitConfigList(process.env.MIPAN_CHECK_SKIP_TYPES || "other,guangya").map((item) => item.toLowerCase())
);
const CHECK_INVALID_STATES = new Set([
  "invalid",
  "bad",
  "dead",
  "expired",
  "deleted",
  "not_found",
  "failed",
  "forbidden",
  "removed",
]);
const CHECK_VALID_STATES = new Set(["valid", "ok", "alive", "locked", "success", "open"]);
const SITE_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";
const ICON_BASE = "https://xget.xi-xu.me/gh/power721/alist-tvbox/raw/refs/heads/master/web-ui/public/";
const MEM_CACHE_MAX = 120;

const PAN_META = {
  baidu: { name: "百度网盘", short: "百度" },
  aliyun: { name: "阿里云盘", short: "阿里" },
  quark: { name: "夸克网盘", short: "夸克" },
  tianyi: { name: "天翼网盘", short: "天翼" },
  uc: { name: "UC网盘", short: "UC" },
  "115": { name: "115网盘", short: "115" },
  xunlei: { name: "迅雷网盘", short: "迅雷" },
  "123": { name: "123网盘", short: "123" },
  pikpak: { name: "PikPak", short: "PikPak" },
  mobile: { name: "移动云盘", short: "移动" },
  guangya: { name: "光鸭云盘", short: "光鸭" },
  others: { name: "其他", short: "其他" },
  magnet: { name: "磁力", short: "磁力" },
  ed2k: { name: "电驴", short: "电驴" },
};

const ICON_FILES = {
  aliyun: "ali.jpg",
  quark: "quark.png",
  uc: "uc.png",
  pikpak: "pikpak.jpg",
  xunlei: "thunder.png",
  "123": "123.png",
  tianyi: "189.png",
  mobile: "139.jpg",
  "115": "115.jpg",
  baidu: "baidu.jpg",
  guangya: "guangya.webp",
  magnet: "magnet.png",
  ed2k: "ed2k.jpg",
  others: "folder.png",
};

const TYPE_HINTS = {
  baidu: ["baidu", "bd"],
  aliyun: ["ali", "aliyun", "alipan"],
  quark: ["quark", "夸克"],
  tianyi: ["a189", "189", "tianyi", "cloud189", "天翼"],
  "115": ["a115", "115"],
  xunlei: ["xunlei", "thunder", "迅雷"],
  "123": ["a123", "123"],
  pikpak: ["pikpak"],
  mobile: ["a139", "139", "mobile", "cmcc", "移动"],
  guangya: ["guangya", "光鸭"],
  uc: ["uc"],
};

const DRIVE_ORDER = ["baidu", "115", "quark", "tianyi", "uc", "123", "aliyun", "xunlei", "mobile", "pikpak", "guangya", "others"];

const HOT_WORDS_FALLBACK = ["兰香如故", "余红旧事", "仙逆", "我不是大师", "吞噬星空", "风云雄霸天下"];

const QUALITY_KEYWORDS = [
  "HDR",
  "杜比视界",
  "DV",
  "REMUX",
  "HQ",
  "臻彩",
  "高码",
  "高画质",
  "60FPS",
  "60帧",
  "高帧率",
  "60HZ",
  "4K",
  "2160P",
  "SDR",
  "1080P",
  "HD",
  "高清",
  "720P",
  "标清",
];
const COMPLETED_KEYWORDS = ["完结", "全集", "已完成", "全"];

const store = {
  init: false,
  redis: null,
  log: null,
  drives: [],
  meta: {
    key: "mipan_grouping",
    name: "觅盘[分组]",
    version: VERSION,
    type: 4,
    api: "/video/mipan_grouping",
    searchable: 1,
    quickSearch: 1,
    changeable: 0,
  },
};

function log(level, message) {
  try {
    const channel = store.log;
    if (channel && typeof channel[level] === "function") channel[level](String(message));
  } catch (error) {
  }
}

function truncateText(value, size) {
  const text = String(value || "");
  return text.length > size ? `${text.slice(0, size)}…` : text;
}

function parseJson(text) {
  if (typeof text !== "string" || !text.trim()) return null;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (error) {
    return null;
  }
}

function toPage(page) {
  const value = parseInt(String(page || "1"), 10);
  return Number.isFinite(value) && value > 0 ? value : 1;
}

function md5(value) {
  return CryptoJS.MD5(String(value)).toString();
}

function encodeBase64Url(raw) {
  return Buffer.from(String(raw), "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function decodeBase64Url(value) {
  let text = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  text += "=".repeat((4 - (text.length % 4)) % 4);
  return Buffer.from(text, "base64").toString("utf8");
}

function encodeId(typ, data) {
  try {
    return `mp:${typ}:${encodeBase64Url(JSON.stringify(data || {}))}`;
  } catch (error) {
    return "";
  }
}

function decodeId(raw) {
  const text = String(raw || "");
  if (!text.startsWith("mp:")) return ["", {}];
  const parts = text.split(":");
  if (parts.length < 3 || parts[1] !== "r" && parts[1] !== "g" && parts[1] !== "k" && parts[1] !== "e") return ["", {}];
  try {
    const data = JSON.parse(decodeBase64Url(parts.slice(2).join(":")));
    return [parts[1], data && typeof data === "object" ? data : {}];
  } catch (error) {
    return ["", {}];
  }
}

function parseLegacyId(raw) {
  const text = String(raw || "");
  if (!text || text.startsWith("mp:") || !text.includes("|")) return null;
  const index = text.indexOf("|");
  const panKey = text.slice(0, index);
  const word = text.slice(index + 1);
  if (!panKey || !word) return null;
  const type = driveKeyToType(panKey);
  if (!type) return null;
  return { type, word };
}

const memCache = new Map();

function memGet(key) {
  const hit = memCache.get(key);
  if (!hit) return undefined;
  if (hit.expireAt && Date.now() > hit.expireAt) {
    memCache.delete(key);
    return undefined;
  }
  memCache.delete(key);
  memCache.set(key, hit);
  return hit.value;
}

function memSet(key, value, exSeconds) {
  if (memCache.has(key)) memCache.delete(key);
  while (memCache.size >= MEM_CACHE_MAX) {
    const oldest = memCache.keys().next().value;
    memCache.delete(oldest);
  }
  memCache.set(key, { value, expireAt: exSeconds ? Date.now() + exSeconds * 1000 : 0 });
}

async function redisGet(key) {
  try {
    const raw = await (store.redis ? store.redis.get(key) : null);
    if (!raw) return undefined;
    return JSON.parse(raw);
  } catch (error) {
    return undefined;
  }
}

async function redisSet(key, value, exSeconds) {
  try {
    if (!store.redis) return;
    await store.redis.set(key, JSON.stringify(value));
    if (exSeconds && exSeconds > 0) await store.redis.expire(key, exSeconds);
  } catch (error) {
    log("warn", `觅盘 写入缓存失败: ${key}, ${error.message}`);
  }
}

const inflight = new Map();

function once(key, factory) {
  if (inflight.has(key)) return inflight.get(key);
  const task = factory();
  inflight.set(key, task);
  const clear = () => {
    if (inflight.get(key) === task) inflight.delete(key);
  };
  if (task && typeof task.then === "function") task.then(clear, clear);
  return task;
}

async function cachedValue(key, exSeconds, loader) {
  const mem = memGet(key);
  if (mem !== undefined && mem !== null) return mem;
  const remote = await redisGet(key);
  if (remote !== undefined && remote !== null) {
    memSet(key, remote, exSeconds);
    return remote;
  }
  const value = await once(key, loader);
  if (value !== undefined && value !== null) {
    memSet(key, value, exSeconds);
    await redisSet(key, value, exSeconds);
  }
  return value;
}

let lastRequestAt = 0;

function waitNextRequest() {
  const now = Date.now();
  const wait = Math.max(0, lastRequestAt + MIN_REQUEST_INTERVAL - now);
  lastRequestAt = now + wait;
  if (wait <= 0) return Promise.resolve();
  return new Promise((resolve) => setTimeout(resolve, wait));
}

const HTTPS_AGENT = new https.Agent({ keepAlive: true });
const HTTP_AGENT = new http.Agent({ keepAlive: true });

let siteIndex = 0;

function webSite() {
  return SITE_CANDIDATES[siteIndex % SITE_CANDIDATES.length];
}

function rotateSite() {
  if (SITE_CANDIDATES.length > 1) siteIndex = (siteIndex + 1) % SITE_CANDIDATES.length;
}

async function httpRequest(url, options = {}) {
  await waitNextRequest();
  const config = {
    url,
    method: options.method || "GET",
    headers: options.headers || {},
    params: options.params,
    data: options.body,
    timeout: options.timeout || REQUEST_TIMEOUT,
    httpsAgent: HTTPS_AGENT,
    httpAgent: HTTP_AGENT,
    responseType: "text",
    validateStatus: () => true,
  };
  if (options.proxy !== undefined && options.proxy !== null) config.proxy = options.proxy;
  const response = await axios(config);
  let body = response.data;
  if (typeof body !== "string") {
    body = body === undefined || body === null ? "" : JSON.stringify(body);
  }
  return { statusCode: response.status, body, headers: response.headers || {} };
}

let apiToken = "";
let tokenExpireAt = 0;
let tokenPromise = null;
let tokenRestored = false;

function buildHeaders(extra) {
  const headers = {
    "User-Agent": SITE_UA,
    Accept: "application/json, text/plain, */*",
    "Content-Type": "application/json",
    Origin: webSite(),
    Referer: `${webSite()}/`,
  };
  if (apiToken) headers["X-Mipan-Token"] = apiToken;
  return Object.assign(headers, extra || {});
}

async function refreshToken(force) {
  if (!force && apiToken && Date.now() < tokenExpireAt) return apiToken;
  if (!tokenPromise) {
    tokenPromise = (async () => {
      const response = await httpRequest(`${webSite()}/api/token`, {
        method: "GET",
        headers: buildHeaders(),
        timeout: Math.min(REQUEST_TIMEOUT, 10000),
      });
      const json = parseJson(response.body) || {};
      const token = String(json.token || "");
      const ttl = Math.max(60, parseInt(json.ttl, 10) || 7200);
      if (!token) throw new Error(`获取觅盘票据失败: HTTP ${response.statusCode}`);
      apiToken = token;
      tokenExpireAt = Date.now() + Math.max(30, ttl - 300) * 1000;
      await redisSet("mp:token", { t: token, e: tokenExpireAt }, Math.max(60, ttl - 60));
      log("info", `觅盘 票据已获取, 有效期约 ${Math.round(ttl / 60)} 分钟`);
      return token;
    })().finally(() => {
      tokenPromise = null;
    });
  }
  return tokenPromise;
}

async function ensureToken() {
  if (apiToken && Date.now() < tokenExpireAt) return apiToken;
  if (!tokenRestored) {
    tokenRestored = true;
    const cached = await redisGet("mp:token");
    if (cached && cached.t && Number(cached.e) > Date.now()) {
      apiToken = String(cached.t);
      tokenExpireAt = Number(cached.e);
      return apiToken;
    }
  }
  return refreshToken(false);
}

async function apiPost(path, body, timeoutMs) {
  await ensureToken();
  const send = () =>
    httpRequest(`${webSite()}${path}`, {
      method: "POST",
      headers: buildHeaders(),
      body,
      timeout: timeoutMs || REQUEST_TIMEOUT,
    });
  let response;
  try {
    response = await send();
  } catch (error) {
    log("warn", `觅盘 接口请求失败, 切换站点重试: ${error.message}`);
    rotateSite();
    response = await send();
  }
  if (response.statusCode === 403) {
    apiToken = "";
    tokenExpireAt = 0;
    await refreshToken(true);
    try {
      response = await send();
    } catch (error) {
      rotateSite();
      response = await send();
    }
  }
  if (response.statusCode !== 200) {
    throw new Error(`觅盘接口 HTTP ${response.statusCode}: ${truncateText(response.body, 160)}`);
  }
  const json = parseJson(response.body);
  if (!json) throw new Error("觅盘接口返回非 JSON 内容");
  if (json.code !== undefined && Number(json.code) !== 0) {
    throw new Error(String(json.message || "觅盘接口返回失败"));
  }
  return json;
}

function parseTime(value) {
  const time = Date.parse(String(value || ""));
  return Number.isFinite(time) ? time : 0;
}

function normalizeSearchResponse(json) {
  let data = json;
  if (json && typeof json === "object" && json.data && typeof json.data === "object") data = json.data;

  const raw = [];
  const pick = (item, typeHint) => {
    if (!item || typeof item !== "object") return;
    const url = String(item.url || item.URL || item.link || "");
    if (!url) return;
    raw.push({
      u: url,
      n: String(item.note || item.Note || item.title || item.name || ""),
      p: String(item.password || item.pwd || item.Password || ""),
      t: String(item.type || item.disk_type || typeHint || "others").toLowerCase(),
      d: String(item.datetime || item.date || item.created_at || item.update_time || ""),
      s: String(item.source || item.channel || item.from || ""),
    });
  };

  if (Array.isArray(data)) {
    data.forEach((item) => pick(item, ""));
  } else if (Array.isArray(data.results)) {
    data.results.forEach((item) => pick(item, ""));
  }
  if (data && data.merged_by_type && typeof data.merged_by_type === "object") {
    for (const [type, list] of Object.entries(data.merged_by_type)) {
      if (!Array.isArray(list)) continue;
      list.forEach((item) => pick(item, type));
    }
  }

  const grouped = new Map();
  const total = Number(data && data.total) || raw.length;
  for (const item of raw) {
    const type = item.t || "others";
    if (HIDE_TYPES.has(type)) continue;
    const base = item.u.split("#")[0].split("?")[0];
    const key = `${type}|${base}`;
    const prev = grouped.get(key);
    if (!prev) grouped.set(key, item);
    else if (!prev.p && item.p) grouped.set(key, item);
  }

  const byType = new Map();
  for (const item of grouped.values()) {
    if (!byType.has(item.t)) byType.set(item.t, []);
    byType.get(item.t).push(item);
  }

  const items = [];
  for (const list of byType.values()) {
    list.sort((a, b) => parseTime(b.d) - parseTime(a.d));
    items.push(...list.slice(0, MAX_ITEMS_PER_GROUP));
  }
  return { items, total };
}

function decodeHtml(value) {
  return String(value || "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ");
}

async function searchHtmlFallback(keyword) {
  try {
    const response = await httpRequest(`${webSite()}/s/${encodeURIComponent(keyword)}.html`, {
      method: "GET",
      headers: {
        "User-Agent": SITE_UA,
        Accept: "text/html,application/xhtml+xml,*/*",
        Referer: `${webSite()}/`,
      },
      timeout: REQUEST_TIMEOUT,
    });
    if (response.statusCode !== 200) return null;
    const html = String(response.body || "");
    const items = [];
    const cardReg = /<article class="card" data-t="([^"]*)">([\s\S]*?)<\/article>/g;
    let match = null;
    while ((match = cardReg.exec(html)) !== null) {
      const type = String(match[1] || "others").toLowerCase();
      const body = match[2];
      const link = /<a class="t" href="([^"]+)"/.exec(body);
      if (!link) continue;
      const title = /<a class="t"[^>]*>([\s\S]*?)<\/a>/.exec(body);
      const pwd = /class="pwd[^"]*"[^>]*data-copy="([^"]*)"/.exec(body);
      const date = /<span class="date">([^<]*)<\/span>/.exec(body);
      const item = {
        u: decodeHtml(link[1]),
        n: decodeHtml((title && title[1]) || "").trim(),
        p: decodeHtml((pwd && pwd[1]) || ""),
        t: type,
        d: (date && date[1]) || "",
        s: "",
      };
      if (HIDE_TYPES.has(item.t)) continue;
      items.push(item);
    }
    if (!items.length) return null;
    const grouped = new Map();
    for (const item of items) {
      const base = item.u.split("#")[0].split("?")[0];
      const key = `${item.t}|${base}`;
      const prev = grouped.get(key);
      if (!prev) grouped.set(key, item);
      else if (!prev.p && item.p) grouped.set(key, item);
    }
    return { items: [...grouped.values()], total: grouped.size };
  } catch (error) {
    log("warn", `觅盘 网页兜底失败: ${error.message}`);
    return null;
  }
}

async function searchRaw(keyword) {
  let normalized = null;
  let failure = null;
  try {
    const json = await apiPost("/api/search", { kw: keyword });
    normalized = normalizeSearchResponse(json);
  } catch (error) {
    failure = error;
    log("warn", `觅盘 搜索接口失败, 尝试网页兜底: ${error.message}`);
  }
  if (!normalized || !normalized.items.length) {
    const fallback = await searchHtmlFallback(keyword);
    if (fallback && fallback.items.length) return fallback;
    if (fallback && !normalized) return fallback;
  }
  if (normalized) return normalized;
  throw failure || new Error("觅盘搜索无结果");
}

function checkVerdict(value) {
  const state = String(value || "").toLowerCase();
  if (CHECK_INVALID_STATES.has(state)) return "invalid";
  if (CHECK_VALID_STATES.has(state)) return "valid";
  return "unknown";
}

function prioritizeForCheck(items, limit) {
  const buckets = new Map();
  for (const item of items || []) {
    if (!item || !item.u || !item.t) continue;
    if (CHECK_SKIP_TYPES.has(String(item.t).toLowerCase())) continue;
    const bucket = buckets.get(item.t);
    if (bucket) bucket.push(item);
    else buckets.set(item.t, [item]);
  }
  const cap = Math.max(1, Number(limit) || 0);
  const queue = [];
  let index = 0;
  while (queue.length < cap) {
    let added = false;
    for (const bucket of buckets.values()) {
      if (index >= bucket.length) continue;
      queue.push(bucket[index]);
      added = true;
      if (queue.length >= cap) break;
    }
    if (!added) break;
    index++;
  }
  return queue;
}

async function checkLinkStates(items) {
  if (!CHECK_ENABLED) return null;
  const queue = prioritizeForCheck(items, CHECK_LIMIT);
  if (!queue.length) return null;
  const verdicts = new Map();
  const raw = new Map();
  let cursor = 0;
  let failure = null;
  const worker = async () => {
    for (;;) {
      if (failure) return;
      const start = cursor;
      cursor += CHECK_CHUNK;
      if (start >= queue.length) return;
      const slice = queue.slice(start, start + CHECK_CHUNK);
      try {
        const json = await apiPost(
          "/api/check/links",
          { items: slice.map((item) => ({ url: item.u, disk_type: item.t })) },
          CHECK_TIMEOUT
        );
        for (const row of (json && json.results) || []) {
          const key = String((row && row.url) || "");
          if (!key) continue;
          const state = String((row && row.state) || "").toLowerCase();
          raw.set(key, state);
          verdicts.set(key, checkVerdict(state));
        }
      } catch (error) {
        if (!failure) failure = error;
        return;
      }
    }
  };
  const lanes = Math.min(CHECK_CONCURRENCY, Math.max(1, Math.ceil(queue.length / CHECK_CHUNK)));
  await Promise.all(Array.from({ length: lanes }, () => worker()));
  if (failure) throw failure;
  return { verdicts, raw, checked: queue.length };
}

function classifySharePage(statusCode, body) {
  const status = Number(statusCode) || 0;
  const text = String(body || "");
  if (status >= 300 && status < 400) return "valid";
  if (status === 404 || status === 410) return "invalid";
  if (status !== 200) return "unknown";
  const title = (text.match(/<title[^>]*>([^<]{0,120})/i) || [])[1] || "";
  if (/链接不存在|页面不存在|文件不存在|已取消|已失效|已过期|无法查看|违规|侵权/.test(title)) return "invalid";
  if (text.length < 800) return "unknown";
  if (/分享的文件已经被取消|该分享已被取消|链接不存在|页面不存在|resource.{0,12}(not found|expired|removed)/i.test(text)) {
    return "invalid";
  }
  return "valid";
}

async function verifyShareUrl(item) {
  const target = withExtractCode(String((item && item.u) || ""), item && item.p);
  if (!target || !/^https?:\/\//i.test(target)) return "unknown";
  try {
    const response = await httpRequest(target, {
      method: "GET",
      headers: {
        "User-Agent": SITE_UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
      },
      timeout: VERIFY_TIMEOUT,
    });
    return classifySharePage(response.statusCode, response.body);
  } catch (error) {
    return "unknown";
  }
}

async function mapLimit(list, limit, worker) {
  const size = Math.max(1, Math.min(limit || 1, list.length || 1));
  let cursor = 0;
  const runners = Array.from({ length: size }, async () => {
    while (cursor < list.length) {
      const index = cursor;
      cursor += 1;
      await worker(list[index], index);
    }
  });
  await Promise.all(runners);
}

async function verifyUncertainLinks(targets) {
  if (!VERIFY_ENABLED || VERIFY_LIMIT <= 0) return 0;
  const list = prioritizeForCheck(targets, VERIFY_LIMIT);
  if (!list.length) return 0;
  log("info", `觅盘 分享页二次校验: ${list.length} 条(接口返回 uncertain)`);
  let invalid = 0;
  await mapLimit(list, VERIFY_CONCURRENCY, async (item) => {
    const verdict = await verifyShareUrl(item);
    item.v = verdict;
    if (verdict === "invalid") invalid++;
  });
  log("info", `觅盘 分享页校验完成: ${list.length} 条, 判定失效 ${invalid} 条`);
  return invalid;
}

async function filterExpiredItems(items) {
  const list = items || [];
  if (!list.length) return list;
  let result = null;
  try {
    result = await checkLinkStates(list);
  } catch (error) {
    log("warn", `觅盘 链接检测失败, 保留全部结果: ${error.message}`);
    return list;
  }
  if (!result) return list;
  for (const item of list) {
    const key = String((item && item.u) || "");
    item.v = key && result.verdicts.has(key) ? result.verdicts.get(key) : "";
  }
  if (VERIFY_ENABLED && VERIFY_LIMIT > 0) {
    const pending = list.filter((item) => item.v === "unknown" && result.raw.get(String(item.u)) === "uncertain");
    try {
      await verifyUncertainLinks(pending);
    } catch (error) {
      log("warn", `觅盘 分享页二次校验失败: ${error.message}`);
    }
  }
  let dead = 0;
  const kept = list.filter((item) => {
    if (item && item.v === "invalid") {
      dead++;
      return false;
    }
    return true;
  });
  const marked = kept.filter((item) => item && item.v).length;
  log(
    "info",
    `觅盘 链接检测: 检测 ${result.checked} 条, 失效剔除 ${dead} 条, 保留 ${kept.length}/${list.length} 条, 标记 ${marked} 条`
  );
  return kept;
}

async function loadItems(keyword) {
  const key = `mp:items:${md5(keyword)}`;
  return cachedValue(key, SEARCH_CACHE_EX, async () => {
    const result = await searchRaw(keyword);
    const items = await filterExpiredItems(sortGroupItems(result.items || []));
    log("info", `觅盘 搜索 "${keyword}": 资源 ${items.length} 条`);
    return { items, total: items.length };
  });
}

// ==================== 123云盘直连(容器123 drive 枚举/播放失败时的兜底) ====================
// 列表: GET {origin}/b/api/share/get?limit&next&shareKey&SharePwd&ParentFileId (Type 1=目录 0=文件,匿名可读)
// 播放: POST {origin}/b/api/share/download/info({ShareKey,FileID,S3keyFlag,Size,Etag})
//       -> data.DownloadURL 的 params(base64) -> GET -> data.redirect_url 即最终播放地址
// 注意: 列表返回字段是 S3KeyFlag(大写K),下载请求体字段是 S3keyFlag(小写k),两者大小写不同
const PAN123_HOST_MAP = {
  "123684.com": "www.123pan.cn",
  "123685.com": "www.123pan.cn",
  "123865.com": "www.123pan.cn",
  "123912.com": "www.123pan.cn",
};
const PAN123_MAX_EPISODES = envInt("MIPAN_123_MAX_EPISODES", 200, 1);

// ==================== UC分享匿名免转存直连(照 omnibox 同款 PowerList 配方) ====================
// 分享匿名换 stoken -> 列目录拿 share_fid_token -> /file/download 换直链,不转存个人网盘。
// 非会员后台 Cookie 不走这条链路;直连失败仍回退容器 drive,后台 UC 账号继续生效。
const UC_SHARE_API = "https://pc-api.uc.cn/1/clouddrive";
const UC_SHARE_REFERER = "https://drive.uc.cn";
const UC_SHARE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) uc-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch";
const UC_SHARE_COOKIE = String(process.env.UC_COOKIE || "").trim();
const UC_SHARE_TOKEN_TTL = 600;
const UC_SHARE_LINK_TTL = 120;
const UC_SHARE_MAX_EPISODES = envInt("MIPAN_UC_MAX_EPISODES", 200, 1);
const UC_SHARE_REQ_INTERVAL = 300;
let UC_SHARE_LAST_REQ = 0;


// 123分享有多个镜像域名,容器/SDK 的123 drive 只认含 "123pan" 的域名;统一改写成 www.123pan.cn(同一套API)
function normalizePanShareURL(raw) {
  const value = String(raw || "");
  if (!value || !/^https?:\/\//i.test(value)) return value;
  const parts = value.match(/^(https?:\/\/)([^/?#]+)(.*)$/i);
  if (!parts) return value;
  const host = parts[2].toLowerCase().replace(/^www\./, "");
  const target = PAN123_HOST_MAP[host];
  if (!target) return value;
  let next = `${parts[1]}${target}${parts[3]}`;
  const pwd = next.match(/[?&]pwd=([^&#]+)/i);
  if (pwd && !/[?&]password=/i.test(next)) next += `${next.includes("?") ? "&" : "?"}password=${pwd[1]}`;
  log("info", `觅盘 123分享域名改写: ${host} -> ${target}`);
  return next;
}

function isPan123URL(url) {
  const parts = String(url || "").match(/^https?:\/\/([^/?#]+)/i);
  if (!parts) return false;
  const host = parts[1].toLowerCase().replace(/^www\./, "");
  return Boolean(PAN123_HOST_MAP[host]) || /(^|\.)123pan\.(cn|com)$/.test(host);
}

function parseUCShare(shareURL) {
  const value = String(shareURL || "").trim();
  if (!value) return null;
  let host = "";
  let path = "";
  let search = "";
  try {
    const u = new URL(value);
    host = u.hostname.toLowerCase();
    path = u.pathname;
    search = u.search;
  } catch (error) {
    const parts = value.match(/^(https?:\/\/)([^/?#]+)([^#]*)/i);
    if (!parts) return null;
    host = String(parts[2] || "").toLowerCase();
    const rest = parts[3] || "";
    const qIndex = rest.indexOf("?");
    path = qIndex >= 0 ? rest.slice(0, qIndex) : rest;
    search = qIndex >= 0 ? rest.slice(qIndex) : "";
  }
  if (!/(^|\.)((drive|fast)\.uc\.cn)$/i.test(host)) return null;
  const pathMatch = path.match(/\/s\/([A-Za-z0-9_-]+)/i);
  if (!pathMatch) return null;
  const shareId = pathMatch[1];
  let sharePwd = "";
  const pwdMatch = search.match(/[?&](?:pwd|password|passcode|code|share_pwd|sharePwd|extract_code|extraction_code|access_code)=([^&#]+)/i);
  if (pwdMatch) {
    try {
      sharePwd = decodeURIComponent(pwdMatch[1] || "");
    } catch (error) {
      sharePwd = pwdMatch[1] || "";
    }
  }
  if (!sharePwd) {
    let decoded = value;
    try {
      decoded = decodeURIComponent(value);
    } catch (error) {
    }
    const inlinePwd = decoded.match(/(?:提取码|密码|访问码)[:：]\s*([A-Za-z0-9]{2,16})/i);
    if (inlinePwd) sharePwd = inlinePwd[1];
  }
  return { shareId, sharePwd };
}

function isUCShareURL(url) {
  return !!parseUCShare(url);
}

function ucParseFileId(fileId) {
  const parts = String(fileId || "").split("-");
  if (parts.length >= 2 && parts[0] && parts[1] && /^[0-9a-f]{16,}$/i.test(parts[0])) {
    return {
      fid: parts[0],
      fidToken: parts[1],
      pid: parts[2] || "",
    };
  }
  return null;
}

async function ucShareHttp(pathname, options = {}) {
  const wait = UC_SHARE_LAST_REQ + UC_SHARE_REQ_INTERVAL - Date.now();
  if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
  UC_SHARE_LAST_REQ = Date.now();
  const url = new URL(UC_SHARE_API + pathname);
  url.searchParams.set("pr", "UCBrowser");
  url.searchParams.set("entry", "ft");
  url.searchParams.set("fr", "pc");
  const query = options.query || {};
  for (const key of Object.keys(query)) {
    const value = query[key];
    if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
  }
  const headers = {
    "User-Agent": UC_SHARE_UA,
    Referer: UC_SHARE_REFERER,
    Accept: "application/json, text/plain, */*",
  };
  if (UC_SHARE_COOKIE) headers.Cookie = UC_SHARE_COOKIE;
  if (options.body) headers["content-type"] = "application/json;charset=UTF-8";
  const response = await axios({
    url: url.toString(),
    method: options.method || "GET",
    headers,
    data: options.body,
    timeout: options.timeout || REQUEST_TIMEOUT,
    httpsAgent: HTTPS_AGENT,
    httpAgent: HTTP_AGENT,
    responseType: "text",
    validateStatus: () => true,
  });
  let body = response.data;
  if (typeof body !== "string") body = body === undefined || body === null ? "" : JSON.stringify(body);
  const data = parseJson(body);
  if (!data || typeof data !== "object") {
    throw new Error(`UC分享接口非JSON响应(HTTP ${response.status})`);
  }
  if (Number(data.code) !== 0) {
    const error = new Error(data.message || `UC业务错误 code=${data.code}`);
    error.ucCode = Number(data.code);
    throw error;
  }
  return data;
}

async function ucShareTokenFetch(info) {
  const data = await ucShareHttp("/share/sharepage/token", {
    method: "POST",
    body: {
      pwd_id: info.shareId,
      passcode: info.sharePwd || "",
      share_for_transfer: true,
    },
  });
  const stoken = String((data.data && data.data.stoken) || "");
  if (!stoken) throw new Error("UC分享stoken获取失败");
  return stoken;
}

async function ucShareToken(info, force) {
  const key = `mp:uc:stoken:${info.shareId}:${info.sharePwd || ""}`;
  if (!force) return cachedValue(key, UC_SHARE_TOKEN_TTL, () => ucShareTokenFetch(info));
  const stoken = await ucShareTokenFetch(info);
  memSet(key, stoken, UC_SHARE_TOKEN_TTL);
  await redisSet(key, stoken, UC_SHARE_TOKEN_TTL);
  return stoken;
}

async function ucShareListPage(info, stoken, parentId, page) {
  const data = await ucShareHttp("/share/sharepage/detail", {
    query: {
      pwd_id: info.shareId,
      stoken,
      pdir_fid: parentId,
      force: "0",
      _page: String(page || 1),
      _size: "100",
      _fetch_banner: "0",
      _fetch_share: "0",
      _fetch_total: "1",
      _sort: "file_type:asc,file_name:asc",
    },
  });
  const list = data.data && Array.isArray(data.data.list) ? data.data.list : [];
  const total = Number((data.metadata && data.metadata._total) || 0);
  return { list, total };
}

async function ucShareFindFile(info, stoken, fileId) {
  const wanted = String(fileId || "");
  let visited = 0;
  const walk = async (parentId, depth) => {
    if (depth > 4 || visited > 2000) return null;
    let fetched = 0;
    for (let page = 1; page <= 30; page++) {
      const result = await ucShareListPage(info, stoken, parentId, page);
      const list = result.list;
      visited += list.length;
      fetched += list.length;
      for (const item of list) {
        const fid = String(item.fid || "");
        const fidToken = String(item.share_fid_token || "");
        const pid = String(item.pdir_fid || parentId || "");
        if (!fid) continue;
        if (fid === wanted || `${fid}-${fidToken}-${pid}` === wanted) {
          return {
            fid,
            fidToken,
            pid,
            name: String(item.file_name || ""),
            size: Number(item.size || 0) || 0,
          };
        }
      }
      for (const item of list) {
        if (Number(item.file_type) !== 0) continue;
        const found = await walk(String(item.fid || ""), depth + 1);
        if (found) return found;
      }
      if (!list.length) break;
      if (result.total > 0 && (fetched >= result.total || page * 100 >= result.total)) break;
      if (list.length < 100) break;
    }
    return null;
  };
  return walk("0", 0);
}

function ucShareLinkCacheKey(info, target) {
  return `mp:uc:dl:${info.shareId}:${target.fid}:${target.fidToken || ""}`;
}

async function ucShareDirectLink(info, stoken, target) {
  const cacheKey = ucShareLinkCacheKey(info, target);
  return cachedValue(cacheKey, UC_SHARE_LINK_TTL, async () => {
    const data = await ucShareHttp("/file/download", {
      method: "POST",
      body: {
        fids: [target.fid],
        fids_token: [target.fidToken],
        pwd_id: info.shareId,
        stoken,
        speedup_session: "",
      },
    });
    const url = String((data.data && data.data[0] && data.data[0].download_url) || "");
    if (!url) throw new Error("UC直链为空");
    return url;
  });
}

function encodeUCEpisode(shareURL, file) {
  try {
    const payload = {
      u: String(shareURL || ""),
      f: String(file.fid || ""),
      t: String(file.fidToken || ""),
      p: String(file.pid || ""),
    };
    if (file.name) payload.n = String(file.name);
    return "puc:" + encodeBase64Url(JSON.stringify(payload));
  } catch (error) {
    return "";
  }
}

function decodeUCEpisode(id) {
  const raw = String(id || "");
  if (!raw.startsWith("puc:")) return null;
  try {
    const data = JSON.parse(decodeBase64Url(raw.slice(4)));
    if (!data || !data.u || !data.f) return null;
    return {
      u: String(data.u),
      f: String(data.f),
      t: String(data.t || ""),
      p: String(data.p || ""),
      n: String(data.n || ""),
    };
  } catch (error) {
    return null;
  }
}

async function ucDirectEpisodes(shareURL) {
  const info = parseUCShare(shareURL);
  if (!info) throw new Error("无法识别的UC分享链接");
  const stoken = await ucShareToken(info);
  const episodes = [];
  let visited = 0;
  const walk = async (parentId, depth) => {
    if (depth > 4 || visited > 2000 || episodes.length >= UC_SHARE_MAX_EPISODES) return;
    let fetched = 0;
    for (let page = 1; page <= 30; page++) {
      const result = await ucShareListPage(info, stoken, parentId, page);
      const list = result.list;
      visited += list.length;
      fetched += list.length;
      for (const item of list) {
        if (Number(item.file_type) !== 1) continue;
        const name = String(item.file_name || "").trim();
        const fid = String(item.fid || "");
        if (!name || !fid || !isVideoFileName(name)) continue;
        const fileSize = Number(item.file_size || item.size || 0) || 0;
        const id = encodeUCEpisode(shareURL, {
          fid,
          fidToken: String(item.share_fid_token || ""),
          pid: String(item.pdir_fid || parentId || ""),
          name,
        });
        const displayName = (fileSize > 0 ? `[${formatFileSize(fileSize)}] ` : "") + name;
        if (id) episodes.push({ id, name: safeEpisodeName(displayName) });
      }
      for (const item of list) {
        if (Number(item.file_type) !== 0) continue;
        await walk(String(item.fid || ""), depth + 1);
        if (episodes.length >= UC_SHARE_MAX_EPISODES) break;
      }
      if (!list.length) break;
      if (result.total > 0 && (fetched >= result.total || page * 100 >= result.total)) break;
      if (list.length < 100) break;
    }
  };
  await walk("0", 0);
  return episodes.slice(0, UC_SHARE_MAX_EPISODES);
}

async function ucDirectVod(shareURL) {
  const episodes = await ucDirectEpisodes(shareURL);
  if (!episodes.length) return null;
  const info = parseUCShare(shareURL);
  log("info", `觅盘 UC直连枚举: ${episodes.length} 个视频 (${info ? info.shareId : "?"})`);
  return {
    vod_play_from: "UC",
    vod_play_url: episodes.map((ep) => `${ep.name}$${ep.id}`).join("#"),
  };
}

async function ucDirectPlayByFile(shareURL, fileId) {
  const info = parseUCShare(shareURL);
  if (!info) throw new Error("无法识别的UC分享链接");
  let stoken = await ucShareToken(info);
  let target = ucParseFileId(fileId);
  let needLookup = !target;
  let retriedToken = false;
  let retriedFidToken = false;
  let retriedEmpty = false;
  while (true) {
    try {
      if (needLookup) {
        target = await ucShareFindFile(info, stoken, fileId);
        needLookup = false;
        if (!target) throw new Error("UC分享中未找到该文件");
      }
      const url = await ucShareDirectLink(info, stoken, target);
      return {
        parse: 0,
        jx: 0,
        url,
        header: {
          "User-Agent": UC_SHARE_UA,
          Referer: url + "\\ ",
          "Accept-Encoding": "identity",
        },
      };
    } catch (error) {
      const message = String((error && error.message) || error || "");
      if (!retriedToken && (Number(error.ucCode) === 50052 || /st invalid|stoken过期|分享的stoken过期/i.test(message))) {
        retriedToken = true;
        stoken = await ucShareToken(info, true);
        if (!target) needLookup = true;
        continue;
      }
      if (!retriedFidToken && target && target.pid && /token校验异常/i.test(message)) {
        retriedFidToken = true;
        const fresh = await ucShareFindFile(info, stoken, target.fid);
        if (fresh) target = fresh;
        continue;
      }
      if (!retriedEmpty && target && target.pid && /UC直链为空/.test(message)) {
        retriedEmpty = true;
        stoken = await ucShareToken(info, true);
        const fresh = await ucShareFindFile(info, stoken, target.fid);
        if (fresh) target = fresh;
        continue;
      }
      throw error;
    }
  }
}

async function ucDirectPlay(encodedId) {
  const file = decodeUCEpisode(encodedId);
  if (!file) throw new Error("UC选集参数异常");
  const fileId = file.t ? `${file.f}-${file.t}-${file.p || ""}` : file.f;
  return ucDirectPlayByFile(file.u, fileId);
}

// ==================== 123账号与签名(照 alist 配方: yun.123pan.com + signPath签名 + 登录态 Bearer) ====================
// 【123账号】123 download 接口需登录(匿名必拒"您需要注册登录或付费后下载"):
//   账密不写死在 JS 里,只配环境变量:PAN_123_USERNAME + PAN_123_PASSWORD(自动登录换token,401自动重登),
//   或已有 token 直接配 PAN_123_TOKEN;"不夜后台添加123账号"功能已随123改版失效,不用管它,以环境变量为准。
// 123 已给 API 加请求签名(不带签名会被风控拦回HTML),签名算法照 AlistGo/alist drivers/123_share 移植
const PAN123_TOKEN_ENV = String(process.env.PAN_123_TOKEN || "").trim();
const PAN123_USERNAME = String(process.env.PAN_123_USERNAME || "").trim();
const PAN123_PASSWORD = String(process.env.PAN_123_PASSWORD || "").trim();
let PAN123_ACCESS_TOKEN = PAN123_TOKEN_ENV;
let PAN123_TOKEN_AT = 0;
const PAN123_TOKEN_TTL = 6 * 3600 * 1000;
const PAN123_SIGNIN_URLS = ["https://login.123pan.com/api/user/sign_in", "https://user.123pan.cn/api/user/sign_in"];
const PAN123_API_HOSTS = ["https://yun.123pan.com", "https://www.123pan.cn", "https://www.123pan.com"];
let PAN123_API_HOST_CACHE = "";
const PAN123_REQ_INTERVAL = 700; // alist 同款限流: 700ms/请求
let PAN123_LAST_REQ = 0;

// signPath 签名: 照 AlistGo/alist drivers/123_share/util.go 1:1 移植(CRC32-IEEE + 东八区时间)
const PAN123_CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();
function pan123Crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = PAN123_CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
const PAN123_SIGN_TABLE = "adefghlmyijnopkqrstubcvwsz";
function pan123SignPath(path) {
  const cst = new Date(Date.now() + 8 * 3600 * 1000); // 东八区,Go time.FixedZone("CST", 8*3600)
  const pad = (n) => String(n).padStart(2, "0");
  const nowStr = `${cst.getUTCFullYear()}${pad(cst.getUTCMonth() + 1)}${pad(cst.getUTCDate())}${pad(cst.getUTCHours())}${pad(cst.getUTCMinutes())}`;
  let mapped = "";
  for (const ch of nowStr) mapped += PAN123_SIGN_TABLE[ch.charCodeAt(0) - 48];
  const timeSign = pan123Crc32(Buffer.from(mapped, "utf8"));
  const timestamp = String(Math.floor(Date.now() / 1000));
  const random = String(Math.round(Math.random() * 1e7));
  const data = [timestamp, random, path, "web", "3", String(timeSign)].join("|");
  const dataSign = pan123Crc32(Buffer.from(data, "utf8"));
  return { k: String(timeSign), v: `${timestamp}-${random}-${dataSign}` };
}
function pan123SignURL(urlStr) {
  try {
    const u = new URL(urlStr);
    const sg = pan123SignPath(u.pathname);
    u.searchParams.set(sg.k, sg.v);
    u.searchParams.sort(); // 对齐 Go url.Values.Encode 的 key 排序
    return u.toString();
  } catch (error) {
    return urlStr;
  }
}

function parsePan123Share(shareURL) {
  const value = String(shareURL || "");
  const parts = value.match(/^(https?:\/\/)([^/?#]+)([^#]*)/i);
  if (!parts) return null;
  const origin = `${parts[1]}${parts[2]}`;
  const path = parts[3] || "";
  let shareKey = "";
  // 兼容两种路径: /s/{token}(旧) 与 /123pan/{token}(新,如 *.share.123pan.cn/123pan/xxx?notoken=1)
  const pathMatch = path.match(/\/(?:s|123pan)\/([^/?#]+)/i);
  if (pathMatch) {
    // key 白名单(字母数字-_): 源数据常把"提取码:xxx"直接粘在路径上,自动截掉防 ShareKey长度异常
    const raw = String(pathMatch[1] || "").replace(/\.html$/i, "");
    const clean = raw.match(/^[A-Za-z0-9][A-Za-z0-9_-]*/);
    shareKey = clean ? clean[0] : raw;
  }
  if (!shareKey) {
    const queryKey = value.match(/[?&]shareKey=([^&#]+)/i);
    if (queryKey) {
      const raw = decodeURIComponent(queryKey[1] || "");
      const clean = raw.match(/^[A-Za-z0-9][A-Za-z0-9_-]*/);
      shareKey = clean ? clean[0] : raw;
    }
  }
  if (!shareKey) return null;
  const pwdMatch = value.match(/[?&](?:pwd|password|SharePwd)=([^&#]+)/i);
  let sharePwd = pwdMatch ? decodeURIComponent(pwdMatch[1] || "") : "";
  if (!sharePwd) {
    let decoded = value;
    try { decoded = decodeURIComponent(value); } catch (error) {} // 源数据里"提取码"可能是 percent-encoded
    const inlinePwd = decoded.match(/提取码[:：]\s*([A-Za-z0-9]{2,12})/i); // 粘连的"提取码:xxx"兜底
    if (inlinePwd) sharePwd = inlinePwd[1];
  }
  return { origin, shareKey, sharePwd };
}

// ===== 123 无限直链(PowerList drivers/123/unlimited.go 同款移植) =====
const PAN123_THUMB_SUFFIX = "_24_24";
const PAN123_THUMB_TRADE_KEY = "&trade_key=123pan-thumbnail";
const PAN123_THUMB_MIN_TTL = 30 * 60 * 1000; // 剩余有效期低于此值就重列目录换新签名(同 Go ThumbLinkMinTTL)
const PAN123_SHARE_DU_SUPPORT = {}; // shareKey -> true/false: 该分享列表是否给 DownloadUrl(试过一次没有就不再白拉)

function pan123StripThumbTransform(raw) {
  // 字面量替换、不重排 query: trade_key 匹配依赖前导 & (照 Go StripThumbTransform)
  let out = String(raw || "");
  const i1 = out.indexOf(PAN123_THUMB_SUFFIX);
  if (i1 >= 0) out = out.slice(0, i1) + out.slice(i1 + PAN123_THUMB_SUFFIX.length);
  const i2 = out.indexOf(PAN123_THUMB_TRADE_KEY);
  if (i2 >= 0) out = out.slice(0, i2) + out.slice(i2 + PAN123_THUMB_TRADE_KEY.length);
  return out;
}

function pan123ThumbTTL(raw) { // t= 过期时间戳 → 剩余毫秒(解析不出返回 0)
  try {
    const ts = parseInt(new URL(String(raw)).searchParams.get("t") || "", 10);
    if (!Number.isFinite(ts) || ts <= 0) return 0;
    return ts * 1000 - Date.now();
  } catch (error) {
    return 0;
  }
}

// 死分享/链接无效类错误: 换鉴权/换参数形态也是同一后端,回退纯属白跑
function isDeadShareError(message) {
  return /此分享不存在|分享不存在|好友已取消(了)?分享|分享已(被)?(取消|失效|删除|过期)|已过期|已被删除|链接不存在|资源不存在|文件不存在|分享链接无效|分享者用户封禁|ShareKey长度异常|提取流量包不足|流量包不足|内容已被清空/i.test(String(message || ""));
}

function isPreciseShareError(message) {
  const msg = String(message || "");
  if (/该 123 分享内容已被清空/.test(msg)) return true;
  if (isDeadShareError(msg)) return true;
  if (/提取码错误|提取码不正确|密码错误|密码不正确/i.test(msg)) return true;
  return false;
}

function pan123Headers(origin, anon) {
  const host = String(origin || PAN123_API_HOSTS[0]).replace(/\/+$/, "");
  const headers = {
    "User-Agent": SITE_UA, // 123 已按特征拦截 alist-client UA("暂不支持Alist服务"),必须普通浏览器 UA
    Accept: "application/json, text/plain, */*",
    origin: host,
    referer: `${host}/`,
    platform: "web",
    "app-version": "3",
  };
  if (anon) return headers; // 匿名(PowerList requestAnon): 分享接口不带 Authorization
  const token = PAN123_ACCESS_TOKEN || "";
  if (token) headers.authorization = `Bearer ${token}`;
  return headers;
}

// 独立于 httpRequest:不走站点限流、不污染觅盘的 cookie jar;700ms 限流对齐 alist
async function pan123Http(url, options = {}) {
  const wait = PAN123_LAST_REQ + PAN123_REQ_INTERVAL - Date.now();
  if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
  PAN123_LAST_REQ = Date.now();
  const response = await axios({
    url,
    method: options.method || "GET",
    headers: options.headers || pan123Headers(""),
    data: options.body,
    timeout: options.timeout || REQUEST_TIMEOUT,
    httpsAgent: HTTPS_AGENT,
    httpAgent: HTTP_AGENT,
    responseType: "text",
    validateStatus: () => true,
  });
  let body = response.data;
  if (typeof body !== "string") body = body === undefined || body === null ? "" : JSON.stringify(body);
  return { statusCode: response.status, body, headers: response.headers || {} };
}

async function pan123EnsureToken(force) {
  if (PAN123_TOKEN_ENV) return PAN123_TOKEN_ENV; // 手填 token 永远优先
  if (!PAN123_USERNAME || !PAN123_PASSWORD) return "";
  if (!force && PAN123_ACCESS_TOKEN && Date.now() - PAN123_TOKEN_AT < PAN123_TOKEN_TTL) return PAN123_ACCESS_TOKEN;
  const body = PAN123_USERNAME.indexOf("@") > 0
    ? { mail: PAN123_USERNAME, password: PAN123_PASSWORD, type: 2 }
    : { passport: PAN123_USERNAME, password: PAN123_PASSWORD, remember: true };
  let lastError = null;
  for (const signInURL of PAN123_SIGNIN_URLS) {
    try {
      const response = await pan123Http(signInURL, {
        method: "POST",
        headers: { ...pan123Headers("https://www.123pan.com"), "content-type": "application/json;charset=UTF-8" },
        body,
      });
      const data = parseJson(response.body);
      const token = data && data.data && String(data.data.token || "");
      if (token && Number(data.code) === 200) {
        PAN123_ACCESS_TOKEN = token;
        PAN123_TOKEN_AT = Date.now();
        log("info", "觅盘 123账号登录成功");
        return token;
      }
      lastError = new Error((data && data.message) || `123登录失败(HTTP ${response.statusCode}) @${signInURL}`);
      if (data && data.code !== undefined) break; // 服务端明确拒绝(如账密错误),不再换端点
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("123登录失败");
}

// 统一带签名请求: 候选域名依次尝试;业务错误(code有值,pan123Business标记)立即抛,HTML/网络错误换下一个域名
async function pan123ApiRequest(method, path, options = {}, isRetry401) {
  const { query = "", body = null, anon = false } = options;
  if (!anon && !isRetry401 && !PAN123_ACCESS_TOKEN && (PAN123_TOKEN_ENV || PAN123_USERNAME)) {
    try {
      await pan123EnsureToken(false);
    } catch (error) {
      log("warn", `觅盘 123登录失败: ${error.message}`);
    }
  }
  const hosts = [];
  if (PAN123_API_HOST_CACHE) hosts.push(PAN123_API_HOST_CACHE);
  for (const host of PAN123_API_HOSTS) if (!hosts.includes(host)) hosts.push(host);
  let firstError = null;
  for (const host of hosts) {
    const url = pan123SignURL(`${host}${path}${query ? `?${query}` : ""}`);
    let businessError = null;
    try {
      const headers = { ...pan123Headers(host, anon) };
      if (body) headers["content-type"] = "application/json;charset=UTF-8";
      const response = await pan123Http(url, { method, headers, body });
      const data = parseJson(response.body);
      if (data && typeof data === "object" && data.code !== undefined) {
        if (data.code === 0) {
          if (PAN123_API_HOST_CACHE !== host) log("info", `觅盘 123API可用域名: ${host}`);
          PAN123_API_HOST_CACHE = host;
          return data;
        }
        // token 过期/无效: 强制重登后整个重试一次(匿名请求不涉及 token)
        if (!anon && Number(data.code) === 401 && !isRetry401 && PAN123_USERNAME && !PAN123_TOKEN_ENV) {
          await pan123EnsureToken(true);
          return pan123ApiRequest(method, path, options, true);
        }
        businessError = new Error(data.message || `123业务错误 code=${data.code}`);
        businessError.pan123Business = true; // 服务端明确业务结论(死分享/流量不足等),上层别再回退
        businessError.pan123Code = Number(data.code); // 5112=分享方提取流量耗尽,精确判定别靠文案猜
      } else if (!firstError) {
        firstError = new Error(`123API非JSON响应(HTTP ${response.statusCode}) @${host}`);
      }
    } catch (error) {
      if (!firstError) firstError = error;
    }
    if (businessError) throw businessError; // 业务错误(如分享不存在)换域名也是同一后端,直接抛
  }
  throw firstError || new Error("123API请求失败");
}

function pan123ListDone(next) {
  return next === undefined || next === null || next === "" || next === -1 || next === "-1" || next === 0 || next === "0";
}

async function pan123ShareListPage(info, parentFileId, page) {
  const parent = String(parentFileId === undefined || parentFileId === null ? 0 : parentFileId);
  // 匿名首选: 对齐官方 web 客户端请求形态(PowerList listQueryAnon: ParentFileId 驼峰、next=-1、带 event 等)
  const anonQuery = new URLSearchParams({
    limit: "100",
    next: "-1",
    orderBy: "file_name",
    orderDirection: "asc",
    ParentFileId: parent,
    Page: String(page || 1),
    shareKey: info.shareKey,
    SharePwd: info.sharePwd || "",
    event: "homeListFile",
    operateType: "4",
    OrderId: "",
    superAdmin: "null",
  }).toString();
  // 兜底: 历史可用形态(小写 parentFileId、next=0) + 带账号
  const legacyQuery = new URLSearchParams({
    limit: "100",
    next: "0",
    orderBy: "file_id",
    orderDirection: "desc",
    parentFileId: parent,
    Page: String(page || 1),
    shareKey: info.shareKey,
    SharePwd: info.sharePwd || "",
  }).toString();
  let data;
  try {
    data = await pan123ApiRequest("GET", "/b/api/share/get", { query: anonQuery, anon: true });
  } catch (error) {
    // 匿名形态可能被反爬以 HTML/网络方式拒绝(非业务code),甚至误报"分享不存在":
    // legacy 形态是升级前一直可用的形态,任何错误都兜底试一次,别让形态回归把活分享判死
    try {
      data = await pan123ApiRequest("GET", "/b/api/share/get", { query: legacyQuery });
    } catch (legacyError) {
      throw error;
    }
  }
  const payload = data.data || {};
  const items = Array.isArray(payload.InfoList) ? payload.InfoList : [];
  for (const item of items) { // 记住该分享是否给列表直链,避免下次为拿 du 白列一次目录
    if (item && item.DownloadUrl) PAN123_SHARE_DU_SUPPORT[info.shareKey] = true;
  }
  return { items, next: payload.Next };
}

function formatFileSize(size) {
  if (!size || size <= 0) return "";
  const units = ["B", "K", "M", "G", "T", "P"];
  let value = size;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  if (value === Math.floor(value)) return `${Math.floor(value)}${units[index]}`;
  return `${value.toFixed(2)}${units[index]}`;
}

function isVideoFileName(name) {
  return /\.(m3u8|mp4|flv|mkv|ts|webm|m4v|avi|mov|wmv|mpg|mpeg|vob|mts|m2ts|rm|rmvb|iso|3gp|ogv|ogm|asf|f4v|dat|tp|trp|ifo)(\?|#|$)/i.test(
    String(name || "")
  );
}

// 123选集ID: p123:<base64url(JSON)>,自包含分享上下文(播放时无需再传分享链接)
function encodePan123Episode(info, file) {
  try {
    const payload = {
      o: info.origin,
      k: info.shareKey,
      w: info.sharePwd || "",
      f: file.fid,
      s: file.s3KeyFlag,
      e: file.etag,
      z: file.size,
    };
    if (file.name) payload.n = file.name; // 文件名: 匿名下载请求体的 FileName 字段用
    if (file.download_url) payload.d = file.download_url; // 无限直链: 列表已签名 DownloadUrl(有才带)
    return "p123:" + encodeBase64Url(JSON.stringify(payload));
  } catch (error) {
    return "";
  }
}

function decodePan123Episode(id) {
  const raw = String(id || "");
  if (!raw.startsWith("p123:")) return null;
  try {
    const data = JSON.parse(decodeBase64Url(raw.slice(5)));
    if (!data || !data.f || !data.k || !data.o) return null;
    return {
      origin: String(data.o),
      shareKey: String(data.k),
      sharePwd: String(data.w || ""),
      fid: String(data.f),
      s3KeyFlag: String(data.s || ""),
      etag: String(data.e || ""),
      size: Number(data.z || 0) || 0,
      name: String(data.n || ""),
      download_url: String(data.d || ""),
    };
  } catch (error) {
    return null;
  }
}

async function pan123DirectEpisodes(shareURL) {
  const info = parsePan123Share(shareURL);
  if (!info) throw new Error("无法识别的123分享链接");
  const episodes = [];
  let visited = 0;
  let anyItem = false;
  const walk = async (parentFileId, depth) => {
    if (depth > 4 || visited > 2000 || episodes.length >= PAN123_MAX_EPISODES * 2) return;
    for (let page = 1; page <= 30; page++) {
      const result = await pan123ShareListPage(info, parentFileId, page);
      visited += result.items.length;
      if (result.items.length) anyItem = true;
      for (const item of result.items) {
        const type = Number(item && item.Type);
        if (type === 1) {
          await walk(Number(item.FileId) || 0, depth + 1);
          continue;
        }
        if (type !== 0) continue;
        const name = String((item && item.FileName) || "").trim();
        const fid = String((item && item.FileId) || "");
        if (!name || !fid || !isVideoFileName(name)) continue;
        const fileSize = Number(item && item.Size ? item.Size : 0) || 0;
        const id = encodePan123Episode(info, {
          fid,
          s3KeyFlag: String(item.S3KeyFlag || ""),
          etag: String(item.Etag || ""),
          size: fileSize,
          name,
          download_url: String(item.DownloadUrl || ""), // 无限直链: 列表已签名直链,播放档①零请求
        });
        const displayName = (fileSize > 0 ? `[${formatFileSize(fileSize)}] ` : "") + name;
        if (id) episodes.push({ id, name: safeEpisodeName(displayName) });
      }
      if (pan123ListDone(result.next) || !result.items.length) break;
    }
  };
  await walk(0, 0);
  if (!episodes.length && !anyItem) throw new Error("该 123 分享内容已被清空（分享记录有效但文件为空）");
  return episodes.slice(0, PAN123_MAX_EPISODES);
}

async function pan123FindFile(info, targetFileId) {
  const target = String(targetFileId || "");
  if (!target) return null;
  let visited = 0;
  const walk = async (parentFileId, depth) => {
    if (depth > 4 || visited > 2000) return null;
    for (let page = 1; page <= 30; page++) {
      const result = await pan123ShareListPage(info, parentFileId, page);
      visited += result.items.length;
      for (const item of result.items) {
        if (String(item && item.FileId) === target) {
          return Number(item && item.Type) === 1
            ? null
            : {
                fid: target,
                s3KeyFlag: String(item.S3KeyFlag || ""),
                etag: String(item.Etag || ""),
                size: Number(item.Size || 0) || 0,
                name: String(item.FileName || ""),
                download_url: String(item.DownloadUrl || ""),
              };
        }
        if (Number(item && item.Type) === 1) {
          const hit = await walk(Number(item.FileId) || 0, depth + 1);
          if (hit) return hit;
        }
      }
      if (pan123ListDone(result.next) || !result.items.length) break;
    }
    return null;
  };
  return walk(0, 0);
}

// p123:选集直接播放(自包含分享上下文);三档取链照 power721/PowerList:①无限直链 ②匿名换直链 ③5112→本人网盘
async function pan123DirectPlay(encodedId) {
  const file = decodePan123Episode(encodedId);
  if (!file) throw new Error("123选集参数异常");
  const info = { origin: file.origin, shareKey: file.shareKey, sharePwd: file.sharePwd };
  let s3KeyFlag = file.s3KeyFlag;
  let etag = file.etag;
  let size = file.size;
  let fileName = file.name;
  let listDirect = file.download_url;
  const duState = PAN123_SHARE_DU_SUPPORT[info.shareKey];
  const needMeta = !s3KeyFlag || !etag;
  const needFreshDu = duState !== false && pan123ThumbTTL(pan123StripThumbTransform(listDirect)) < PAN123_THUMB_MIN_TTL;
  // 元数据缺失,或列表直链缺失/签名快过期: 重列一次目录(PowerList refreshDownloadUrl 同款,顺带换新签名)
  if (needMeta || needFreshDu) {
    const found = await pan123FindFile(info, file.fid);
    if (!found) {
      if (needMeta) throw new Error("123分享中未找到该文件");
    } else {
      if (!s3KeyFlag) s3KeyFlag = found.s3KeyFlag;
      if (!etag) etag = found.etag;
      if (!size) size = found.size;
      if (!fileName) fileName = found.name;
      if (found.download_url) listDirect = found.download_url;
      else if (!PAN123_SHARE_DU_SUPPORT[info.shareKey]) PAN123_SHARE_DU_SUPPORT[info.shareKey] = false; // 读实时值,别覆盖刚标上的 true
    }
  }
  // 档① 无限直链: 列表已签名 DownloadUrl 剥掉缩略图标记直接用(零请求,签名约7天有效,大概率不计额度)
  const directRaw = pan123StripThumbTransform(listDirect);
  const directTTL = pan123ThumbTTL(directRaw);
  if (directRaw && directTTL > 0) {
    log("info", `觅盘 123无限直链命中(剩余约${Math.round(directTTL / 60000)}分钟): ${fileName || file.fid}`);
    return { parse: 0, jx: 0, url: directRaw, header: {} };
  }
  // 档② 匿名换直链(无 Bearer);业务错误且非流量/死分享时带账号重试一次(PowerList: 匿名优先,账号兜底)
  const dlBody = {
    driveId: "0",
    shareKey: info.shareKey,
    SharePwd: info.sharePwd || "",
    etag,
    fileId: Number(file.fid) || file.fid,
    s3keyFlag: s3KeyFlag,
    size,
  };
  if (fileName) dlBody.FileName = fileName;
  let dlData = null;
  let lastDlError = null;
  try {
    // alist 同款下载请求体: 小驼峰 {shareKey,SharePwd,etag,fileId,s3keyFlag,size}
    dlData = await pan123ApiRequest("POST", "/b/api/share/download/info", { body: dlBody, anon: true });
  } catch (error) {
    lastDlError = error;
    const message = String((error && error.message) || error || "");
    const traffic = !!(error && error.pan123Business) &&
      (Number(error.pan123Code) === 5112 || /提取流量|流量包不足|流量不足/.test(message)); // 精确匹配,别让"提取码不正确"误判成流量耗尽
    // 5112 分享方流量耗尽/死分享: 账号重试也无意义(同一后端),不打账号
    if (!traffic && !isDeadShareError(message) && error && error.pan123Business && (PAN123_TOKEN_ENV || PAN123_USERNAME)) {
      try {
        dlData = await pan123ApiRequest("POST", "/b/api/share/download/info", { body: dlBody });
      } catch (authError) {
        lastDlError = authError;
      }
    }
  }
  if (!dlData && lastDlError) {
    const message = String((lastDlError && lastDlError.message) || lastDlError || "");
    const code = Number(lastDlError && lastDlError.pan123Code) || 0;
    // 5103: 区分"此分享不存在"(真失效) 与"提取码错误"(非失效,需修正提取码)
    if (code === 5103) {
      if (/此分享不存在|分享不存在|好友已取消(了)?分享|分享已(被)?(取消|失效|删除|过期)|已过期|已被删除|链接不存在|资源不存在|文件不存在|分享链接无效|ShareKey长度异常/i.test(message)) {
        throw new Error("该 123 分享已失效（此分享不存在）");
      }
      if (/提取码错误|提取码不正确|密码错误|密码不正确/i.test(message)) {
        throw new Error("123 提取码不正确（非失效，请修正提取码后重试）");
      }
    }
    // 档③ 分享方无提取流量(免费号为0): 文件在自己盘里时改走"我的网盘"下载接口(消耗自己普通下载流量,alist 挂载同款)
    const trafficMsg = code === 5112 || /提取流量|流量包不足|流量不足/.test(message);
    if (!(lastDlError && lastDlError.pan123Business) || !trafficMsg) throw lastDlError;
    try {
      dlData = await pan123ApiRequest("POST", "/b/api/file/download_info", {
        body: { driveId: 0, etag, fileId: Number(file.fid) || file.fid, s3keyFlag: s3KeyFlag, size },
      });
      log("info", "觅盘 123分享无提取流量,已改走本人网盘下载接口");
    } catch (selfError) {
      throw lastDlError; // 自己盘里也没有(别人的文件),抛原始分享错误
    }
  }
  if (!dlData) throw new Error("123获取下载地址失败");
  const downloadURL = String((dlData.data && dlData.data.DownloadURL) || "");
  if (!downloadURL) throw new Error("123获取下载地址失败");
  const apiHost = PAN123_API_HOST_CACHE || PAN123_API_HOSTS[0];
  let finalURL = downloadURL;
  const paramsMatch = downloadURL.match(/[?&]params=([^&]+)/);
  if (paramsMatch) {
    const step1URL = Buffer.from(paramsMatch[1], "base64").toString("utf8");
    if (!/^https?:\/\//i.test(step1URL)) throw new Error("123下载地址参数异常");
    // step2: 302 取 location;非跳转响应则解析 JSON 的 redirect_url;直接就是文件流则用原地址
    // 只带 UA+Referer,不带 Bearer(PowerList unwrap123DownloadLink 同款): 令牌别发给解码出来的任意域名
    const step2 = await pan123Http(step1URL, {
      headers: { "User-Agent": SITE_UA, referer: `${apiHost}/`, Range: "bytes=0-1023" },
    });
    if (step2.statusCode === 301 || step2.statusCode === 302) {
      finalURL = String(step2.headers.location || "");
    } else if (step2.statusCode < 300) {
      const step2Data = parseJson(step2.body);
      finalURL = String((step2Data && step2Data.data && (step2Data.data.redirect_url || step2Data.data.DownloadUrl)) || step1URL);
    } else {
      throw new Error(`123获取最终播放地址失败(HTTP ${step2.statusCode})`);
    }
  }
  if (!/^https?:\/\//i.test(finalURL)) throw new Error("123获取最终播放地址失败");
  return { parse: 0, jx: 0, url: finalURL, header: {} };
}

// 123直连枚举 → 标准 vod_play_from/play_url 结构(供详情页展示分集)
async function pan123DirectVod(shareURL) {
  const episodes = await pan123DirectEpisodes(shareURL);
  if (!episodes.length) return null;
  const info = parsePan123Share(shareURL);
  log("info", `觅盘 123直连枚举: ${episodes.length} 个视频 (${info ? info.shareKey : "?"})`);
  return {
    vod_play_from: "123",
    vod_play_url: episodes.map((ep) => `${ep.name}$${ep.id}`).join("#"),
  };
}

// ==================== 百度网盘分享匿名直连枚举(照页面同款 H5: verify 换 BDCLND -> yunData 拿 shareid/uk -> /share/list) ====================
// 背景: SDK 内部"分享信息"调用在百度侧偶发 errno=-21 持续失败(同一分享 verify 实测 errno=0 活着),
//   列表取不到就出"资源获取失败(瞬时原因)"占位。本节在插件侧按页面同款链路自己枚举:
// 目录导航与页面一致: 根 = root=1;子目录 = dir=<sharelink 形式完整路径> 且不带 root 参数——
//   实测 root=1 会把 dir 忽略,dir 带 owner 形式路径或纯 fs_id 都报 errno=2;
//   根层子目录路径按页面嵌入 file_list 同款拼 /sharelink{uk}-{fs_id}/{name}(实测可列),深层用列表返回的 sharelink 路径。
// 错误口径: -7/-8/空分享抛死分享原话(直连判定为准,详情照常判死);-9 提取码不正确、-3 目录未命中
//   (不带服务端原文防"文件不存在"字样误判死)等其余一律瞬时——loadShareVod 捕获后回退容器 drive(死分享/提取码经 isPreciseShareError 直抛占位卡)。
// 播放: 选集 ID 为 pbaidu: 自包含形态(照 p123:/puc: 惯例);容器选集 ID 也先试匿名直连,失败回退容器。
// 百度匿名请求通道: 独立 axios 直发(不走站点限流、不与容器/站点 Cookie 混罐)
let BAIDU_LAST_REQ = 0;
async function baiduHttp(url, options = {}) {
  const wait = BAIDU_LAST_REQ + 150 - Date.now();
  if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
  BAIDU_LAST_REQ = Date.now();
  const response = await axios({
    url,
    method: options.method || "GET",
    headers: options.headers || {},
    data: options.body,
    timeout: options.timeout || REQUEST_TIMEOUT,
    httpsAgent: HTTPS_AGENT,
    responseType: "text",
    validateStatus: () => true,
  });
  let body = response.data;
  if (typeof body !== "string") body = body === undefined || body === null ? "" : JSON.stringify(body);
  return { statusCode: response.status, body, headers: response.headers || {} };
}

const BAIDU_SHARE_MAX_DEPTH = 4;
const BAIDU_SHARE_MAX_VISITED = 2000;
const BAIDU_SHARE_MAX_VIDEOS = 400;
const BAIDU_SHARE_MAX_PAGES = 30;
const BAIDU_SHARE_PAGE_SIZE = 100;
// 播放取链(页面视频插件同款): BPSType 默认 M3U8_FLV_264_480,响应即 M3U8 播放列表;会话/签名短缓存复用
const BAIDU_STREAM_TYPE = "M3U8_FLV_264_480";
const BAIDU_SESSION_TTL = 600;
const BAIDU_SIGN_TTL = 120;

function isBaiduShareURL(url) {
  return !!parseBaiduShare(url);
}

function parseBaiduShare(shareURL) {
  const value = String(shareURL || "").trim();
  if (!value) return null;
  try {
    const u = new URL(value);
    if (!/(^|\.)pan\.baidu\.com$/i.test(u.hostname)) return null;
    const pathMatch = u.pathname.match(/^\/s\/(1?)([A-Za-z0-9_-]+)/i);
    if (!pathMatch || !pathMatch[2]) return null;
    const surl = pathMatch[2];
    let pwd = "";
    const pwdMatch = u.search.match(/[?&](?:pwd|password|passcode|code|share_pwd|sharePwd|extract_code|extraction_code|access_code)=([^&#]+)/i);
    if (pwdMatch) {
      try {
        pwd = decodeURIComponent(pwdMatch[1] || "");
      } catch (error) {
        pwd = pwdMatch[1] || "";
      }
    }
    if (!pwd) {
      let decoded = value;
      try {
        decoded = decodeURIComponent(value);
      } catch (error) {
        // 保持原样
      }
      const inlinePwd = decoded.match(/(?:提取码|密码|访问码)[:：]\s*([A-Za-z0-9]{2,16})/i);
      if (inlinePwd) pwd = inlinePwd[1];
    }
    return { surl, pwd };
  } catch (error) {
    return null;
  }
}

// 分享页元数据解析: 老版 window.yunData 与新版 disk-share-v2 转义 JSON 双形态(AB 灰度按请求随机);解析不出返回 null
function baiduParseShareMeta(bodyText) {
  const text = String(bodyText || "");
  const yunIndex = text.indexOf("window.yunData=");
  let segment = "";
  if (yunIndex >= 0) {
    segment = text.slice(yunIndex, yunIndex + 1200);
  } else {
    // 新版页面无 yunData,分享元数据以转义 JSON 内嵌——按 share_uk 锚点开窗反转义后复用同款正则
    const metaIndex = text.indexOf("share_uk");
    if (metaIndex < 0) return null;
    segment = text.slice(Math.max(0, metaIndex - 600), metaIndex + 1200).replace(/\\"/g, '"');
  }
  const uk = (segment.match(/["']?share_uk["']?\s*:\s*["']?(\d+)["']?/) || [])[1];
  const shareid = (segment.match(/["']?shareid["']?\s*:\s*["']?(\d+)["']?/) || [])[1];
  if (!uk || !shareid) return null;
  return { uk, shareid };
}

// 匿名会话: 带提取码的分享先 verify 换 BDCLND Cookie,再开分享页解析 window.yunData 拿 shareid/share_uk。
// Cookie 罐吸收 verify+分享页两个响应的全部 set-cookie(BDCLND/BAIDUID/PANPSC 等)——播放签名接口
// 对只有 BDCLND 的精简 Cookie 会回 9019 need verify,必须带完整罐。
async function baiduAnonSession(info) {
  const surl = String(info.surl || "");
  const pwd = String(info.pwd || "");
  const pageURL = `https://pan.baidu.com/s/1${surl}${pwd ? `?pwd=${encodeURIComponent(pwd)}` : ""}`;
  const jar = new Map();
  const absorb = (setCookie) => {
    const list = Array.isArray(setCookie) ? setCookie : setCookie ? [setCookie] : [];
    for (const item of list) {
      const kv = String(item).split(";")[0];
      const i = kv.indexOf("=");
      if (i > 0) jar.set(kv.slice(0, i).trim(), kv.slice(i + 1).trim());
    }
  };
  const cookieHeader = () =>
    Array.from(jar.entries())
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");
  if (pwd) {
    let verify = null;
    for (let attempt = 1; attempt <= 3; attempt++) {
      verify = await baiduHttp(`https://pan.baidu.com/share/verify?surl=${encodeURIComponent(surl)}&channel=channellist&clienttype=0&app_id=250528`, {
        method: "POST",
        headers: {
          "User-Agent": SITE_UA,
          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          Accept: "application/json, text/javascript, */*; q=0.01",
          "Accept-Language": "zh-CN,zh;q=0.9",
          Referer: "https://pan.baidu.com/",
          Origin: "https://pan.baidu.com",
        },
        body: new URLSearchParams({ pwd, vcode: "", vcode_str: "" }).toString(),
      });
      const json = parseJson(verify.body) || {};
      const errno = Number(json.errno);
      if (errno === 0) break;
      // 实测正确提取码偶发误报一次 -12: 短延迟重试定性,防把活分享标成"提取码不正确"
      if ((errno === -12 || errno === -9) && attempt < 3) {
        await new Promise((resolve) => setTimeout(resolve, 800));
        continue;
      }
      const msg = String(json.show_msg || json.err_msg || json.errmsg || "");
      // 实测密码错误/缺失是 -12(err_msg 为空),字典另记 -9 访问密码错误——两者都按精确错误处理
      if (errno === -12 || errno === -9) {
        throw new Error(pwd
          ? "百度分享提取码不正确（非失效,修正提取码后重试）"
          : "百度分享需要提取码(链接未携带,补充?pwd=后重试)");
      }
      if (errno === -7) throw new Error("百度分享已删除或已取消");
      if (errno === -8) throw new Error("百度分享已过期");
      throw new Error(`百度分享校验失败(errno=${errno}${msg ? `, ${msg}` : ""})`);
    }
    absorb(verify.headers && (verify.headers["set-cookie"] || verify.headers["Set-Cookie"]));
    // 偶发 verify 只在响应体发 randsk 不下发 BDCLND Cookie: 兜底补进罐,否则分享页 302 进 /share/init 拿不到 yunData
    const verifyJson = parseJson(verify.body) || {};
    if (verifyJson.randsk && !jar.has("BDCLND")) jar.set("BDCLND", String(verifyJson.randsk));
  }
  const page = await baiduHttp(pageURL, {
    headers: {
      "User-Agent": SITE_UA,
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
      "Accept-Language": "zh-CN,zh;q=0.9",
      Referer: "https://pan.baidu.com/",
      Cookie: cookieHeader(),
    },
  });
  if (page.statusCode < 200 || page.statusCode >= 300) throw new Error(`百度分享页面获取失败(HTTP ${page.statusCode})`);
  absorb(page.headers && (page.headers["set-cookie"] || page.headers["Set-Cookie"]));
  const cookie = cookieHeader();
  const sekey = jar.has("BDCLND") ? decodeURIComponent(jar.get("BDCLND") || "") : "";
  const bodyText = String(page.body || "");
  if (/请输入提取码/.test(bodyText)) throw new Error("百度分享页面校验未通过(仍需提取码)");
  const meta = baiduParseShareMeta(bodyText);
  if (!meta) throw new Error("百度分享页面解析失败(缺 shareid/share_uk)");
  return { cookie, sekey, uk: meta.uk, shareid: meta.shareid, referer: pageURL, surl };
}

// 目录项 -> /share/list 的 dir 路径: 返回里已是 sharelink 形式就直接用;
// 根层返回的是 owner 形式路径,按页面嵌入 file_list 同款拼 /sharelink{uk}-{fs_id}/{name}(实测可列)
function baiduChildPath(session, item, parentPath) {
  const raw = String((item && item.path) || "");
  if (/^\/sharelink\d*-\d+(\/|$)/.test(raw)) return raw;
  const name = String((item && item.server_filename) || "");
  if (!name) return "";
  if (parentPath) return `${parentPath}/${name}`;
  return `/sharelink${session.uk}-${item.fs_id}/${name}`;
}

async function baiduAnonListPage(session, dirPath, page) {
  const query = new URLSearchParams({
    shareid: session.shareid,
    uk: session.uk,
    app_id: "250528",
    channel: "channellist",
    clienttype: "0",
    order: "time",
    desc: "1",
    showempty: "0",
    view_mode: "1",
    web: "1",
    page: String(page),
    num: String(BAIDU_SHARE_PAGE_SIZE),
  });
  if (session.sekey) {
    query.set("is_from_web", "1");
    query.set("sekey", session.sekey);
  }
  if (dirPath) query.set("dir", String(dirPath));
  else query.set("root", "1");
  const response = await baiduHttp(`https://pan.baidu.com/share/list?${query.toString()}`, {
    headers: {
      "User-Agent": SITE_UA,
      Referer: session.referer,
      Cookie: session.cookie || "",
      Accept: "application/json, text/plain, */*",
    },
  });
  const json = parseJson(response.body) || {};
  const errno = Number(json.errno);
  if (errno !== 0) {
    if (errno === -7) throw new Error("百度分享已删除或已取消");
    if (errno === -8) throw new Error("百度分享已过期");
    if (errno === -11) throw new Error("百度分享校验票据失效(errno=-11)");
    // -3 是子目录路径没命中(目录未列出,文件还在):不带服务端原文,防"文件不存在"字样被误判成死分享
    if (errno === -3) throw new Error("百度分享子目录未命中(errno=-3,路径可能已调整)");
    const msg = String(json.show_msg || json.errmsg || "");
    throw new Error(`百度分享列表失败(errno=${errno}${msg ? `, ${msg}` : ""})`);
  }
  return Array.isArray(json.list) ? json.list : [];
}

function baiduToVideoFile(item) {
  const fid = String((item && item.fs_id) || "");
  const name = String((item && item.server_filename) || "");
  if (!fid || !name) return null;
  return { fid, name, file_name: name, size: Number((item && item.size) || 0), dir: false };
}

// 深度优先遍历(照 pan123DirectVideoFiles 同款护栏: 深度4/访问2000/视频400/单目录30页)
async function baiduDirectVideoFiles(shareURL) {
  const info = parseBaiduShare(shareURL);
  if (!info) throw new Error("无法识别的百度分享链接");
  const session = await baiduSessionCached(shareURL, info, false);
  const videos = [];
  let visited = 0;
  let anyItem = false;
  const walk = async (dirPath, depth) => {
    if (depth > BAIDU_SHARE_MAX_DEPTH || visited >= BAIDU_SHARE_MAX_VISITED || videos.length >= BAIDU_SHARE_MAX_VIDEOS) return;
    for (let page = 1; page <= BAIDU_SHARE_MAX_PAGES; page++) {
      const items = await baiduAnonListPage(session, dirPath, page);
      visited += items.length;
      if (items.length) anyItem = true;
      for (const item of items) {
        if (!item) continue;
        const isDir = item.isdir === 1 || item.isdir === "1" || item.isdir === true;
        if (isDir) {
          const childPath = baiduChildPath(session, item, dirPath);
          if (childPath) await walk(childPath, depth + 1);
          continue;
        }
        const file = baiduToVideoFile(item);
        if (file && isVideoFileName(file.name)) videos.push(file);
      }
      if (items.length < BAIDU_SHARE_PAGE_SIZE) break;
    }
  };
  await walk(null, 0);
  if (!videos.length && !anyItem) throw new Error("该百度分享内容已被清空（分享记录有效但文件为空）");
  log("info", `觅盘 百度直连枚举成功: ${videos.length} 个视频`);
  return videos;
}

// 会话短缓存: verify+分享页两连击在详情/播放间复用;force=true 绕过缓存强刷(票据过期 9019/-11 时用)
async function baiduSessionCached(shareURL, info, force) {
  const key = `mp:bdsess:${shareURL}`;
  if (!force) {
    try {
      const cached = memGet(key);
      if (cached && typeof cached === "object" && cached.shareid && cached.uk) return cached;
    } catch (error) {
      // 缓存读失败按未命中处理
    }
  }
  const session = await baiduAnonSession(info);
  try {
    memSet(key, session, BAIDU_SESSION_TTL);
  } catch (error) {
    // 缓存写失败不影响本次使用
  }
  return session;
}

// 页面同款取播放签名: GET /share/tplconfig(必须带 X-Requested-With,否则 9019 need verify)拿 sign/timestamp
async function baiduStreamSigned(session) {
  const response = await baiduHttp(
    `https://pan.baidu.com/share/tplconfig?surl=1${encodeURIComponent(session.surl || "")}&shareid=${encodeURIComponent(session.shareid || "")}&uk=${encodeURIComponent(session.uk || "")}&fields=sign,timestamp&view_mode=1`,
    {
      headers: {
        "User-Agent": SITE_UA,
        Referer: session.referer,
        Origin: "https://pan.baidu.com",
        Cookie: session.cookie || "",
        "X-Requested-With": "XMLHttpRequest",
        Accept: "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
      },
    }
  );
  const json = parseJson(response.body) || {};
  const errno = Number(json.errno);
  if (errno !== 0) throw new Error(errno === 9019 ? "百度签名校验需要重新验证(errno=9019)" : `百度取播放签名失败(errno=${errno})`);
  const sign = String((json.data && json.data.sign) || "");
  const ts = Number((json.data && json.data.timestamp) || 0);
  if (!sign || !ts) throw new Error("百度播放签名缺失(sign/timestamp 为空)");
  return { sign, ts };
}

async function baiduSignCached(shareURL, session, force) {
  const key = `mp:bdsign:${shareURL}`;
  if (!force) {
    try {
      const cached = memGet(key);
      if (cached && typeof cached === "object" && cached.sign && cached.ts) return cached;
    } catch (error) {
      // 缓存读失败按未命中处理
    }
  }
  const signed = await baiduStreamSigned(session);
  try {
    memSet(key, signed, BAIDU_SIGN_TTL);
  } catch (error) {
    // 缓存写失败不影响本次使用
  }
  return signed;
}

// 百度匿名直连播放(页面视频插件同款): 会话 -> tplconfig 签名 -> /share/streaming 出 M3U8 播放列表。
// 不做文件路径查找(fid 直用);先小流量探活一次,接口拒绝(签名过期/风控)时抛瞬时错,由播放链路回退容器。
async function baiduStreamPlay(shareURL, fileId) {
  const info = parseBaiduShare(shareURL);
  if (!info) throw new Error("无法识别的百度分享链接");
  const fid = String(fileId || "");
  if (!fid || /^undefined$|^null$/i.test(fid)) throw new Error("百度播放缺少文件ID");
  let session = await baiduSessionCached(shareURL, info, false);
  let signed;
  try {
    signed = await baiduSignCached(shareURL, session, false);
  } catch (error) {
    // 签名被拒 = 会话大概率过期(9019/-11): 会话+签名一起强刷重试一次
    const message = errorText(error);
    if (!/9019|errno=-11|重新验证/.test(message)) throw error;
    session = await baiduSessionCached(shareURL, info, true);
    signed = await baiduSignCached(shareURL, session, true);
  }
  const streamURL = `https://pan.baidu.com/share/streaming?channel=chunlei&uk=${encodeURIComponent(session.uk)}&fid=${encodeURIComponent(fid)}&sign=${encodeURIComponent(signed.sign)}&timestamp=${encodeURIComponent(signed.ts)}&shareid=${encodeURIComponent(session.shareid)}&type=${BAIDU_STREAM_TYPE}&vip=0&check_blue=1&isplayer=1`;
  const streamHeaders = {
    "User-Agent": SITE_UA,
    Referer: session.referer,
    Cookie: session.cookie || "",
    Accept: "*/*",
  };
  const probe = await baiduHttp(streamURL, { headers: Object.assign({}, streamHeaders, { Range: "bytes=0-1023" }) });
  const body = String((probe && probe.body) || "");
  if (!probe || probe.statusCode < 200 || probe.statusCode >= 300) throw new Error(`百度播放流接口失败(HTTP ${probe && probe.statusCode})`);
  if (/^\s*\x7B/.test(body)) {
    const json = parseJson(body) || {};
    throw new Error(`百度播放流接口拒绝(errno=${json.errno || "?"})`);
  }
  if (!/^#EXTM3U/.test(body.trim())) throw new Error("百度播放流返回异常(非M3U8)");
  log("info", `觅盘 百度流媒体取链成功(fid=${fid}, ${BAIDU_STREAM_TYPE})`);
  return { parse: 0, jx: 0, url: streamURL, header: { "User-Agent": SITE_UA, Cookie: session.cookie || "", Referer: session.referer } };
}


// pbaidu: 选集自包含编码(照 puc: 惯例): u=分享链接 f=fs_id n=原名
function encodeBaiduEpisode(shareURL, file) {
  try {
    const payload = { u: String(shareURL || ""), f: String(file.fid || "") };
    if (file.name) payload.n = String(file.name);
    return "pbaidu:" + encodeBase64Url(JSON.stringify(payload));
  } catch (error) {
    return "";
  }
}

function decodeBaiduEpisode(id) {
  const raw = String(id || "");
  if (!raw.startsWith("pbaidu:")) return null;
  try {
    const data = JSON.parse(decodeBase64Url(raw.slice(7)));
    if (!data || !data.u || !data.f) return null;
    return { u: String(data.u), f: String(data.f), n: String(data.n || "") };
  } catch (error) {
    return null;
  }
}

async function baiduDirectEpisodes(shareURL) {
  const files = await baiduDirectVideoFiles(shareURL);
  return files
    .map((file) => {
      const id = encodeBaiduEpisode(shareURL, file);
      const displayName = (file.size > 0 ? `[${formatFileSize(file.size)}] ` : "") + file.name;
      return { id, name: safeEpisodeName(displayName) };
    })
    .filter((ep) => ep.id);
}

async function baiduDirectVod(shareURL) {
  const info = parseBaiduShare(shareURL);
  const episodes = await baiduDirectEpisodes(shareURL);
  if (!episodes.length) return null;
  log("info", `觅盘 百度直连枚举: ${episodes.length} 个视频 (${info ? info.surl : "?"})`);
  return {
    vod_play_from: "百度",
    vod_play_url: episodes.map((ep) => `${ep.name}$${ep.id}`).join("#"),
  };
}

async function baiduDirectPlay(encodedId) {
  const data = decodeBaiduEpisode(encodedId);
  if (!data) throw new Error("百度选集参数异常");
  return baiduStreamPlay(data.u, data.f);
}

// 容器选集 ID 兜底: 纯数字当 fs_id 直用;否则按分集名在直连枚举里匹配(单视频分享直接命中)
async function baiduDirectPlayByEpisode(shareURL, episodeId, nameHint) {
  const raw = String(episodeId || "");
  if (/^\d{6,}$/.test(raw)) return baiduStreamPlay(shareURL, raw);
  const files = await baiduDirectVideoFiles(shareURL);
  if (!files.length) throw new Error("百度直连未枚举到视频");
  const hint = String(nameHint || "")
    .trim()
    .replace(/^\[[^\]]+\]\s*/, "");
  const target = (hint && files.find((f) => f.name === hint)) || (files.length === 1 ? files[0] : null);
  if (!target) throw new Error("百度直连未按名称匹配到分集");
  return baiduStreamPlay(shareURL, target.fid);
}

function loadShareVod(shareURL) {
  // 123镜像域名兜底改写(缓存键也用改写后的链接,避免同分享两套缓存)
  shareURL = normalizePanShareURL(shareURL);
  const key = `mp:vod:${md5(shareURL)}`;
  return cachedValue(key, DETAIL_CACHE_EX, async () => {
    // UC分享优先匿名免转存枚举,不依赖后台会员 Cookie;失败再回退容器 drive
    if (isUCShareURL(shareURL)) {
      try {
        const direct = await ucDirectVod(shareURL);
        if (direct) return direct;
      } catch (error) {
        log("warn", `觅盘 UC直连枚举失败: ${errorText(error)}`);
      }
    }
    // 百度分享优先匿名直连枚举(容器百度"分享信息"偶发 -21 故障时 getVod 必挂);死分享/提取码直抛,瞬时回退容器
    if (isBaiduShareURL(shareURL)) {
      try {
        const direct = await baiduDirectVod(shareURL);
        if (direct) return direct;
      } catch (error) {
        const message = errorText(error);
        if (isPreciseShareError(message)) throw error;
        // 会话票据过期(-11): 作废会话缓存,下次换新会话
        if (/校验票据失效|errno=-11/.test(message)) memSet(`mp:bdsess:${shareURL}`, "", 5);
        log("warn", `觅盘 百度直连枚举失败,回退容器: ${truncateText(message, 300)}`);
      }
    }
    const drive = findDrive("", shareURL);
    let vod = null;
    if (drive) {
      try {
        const got = await drive.getVod(shareURL);
        if (got && typeof got === "object") vod = got;
      } catch (error) {
        log("warn", `觅盘 解析分享失败: ${error.message}`);
      }
      if (!vod && hasExtractCode(shareURL)) {
        const bare = stripExtractCode(shareURL);
        try {
          const got = await drive.getVod(bare);
          if (got && typeof got === "object") vod = got;
        } catch (error) {
          log("warn", `觅盘 去除提取码重试失败: ${error.message}`);
        }
      }
      // 123直连枚举兜底: 容器123 drive 没给出分集时走123官方分享列表API(匿名可读)
      if (isPan123URL(shareURL) && (!vod || !vod.vod_play_url)) {
        try {
          const direct = await pan123DirectVod(shareURL);
          if (direct) return direct;
        } catch (error) {
          const msg = error.message;
          if (isPreciseShareError(msg)) throw error;
          log("warn", `觅盘 123直连枚举兜底失败: ${msg}`);
        }
      }
      if (vod) return vod;
      log("warn", `觅盘 未拿到分享内容: ${truncateText(shareURL, 80)}`);
      return null;
    }
    // 未配置对应网盘时,123直连仍可匿名枚举
    if (isPan123URL(shareURL)) {
      try {
        const direct = await pan123DirectVod(shareURL);
        if (direct) return direct;
      } catch (error) {
        const msg = error.message;
        if (isPreciseShareError(msg)) throw error;
        log("warn", `觅盘 123直连枚举兜底失败: ${msg}`);
      }
    }
    log("warn", `觅盘 未找到匹配的网盘: ${truncateText(shareURL, 80)}`);
    return null;
  });
}

async function getHotWords() {
  const key = "mp:hotwords";
  const mem = memGet(key);
  if (Array.isArray(mem) && mem.length) return mem;
  const remote = await redisGet(key);
  if (Array.isArray(remote) && remote.length) {
    memSet(key, remote, HOT_CACHE_EX);
    return remote;
  }
  return once(key, async () => {
    let words = [];
    try {
      const response = await httpRequest(`${webSite()}/topics/`, {
        method: "GET",
        headers: {
          "User-Agent": SITE_UA,
          Accept: "text/html,application/xhtml+xml,*/*",
          Referer: `${webSite()}/`,
        },
        timeout: Math.min(REQUEST_TIMEOUT, 10000),
      });
      if (response.statusCode === 200) {
        const html = String(response.body || "");
        const block = /<div class="links">([\s\S]*?)<\/div>/.exec(html);
        const scope = block ? block[1] : html;
        const reg = /<a[^>]+href="\/s\/[^"]+?\.html"[^>]*>([^<]+)<\/a>/g;
        let match = null;
        while ((match = reg.exec(scope)) !== null) {
          const word = String(match[1] || "").trim();
          if (word && !words.includes(word)) words.push(word);
          if (words.length >= HOT_LIMIT) break;
        }
      }
    } catch (error) {
      log("warn", `觅盘 获取热词失败: ${error.message}`);
    }
    if (!words.length) words = HOT_WORDS_FALLBACK.slice(0, HOT_LIMIT);
    words = words.slice(0, HOT_LIMIT);
    memSet(key, words, HOT_CACHE_EX);
    await redisSet(key, words, HOT_CACHE_EX);
    return words;
  });
}

function normalizeDriveType(raw) {
  const value = String(raw || "").toLowerCase().trim();
  if (!value) return "others";
  if (value.includes("baidu") || value.includes("百度")) return "baidu";
  if (value.includes("aliyun") || value.includes("alipan") || value.includes("阿里")) return "aliyun";
  if (value.includes("quark") || value.includes("夸克")) return "quark";
  if (value.includes("tianyi") || value.includes("189") || value.includes("天翼")) return "tianyi";
  if (value.includes("115")) return "115";
  if (value.includes("xunlei") || value.includes("thunder") || value.includes("迅雷")) return "xunlei";
  if (value.includes("123") || value.includes("pan123")) return "123";
  if (value.includes("pikpak")) return "pikpak";
  if (value.includes("mobile") || value.includes("139") || value.includes("移动")) return "mobile";
  if (value.includes("guangya") || value.includes("光鸭")) return "guangya";
  if (value.includes("magnet") || value.includes("磁力")) return "magnet";
  if (value.includes("ed2k") || value.includes("电驴")) return "ed2k";
  if (value.includes("uc")) return "uc";
  return "others";
}

function panName(type) {
  const key = normalizeDriveType(type);
  return (PAN_META[key] || PAN_META.others).name;
}

function panPic(type) {
  const key = normalizeDriveType(type);
  return `${ICON_BASE}${ICON_FILES[key] || ICON_FILES.others}`;
}

function driveKeyToType(key) {
  const value = String(key || "").toLowerCase().trim();
  if (!value) return "";
  for (const [type, hints] of Object.entries(TYPE_HINTS)) {
    for (const hint of hints) if (value === hint) return type;
  }
  for (const [type, hints] of Object.entries(TYPE_HINTS)) {
    for (const hint of hints) if (hint.length >= 3 && value.includes(hint)) return type;
  }
  return "";
}

function hostOfUrl(value) {
  try {
    return new URL(String(value || "")).hostname.toLowerCase();
  } catch (error) {
    return "";
  }
}

function buildTypeDriveMap(items) {
  const drives = store.drives || [];
  const map = new Map();
  if (!drives.length) return map;
  const sample = new Map();
  for (const item of items || []) {
    if (!item || !item.t || !item.u) continue;
    if (!sample.has(item.t)) sample.set(item.t, []);
    const list = sample.get(item.t);
    if (list.length >= 5) continue;
    const host = hostOfUrl(item.u);
    if (list.some((entry) => entry.host === host)) continue;
    list.push({ host, url: item.u });
  }
  for (const [type, entries] of sample) {
    for (const entry of entries) {
      const hit = drives.find((drive) => {
        try {
          return !!drive.matchShare(entry.url);
        } catch (error) {
          return false;
        }
      });
      if (hit) {
        map.set(type, hit);
        break;
      }
    }
  }
  for (const type of sample.keys()) {
    if (map.has(type)) continue;
    const hit = drives.find((drive) => driveKeyToType(drive.key) === type);
    if (hit) map.set(type, hit);
  }
  return map;
}

function buildGroups(items) {
  const drives = store.drives || [];
  if (!drives.length) return [];
  const typeDrive = buildTypeDriveMap(items);
  const fallback = typeDrive.size === 0;
  const groups = new Map();
  for (const item of items || []) {
    if (!item || !item.t) continue;
    let key;
    let drive = null;
    if (fallback) {
      key = `t:${item.t}`;
    } else {
      drive = typeDrive.get(item.t);
      if (!drive) continue;
      key = String(drive.key);
    }
    let group = groups.get(key);
    if (!group) {
      group = { key, drive, types: new Set(), rows: [] };
      groups.set(key, group);
    }
    group.types.add(item.t);
    group.rows.push(item);
  }
  const driveRank = (group) => {
    if (!group.drive) return Number.MAX_SAFE_INTEGER;
    const index = drives.indexOf(group.drive);
    return index < 0 ? Number.MAX_SAFE_INTEGER : index;
  };
  const orderRank = (group) => {
    let best = 999;
    for (const type of group.types) {
      const index = DRIVE_ORDER.indexOf(type);
      if (index >= 0 && index < best) best = index;
    }
    return best;
  };
  return [...groups.values()].sort((a, b) => orderRank(a) - orderRank(b) || driveRank(a) - driveRank(b));
}

function groupRepresentative(group) {
  if (group.drive && group.drive.key) {
    const type = driveKeyToType(group.drive.key);
    if (type) return type;
  }
  let best = "";
  let bestRank = 999;
  for (const type of group.types) {
    const index = DRIVE_ORDER.indexOf(type);
    const rank = index < 0 ? 999 : index;
    if (rank < bestRank) {
      bestRank = rank;
      best = type;
    }
  }
  return best || [...group.types][0] || "others";
}

function groupSourceName(group) {
  if (group.drive && group.drive.key) return String(group.drive.key);
  return panName(groupRepresentative(group));
}

function groupTypeFilter(data) {
  if (Array.isArray(data.ts) && data.ts.length) return data.ts.map((type) => String(type)).filter(Boolean);
  const type = String(data.t || "");
  return type ? [type] : null;
}


function findDrive(flag, shareURL) {
  const drives = store.drives || [];
  const text = String(flag || "");
  if (text) {
    const hit = drives.find((drive) => text.toLowerCase().startsWith(String(drive.key || "").toLowerCase()));
    if (hit) return hit;
  }
  const url = String(shareURL || "");
  if (url) {
    for (const drive of drives) {
      try {
        if (drive.matchShare(url)) return drive;
      } catch (error) {
      }
    }
  }
  return null;
}

function hasExtractCode(url) {
  return /([?&](pwd|password|code|pass|passcode)=)/i.test(String(url || ""));
}

function withExtractCode(url, password) {
  const raw = String(url || "");
  const code = String(password || "").trim();
  if (!raw || !code) return raw;
  if (hasExtractCode(raw)) return raw;
  const hash = raw.indexOf("#");
  const base = hash >= 0 ? raw.slice(0, hash) : raw;
  const fragment = hash >= 0 ? raw.slice(hash) : "";
  const sep = base.includes("?") ? "&" : "?";
  let host = "";
  try {
    host = new URL(raw).hostname.toLowerCase();
  } catch (error) {
    host = "";
  }
  let param = "pwd";
  if (host.includes("115")) param = "password";
  else if (host.includes("189")) param = "code";
  return `${base}${sep}${param}=${encodeURIComponent(code)}${fragment}`;
}

function stripExtractCode(url) {
  const raw = String(url || "");
  if (!raw) return raw;
  try {
    const parsed = new URL(raw);
    ["pwd", "password", "code", "pass", "passcode"].forEach((name) => parsed.searchParams.delete(name));
    return parsed.toString();
  } catch (error) {
    return raw
      .replace(/([?&])(pwd|password|code|pass|passcode)=[^&#]*/gi, "$1")
      .replace(/[?&]$/, "");
  }
}

function isMagnetUrl(value) {
  return /^(magnet|ed2k):/i.test(String(value || "").trim());
}

function isShareUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

function extractMagnet(value) {
  const match = /magnet:\?[^\s"'<>]+/i.exec(String(value || "").replace(/&amp;/g, "&"));
  if (!match) return "";
  return match[0].replace(/[),.;]+$/, "");
}

function formatDateShort(value) {
  const text = String(value || "").trim();
  if (!text || text.startsWith("0001")) return "";
  const time = Date.parse(text);
  if (!Number.isFinite(time)) return text.slice(0, 10);
  const date = new Date(time);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const year = String(date.getFullYear()).slice(-2);
  return `${month}${day}${year}`;
}

function qualityScore(name) {
  const upper = String(name || "").toUpperCase();
  let score = 0;
  let count = 0;
  for (let i = 0; i < QUALITY_KEYWORDS.length; i++) {
    if (upper.includes(QUALITY_KEYWORDS[i].toUpperCase())) {
      score += QUALITY_KEYWORDS.length - i;
      count++;
    }
  }
  return score + count;
}

function countKeyword(name, list) {
  const upper = String(name || "").toUpperCase();
  let count = 0;
  for (const word of list) {
    if (upper.includes(String(word).toUpperCase())) count++;
  }
  return count;
}

function sortGroupItems(items) {
  return [...items].sort((a, b) => {
    const qualityA = qualityScore(a.n);
    const qualityB = qualityScore(b.n);
    if (qualityA !== qualityB) return qualityB - qualityA;
    const completeA = countKeyword(a.n, COMPLETED_KEYWORDS);
    const completeB = countKeyword(b.n, COMPLETED_KEYWORDS);
    if (completeA !== completeB) return completeB - completeA;
    const hitA = countKeyword(a.n, QUALITY_KEYWORDS);
    const hitB = countKeyword(b.n, QUALITY_KEYWORDS);
    if (hitA !== hitB) return hitB - hitA;
    return parseTime(b.d) - parseTime(a.d);
  });
}

function stateLabel(value) {
  const state = String(value || "").toLowerCase();
  if (state === "valid") return "有效";
  if (state === "invalid") return "已失效";
  return "";
}

function remarksOf(item) {
  const source = String((item && item.s) || "").replace(/^plugin:/i, "plg:");
  const date = formatDateShort((item && item.d) || "");
  const label = stateLabel(item && item.v);
  return [label, source, date].filter(Boolean).join(" | ");
}

function safeEpisodeName(value) {
  const text = String(value || "")
    .replace(/[$#\r\n\t]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return truncateText(text || "资源", 120);
}

function toHotVod(word) {
  return {
    vod_id: encodeId("k", { k: word }),
    vod_name: word,
    vod_pic: panPic("others"),
    vod_remarks: "热搜",
    vod_tag: "folder",
  };
}

function toGroupCard(group, keyword) {
  const type = groupRepresentative(group);
  return {
    vod_id: encodeId("g", { k: keyword, t: type, ts: [...group.types] }),
    vod_name: panName(type),
    vod_pic: panPic(type),
    vod_remarks: `${group.rows.length}条结果`,
    vod_tag: "folder",
    pan: groupSourceName(group),
  };
}

function toResourceVod(item, keyword) {
  return {
    vod_id: encodeId("r", { u: item.u, n: item.n, p: item.p, t: item.t, d: item.d, s: item.s, k: keyword }),
    vod_name: item.n || item.u,
    vod_pic: panPic(item.t),
    vod_remarks: remarksOf(item),
    time: parseTime(item.d),
    pan: item.t,
  };
}

function withShareLink(content, link) {
  if (!SHOW_SHARE_URL) return String(content || "");
  const url = String(link || "").trim();
  if (!url) return String(content || "");
  const text = String(content || "").trim();
  if (!text) return `分享链接: ${url}`;
  if (/^分享链接\s*[:：]/.test(text)) {
    const rest = text.replace(/^分享链接\s*[:：]\s*/, "");
    const pipe = rest.indexOf("|");
    const desc = pipe >= 0 ? rest.slice(pipe + 1).trim() : "";
    return desc ? `分享链接: ${url} | ${desc}` : `分享链接: ${url}`;
  }
  if (text.includes(url)) return text;
  return `分享链接: ${url} | ${text}`;
}

function placeholderVod(rawId, data, remarks, content) {
  return {
    vod_id: rawId,
    vod_name: String(data.n || "") || panName(data.t),
    vod_pic: panPic(data.t),
    type_name: panName(data.t),
    vod_remarks: remarks,
    vod_content: content,
    vod_play_from: "提示",
    vod_play_url: `暂无资源$${encodeId("e", {})}`,
  };
}

async function buildFailedShareVod(rawId, data, shareURL, rawName, task, loadErr) {
  let note = "未能解析该分享, 链接可能已失效";
  if (loadErr) {
    const msg = String(loadErr.message || loadErr);
    if (/百度/.test(msg)) note = msg; // 百度直连原话已自带网盘前缀,别落进 123 分支被标成"该 123 分享"
    else if (/该 123 分享内容已被清空/.test(msg)) note = "该 123 分享内容已被清空（分享记录有效但文件为空）";
    else if (/此分享不存在|分享不存在|好友已取消(了)?分享|分享已(被)?(取消|失效|删除|过期)|已过期|已被删除|链接不存在|资源不存在|文件不存在|分享链接无效|ShareKey长度异常/.test(msg)) note = "该 123 分享已失效";
    else if (/提取码不正确|提取码错误|密码错误|密码不正确/.test(msg)) note = "123 提取码不正确（请修正提取码后重试）";
    else note = `解析失败: ${msg}`;
  }
  const out = placeholderVod(rawId, data, "解析失败", note);
  const fallbackPic = String(out.vod_pic || "");
  out.vod_pic = "";
  out.vod_content = "";
  try {
    await loadMetaFor(out, rawName || scrapeNameOf(out, String(data.n || "")), task);
  } catch (error) {
    log("warn", `觅盘 TMDB 补全失败: ${errorText(error)}`);
  }
  if (!String(out.vod_pic || "").trim()) out.vod_pic = fallbackPic;
  out.vod_content = withShareLink(String(out.vod_content || "").trim() || note, shareURL);
  return out;
}

function firstEpisodeId(vod) {
  if (!vod) return "";
  const raw = String(vod.vod_play_url || "");
  if (!raw) return String(vod.vod_id || "");
  for (const source of raw.split("$$$")) {
    for (const episode of String(source).split("#")) {
      const text = String(episode || "").trim();
      if (!text) continue;
      const index = text.indexOf("$");
      const value = index >= 0 ? text.slice(index + 1) : text;
      if (value) return value;
    }
  }
  return "";
}

function normalizePlayResult(result) {
  if (typeof result === "string") return { parse: 0, jx: 0, url: result, header: {} };
  if (result && typeof result === "object") return result;
  return { parse: 0, jx: 0, url: "", header: {} };
}

function emptyPlayResult() {
  return { parse: 0, jx: 0, url: "", header: {} };
}

function errorText(error) {
  if (error === null || error === undefined) return "未知错误";
  if (typeof error === "string") return error;
  return String(error.message || error);
}

const PLACEHOLDER_CONTENT = new Set(["来自网盘", "网盘资源", "暂无简介", "无简介", "分享"]);

function stripSharePrefix(text) {
  const value = String(text || "").trim();
  if (!/^分享链接\s*[:：]/.test(value)) return value;
  const rest = value.replace(/^分享链接\s*[:：]\s*/, "");
  const pipe = rest.indexOf("|");
  return pipe >= 0 ? rest.slice(pipe + 1).trim() : "";
}

function contentHasRealText(text) {
  const value = String(text || "")
    .replace(/https?:\/\/\S+/gi, " ")
    .replace(/\bmagnet:\?\S+/gi, " ")
    .replace(/(?:分享链接|提取码|访问码|密码|链接|网盘|资源地址|分享地址)\s*[:：]?\s*/gi, " ")
    .replace(/[\s|,;，。、·\-—_./?=&#%]+/g, "");
  return value.length >= 6;
}

function isPlaceholderContent(vod) {
  const text = stripSharePrefix(vod && vod.vod_content);
  if (!text) return true;
  if (PLACEHOLDER_CONTENT.has(text)) return true;
  if (text === String((vod && vod.vod_name) || "").trim()) return true;
  if (!contentHasRealText(text)) return true;
  return false;
}

function tmdbImageOrigin() {
  if (TMDB_IMAGE_MIRROR) return TMDB_IMAGE_MIRROR;
  if (TMDB_MIRROR && tmdbMirrorOk) return TMDB_MIRROR;
  return "https://image.tmdb.org";
}

function tmdbImageUrl(posterPath, size) {
  const value = String(posterPath || "").trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  return `${tmdbImageOrigin()}/t/p/${size || TMDB_IMAGE_SIZE}${value.startsWith("/") ? value : `/${value}`}`;
}

function parseProxy(raw) {
  if (!raw) return undefined;
  try {
    const parsed = new URL(raw);
    if (!parsed.hostname) return undefined;
    const secure = parsed.protocol === "https:";
    const auth =
      parsed.username || parsed.password
        ? Buffer.from(`${decodeURIComponent(parsed.username || "")}:${decodeURIComponent(parsed.password || "")}`).toString(
            "base64"
          )
        : "";
    return {
      protocol: secure ? "https" : "http",
      host: parsed.hostname,
      port: Number(parsed.port) || (secure ? 443 : 80),
      auth,
      builtin: false,
    };
  } catch (error) {
    return undefined;
  }
}

let builtinProxyDownUntil = 0;
let builtinProxyFails = 0;

function tmdbProxyConfig() {
  const explicit =
    parseProxy(envStr("TMDB_PROXY")) ||
    parseProxy(envStr("HTTPS_PROXY")) ||
    parseProxy(envStr("https_proxy")) ||
    parseProxy(envStr("HTTP_PROXY")) ||
    parseProxy(envStr("http_proxy"));
  if (explicit) return explicit;
  if (!BUILTIN_TMDB_PROXY) return undefined;
  if (Date.now() < builtinProxyDownUntil) return undefined;
  const builtin = parseProxy(BUILTIN_TMDB_PROXY);
  if (!builtin) return undefined;
  builtin.builtin = true;
  return builtin;
}

function tmdbNoteProxyFailure(proxy) {
  if (!proxy || !proxy.builtin) return;
  builtinProxyFails += 1;
  if (builtinProxyFails >= BUILTIN_PROXY_FAILS) {
    builtinProxyDownUntil = Date.now() + BUILTIN_PROXY_DOWN * 1000;
    builtinProxyFails = 0;
  }
}

function tmdbNoteProxySuccess(proxy) {
  if (proxy && proxy.builtin) builtinProxyFails = 0;
}

let tmdbMirrorDownUntil = 0;
let tmdbDownUntil = 0;
let tmdbFailStreak = 0;
let tmdbMirrorOk = false;
let tmdbHintShown = false;

function tmdbMirrorReady() {
  return TMDB_MIRRORS.length > 0 && Date.now() >= tmdbMirrorDownUntil;
}

function tmdbParseChunked(buf) {
  let out = Buffer.alloc(0);
  let i = 0;
  while (i < buf.length) {
    const lineEnd = buf.indexOf("\r\n", i);
    if (lineEnd < 0) break;
    const size = parseInt(buf.slice(i, lineEnd).toString("ascii").split(";")[0], 16);
    if (!Number.isFinite(size) || size <= 0) break;
    out = Buffer.concat([out, buf.slice(lineEnd + 2, lineEnd + 2 + size)]);
    i = lineEnd + 2 + size + 2;
  }
  return out;
}

function tmdbParseResponse(raw) {
  const split = raw.indexOf("\r\n\r\n");
  if (split < 0) throw new Error("TMDB 响应格式异常");
  const head = raw.slice(0, split).toString("utf8");
  const lines = head.split("\r\n");
  const status = Number((lines[0] || "").split(" ")[1]) || 0;
  const headers = {};
  for (const line of lines.slice(1)) {
    const index = line.indexOf(":");
    if (index > 0) headers[line.slice(0, index).trim().toLowerCase()] = line.slice(index + 1).trim();
  }
  let body = raw.slice(split + 4);
  if (/chunked/i.test(headers["transfer-encoding"] || "")) {
    body = tmdbParseChunked(body);
  } else if (headers["content-length"]) {
    const size = parseInt(headers["content-length"], 10);
    if (Number.isFinite(size) && size >= 0) body = body.slice(0, size);
  }
  return { statusCode: status, body: body.toString("utf8") };
}

function tmdbSocketRequest(url, proxy, timeoutMs) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(value);
    };
    const timer = setTimeout(() => finish(new Error(`TMDB 请求超时(${timeoutMs}ms)`)), timeoutMs);
    let target;
    try {
      target = new URL(url);
    } catch (error) {
      return finish(new Error(`TMDB 地址无效: ${url}`));
    }
    const secure = target.protocol === "https:";
    const host = target.hostname;
    const port = Number(target.port) || (secure ? 443 : 80);
    const requestPath = `${target.pathname}${target.search}`;
    const hostHeader = port === (secure ? 443 : 80) ? host : `${host}:${port}`;
    const payload =
      `GET ${requestPath} HTTP/1.1\r\nHost: ${hostHeader}\r\nUser-Agent: ${SITE_UA}\r\n` +
      "Accept: application/json, text/plain, */*\r\nConnection: close\r\n\r\n";
    const readResponse = (socket) => {
      let stream = socket;
      const chunks = [];
      const collect = (data) => chunks.push(data);
      const done = () => {
        try {
          finish(null, tmdbParseResponse(Buffer.concat(chunks)));
        } catch (error) {
          finish(error);
        }
      };
      if (secure) {
        stream = tls.connect({ socket, servername: host });
        stream.on("error", (error) => finish(new Error(`TMDB TLS 失败: ${error.message}`)));
        stream.on("secureConnect", () => stream.write(payload));
      } else {
        stream.on("error", (error) => finish(new Error(`TMDB 连接失败: ${error.message}`)));
        stream.write(payload);
      }
      stream.on("data", collect);
      stream.on("end", done);
      stream.on("close", () => {
        if (chunks.length) done();
      });
    };
    if (proxy) {
      const proxySecure = proxy.protocol === "https:";
      const headers = proxy.auth ? { "Proxy-Authorization": `Basic ${proxy.auth}` } : {};
      const request = (proxySecure ? https : http).request({
        host: proxy.host,
        port: proxy.port,
        method: "CONNECT",
        path: `${host}:${port}`,
        headers,
        timeout: timeoutMs,
      });
      request.on("connect", (response, socket) => {
        if (response.statusCode !== 200) {
          socket.destroy();
          return finish(new Error(`代理 CONNECT 失败(${response.statusCode})`));
        }
        readResponse(socket);
      });
      request.on("timeout", () => {
        request.destroy();
        finish(new Error("代理连接超时"));
      });
      request.on("error", (error) => finish(new Error(`代理连接失败: ${error.message}`)));
      request.end();
      return;
    }
    const socket = net.connect({ host, port, timeout: timeoutMs });
    socket.on("timeout", () => {
      socket.destroy();
      finish(new Error("TMDB 直连超时"));
    });
    socket.on("error", (error) => finish(new Error(`TMDB 直连失败: ${error.message}`)));
    socket.once("connect", () => {
      socket.removeAllListeners("error");
      readResponse(socket);
    });
  });
}

async function tmdbAttempt(attempt) {
  const headers = { "User-Agent": SITE_UA, Accept: "application/json, text/plain, */*" };
  if (attempt.raw) return await tmdbSocketRequest(attempt.url, attempt.proxy, attempt.timeout);
  return await httpRequest(attempt.url, {
    method: "GET",
    headers,
    timeout: attempt.timeout,
    proxy: attempt.proxy,
  });
}

async function tmdbRaw(target) {
  const proxy = tmdbProxyConfig();
  const attempts = [];
  if (tmdbMirrorReady()) {
    for (const mirror of TMDB_MIRRORS) {
      attempts.push({
        host: "mirror",
        label: mirror,
        url: `${mirror}${target}`,
        timeout: TMDB_MIRROR_TIMEOUT,
        proxy: false,
        raw: false,
      });
    }
  }
  attempts.push({
    host: "official",
    label: `${TMDB_HOST}${proxy ? " 走代理" : ""}`,
    url: `https://${TMDB_HOST}${target}`,
    timeout: proxy ? TMDB_PROXY_TIMEOUT : TMDB_TIMEOUT,
    proxy: proxy || false,
    raw: Boolean(proxy),
  });
  if (proxy) {
    attempts.push({
      host: "official",
      label: `${TMDB_HOST} 直连`,
      url: `https://${TMDB_HOST}${target}`,
      timeout: TMDB_TIMEOUT,
      proxy: false,
      raw: false,
    });
  }
  const errors = [];
  for (const attempt of attempts) {
    try {
      const response = await tmdbAttempt(attempt);
      if (response.statusCode !== 200) throw new Error(`HTTP ${response.statusCode}`);
      const data = JSON.parse(response.body);
      if (attempt.raw && attempt.proxy) tmdbNoteProxySuccess(attempt.proxy);
      if (attempt.host === "mirror") {
        tmdbMirrorDownUntil = 0;
        tmdbMirrorOk = true;
      }
      return data && typeof data === "object" ? data : null;
    } catch (error) {
      errors.push(`${attempt.label}: ${errorText(error)}`);
      if (attempt.raw && attempt.proxy && !/^HTTP \d{3}/.test(errorText(error))) {
        tmdbNoteProxyFailure(attempt.proxy);
      }
      if (attempt.host === "mirror") {
        tmdbMirrorDownUntil = Date.now() + TMDB_MIRROR_DOWN * 1000;
        tmdbMirrorOk = false;
      }
    }
  }
  throw new Error(errors.join(" | ") || "TMDB 接口不可用");
}

async function tmdbJson(path, params, language) {
  if (!TMDB_API_KEY) return null;
  const query = new URLSearchParams({ api_key: TMDB_API_KEY, language: language || "zh-CN" });
  for (const [name, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") query.set(name, String(value));
  }
  const target = `/3${path}${path.includes("?") ? "&" : "?"}${query.toString()}`;
  return await tmdbRaw(target);
}

const TMDB_CUT_PATTERN =
  /(4k|8k|2160p|1080p|720p|480p|remex|remux|hdr10\+?|hdr|dolby|杜比视界|杜比|web-?dl|webrip|web-?rip|bluray|bdrip|brrip|hdtv|x26[45]|hevc|av1|原盘|内封|内嵌|外挂|硬字幕|软字幕|特效字幕|多国字幕|简英|中字|双语|国语|粤语|合集|全集|完结|全\d+集|\d+\s*集全|更新\s*至?\s*\d+集|连载\s*至?\s*\d+集|第\s*\d+\s*[集话]|全\d+部|\d+\s*部|dis[ck]|剧情|动作|科幻|冒险|犯罪|爱情|悬疑|喜剧|惊悚|恐怖|战争|历史|古装|武侠|仙侠|纪录|综艺|真人秀|动画片|电视剧|剧集|系列|收藏版|未删减|未删节|导演剪辑|amzn|hulu|itunes|truehd|atmos|lpcm|hires|60fps|50fps|hi-?fi|菁彩|蓝光|修复版)/i;
const TMDB_TV_PATTERN =
  /电视剧|剧集|动漫|综艺|纪录片|动画|TV|Series|第\s*\d+\s*[集话]|全\s*\d+\s*集|\d+\s*集全|更新\s*至?\s*\d+集|连载|S\d{1,2}\s*E\d{1,2}/i;
const TMDB_KEEP = /[^\u4e00-\u9fff\u3040-\u30ff\uf900-\ufaffA-Za-z0-9：:\-&'·\-. 【】\[\]（）()]+/g;
const TMDB_STRIP = /[^\u4e00-\u9fff\u3040-\u30ff\uf900-\ufaffA-Za-z0-9：:\-&'·\-. ]+/g;
const TMDB_INVISIBLE = /[\u200b-\u200f\u202a-\u202e\ufeff]/g;
const TMDB_PARENS = [/\uff08[^\uff09]*\uff09/g, /\([^\)]*\)/g];
const TMDB_SQUARE = /[[\]【】［］]/g;
const TMDB_LEAD_JUNK = /^(电影|剧集|电视剧|动漫|动画|系列)\s*[:：\-·]\s*/i;
const TMDB_LEAD_LABEL = /^(资源名称|资源名|片名|影片|名称|标题|剧名|影名|国产剧|国剧|港剧|台剧|美剧|日剧|韩剧|泰剧|国漫|日漫|连续剧|纪录片|综艺|资源|合集|全集|完结|高清|超清)\s*[:：\-·]?\s*/i;
const TMDB_LEAD_ASCII = /^(?:[A-Za-z0-9]{1,3}\s+)+/;

function tmdbQueryName(name) {
  const original = String(name || "").trim();
  if (!original) return "";
  let value = original.normalize("NFKC").replace(TMDB_INVISIBLE, " ").replace(TMDB_KEEP, " ");
  value = value.replace(/\s+/g, " ").trim();
  for (const pattern of TMDB_PARENS) value = value.replace(pattern, " ");
  value = value.replace(TMDB_SQUARE, " ");
  value = value.replace(/\s+/g, " ").trim();
  if (/[\u4e00-\u9fff]/.test(value)) value = value.replace(TMDB_LEAD_ASCII, "");
  value = value.replace(TMDB_LEAD_LABEL, "").replace(TMDB_LEAD_JUNK, " ");
  const cut = TMDB_CUT_PATTERN.exec(value);
  if (cut && cut.index >= 2) value = value.slice(0, cut.index);
  const year = /\b(?:19|20)\d{2}\b/.exec(value);
  if (year && year.index >= 2) value = value.slice(0, year.index);
  value = value.replace(TMDB_STRIP, " ");
  const tokens = value
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .filter((token, index, list) => token && list.indexOf(token) === index);
  value = tokens
    .join(" ")
    .replace(/^[\s·:：\-—_.]+/, "")
    .replace(/[\s·:：\-—_.]+$/, "")
    .trim();
  return value || original;
}

function tmdbQueryVariants(name) {
  const primary = tmdbQueryName(name);
  const list = [];
  const pushSub = (value) => {
    const text = String(value || "").trim();
    if (text.length >= 3 && !list.includes(text)) list.push(text);
  };
  if (primary) list.push(primary);
  pushSub(primary.split(/\s+/)[0]);
  const colon = primary.split(/[:：]/)[0];
  pushSub(colon);
  pushSub(colon.replace(/[\s\d]+$/, ""));
  pushSub(primary.split("·")[0]);
  return list;
}

function titleMatchScore(query, candidate) {
  const norm = (value) =>
    String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9一-龥]+/g, "");
  const q = norm(query);
  const t = norm(candidate);
  if (!q || !t) return 0;
  if (t === q) return 100;
  if (t.startsWith(q) || q.startsWith(t)) return 80;
  if (t.includes(q) || q.includes(t)) return 60;
  let i = 0;
  while (i < q.length && i < t.length && q[i] === t[i]) i++;
  return i >= 4 && i / Math.max(q.length, t.length) >= 0.5 ? 45 : 0;
}

async function searchTmdbQuery(query, isTv, year, deadline) {
  const preferred = isTv ? "tv" : "movie";
  const other = isTv ? "movie" : "tv";
  const plan = [
    { type: preferred, withYear: true },
    { type: preferred, withYear: false },
    { type: other, withYear: true },
    { type: other, withYear: false },
  ];
  let yearHit = null;
  let yearScore = 0;
  let anyHit = null;
  let anyScore = 0;
  let soft = null;
  const seen = new Set();
  for (const step of plan) {
    if (Date.now() > deadline) break;
    const hasYear = !!(step.withYear && year);
    const signature = `${step.type}|${hasYear ? year : ""}`;
    if (seen.has(signature)) continue;
    seen.add(signature);
    const params = { query };
    if (hasYear) {
      if (step.type === "movie") params.year = year;
      else params.first_air_date_year = year;
    }
    let results = [];
    try {
      const hit = await tmdbJson(`/search/${step.type}`, params, "zh-CN");
      results = hit && Array.isArray(hit.results) ? hit.results : [];
    } catch (error) {
      if (anyScore >= 45) break;
      throw error;
    }
    const single = results.length === 1 && results[0] ? results[0] : null;
    if (!soft && single) {
      const singleYear = String(single.release_date || single.first_air_date || "").slice(0, 4);
      const singleTitle = single.title || single.name || single.original_title || single.original_name || "";
      const evidence = titleMatchScore(query, singleTitle) > 0;
      const foreign = /[\u4e00-\u9fff]/.test(query) && !/[\u4e00-\u9fff]/.test(String(singleTitle));
      if ((!hasYear || singleYear === String(year)) && (evidence || foreign)) {
        soft = { type: step.type, id: single.id, title: singleTitle };
      }
    }
    for (const item of results.slice(0, 8)) {
      if (!item) continue;
      const display = item.title || item.name || item.original_title || item.original_name || "";
      const itemYear = String(item.release_date || item.first_air_date || "").slice(0, 4);
      const yearOk = hasYear && itemYear === String(year);
      let score = 0;
      const candidates = [item.title, item.name, item.original_title, item.original_name];
      for (const candidate of candidates) {
        const matched = titleMatchScore(query, candidate);
        if (matched > score) score = matched;
      }
      if (!score) continue;
      if (step.type === preferred) score += 10;
      if (yearOk) score += 3;
      if (score > anyScore) {
        anyScore = score;
        anyHit = { type: step.type, id: item.id, title: display, hasYear };
      }
      if (yearOk && score > yearScore) {
        yearScore = score;
        yearHit = { type: step.type, id: item.id, title: display, hasYear };
      }
    }
    if (yearScore >= 90 || (!year && anyScore >= 110) || Date.now() > deadline) break;
  }
  return { yearHit, yearScore, anyHit, anyScore, soft };
}

async function searchTmdb(name, isTv, year, deadline) {
  for (const query of tmdbQueryVariants(name)) {
    const found = await searchTmdbQuery(query, isTv, year, deadline);
    let winner = null;
    if (found && found.yearHit && found.yearScore >= 45) {
      winner = Object.assign({}, found.yearHit, { score: found.yearScore });
    } else if (found && found.anyHit && found.anyScore >= 45) {
      winner = Object.assign({}, found.anyHit, { score: found.anyScore });
    } else if (found && found.soft) {
      winner = Object.assign({}, found.soft, { score: 46 });
    }
    if (winner) return winner;
    if (Date.now() > deadline) break;
  }
  return null;
}

function applyTmdbPayload(vod, payload) {
  if (!vod || !payload || typeof payload !== "object") return vod;
  const missing = (value) => !String(value === null || value === undefined ? "" : value).trim();
  const uniq = (list) => list.filter((name, index) => name && list.indexOf(name) === index);
  const credits = payload.credits || {};
  if (missing(vod.vod_actor) && Array.isArray(credits.cast) && credits.cast.length) {
    vod.vod_actor = uniq(credits.cast.slice(0, 12).map((cast) => (cast && (cast.name || cast.character)) || ""))
      .slice(0, 8)
      .join("、");
  }
  if (missing(vod.vod_director) && Array.isArray(credits.crew) && credits.crew.length) {
    const directors = credits.crew.filter(
      (crew) => crew && (crew.job === "Director" || crew.department === "Directing" || crew.known_for_department === "Directing")
    );
    vod.vod_director = uniq(directors.slice(0, 6).map((crew) => crew.name || ""))
      .slice(0, 3)
      .join("、");
  }
  if (missing(vod.vod_content) && payload.overview) vod.vod_content = String(payload.overview);
  if (missing(vod.vod_year) && payload.releaseDate) vod.vod_year = String(payload.releaseDate).slice(0, 4);
  if (missing(vod.vod_pic) && payload.posterPath) vod.vod_pic = tmdbImageUrl(payload.posterPath);
  if (missing(vod.vod_douban_score) && payload.voteAverage) vod.vod_douban_score = Number(payload.voteAverage).toFixed(1);
  if (missing(vod.vod_area) && Array.isArray(payload.originCountry) && payload.originCountry.length) {
    vod.vod_area = String(payload.originCountry[0]);
  }
  return vod;
}

async function scrapeTmdb(rawName) {
  const query = tmdbQueryName(rawName);
  if (!query) return null;
  const deadline = Date.now() + TMDB_TOTAL;
  const yearMatch = /(?:19|20)\d{2}/.exec(String(rawName));
  const year = yearMatch ? yearMatch[0] : "";
  const hit = await searchTmdb(query, TMDB_TV_PATTERN.test(String(rawName)), year, deadline);
  if (!hit) return null;
  let detail = await tmdbJson(`/${hit.type}/${hit.id}`, { append_to_response: "credits" }, "zh-CN");
  if (!detail) return null;
  if (!String(detail.overview || "").trim() && Date.now() <= deadline) {
    const en = await tmdbJson(`/${hit.type}/${hit.id}`, { append_to_response: "credits" }, "en-US");
    if (en) detail = en;
  }
  const country = Array.isArray(detail.origin_country) && detail.origin_country.length
    ? detail.origin_country
    : Array.isArray(detail.production_countries)
      ? detail.production_countries.map((item) => (item && (item.name || item.iso_3166_1)) || "").filter(Boolean)
      : [];
  log("info", `觅盘 TMDB 补全: ${query} -> ${hit.title}[${hit.type}](匹配分${hit.score})`);
  return {
    miss: false,
    title: hit.title,
    overview: detail.overview || "",
    releaseDate: detail.release_date || detail.first_air_date || "",
    posterPath: detail.poster_path || "",
    originCountry: country,
    voteAverage: Number(detail.vote_average) || 0,
    credits: detail.credits || {},
  };
}

const tmdbInflight = new Map();

function tmdbCacheKey(name) {
  const query = tmdbQueryName(name);
  const yearMatch = /(?:19|20)\d{2}/.exec(String(name));
  const year = yearMatch ? yearMatch[0] : "";
  const isTv = TMDB_TV_PATTERN.test(String(name));
  return `mp:tmdb:${md5(`${query}|${year}|${isTv ? "tv" : "movie"}`)}`;
}

async function loadTmdbPayload(name) {
  const key = tmdbCacheKey(name);
  const mem = memGet(key);
  if (mem !== undefined && mem !== null) return mem;
  const remote = await redisGet(key);
  if (remote !== undefined && remote !== null) {
    memSet(key, remote, TMDB_HIT_EX);
    return remote;
  }
  if (Date.now() < tmdbDownUntil) return { miss: true };
  const running = tmdbInflight.get(key);
  if (running) return running;
  const task = (async () => {
    let value = { miss: true };
    try {
      const payload = await scrapeTmdb(name);
      if (payload) {
        value = payload;
        tmdbFailStreak = 0;
      } else {
        log("info", `觅盘 TMDB 未匹配: ${name}`);
      }
    } catch (error) {
      tmdbFailStreak++;
      log("warn", `觅盘 TMDB 补全失败: ${errorText(error)}`);
      if (tmdbFailStreak >= TMDB_FAIL_STREAK) {
        tmdbDownUntil = Date.now() + TMDB_DOWN * 1000;
        log("warn", `觅盘 TMDB 连续失败 ${tmdbFailStreak} 次,暂停 ${TMDB_DOWN} 秒`);
      }
      if (!tmdbHintShown) {
        tmdbHintShown = true;
        const proxy = tmdbProxyConfig();
        if (proxy) {
          log("warn", `觅盘 TMDB 走代理 ${proxy.host}:${proxy.port} 仍失败,请检查代理是否可用或更换 TMDB_MIRROR`);
        } else {
          log(
            "warn",
            "觅盘 TMDB 没有可用代理且镜像不可用,补全不会生效。可设环境变量 TMDB_PROXY=<代理>,或用 MIPAN_BUILTIN_PROXY=<代理> 更换内置代理"
          );
        }
      }
    }
    const ttl = value.miss ? TMDB_MISS_EX : TMDB_HIT_EX;
    memSet(key, value, ttl);
    try {
      await redisSet(key, value, ttl);
    } catch (error) {}
    return value;
  })().finally(() => {
    if (tmdbInflight.get(key) === task) tmdbInflight.delete(key);
  });
  tmdbInflight.set(key, task);
  return task;
}

function tmdbEnabled() {
  return store.tmdbEnabled === undefined ? TMDB_ENABLED : !!store.tmdbEnabled;
}

function tmdbResetState() {
  tmdbMirrorDownUntil = 0;
  tmdbDownUntil = 0;
  tmdbFailStreak = 0;
  tmdbMirrorOk = false;
  tmdbHintShown = false;
  builtinProxyDownUntil = 0;
  builtinProxyFails = 0;
}

const GENERIC_SCRAPE_NAMES = new Set([
  "网盘资源",
  "来自网盘",
  "分享",
  "资源",
  "未知",
  "暂无",
  "暂无资源",
  "磁力资源",
  "提示",
]);
const PAN_NAME_VALUES = new Set(
  Object.values(PAN_META)
    .map((item) => item && item.name)
    .filter(Boolean)
);

function genericName(value) {
  const text = String(value || "").trim();
  return !text || text.length < 2 || GENERIC_SCRAPE_NAMES.has(text) || PAN_NAME_VALUES.has(text);
}

function scrapeNameOf(vod, alt) {
  const primary = String((vod && vod.vod_name) || "").trim();
  const extra = String(alt || "").trim();
  if (!genericName(primary)) return primary;
  if (!genericName(extra)) return extra;
  return primary || extra;
}

async function loadMetaFor(vod, rawName, task) {
  if (!tmdbEnabled() || !TMDB_API_KEY || !vod || genericName(rawName)) return false;
  const missing = (value) => !String(value === null || value === undefined ? "" : value).trim();
  if (isPlaceholderContent(vod)) vod.vod_content = "";
  const needs =
    missing(vod.vod_actor) ||
    missing(vod.vod_director) ||
    missing(vod.vod_content) ||
    missing(vod.vod_year) ||
    missing(vod.vod_douban_score) ||
    missing(vod.vod_area) ||
    missing(vod.vod_pic);
  if (!needs) return false;
  const payload = task ? await task : await loadTmdbPayload(rawName);
  if (!payload || payload.miss) return false;
  applyTmdbPayload(vod, payload);
  return true;
}

async function init(server) {
  if (store.init) return;
  store.redis = (server && server.redis) || null;
  store.log = (server && server.log) || null;
  store.drives = (server && server.drives) || [];
  store.init = true;
  const cached = await redisGet("mp:token");
  if (cached && cached.t && Number(cached.e) > Date.now()) {
    apiToken = String(cached.t);
    tokenExpireAt = Number(cached.e);
  }
  tokenRestored = true;
  const proxy = tmdbProxyConfig();
  const proxyText = !proxy ? "无" : `${proxy.host}:${proxy.port}${proxy.builtin ? "(内置)" : ""}`;
  log(
    "info",
    `觅盘 v${VERSION} 已加载, 网盘数: ${store.drives.length}, TMDB: ${
      tmdbEnabled() ? "开" : "关"
    }, 代理: ${proxyText}, 镜像: ${TMDB_MIRROR || "无"}`
  );
}

async function hotListPage() {
  const words = await getHotWords();
  return { list: words.map(toHotVod), page: 1, pagecount: 1, total: words.length };
}

async function resourcePage(keyword, types, page) {
  const result = await loadItems(keyword);
  const filter = Array.isArray(types) ? types.map((type) => String(type)).filter(Boolean) : types ? [String(types)] : [];
  const allowAll = filter.length === 0;
  let list = (result.items || []).filter((item) => (allowAll || filter.includes(item.t)) && item.t);
  list = sortGroupItems(list);
  const total = list.length;
  const pagecount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const current = Math.max(1, Math.min(toPage(page), pagecount));
  const start = (current - 1) * PAGE_SIZE;
  const slice = list.slice(start, start + PAGE_SIZE);
  return {
    list: slice.map((item) => toResourceVod(item, keyword)),
    page: current,
    pagecount,
    total,
  };
}

async function buildGroupCards(keyword) {
  const result = await loadItems(keyword);
  return buildGroups(result.items || []).map((group) => toGroupCard(group, keyword));
}

async function buildShareVod(rawId, data) {
  const shareURL = withExtractCode(String(data.u || ""), data.p);
  if (!shareURL) return null;
  const magnet = extractMagnet(shareURL);
  if (magnet || isMagnetUrl(shareURL)) {
    const link = magnet || shareURL;
    return {
      vod_id: rawId,
      vod_name: String(data.n || "") || panName(data.t),
      vod_pic: panPic(data.t),
      type_name: panName(data.t),
      vod_remarks: "磁力资源",
      vod_content: withShareLink(String(data.n || "") || link, link),
      vod_play_from: "磁力",
      vod_play_url: `${safeEpisodeName(String(data.n || "") || "磁力资源")}$${link}`,
    };
  }
  const listName = String(data.n || "").trim();
  const prefName = genericName(listName) ? "" : listName;
  const canPrefetch = Boolean(prefName) && tmdbEnabled() && Boolean(TMDB_API_KEY);
  const task = canPrefetch ? loadTmdbPayload(prefName).catch(() => null) : null;
  let vod = null;
  let loadErr = null;
  try {
    vod = await loadShareVod(shareURL);
  } catch (error) {
    loadErr = error;
  }
  if (!vod) {
    return await buildFailedShareVod(rawId, data, shareURL, prefName, task, loadErr);
  }
  const out = Object.assign({}, vod);
  out.vod_id = rawId;
  if (prefName) out.vod_name = prefName;
  else if (!out.vod_name) out.vod_name = panName(data.t);
  const hadContent = String(out.vod_content || "");
  const hadPic = String(out.vod_pic || "");
  if (isPlaceholderContent(out)) out.vod_content = "";
  const rawName = prefName || (genericName(out.vod_name) ? "" : String(out.vod_name).trim());
  try {
    await loadMetaFor(out, rawName, prefName && rawName === prefName ? task : null);
  } catch (error) {
    log("warn", `觅盘 TMDB 补全失败: ${errorText(error)}`);
  }
  out.vod_content = withShareLink(
    String(out.vod_content || "").trim() || (contentHasRealText(hadContent) ? hadContent : ""),
    shareURL
  );
  if (!String(out.vod_pic || "").trim()) out.vod_pic = hadPic || panPic(data.t);
  return out;
}

async function buildExpandedVod(rawId, typ, data) {
  const keyword = String(data.k || "");
  const type = typ === "g" ? String(data.t || "") : "";
  const types = typ === "g" ? groupTypeFilter(data) : null;
  const result = await loadItems(keyword);
  const pool = (result.items || []).filter((item) => (types ? types.includes(item.t) : true));
  const groups = buildGroups(pool);
  const froms = [];
  const sources = [];
  let kept = 0;
  for (const group of groups) {
    const rows = sortGroupItems(group.rows).slice(0, MAX_ITEMS_PER_GROUP);
    if (!rows.length) continue;
    kept += rows.length;
    const episodes = rows.map((item) => {
      const playId = encodeId("r", { u: item.u, n: item.n, p: item.p, t: item.t, d: item.d, s: item.s, k: keyword });
      return `${safeEpisodeName(item.n || item.u)}$${playId}`;
    });
    froms.push(groupSourceName(group));
    sources.push(episodes.join("#"));
  }
  const vod = {
    vod_id: rawId,
    vod_name: type ? `${panName(type)} · ${keyword}` : keyword,
    vod_pic: panPic(type || "others"),
    type_name: panName(type || "others"),
    vod_remarks: `${kept}条结果`,
    vod_content: `觅盘网盘分组: ${type ? panName(type) : "全部网盘"}, 关键词 ${keyword}, 共 ${kept} 条分享`,
  };
  if (froms.length) {
    vod.vod_play_from = froms.join("$$$");
    vod.vod_play_url = sources.join("$$$");
  } else {
    vod.vod_play_from = "提示";
    vod.vod_play_url = `暂无资源$${encodeId("e", {})}`;
  }
  return vod;
}

async function buildDetail(rawId) {
  if (!rawId) return null;
  const [typ, data] = decodeId(rawId);
  if (typ === "g" || typ === "k") return buildExpandedVod(rawId, typ, data);
  if (typ === "e") return placeholderVod(rawId, data, "空资源", "该条目没有可播放内容");
  if (typ === "r" && data.u) return buildShareVod(rawId, data);
  const legacy = parseLegacyId(rawId);
  if (legacy) return buildExpandedVod(rawId, "g", { k: legacy.word, t: legacy.type });
  if (isMagnetUrl(rawId)) {
    return {
      vod_id: rawId,
      vod_name: rawId,
      vod_pic: panPic("magnet"),
      type_name: panName("magnet"),
      vod_remarks: "磁力资源",
      vod_content: rawId,
      vod_play_from: "磁力",
      vod_play_url: `磁力资源$${rawId}`,
    };
  }
  if (isShareUrl(rawId)) return buildShareVod(rawId, { u: rawId, n: "", p: "", t: "" });
  return null;
}

async function _home() {
  const words = await getHotWords();
  return { class: [{ type_id: "hot", type_name: "热门搜索" }], list: words.map(toHotVod) };
}

async function _category({ id, page }) {
  const key = String(id === undefined || id === null ? "" : id).trim();
  if (!key || key === "hot" || key === "1") return hotListPage();
  const [typ, data] = decodeId(key);
  if (typ === "g") return resourcePage(String(data.k || ""), groupTypeFilter(data), page);
  if (typ === "k") return resourcePage(String(data.k || ""), null, page);
  if (typ === "r" && data.k) return resourcePage(String(data.k), data.t ? [String(data.t)] : null, page);
  const legacy = parseLegacyId(key);
  if (legacy) return resourcePage(legacy.word, [legacy.type], page);
  return hotListPage();
}

async function _search({ page, quick, wd }) {
  const keyword = String(wd || "").trim();
  if (!keyword) return { list: [], page: 1, pagecount: 1, total: 0 };
  if (toPage(page) > 1) return { list: [], page: toPage(page), pagecount: 1, total: 0 };
  try {
    const list = await buildGroupCards(keyword);
    return { list, page: 1, pagecount: 1, total: list.length };
  } catch (error) {
    log("warn", `觅盘 搜索失败: ${errorText(error)}`);
    return { list: [], page: 1, pagecount: 1, total: 0 };
  }
}

async function _detail({ id }) {
  const ids = Array.isArray(id) ? id : [id];
  const list = [];
  for (const rawId of ids) {
    const cleaned = String(rawId || "").trim();
    if (!cleaned) continue;
    try {
      const vod = await buildDetail(cleaned);
      if (vod) list.push(vod);
    } catch (error) {
      // 单条失败出占位卡,不让整批详情被一次网络错误拖垮
      const [, data] = decodeId(cleaned);
      const obj = data && typeof data === "object" ? data : {};
      // 占位卡也带分享链接: r 型条目解 data.u 照成功路径拼提取码,裸分享链接直接回填
      const failLink = obj.u ? withExtractCode(String(obj.u), obj.p) : isShareUrl(cleaned) ? cleaned : "";
      list.push(placeholderVod(cleaned, obj, "获取失败,可重试", withShareLink(errorText(error), failLink)));
    }
  }
  return { list };
}

async function playShare(shareURL, flag) {
  // 123镜像域名兜底改写
  shareURL = normalizePanShareURL(shareURL);
  const magnet = extractMagnet(shareURL);
  if (magnet) return { parse: 0, jx: 0, url: magnet, header: {} };
  if (isMagnetUrl(shareURL)) return { parse: 0, jx: 0, url: shareURL, header: {} };
  let vod = await loadShareVod(shareURL);
  if (!vod) vod = await loadShareVod(shareURL); // 瞬时失败(网络/限流)不入缓存,立刻再试一次
  if (!vod && hasExtractCode(shareURL)) vod = await loadShareVod(stripExtractCode(shareURL));
  const episodeId = firstEpisodeId(vod);
  const firstName = String((vod && vod.vod_play_url) || "").split("#")[0].split("$")[0] || "";
  // 123直连选集(p123:前缀,自包含分享上下文):直接走123下载API,不经容器drive
  if (episodeId.startsWith("p123:")) {
    log("info", `觅盘 123直连播放: ${truncateText(episodeId, 80)}`);
    return normalizePlayResult(await pan123DirectPlay(episodeId));
  }
  // UC免转存选集(puc:前缀,自包含分享上下文):直接走UC分享下载接口,不经容器drive
  if (episodeId.startsWith("puc:")) {
    log("info", `觅盘 UC免转存播放: ${truncateText(episodeId, 80)}`);
    return normalizePlayResult(await ucDirectPlay(episodeId));
  }
  // 百度直连选集(pbaidu:前缀,自包含分享上下文):直接走页面同款流媒体链,不经容器drive
  if (episodeId.startsWith("pbaidu:")) {
    log("info", `觅盘 百度直连播放: ${truncateText(episodeId, 80)}`);
    return normalizePlayResult(await baiduDirectPlay(episodeId));
  }
  // 先判空再找网盘: 解析失败时给真实原因(网络/反爬/分享失效),别误报"未找到匹配的网盘"
  if (!episodeId) throw new Error(`分享解析失败,未获取到可播放内容: ${truncateText(shareURL, 80)}`);
  // 容器UC drive给出的选集ID也尝试匿名直连,失败再回退后台UC账号链路
  if (isUCShareURL(shareURL) && (ucParseFileId(episodeId) || /^[0-9a-f]{16,}$/i.test(episodeId))) {
    try {
      log("info", `觅盘 UC免转存播放: ${truncateText(episodeId, 80)}`);
      return normalizePlayResult(await ucDirectPlayByFile(shareURL, episodeId));
    } catch (error) {
      const message = errorText(error);
      log("warn", `觅盘 UC免转存播放失败: ${message}`);
      if (isDeadShareError(message)) throw error;
    }
  }
  // 容器百度 drive给出的选集ID也先试匿名直连(fs_id 直用/按分集名匹配),失败再回退容器链路
  if (isBaiduShareURL(shareURL)) {
    try {
      log("info", `觅盘 百度匿名播放: ${truncateText(episodeId, 80)}`);
      return normalizePlayResult(await baiduDirectPlayByEpisode(shareURL, episodeId, firstName));
    } catch (error) {
      const message = errorText(error);
      log("warn", `觅盘 百度匿名播放失败,回退容器: ${truncateText(message, 300)}`);
      if (isDeadShareError(message)) throw error;
    }
  }
  const drive = findDrive(flag, shareURL);
  if (!drive) throw new Error(`未找到匹配的网盘: ${truncateText(shareURL, 80)}`);
  log("info", `觅盘 播放: ${drive.key} -> ${truncateText(episodeId, 80)}`);
  return normalizePlayResult(await drive.play(episodeId, flag || drive.key));
}

async function _play({ flag, flags, id }) {
  const raw = String(id || "").trim();
  if (!raw) return emptyPlayResult();
  // 123直连选集:自包含分享上下文,直接走123下载API
  if (raw.startsWith("p123:")) return normalizePlayResult(await pan123DirectPlay(raw));
  // UC免转存选集:自包含分享上下文,直接走UC分享下载接口
  if (raw.startsWith("puc:")) return normalizePlayResult(await ucDirectPlay(raw));
  // 百度直连选集:自包含分享上下文,直接走页面同款流媒体链
  if (raw.startsWith("pbaidu:")) return normalizePlayResult(await baiduDirectPlay(raw));
  const [typ, data] = decodeId(raw);
  if (typ === "e") return emptyPlayResult();
  if (typ === "r" && data.u) return playShare(withExtractCode(String(data.u), data.p), flag);
  if (typ === "g" || typ === "k" || typ === "r") throw new Error("该条目不支持直接播放");
  if (isMagnetUrl(raw)) return { parse: 0, jx: 0, url: raw, header: {} };
  const embedded = extractMagnet(raw);
  if (embedded) return { parse: 0, jx: 0, url: embedded, header: {} };
  if (isShareUrl(raw)) return playShare(raw, flag);
  const drive = findDrive(flag, "");
  if (!drive) throw new Error(`未找到线路对应的网盘: ${flag}`);
  log("info", `觅盘 播放直传: ${drive.key}`);
  return normalizePlayResult(await drive.play(raw, flag || drive.key));
}

module.exports = async (app, opt) => {
  app.get(store.meta.api, async (req, reply) => {
    if (!store.init) await init(req.server);
    const { filter, t, ac, pg, ext, ids, flag, play, wd, quick } = req.query;
    if (play) {
      return await _play({ flag: flag || "", flags: [], id: play });
    } else if (wd) {
      return await _search({ page: toPage(pg), quick: quick || false, wd });
    } else if (!ac) {
      return await _home({ filter: filter ?? false });
    } else if (ac === "detail") {
      if (t) {
        return await _category({ id: t, page: toPage(pg), filter: !!filter, filters: {} });
      } else if (ids) {
        return await _detail({ id: String(ids).split(",").map((_id) => _id.trim()).filter(Boolean) });
      }
    }
    return req.query;
  });
  opt.sites.push(store.meta);
};
