// 不夜容器版 聚影
// 参考 聚影.js(聚影站点协议、接口、线路构建) 与 不夜觅盘.js(不夜容器接入方式)
// 适配不夜容器(vodspider/release)+ OK影视:站点影视库聚合、网盘分享分集、TMDB 补全
// 支持: 首页/分类(影视库·系列合集·类型筛选)/搜索/详情/播放;刮削用 TMDB 补全
// 不支持: 弹幕、播放记录、刮削引擎(这三项为 OmniBox SDK 专有能力)
// 依赖: axios;运行时由不夜容器注入 server.redis / server.log / server.drives

const VERSION = "1.1.15";

// ==================== 版本更新说明(重点) ====================

// 1.1.15  2026-10-25
//   - 全量验收修复: ①死分享判定补认"好友已取消(了)?分享"与"分享者用户封禁"(此前这两类永远当瞬时
//     错误重试/出可重试占位,点一次错一次); ②百度直连播放两处死/精确错误门补认"需要提取码"
//     (与详情侧口径对齐,缺 pwd 时直抛"补充?pwd=后重试"指引而不是回退容器出笼统错);
//   - ③123 分享下载接口遇提取码错误文案不再浪费一次账号重试(密码错账号也救不回);
//   - ④_detail 单条失败占位卡补拼分享链接(r 型条目解 share_link/target 等字段),失败可复制链接自取;
//   - ⑤删除零调用死代码 baiduDirectVod。
// 1.1.14  2026-10-24
//   - 新增 百度分享匿名直连(照不夜觅盘/omnibox 配方): 详情 loadShareEpisodes 百度直连优先枚举(pbaidu: 自包含
//     选集,带文件大小前缀),容器百度"分享信息"偶发 -21 故障时不再落"解析失败"占位;死分享/提取码直抛由外层
//     failKey 落占位卡;
//   - 播放 playShare/playEpisode 走 pbaidu: 直连,容器选集ID播放失败先试匿名直连(fs_id 直用/按分集名匹配,
//     失败回退刷新/容器);
//   - 稳健性: verify 误报 -12 重试、新旧分享页双形态解析(window.yunData/转义 JSON AB灰度)、randsk 兜底
//     BDCLND Cookie、会话600s/签名120s缓存(jy: 键)、/share/streaming 出 M3U8 探活后交宿主。
// 1.1.13  2026-10-23
//   - 123直连选集小标题显示文件大小(`[1.23G] 名`);容器123选集也回填直接枚举的尺寸(UC容器暂依赖容器端)。
// 1.1.12  2026-10-19
//   - 播放 r 型资源补三层恢复(资源有效却播不出来的隐形坑): ①存量分享链接播放失败 → 强制刷新票据
//     换新链接重试; ②新链接仍失败 → 按 rid+mid 重拉资源列表恢复; ③全程保留原始报错。
//     此前 r 型用陈旧 share_link 直接播,失败即止——而资源列表里明明有可用新链接。
// 1.1.11  2026-10-19
//   - 死分享判定剔除"无法识别的分享链接":那是识别缺口(如镜像域名变更)不是死分享,误判会把活分享
//     误记死并跳过本可成功的回退路径。覓盘 v1.6.13 根因修复(123685/123865 镜像漏认)同款防护。
// 1.1.10  2026-10-19
//   - 从网盘分组进详情时,若该分组过滤后一条资源都不剩(如百度分组里分享全被取消),
//     回退展示全量资源(其他网盘的活线路),不再被分组连坐成"无分集"。
//   - 注:分享被资源方取消("来晚啦，该分享已被取消")属数据死链,刷新资源链接也无法复活,
//     需资源库更新;同剧其他网盘资源会正常出分集。
// 1.1.9  2026-10-17
//   - 123分享列表:匿名形态被反爬以 HTML/网络方式拒绝(非业务code),或误报"分享不存在"时,
//     不再短路直接抛,必兜底试一次 legacy 原形态(升级前一直可用)——修复形态回归导致的
//     活分享被误判死、详情只出失效占位的问题。
// 1.1.8  2026-10-17
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
// 1.1.7  2026-10-16
//   - 123大版本适配(123已改版,旧匿名/无签名接口全部失效):
//     a) API 固定 yun.123pan.com(候选 www.123pan.cn/.com),每个请求带 signPath 签名(照 alist drivers/123_share);
//     b) 下载接口需登录(匿名必拒"您需要注册登录或付费后下载"):sign_in 自动登录换token(401自动重登),
//        账密不写死在 JS 里,只配环境变量 PAN_123_USERNAME + PAN_123_PASSWORD(或已有token配 PAN_123_TOKEN);
//        "不夜后台添加123账号"功能已随123改版失效,不用管它,以环境变量为准;
//     c) 下载请求体改小驼峰;分享方无提取流量(免费号为0)且文件在自己盘里时,自动改走本人网盘
//        /b/api/file/download_info(消耗普通下载流量,alist挂载同款),自己的分享可完整播放;
//     d) 分页改Page制、step2支持302/JSON双分支、shareKey按白名单截断(防源数据粘"提取码:xxx")。
// 1.1.6  2026-10-15
//   - 123云盘直连枚举兜底:123分享列表API(/b/api/share/get)匿名可读,当容器123 drive 枚举
//     失败/为空时直接走官方分享列表递归收集视频(实测新闻女王26集、伟大的长征13集枚举成功)。
//     支持新旧分享路径(/s/{token} 与 /123pan/{token},含 *.share.123pan.cn 子域);选集用
//     p123:前缀编码(免二次遍历),播放分流直连下载API。枚举顺序:容器drive优先,直连兜底。
//     注:123 download API 需登录/付费(5112),枚举解决"不出分集",播放对需登录分享会明确报错。
// 1.1.5  2026-10-15
//   - 修复123云盘从不出分集(根因):123分享用的是123684/123685/123865/123912等镜像域名,而容器/SDK的
//     123 drive 只认含 "123pan" 的域名,matchShare 一失败就从不枚举分集。新增 normalizePanShareURL
//     把这些镜像域名统一改写成 www.123pan.cn(同一套API)并补 password 参数,在 accessResource/
//     loadShareEpisodes/playEpisode/playShare 四个入口应用(与旧版聚影一致,已验证123pan.cn与镜像同页)。
// 1.1.4  2026-10-15  (按 big 代码质量评审结论做低风险清理)
//   - 筛选健壮性:ext base64 解码前还原空格为 +,查询串里的 + 被解码成空格不再导致筛选静默失效。
//   - 详情枚举预算 18s→12s(速度与分集完整折中);TMDB 维持直连不加环境代理(当前网络可达,避免代理白等)。
//   - 清理死代码/冗余:删未用 TMDB_HOST、未读的 resolveErrors 计数、buildTypeIds 重复算类型;
//     buildDetailByMid 双重 decodeId 合并;scrapeTmdb 不再请求未用的 images;_home 去掉空入参与 filter 解构。
//   - movieResourceCategoryPage 分组卡直接构建,不再先建完整资源卡再全部覆盖(取图优先级不变)。
// 1.1.3  2026-10-15
//   - 崩溃:分类传 t="1"/"0" 时 const 二次赋值 TypeError(分类必空),统一归到 all。
//   - 简介:影片剧情简介优先(资源短描述已放 vod_remarks),分享链接前缀幂等不再重复。
//   - 百度/天翼分集:提取码按网盘选参数(百度 pwd、天翼 code、115 password),插在 # 之前。
//   - 缓存:clearShareCache/invalidateResourceCache 改写 null、读取把 "" 当未命中,清缓存后能真正重试;
//     access/resources 端点不进 apiCall 300s 缓存(旧票据/死链),accessResource 支持 force 强制取新。
//   - 自愈:详情/资源条目"解析全失败刷新"改按 shareOk===0 判断(旧条件恒假);magnet lazy 补 rid/mid。
//   - 路由:ac=list/videolist/class 带 t 走分类,不再返回原始 query;quick 用 1/true 判定。
//   - 性能:apiBudget 按线路重置+access 受时间预算,多网盘影片每条线路都能出分集;
//     REQUEST_TIMEOUT 12s→18s、apiCall 重试 3→2 次且仅连接错误换站、播放超时 25s→12s。
//   - TMDB:默认代理改空(内网地址外部白等)、api.tmdb.org 优先、负缓存存哨兵生效、搜索排除 person。
//   - 筛选:类型组只在"影视库(all)"下发(具体分类下选了不生效);搜索 limit/pagecount 对齐、空词 pagecount=0。
//   - 限流:分类/搜索结果为空且确在限流时插占位卡"站点限流,稍后刷新",不再被客户端当成"到底了"。
//   - 详情:兼容裸数字 mid;名称/海报用 id 内 n/p 兜底;MEMORY 缓存 200→600;RESOURCE_ORDER "others" 归位。
// 1.1.2  2026-10-15
//   - 修复:115 等 access 票据类网盘播放失败/不出分集。根因:access_ticket 绑定账号 uid,
//          票据失效后 apiCall 无意义换号重试(票据在请求体里,换号必 403)陷入死循环;
//          且资源缓存键不含账号,换号后仍复用旧账号票据继续 403。
//          现:access 端点 403 直接返回空(由上层刷新票据)、资源缓存按账号隔离、换号清票据缓存。
//   - 修复:115 播放失败(觅盘能播聚影不能)。normalizePlayResult 原强行改写成 parse:0/取 url 首条,
//          a115 等返回 parse:1 或 url 数组时被破坏;现与不夜觅盘一致原样透传 drive.play 结果。
//   - 账号:默认回退账号 rrme/kisser123,可用 JUYING_ACCOUNTS 或 JUYING_USERNAME/JUYING_PASSWORD 覆盖。
// 1.1.1  2026-10-15
//   - 修复:OK影视主页出不来。FongMi type=4 首页请求是 ?ac=detail&filter=true(无 t/ids),
//          旧逻辑把它当无效请求返回原始 query(无 class/list)导致首页空白;现按首页返回。
//          另兼容 ac=class/list/videolist 的首页请求。搜索/详情/播放不受影响(实测正常)。
//   - 修复:筛选格式对齐 OK影视/FongMi 规范 {key,name,value:[{n,v}]}(value 为选项数组),
//          旧的 value:"全部"+options:[...] 会在渲染筛选时解析失败。
//   - 修复:详情简介最前面显示已解析到的分享链接,其余简介排在后面(旧逻辑分享链接恒为空)。
//   - 修复:115 等网盘播放失败时,若 drive.play 校验 flag 需等于自身 key(如 a115),
//          自动改用 drive.key 重试一次(百度等不受影响)。
// 1.1.0  2026-10-15
//   - 修复:影片详情恒为空(buildDetailByMid 对 mid 二次解码),此前详情/播放入口全废
//   - 修复:网盘分组卡片缺 folder 标记,点进分组是空白页;分组详情现只显示该网盘线路
//   - 新增:首页"系列合集"类目(对齐站点 /series:系列列表 -> 系列影片目录)
//   - 提速:分享枚举预算改整次详情共享(12s,原先每条线路各 15s)、刮削与资源拉取并行、
//          首页单请求(home-initial-data 自带统计)、公共接口不等登录(登录转后台)、
//          apiCall 内存缓存 5 分钟 TTL、请求超时 20s→12s、quick 搜索少拉页、列表海报透传
//   - 播放:access 预算用尽/解析失败的资源降级为"播放时解析"不再丢条目;
//          lazy 失败可用 rid+mid 刷新资源链接自愈,恢复链路支持磁力/直链
//   - 刮削:移除已失效默认镜像 tmdb.itv666.cc,改官方双域名(api.themoviedb.org/api.tmdb.org)
//          + 代理连续失败自动冷却转直连;限流 429 双线路冷却
//   - 筛选:选项格式对齐 OK影视/TVBox {n,v};类型别名 documentary→doc;
//          站点限流时不再误显示"暂无资源"
// 1.0.0  2026-10-14 初版
//   - 首页/分类/搜索/详情/播放全链路;网盘分享分集与多网盘线路分组
//   - 多账号登录自动切换(401/403 换号重登)+ 每日签到
//   - 分类筛选按站点统计动态生成(类型/年份/地区/标签/分类/网盘/排序)
//   - TMDB 补全(优先站点 tmdb_id 直查),海报取 cover/cover_url/backdrop_url
//   - 访问链接 90 秒短缓存(按 expires_in 收敛)防死链;分享解析失败负缓存
//   - 磁力/电驴直出,播放超时保护,播放失败清缓存重枚举重试
// ============================================================

const http = require("http");
const https = require("https");
const crypto = require("crypto");
const axios = require("axios");

// ==================== 配置区域 ====================
const DISABLE_WORDS = /^(off|false|none|no|0)$/i;

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

// 站点地址:可填一个或多个(逗号/分号分隔),运行时按顺序探测,能连上的自动作为当前站点
// 留空则依次尝试 https://www.jying.top -> https://jying.top
const SITE_CANDIDATES = (() => {
  const raw = splitConfigList(process.env.JUYING_WEB_SITE || "");
  const list = (raw.length ? raw : ["https://www.jying.top", "https://jying.top"]).map((item) =>
    String(item || "").trim().replace(/\/+$/, "")
  );
  const valid = list.filter((item) => /^https?:\/\//i.test(item));
  return valid.length ? valid : ["https://www.jying.top"];
})();

// 账号密码:支持多账号(逗号/分隔 用户名:密码),登录受限/失败时自动切换下一个
// 通过环境变量 JUYING_ACCOUNTS="user1:pass1,user2:pass2" 或 JUYING_USERNAME/JUYING_PASSWORD 配置
const AUTH_ACCOUNTS = (() => {
  const raw = splitConfigList(process.env.JUYING_ACCOUNTS || "");
  const pairs = [];
  for (const item of raw) {
    const idx = item.indexOf(":");
    if (idx > 0) pairs.push({ user: item.slice(0, idx).trim(), pass: item.slice(idx + 1).trim() });
  }
  if (pairs.length) return pairs;
  const user = envStr("JUYING_USERNAME", "");
  const pass = envStr("JUYING_PASSWORD", "");
  if (user && pass) return [{ user, pass }];
  return [{ user: "rrme", pass: "kisser123" }];
})();
let accountIndex = 0;
const STATIC_TOKEN = envStr("JUYING_TOKEN", "");
const STATIC_COOKIE = envStr("JUYING_COOKIE", "");

const REQUEST_TIMEOUT = envInt("JUYING_TIMEOUT", 18000, 3000);
const MIN_REQUEST_INTERVAL = envInt("JUYING_MIN_INTERVAL", 150, 0);
const PAGE_SIZE = envInt("JUYING_LIMIT", 24, 1);
// 单个影片最多处理的资源数(站点对资源接口有频率限制,不宜过大)
const MAX_RESOURCES = envInt("JUYING_MAX_RESOURCES", 20, 1);
// 最多拉取的资源页数
const MAX_RESOURCE_PAGES = envInt("JUYING_MAX_RESOURCE_PAGES", 3, 1);
// 单条线路提前解析真实链接的资源数(每条资源一次 access 请求,受站点频率限制)
const MAX_ACCESS_PER_GROUP = envInt("JUYING_MAX_ACCESS", 8, 1);
// 单条线路最多返回的选集数
const MAX_EPISODES = envInt("JUYING_MAX_EPISODES", 200, 1);
// 缓存时间(秒)
const CACHE_EX = envInt("JUYING_CACHE_EX_SECONDS", 43200, 60);
const DETAIL_CACHE_EX = envInt("JUYING_DETAIL_CACHE_EX_SECONDS", 1800, 60);
const RESOURCE_CACHE_EX = envInt("JUYING_RESOURCE_CACHE_EX_SECONDS", 600, 30);
// access 返回的分享链接服务端标注约120秒过期,默认只缓存90秒
const ACCESS_CACHE_EX = envInt("JUYING_ACCESS_CACHE_EX_SECONDS", 90, 10);
const SHARE_CACHE_EX = envInt("JUYING_SHARE_CACHE_EX_SECONDS", 1800, 60);
// apiCall 结果的内存缓存:列表/详情等动态数据,防止进程内永久陈旧与无上限增长
const API_MEM_EX = envInt("JUYING_API_CACHE_EX_SECONDS", 300, 10);
// 网盘分享解析:单个超时/单线路总时间预算(防止详情页卡死)
const ENUM_TIMEOUT_MS = envInt("JUYING_ENUM_TIMEOUT_MS", 8000, 1000);
const ENUM_BUDGET_MS = envInt("JUYING_ENUM_BUDGET_MS", 12000, 2000);
const ENUM_FAIL_EX = envInt("JUYING_ENUM_FAIL_EX_SECONDS", 300, 30);
// 单次 drive.play 超时(取真实播放地址)
const PLAY_TIMEOUT_MS = envInt("JUYING_PLAY_TIMEOUT_MS", 12000, 3000);
// 详情页简介前面显示分享链接(单行:"分享链接: xxx | 简介"),改成 "false" 关闭
const SHOW_SHARE_URL = envBool("JUYING_SHOW_SHARE_URL", true);
const SITE_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";
const ICON_BASE = "https://xget.xi-xu.me/gh/power721/alist-tvbox/raw/refs/heads/master/web-ui/public/";
const MEM_CACHE_MAX = 600;

// 详情页播放线路的网盘排序顺序
const DRIVE_ORDER = splitConfigList(
  envStr("JUYING_DRIVE_ORDER", "baidu;115;quark;tianyi;uc;123;aliyun;xunlei;mobile;pikpak;guangya")
).map((item) => item.toLowerCase());

// TMDB 密钥:留空则使用全局环境变量 TMDB_API_KEY
const TMDB_ENABLED = envBool("JUYING_TMDB", true);
const TMDB_API_KEY = envStr("TMDB_API_KEY", "fe9ee1bf19dfa140736bd03fbce42a62");
// 默认不启用镜像(实测 tmdb.itv666.cc 已522),官方直连+可选代理优先;可用 TMDB_MIRROR 自定义
const TMDB_MIRROR = (splitConfigList(process.env.TMDB_MIRROR || "")
  .map((item) => item.replace(/\/+$/, ""))
  .find((item) => /^https?:\/\//i.test(item)) || "");
const TMDB_HOSTS = ["api.tmdb.org", "api.themoviedb.org"];
const TMDB_MIRROR_TIMEOUT = envInt("JUYING_TMDB_MIRROR_TIMEOUT", 8000, 500);
const TMDB_TIMEOUT = envInt("JUYING_TMDB_TIMEOUT", 4000, 500);
const TMDB_PROXY_TIMEOUT = envInt("JUYING_TMDB_PROXY_TIMEOUT", 4000, 1000);
const TMDB_TOTAL = envInt("JUYING_TMDB_TOTAL_TIMEOUT", 15000, 2000);
const TMDB_MIRROR_DOWN = envInt("JUYING_TMDB_MIRROR_DOWN_SECONDS", 120, 5);
const TMDB_DOWN = envInt("JUYING_TMDB_DOWN_SECONDS", 120, 10);
const TMDB_FAIL_STREAK = envInt("JUYING_TMDB_FAIL_STREAK", 2, 1);
const TMDB_HIT_EX = envInt("JUYING_TMDB_CACHE_EX_SECONDS", 604800, 60);
const TMDB_MISS_EX = envInt("JUYING_TMDB_MISS_EX_SECONDS", 300, 30);
const TMDB_IMAGE_SIZE = envStr("JUYING_TMDB_IMAGE_SIZE", "w500");
const TMDB_IMAGE_MIRROR = envStr("TMDB_IMAGE_MIRROR", "").replace(/\/+$/, "");
// 内置 TMDB 代理:默认不启用(仅显式配置 JUYING_BUILTIN_PROXY 才走代理,避免内网地址在外部网络白等超时)
const BUILTIN_TMDB_PROXY = (() => {
  const raw = String(process.env.JUYING_BUILTIN_PROXY || "").trim();
  const value = raw.replace(/\/+$/, "");
  return DISABLE_WORDS.test(value) ? "" : value;
})();
// ==================== 配置区域结束 ====================

const store = {
  init: false,
  redis: null,
  log: null,
  server: null,
  drives: [],
  meta: {
    key: "juying",
    name: "聚影",
    version: VERSION,
    type: 4,
    api: "/video/juying",
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

// ==================== 基础工具 ====================
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
  return crypto.createHash("md5").update(String(value)).digest("hex");
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
    return `jy:${typ}:${encodeBase64Url(JSON.stringify(data || {}))}`;
  } catch (error) {
    return "";
  }
}

function decodeId(raw) {
  const text = String(raw || "");
  if (!text.startsWith("jy:")) return ["", {}];
  const parts = text.split(":");
  if (parts.length < 3 || !parts[1]) return ["", {}];
  try {
    const data = JSON.parse(decodeBase64Url(parts.slice(2).join(":")));
    return [parts[1], data && typeof data === "object" ? data : {}];
  } catch (error) {
    return ["", {}];
  }
}

function escapePlayName(value) {
  return String(value || "")
    .replace(/\$/g, "＄")
    .replace(/#/g, "＃")
    .trim();
}

function clean(value) {
  return escapePlayName(String(value || "资源").replace(/\s+/g, " ").trim().slice(0, 120));
}

// 站点演员/导演字段可能是数组或字符串,统一成中文顿号分隔的字符串
function joinNames(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => (item && (item.name || item)) || "")
      .filter(Boolean)
      .join("、");
  }
  return String(value || "");
}

function dedupe(list) {
  const out = [];
  const seen = new Set();
  for (const item of Array.isArray(list) ? list : []) {
    const key = String((item && (item.id || item.share_link || item.title)) || item);
    if (key && !seen.has(key)) {
      seen.add(key);
      out.push(item);
    }
  }
  return out;
}

function errorText(error) {
  if (error === null || error === undefined) return "未知错误";
  if (typeof error === "string") return error;
  return String(error.message || error);
}

function emptyPlayResult() {
  return { parse: 0, jx: 0, url: "", header: {} };
}

// 不夜容器 drive.play 的返回可能是字符串/对象/对象含 url 数组,统一成 OK影视 能识别的结构
function normalizePlayResult(result) {
  if (typeof result === "string") return { parse: 0, jx: 0, url: result, header: {} };
  // 与不夜觅盘一致:drive.play 返回对象时原样透传。
  // a115 等网盘会返回 parse:1(需二次解析)或 url 数组,强行归一成 parse:0/取首条会导致播放失败。
  if (result && typeof result === "object") return result;
  return emptyPlayResult();
}

// ==================== 缓存(内存 + redis) ====================
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
    log("warn", `聚影 写入缓存失败: ${key}, ${error.message}`);
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
  // ""/null 都视为未命中:clearShareCache 软删写的是 null,空串也不能当有效缓存
  if (mem !== undefined && mem !== null && mem !== "") return mem;
  const remote = await redisGet(key);
  if (remote !== undefined && remote !== null && remote !== "") {
    memSet(key, remote, exSeconds);
    return remote;
  }
  const value = await once(key, loader);
  if (value !== undefined && value !== null && value !== "") {
    memSet(key, value, exSeconds);
    await redisSet(key, value, exSeconds);
  }
  return value;
}

async function cacheGet(key, exSeconds) {
  const ex = exSeconds || CACHE_EX;
  const mem = memGet(key);
  if (mem !== undefined && mem !== null && mem !== "") return mem;
  const remote = await redisGet(key);
  if (remote !== undefined && remote !== null && remote !== "") {
    memSet(key, remote, ex);
    return remote;
  }
  return null;
}

async function cacheSet(key, value, exSeconds) {
  const ex = exSeconds || CACHE_EX;
  memSet(key, value, ex);
  await redisSet(key, value, ex);
}

// ==================== 站点选择 ====================
let WEB_SITE = "";
let siteIndex = 0;
let sitePromise = null;

// 网络层失败时丢弃当前站点,下次从下一个候选继续探测
function invalidateWebSite() {
  if (!WEB_SITE) return;
  const idx = SITE_CANDIDATES.indexOf(WEB_SITE);
  siteIndex = idx >= 0 ? (idx + 1) % SITE_CANDIDATES.length : 0;
  WEB_SITE = "";
}

function probeSite(site) {
  return httpRequest(`${site}/api/csrf/`, {
    headers: {
      "User-Agent": SITE_UA,
      Accept: "application/json, text/plain, */*",
      Referer: `${site}/categories`,
    },
    timeout: Math.min(REQUEST_TIMEOUT, 8000),
  });
}

async function resolveWebSite() {
  if (WEB_SITE) return WEB_SITE;
  if (!sitePromise) {
    const start = siteIndex >= 0 && siteIndex < SITE_CANDIDATES.length ? siteIndex : 0;
    sitePromise = (async () => {
      for (let i = 0; i < SITE_CANDIDATES.length; i++) {
        const idx = (start + i) % SITE_CANDIDATES.length;
        const site = SITE_CANDIDATES[idx];
        try {
          const res = await probeSite(site);
          if (res.statusCode > 0 && res.statusCode < 500) {
            WEB_SITE = site;
            siteIndex = idx;
            log("info", `聚影 站点地址: ${WEB_SITE} (不夜聚影 v${VERSION})`);
            return WEB_SITE;
          }
          log("warn", `聚影 站点探测不可用: ${site} (HTTP ${res.statusCode})`);
        } catch (error) {
          log("warn", `聚影 站点探测失败: ${site}, ${error.message}`);
        }
      }
      WEB_SITE = SITE_CANDIDATES[start];
      log("warn", `聚影 站点全部探测失败,暂用: ${WEB_SITE}`);
      return WEB_SITE;
    })().finally(() => {
      sitePromise = null;
    });
  }
  return sitePromise;
}

// 站点允许匿名访问的 GET 接口:请求时只触发后台登录,不等登录完成
const PUBLIC_API_RE = /^\/api\/app\/(categories|home-initial-data|movies|movie\/[^/]+\/detail|series)/;

// ==================== 运行时状态 ====================
let authToken = String(STATIC_TOKEN || "");
let tokenRestored = false;
let loginPromise = null;
let loginFailedAt = 0;
const cookieJar = new Map();

// ==================== Cookie / Header ====================
function captureCookies(headers) {
  let raw = headers ? headers["set-cookie"] : null;
  if (!raw) return;
  if (typeof raw === "string") raw = [raw];
  if (!Array.isArray(raw)) return;
  for (const item of raw) {
    const pair = String(item).split(";")[0] || "";
    const idx = pair.indexOf("=");
    if (idx <= 0) continue;
    const name = pair.slice(0, idx).trim();
    const value = pair.slice(idx + 1).trim();
    if (value) cookieJar.set(name, value);
    else cookieJar.delete(name);
  }
}

function cookieHeader() {
  const parts = [];
  for (const [name, value] of cookieJar.entries()) parts.push(`${name}=${value}`);
  return parts.join("; ");
}

function buildHeaders(extra) {
  const headers = {
    "User-Agent": SITE_UA,
    Accept: "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    Referer: `${WEB_SITE}/categories`,
  };
  const ck = cookieHeader() || STATIC_COOKIE;
  if (ck) headers.Cookie = ck;
  if (authToken) headers["X-App-User-Token"] = authToken;
  const csrf = cookieJar.get("csrftoken");
  if (csrf) headers["X-CSRFToken"] = csrf;
  return Object.assign(headers, extra || {});
}

// ==================== HTTP ====================
const INSECURE_HTTPS_AGENT = new https.Agent({ rejectUnauthorized: false, keepAlive: true });
const HTTP_AGENT = new http.Agent({ keepAlive: true });
let lastRequestAt = 0;

function waitNextRequest() {
  const now = Date.now();
  const wait = Math.max(0, lastRequestAt + MIN_REQUEST_INTERVAL - now);
  lastRequestAt = now + wait;
  if (wait <= 0) return Promise.resolve();
  return new Promise((resolve) => setTimeout(resolve, wait));
}

async function httpRequest(url, options = {}) {
  await waitNextRequest();
  const response = await axios({
    url,
    method: String(options.method || "GET").toUpperCase(),
    headers: options.headers || {},
    params: options.params,
    data: options.body,
    timeout: options.timeout || REQUEST_TIMEOUT,
    httpsAgent: INSECURE_HTTPS_AGENT,
    httpAgent: HTTP_AGENT,
    responseType: "text",
    validateStatus: () => true,
  });
  captureCookies(response.headers || {});
  let body = response.data;
  if (typeof body !== "string") {
    body = body === undefined || body === null ? "" : JSON.stringify(body);
  }
  return { statusCode: response.status, body, headers: response.headers || {} };
}

// ==================== 登录(多账号自动切换) ====================
function currentAccount() {
  if (!AUTH_ACCOUNTS.length) return null;
  if (accountIndex >= AUTH_ACCOUNTS.length) accountIndex = 0;
  return AUTH_ACCOUNTS[accountIndex];
}

async function doLogin(maxAttempts) {
  const attempts = typeof maxAttempts === "number" ? maxAttempts : AUTH_ACCOUNTS.length;
  const account = currentAccount();
  if (!account || !account.user || !account.pass) {
    log("warn", "聚影 登录跳过: 无可用账号");
    loginFailedAt = Date.now();
    return false;
  }
  try {
    await resolveWebSite();
    await httpRequest(`${WEB_SITE}/api/csrf/`, { timeout: REQUEST_TIMEOUT });
    const headers = buildHeaders({ Origin: WEB_SITE, Referer: `${WEB_SITE}/login` });
    const response = await httpRequest(`${WEB_SITE}/api/app/login/`, {
      method: "POST",
      headers,
      body: { username: account.user, password: account.pass },
      timeout: REQUEST_TIMEOUT,
    });
    const data = parseJson(response.body) || {};
    authToken = String(data.token || "");
    if (authToken) {
      log("info", `聚影 登录成功: ${(data.user && data.user.username) || account.user} (账号 ${accountIndex + 1}/${AUTH_ACCOUNTS.length})`);
      await redisSet("jy:token", authToken, 86400 * 6);
      await redisSet("jy:token_account", accountIndex, 86400 * 6);
      return true;
    }
    log("warn", `聚影 登录失败: HTTP ${response.statusCode} (账号 ${account.user})`);
    // 登录失败(可能限流/密码失效):切换下一个账号重试,最多轮一遍
    if (AUTH_ACCOUNTS.length > 1 && attempts > 1) {
      accountIndex = (accountIndex + 1) % AUTH_ACCOUNTS.length;
      log("info", `聚影 切换到账号 ${accountIndex + 1}/${AUTH_ACCOUNTS.length}: ${currentAccount().user}`);
      return await doLogin(attempts - 1);
    }
    loginFailedAt = Date.now();
    return false;
  } catch (error) {
    log("error", `聚影 登录异常: ${error.message}`);
    invalidateWebSite();
    if (AUTH_ACCOUNTS.length > 1 && attempts > 1) {
      accountIndex = (accountIndex + 1) % AUTH_ACCOUNTS.length;
      log("info", `聚影 切换到账号 ${accountIndex + 1}/${AUTH_ACCOUNTS.length}: ${currentAccount().user}`);
      return await doLogin(attempts - 1);
    }
    loginFailedAt = Date.now();
    return false;
  }
}

async function ensureLogin() {
  if (authToken) return true;
  if (!tokenRestored) {
    tokenRestored = true;
    const cached = await redisGet("jy:token");
    if (cached) authToken = String(cached);
    const cachedIdx = await redisGet("jy:token_account");
    if (typeof cachedIdx === "number" && cachedIdx >= 0 && cachedIdx < AUTH_ACCOUNTS.length) accountIndex = cachedIdx;
    if (authToken) return true;
  }
  if (STATIC_COOKIE) return true;
  if (Date.now() - loginFailedAt < 8000) return false;
  if (!loginPromise) {
    loginPromise = doLogin().finally(() => {
      loginPromise = null;
    });
  }
  return loginPromise;
}

// 401/403 后强制换账号重新登录(先清 token 再切账号)
async function reloginWithNextAccount() {
  authToken = "";
  await redisSet("jy:token", "", 1);
  if (AUTH_ACCOUNTS.length > 1) {
    accountIndex = (accountIndex + 1) % AUTH_ACCOUNTS.length;
    log("info", `聚影 换账号重新登录: ${currentAccount().user}`);
    // access_ticket 绑定旧账号 uid,换号后旧票据全失效:清内存资源缓存,下次 resourceListApi 拉新票据
    clearAllResourceMemCache();
  }
  loginFailedAt = 0;
  return await ensureLogin();
}

// ==================== 每日签到 ====================
// home 入口自动签到,按 账号+日期 缓存一天;先查 stats 再 POST do(服务端幂等兜底)
// 只做普通签到(5积分/5EXP),不含可能扣分的幸运签到与奖池抽取
function checkinDayKey() {
  const now = new Date();
  const day = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const account = currentAccount();
  return `jy:checkin:${(account && account.user) || "anon"}:${day}`;
}

function checkinCacheSeconds(now) {
  const next = new Date(now || new Date());
  next.setHours(24, 0, 0, 0);
  return Math.max(600, Math.ceil((next - now) / 1000) + 300);
}

let checkinInFlight = null;

async function dailyCheckin() {
  if (checkinInFlight) return checkinInFlight;
  checkinInFlight = (async () => {
    try {
      const key = checkinDayKey();
      if (await cacheGet(key)) return;
      const stats = await apiCall("/api/app/checkin/stats/");
      if (!stats || stats.status !== "success") return;
      if (stats.checked_today) {
        await cacheSet(key, 1, checkinCacheSeconds());
        log("info", "聚影 今日已签到");
        return;
      }
      if (!stats.can_checkin) {
        log("warn", "聚影 今日无法签到(can_checkin=false),跳过");
        return;
      }
      const res = await apiCall("/api/app/checkin/do/", { post: {} });
      const msg = String((res && (res.message || res.msg)) || "");
      if (res && res.status === "success") {
        await cacheSet(key, 1, checkinCacheSeconds());
        log(
          "info",
          `聚影 每日签到成功: 获得 ${res.points_awarded ?? "?"} 积分、${res.experience_awarded ?? "?"} EXP`
        );
      } else if (/已签到|already/i.test(msg)) {
        await cacheSet(key, 1, checkinCacheSeconds());
        log("info", "聚影 今日已签到");
      } else {
        log("warn", `聚影 每日签到失败: ${msg || "未知响应"}`);
      }
    } catch (error) {
      log("warn", `聚影 每日签到失败: ${error.message}`);
    }
  })().finally(() => {
    checkinInFlight = null;
  });
  return checkinInFlight;
}

// ==================== API 请求 ====================
const rateLimits = new Map();

function scopeForPath(path) {
  const p = String(path || "");
  if (/\/access\//.test(p)) return "resource_access";
  if (/\/resources\//.test(p)) return "resource_read";
  if (/\/movies\/|\/home-initial-data\//.test(p)) return "list_read";
  if (/\/detail\//.test(p)) return "detail_read";
  return "default";
}

function rateLimitRemaining(path) {
  const until = rateLimits.get(scopeForPath(path)) || 0;
  return Math.max(0, until - Date.now());
}

function noteRateLimit(parsed, path) {
  const retryAfter = parseInt((parsed && (parsed.retry_after || parsed.retryAfter)) || "", 10) || 300;
  const seconds = Math.min(Math.max(retryAfter, 30), 1800);
  const until = Date.now() + seconds * 1000;
  rateLimits.set(scopeForPath(path), until);
  const reported = String((parsed && parsed.limit_scope) || "").replace(/_cooldown$/, "");
  if (reported) rateLimits.set(reported, until);
  log("warn", `聚影 站点触发限流(${reported || "未知范围"}),${seconds}秒后自动恢复: ${path}`);
}

async function apiCall(path, options = {}) {
  const params = options.params || null;
  const post = options.post;
  // access(分享链接约120秒过期)与 resources(含账号绑定票据)不走 apiCall 内存缓存:
  // 前者缓存会出死链,后者缓存不带账号作用域会让"刷新票据"空转(资源列表有自己的按账号缓存)
  const noCache = path.includes("/access/") || path.includes("/resources/");
  const cacheKey = `${post ? "p:" : "g:"}${path}|${JSON.stringify(params || {})}|${JSON.stringify(post || {})}`;
  if (!noCache) {
    const hit = memGet(cacheKey);
    if (hit !== undefined && hit !== null && hit !== "") return hit;
  }
  const remaining = rateLimitRemaining(path);
  if (remaining > 0) {
    log("warn", `聚影 站点限流冷却中(${Math.ceil(remaining / 1000)}秒),跳过请求: ${path}`);
    return {};
  }

  let result = {};
  let cacheable = false;
  // 重试 2 次:站点单请求 2~8 秒,3 次叠加换站探测最坏 60 秒,对客户端过久
  for (let attempt = 0; attempt < 2; attempt++) {
    await resolveWebSite();
    if (!post && PUBLIC_API_RE.test(path)) {
      ensureLogin().catch(() => {});
    } else {
      const ok = await ensureLogin();
      // 登录失败也继续:受保护接口会走 401 -> 换账号重登;公共数据照常返回
      if (!ok) log("warn", `聚影 未登录,仍尝试请求: ${path}`);
    }
    try {
      const response = await httpRequest(WEB_SITE + path, {
        method: post ? "POST" : "GET",
        headers: buildHeaders({ Referer: `${WEB_SITE}/categories` }),
        params: params || undefined,
        body: post,
        timeout: REQUEST_TIMEOUT,
      });
      const parsed = parseJson(response.body);
      if (response.statusCode === 429 || (parsed && parsed.code === "rate_limited")) {
        noteRateLimit(parsed, path);
        return {};
      }
      if (response.statusCode === 401 || response.statusCode === 403) {
        // access 端点:票据(access_ticket)绑定 uid 且在请求体里,换账号重试无用(必 403)。
        // 直接返回空,由上层(invalidateResourceCache+resourceListApi)重新拉列表拿当前账号的新票据再试。
        if (path.includes("/access/")) {
          log("warn", `聚影 access 票据对当前账号无效(${response.statusCode}),返回空待上层刷新票据: ${path}`);
          return {};
        }
        log("warn", `聚影 接口鉴权失败(${response.statusCode}),换账号重新登录: ${path}`);
        const ok2 = await reloginWithNextAccount();
        if (!ok2) break;
        continue;
      }
      result = parsed || {};
      cacheable = Boolean(result) && Object.keys(result).length > 0 && result.status !== "error";
      break;
    } catch (error) {
      log("warn", `聚影 请求失败: ${path}, ${error.message}`);
      result = {};
      // 仅连接类错误才换站重探测;读超时/业务错误换站没意义(只会拖慢)
      const msg = String(error && error.message || "");
      if (/ECONNREFUSED|ENOTFOUND|ECONNRESET|EAI_AGAIN|ETIMEDOUT|socket hang up/i.test(msg)) {
        invalidateWebSite();
      }
    }
  }

  if (cacheable && !noCache) memSet(cacheKey, result, API_MEM_EX);
  return result;
}

function overviewApi() {
  return apiCall("/api/app/categories/");
}

function homeInitialApi() {
  return apiCall("/api/app/home-initial-data/", { params: { page_size: 24 } });
}

function pickMovieMeta(detailData) {
  return (detailData && (detailData.data || detailData.movie)) || detailData || {};
}

async function movieDetailApi(mid) {
  const cacheKey = `jy:detail:${mid}`;
  try {
    const cached = await cacheGet(cacheKey, DETAIL_CACHE_EX);
    if (cached && typeof cached === "object" && Object.keys(cached).length) return cached;
  } catch (error) {
    /* 忽略缓存读取失败 */
  }
  const result = await apiCall(`/api/app/movie/${encodeURIComponent(mid)}/detail/`);
  if (result && Object.keys(result).length) {
    try {
      await cacheSet(cacheKey, result, DETAIL_CACHE_EX);
    } catch (error) {
      /* 忽略缓存写入失败 */
    }
  }
  return result;
}

function capResources(list, max) {
  if (list.length <= max) return list;
  const groups = groupByResourceType(list);
  const buckets = orderedGroupKeys(groups).map((key) => groups[key] || []);
  const picked = [];
  let offset = 0;
  while (picked.length < max) {
    let took = false;
    for (const bucket of buckets) {
      if (picked.length >= max) break;
      const item = bucket[offset];
      if (item !== undefined) {
        picked.push(item);
        took = true;
      }
    }
    if (!took) break;
    offset += 1;
  }
  return picked;
}

// 资源缓存按当前账号隔离:access_ticket 绑定 uid,换号后旧票据全部失效,不能跨账号复用
function resourceCacheScope() {
  const account = currentAccount();
  return (account && account.user) || "anon";
}

async function resourceListApi(mid) {
  const scope = resourceCacheScope();
  const key = `res|${scope}|${mid}`;
  const hit = memGet(key);
  if (hit !== undefined && hit !== null) return hit;
  // 二次进入时站点常在限流冷却:先读持久缓存,进程重启也能出资源
  // 缓存键带账号 scope:access_ticket 绑定 uid,换号后旧票据必 403,不能跨账号复用
  const storeKey = `jy:res:${scope}:${mid}`;
  try {
    const stored = await cacheGet(storeKey, RESOURCE_CACHE_EX);
    if (Array.isArray(stored) && stored.length) {
      memSet(key, stored, RESOURCE_CACHE_EX);
      return stored;
    }
  } catch (error) {
    /* 忽略缓存读取失败 */
  }
  const list = [];
  let page = 1;
  while (page <= MAX_RESOURCE_PAGES && list.length < MAX_RESOURCES) {
    const data = await apiCall(`/api/app/movie/${encodeURIComponent(mid)}/resources/`, {
      params: { page, page_size: 120 },
    });
    const items = Array.isArray(data.resources) ? data.resources : [];
    if (!items.length) break;
    list.push(...items);
    if (!data.has_more) break;
    page += 1;
  }
  const result = capResources(dedupe(list), MAX_RESOURCES);
  if (result.length) {
    memSet(key, result, RESOURCE_CACHE_EX);
    try {
      await cacheSet(storeKey, result, RESOURCE_CACHE_EX);
    } catch (error) {
      /* 忽略缓存写入失败 */
    }
  }
  return result;
}

// 清掉某影片的持久资源缓存,让下次 resourceListApi 拉取带新票据的列表
async function invalidateResourceCache(mid) {
  if (!mid) return;
  const scope = resourceCacheScope();
  memCache.delete(`res|${scope}|${mid}`);
  try {
    await cacheSet(`jy:res:${scope}:${mid}`, null, 1);
  } catch (error) {
    /* 忽略缓存清理失败 */
  }
}

// 换账号后清掉全部内存里的资源/分享票据缓存(旧票据绑定旧 uid,继续用必 403)
function clearAllResourceMemCache() {
  for (const key of Array.from(memCache.keys())) {
    if (key.startsWith("res|") || key.startsWith("access|")) memCache.delete(key);
  }
}

// ==================== 资源真实链接 ====================
// 按网盘域名选提取码参数名:115→password、天翼189→code、其余(百度/夸克/UC/123等)→pwd
// 参数插在 #fragment 之前,避免落进 hash 变成无效参数
function attachSharePassword(url, code) {
  const raw = String(url || "");
  const pwd = String(code || "").trim();
  if (!raw || !pwd || !isPanShareUrl(raw)) return raw;
  if (/[?&](password|pass|pwd|code|passcode)=/i.test(raw)) return raw;
  const hash = raw.indexOf("#");
  const base = hash >= 0 ? raw.slice(0, hash) : raw;
  const fragment = hash >= 0 ? raw.slice(hash) : "";
  let host = "";
  try {
    host = new URL(raw).hostname.toLowerCase();
  } catch (error) {
    host = "";
  }
  let param = "pwd";
  if (host.includes("115")) param = "password";
  else if (host.includes("189")) param = "code";
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}${param}=${encodeURIComponent(pwd)}${fragment}`;
}

// 123云盘同一批分享有多个镜像域名(123684/123685/123865/123912),容器/SDK 的123 drive 只认含
// "123pan" 的域名,其它镜像域名 matchShare 会失败导致从不枚举分集(实测123从不出分集的根因);
// 统一改写成 www.123pan.cn(与镜像同套 API)并补 password 参数(与旧版聚影一致)
const PAN123_HOST_MAP = {
  "123684.com": "www.123pan.cn",
  "123685.com": "www.123pan.cn",
  "123865.com": "www.123pan.cn",
  "123912.com": "www.123pan.cn",
};

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
  log("info", `聚影 123分享域名改写: ${host} -> ${target}`);
  return next;
}

// ==================== 123云盘直连(照 alist 配方: yun.123pan.com + signPath签名 + 登录态 Bearer) ====================
// 列表: GET /b/api/share/get(Page分页,返回 data.InfoList,Type1=目录 0=文件)
// 下载: POST /b/api/share/download/info({shareKey,SharePwd,etag,fileId,s3keyFlag,size}) -> data.DownloadURL
//       -> params(base64) 解码 -> GET(302取location/JSON取redirect_url) 即最终播放地址
//       分享方无提取流量(免费号为0)且文件在自己盘里时,自动改走 POST /b/api/file/download_info(消耗普通下载流量)
// 【123账号】123 download 接口需登录(匿名必拒"您需要注册登录或付费后下载"):
//   账密不写死在 JS 里,只配环境变量:PAN_123_USERNAME + PAN_123_PASSWORD(自动登录换token,401自动重登),
//   或已有 token 直接配 PAN_123_TOKEN;"不夜后台添加123账号"功能已随123改版失效,不用管它,以环境变量为准。
// 123 已给 API 加请求签名(不带签名会被风控拦回HTML),签名算法照 AlistGo/alist drivers/123_share 移植
function isPan123URL(url) {
  const parts = String(url || "").match(/^https?:\/\/([^/?#]+)/i);
  if (!parts) return false;
  const host = parts[1].toLowerCase().replace(/^www\./, "");
  return Boolean(PAN123_HOST_MAP[host]) || /(^|\.)123pan\.(cn|com)$/.test(host);
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

// 独立于 httpRequest:不走站点限流、不污染 jying 的 cookie jar;700ms 限流对齐 alist
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
    httpsAgent: INSECURE_HTTPS_AGENT,
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
        log("info", "聚影 123账号登录成功");
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
      log("warn", `聚影 123登录失败: ${error.message}`);
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
          if (PAN123_API_HOST_CACHE !== host) log("info", `聚影 123API可用域名: ${host}`);
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

function isVideoFileName(name) {
  return /\.(m3u8|mp4|flv|mkv|ts|webm|m4v|avi|mov|wmv|mpg|mpeg|vob|mts|m2ts|rm|rmvb|iso|3gp|ogv|ogm|asf|f4v|dat|tp|trp|ifo)(\?|#|$)/i.test(
    String(name || "")
  );
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

// 123选集播放ID编码: p123:<base64url(JSON)>,带 s3/etag/size/直链 让播放时免二次遍历
function encodePan123Episode(file) {
  try {
    const payload = { f: file.fid, s: file.s3KeyFlag, e: file.etag, z: file.size };
    if (file.name) payload.n = file.name; // 文件名: 匿名下载请求体的 FileName 字段用
    if (file.download_url) payload.d = file.download_url; // 无限直链: 列表已签名 DownloadUrl(有才带)
    return "p123:" + encodeBase64Url(JSON.stringify(payload));
  } catch (error) {
    return "p123:" + String(file.fid || "");
  }
}

function decodePan123Episode(id) {
  const raw = String(id || "");
  if (!raw.startsWith("p123:")) return null;
  const payload = raw.slice(5);
  try {
    const data = JSON.parse(decodeBase64Url(payload));
    return {
      fid: String(data.f || ""),
      s3KeyFlag: String(data.s || ""),
      etag: String(data.e || ""),
      size: Number(data.z || 0) || 0,
      name: String(data.n || ""),
      download_url: String(data.d || ""),
    };
  } catch (error) {
    return { fid: payload, s3KeyFlag: "", etag: "", size: 0, name: "", download_url: "" };
  }
}

async function pan123DirectEpisodes(shareURL) {
  const info = parsePan123Share(shareURL);
  if (!info) throw new Error("无法识别的123分享链接");
  const episodes = [];
  let visited = 0;
  const walk = async (parentFileId, depth) => {
    if (depth > 4 || visited > 2000 || episodes.length >= MAX_EPISODES * 2) return;
    for (let page = 1; page <= 30; page++) {
      const result = await pan123ShareListPage(info, parentFileId, page);
      visited += result.items.length;
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
        const displayName = (fileSize > 0 ? `[${formatFileSize(fileSize)}] ` : "") + name;
        episodes.push({
          id: encodePan123Episode({
            fid,
            s3KeyFlag: String(item.S3KeyFlag || ""),
            etag: String(item.Etag || ""),
            size: fileSize,
            name,
            download_url: String(item.DownloadUrl || ""), // 无限直链: 列表已签名直链,播放档①零请求
          }),
          name: displayName,
        });
      }
      if (pan123ListDone(result.next) || !result.items.length) break;
    }
  };
  await walk(0, 0);
  log("info", `聚影 123直连枚举: ${episodes.length} 个视频 (${info.shareKey})`);
  return episodes;
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

async function pan123DirectPlay(shareURL, encodedId) {
  const file = decodePan123Episode(encodedId);
  if (!file || !file.fid) throw new Error("123选集参数异常");
  const info = parsePan123Share(shareURL);
  if (!info) throw new Error("无法识别的123分享链接");
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
    log("info", `聚影 123无限直链命中(剩余约${Math.round(directTTL / 60000)}分钟): ${fileName || file.fid}`);
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
    // 5112 分享方流量耗尽/死分享: 账号重试也无意义(同一后端),不打账号;
    // 提取码错误文案同理:密码错,换账号也救不回,别浪费一次鉴权重试
    if (
      !traffic &&
      !isDeadShareError(message) &&
      !/提取码错误|提取码不正确|密码错误|密码不正确/.test(message) &&
      error &&
      error.pan123Business &&
      (PAN123_TOKEN_ENV || PAN123_USERNAME)
    ) {
      try {
        dlData = await pan123ApiRequest("POST", "/b/api/share/download/info", { body: dlBody });
      } catch (authError) {
        lastDlError = authError;
      }
    }
  }
  if (!dlData && lastDlError) {
    const message = String((lastDlError && lastDlError.message) || lastDlError || "");
    // 档③ 分享方无提取流量(免费号为0): 文件在自己盘里时改走"我的网盘"下载接口(消耗自己普通下载流量,alist 挂载同款)
    const trafficMsg = Number(lastDlError && lastDlError.pan123Code) === 5112 || /提取流量|流量包不足|流量不足/.test(message);
    if (!(lastDlError && lastDlError.pan123Business) || !trafficMsg) throw lastDlError;
    try {
      dlData = await pan123ApiRequest("POST", "/b/api/file/download_info", {
        body: { driveId: 0, etag, fileId: Number(file.fid) || file.fid, s3keyFlag: s3KeyFlag, size },
      });
      log("info", "聚影 123分享无提取流量,已改走本人网盘下载接口");
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

async function accessResource(x, force) {
  if (!x || typeof x !== "object") return "";
  const ridKey = String(x.id || "");
  const ticketKey = String(x.access_ticket || "");
  // id/ticket 缺失时不同资源会共用同一缓存键导致串数据:跳过缓存直接取数
  const cacheableKey = ridKey && ticketKey;
  const cacheKey = `access|${ridKey}|${ticketKey}`;
  const storeKey = `jy:${cacheKey}`;
  if (!force && cacheableKey) {
    const memHit = memGet(cacheKey);
    if (memHit) return memHit;
    // 持久缓存:二次进入/限流冷却时直接复用上次拿到的分享链接
    try {
      const stored = await cacheGet(storeKey);
      if (stored && typeof stored === "string") {
        memSet(cacheKey, stored, ACCESS_CACHE_EX);
        return stored;
      }
    } catch (error) {
      /* 忽略缓存读取失败 */
    }
  }

  let target = "";
  let ttl = ACCESS_CACHE_EX;
  if (x.target) {
    target = String(x.target);
  } else {
    const shared = x.share_link || x.raw_share_link || x.share_link_with_code || "";
    if (shared) target = String(shared);
    else {
      const rid = x.id;
      const ticket = x.access_ticket || x.ticket || "";
      if (rid && ticket) {
        const data = await apiCall(`/api/app/resource/${encodeURIComponent(rid)}/access/`, {
          post: { access_ticket: String(ticket) },
        });
        const raw = data.target || data.share_link || data.url || "";
        if (raw) {
          target = normalizePlayUrl(String(raw));
          target = attachSharePassword(target, data.access_code || data.extraction_code || "");
          // 服务端返回过期时间(实测约120秒),按其收敛缓存,避免拿到死链
          const expires = parseInt(data.expires_in, 10);
          if (Number.isFinite(expires) && expires > 5) ttl = Math.min(ttl, Math.max(10, expires - 15));
        }
      }
    }
  }

  target = normalizePlayUrl(target);
  // 123镜像域名改写:让容器123 drive能 matchShare/getVod,否则从不出分集
  target = normalizePanShareURL(target);
  if (target && cacheableKey) {
    memSet(cacheKey, target, ttl);
    try {
      await cacheSet(storeKey, target, ttl);
    } catch (error) {
      /* 忽略缓存写入失败 */
    }
  }
  return target;
}

// ==================== 链接工具 ====================
function normalizePlayUrl(raw) {
  let value = String(raw || "").replace(/&amp;/g, "&").trim();
  while (value.length > 0 && (value.charAt(0) === '"' || value.charAt(0) === "'")) {
    value = value.slice(1).trim();
  }
  while (value.length > 0) {
    const last = value.charAt(value.length - 1);
    if (last !== '"' && last !== "'") break;
    value = value.slice(0, -1).trim();
  }
  if (!value) return "";
  const hasScheme = /^(https?|magnet|ed2k):/i.test(value);
  if (!hasScheme && /%3a%2f%2f/i.test(value)) {
    try {
      const decoded = decodeURIComponent(value).trim();
      if (/^(https?|magnet|ed2k):/i.test(decoded)) value = decoded;
    } catch (error) {
      // 保持原样
    }
  }
  return value.trim();
}

function isRawPlayable(url) {
  const value = String(url || "");
  const lower = value.toLowerCase();
  if (lower.startsWith("magnet:") || lower.startsWith("ed2k://")) return true;
  return /\.(m3u8|mp4|flv|mkv|ts|webm|m4v|avi|mov|wmv|mpg|mpeg|vob|mts|m2ts|rm|rmvb|iso|3gp|ogv|ogm|asf|f4v|dat|tp|trp|ifo)(\?|#|$)/i.test(
    value
  );
}

function isPanShareUrl(url) {
  return /115|quark|aliyun|alipan|baidu|uc\.cn|123pan|123684|123685|123865|123912|189\.cn|139\.cn|xunlei|anxia|guangyapan|tianyi|pikpak/i.test(
    String(url || "")
  );
}

// 站点已标明网盘类型的资源一律按网盘枚举(分享域名会新增,不能只靠 URL 特征判断)
const PAN_TYPE_KEYS = new Set([
  "115",
  "123",
  "baidu",
  "xunlei",
  "quark",
  "aliyun",
  "uc",
  "guangya",
  "tianyi",
  "pikpak",
  "mobile",
  "139",
  "189",
]);

function isPanResourceKey(key) {
  return PAN_TYPE_KEYS.has(String(key || "").toLowerCase());
}

// 磁力/电驴只需在播放时取一次真实链接,详情页直接延迟解析,避免批量请求触发站点限流
function isLazyResourceType(item) {
  const key = resourceType(item);
  return key === "magnet" || key === "ed2k";
}

function compactResource(item) {
  const src = item && typeof item === "object" ? item : {};
  const out = {};
  for (const key of [
    "id",
    "access_ticket",
    "ticket",
    "share_link",
    "raw_share_link",
    "share_link_with_code",
    "target",
    "access_code",
    "extraction_code",
    "resource_type",
    "title",
    "resource_description",
  ]) {
    if (src[key] !== undefined && src[key] !== null && src[key] !== "") out[key] = src[key];
  }
  return out;
}

function isMagnetUrl(value) {
  return /^(magnet|ed2k):/i.test(String(value || "").trim());
}

function extractMagnet(value) {
  const match = /magnet:\?[^\s"'<>]+/i.exec(String(value || "").replace(/&amp;/g, "&"));
  if (!match) return "";
  return match[0].replace(/[),.;]+$/, "");
}

function hasExtractCode(url) {
  return /([?&](pwd|password|code|pass|passcode)=)/i.test(String(url || ""));
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

function directHeader(url) {
  const value = String(url || "").toLowerCase();
  if (value.startsWith("magnet:") || value.startsWith("ed2k://")) return {};
  return { "User-Agent": SITE_UA };
}

// ==================== 站点字段工具 ====================
function resourceType(x) {
  const type = String((x && x.resource_type) || "other").toLowerCase();
  if (type === "magnetlink") return "magnet";
  if (type.includes("123")) return "123";
  if (type.includes("baidu")) return "baidu";
  if (type.includes("xunlei")) return "xunlei";
  if (type.includes("quark")) return "quark";
  if (type.includes("aliyun") || type.includes("alipan") || type === "ali") return "aliyun";
  if (type.includes("115")) return "115";
  if (type === "uc") return "uc";
  if (type.includes("ed2k")) return "ed2k";
  if (type.includes("magnet")) return "magnet";
  return type || "other";
}

const PAN_META = {
  baidu: { name: "百度网盘", short: "百度" },
  aliyun: { name: "阿里云盘", short: "阿里" },
  quark: { name: "夸克网盘", short: "夸克" },
  tianyi: { name: "天翼网盘", short: "天翼" },
  uc: { name: "UC网盘", short: "UC" },
  "115": { name: "115网盘", short: "115" },
  xunlei: { name: "迅雷网盘", short: "迅雷" },
  "123": { name: "123云盘", short: "123" },
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

const RESOURCE_ORDER = ["baidu", "115", "123", "xunlei", "quark", "aliyun", "uc", "guangya", "tianyi", "magnet", "ed2k", "others"];

// 不夜容器网盘 key(如 quark/a115/a189/ali)与聚影资源类型的对应提示
const DRIVE_KEY_HINTS = {
  baidu: ["baidu", "百度"],
  aliyun: ["ali", "aliyun", "alipan", "阿里"],
  quark: ["quark", "夸克"],
  tianyi: ["a189", "189", "tianyi", "天翼"],
  "115": ["a115", "115"],
  xunlei: ["xunlei", "thunder", "迅雷"],
  "123": ["a123", "123"],
  pikpak: ["pikpak"],
  mobile: ["a139", "139", "mobile", "cmcc", "移动"],
  guangya: ["guangya", "光鸭"],
  uc: ["uc"],
};

function normalizeDriveType(raw) {
  const value = String(raw || "").toLowerCase().trim();
  if (!value) return "";
  if (value.includes("baidu") || value.includes("百度")) return "baidu";
  if (
    value.includes("aliyun") ||
    value.includes("alipan") ||
    value === "ali" ||
    value.startsWith("ali") ||
    value.includes("阿里")
  ) {
    return "aliyun";
  }
  if (value.includes("quark") || value.includes("夸克")) return "quark";
  if (value.includes("tianyi") || value.includes("189") || value.includes("天翼")) return "tianyi";
  if (value.includes("115")) return "115";
  if (value.includes("xunlei") || value.includes("thunder") || value.includes("迅雷")) return "xunlei";
  if (value.includes("123")) return "123";
  if (value.includes("pikpak")) return "pikpak";
  if (value.includes("mobile") || value.includes("139") || value.includes("移动")) return "mobile";
  if (value.includes("guangya") || value.includes("光鸭")) return "guangya";
  if (value.includes("magnet") || value.includes("磁力")) return "magnet";
  if (value.includes("ed2k") || value.includes("电驴")) return "ed2k";
  if (value.includes("uc")) return "uc";
  return "others";
}

// 不夜容器 drive.key -> 聚影资源类型
function driveKeyToType(key) {
  const value = String(key || "").toLowerCase().trim();
  if (!value) return "";
  for (const [type, hints] of Object.entries(DRIVE_KEY_HINTS)) {
    for (const hint of hints) if (value === String(hint).toLowerCase()) return type;
  }
  for (const [type, hints] of Object.entries(DRIVE_KEY_HINTS)) {
    for (const hint of hints) if (hint.length >= 3 && value.includes(String(hint).toLowerCase())) return type;
  }
  return normalizeDriveType(value) === "others" ? "" : normalizeDriveType(value);
}

function panName(type) {
  const key = normalizeDriveType(type);
  return (PAN_META[key] || PAN_META.others).name;
}

function panPic(type) {
  const key = normalizeDriveType(type);
  return `${ICON_BASE}${ICON_FILES[key] || ICON_FILES.others}`;
}

function resourceName(key, item) {
  if (item && item.resource_type_display) return String(item.resource_type_display);
  const type = normalizeDriveType(key);
  return (PAN_META[type] || PAN_META.others).name;
}

// ==================== 不夜容器网盘 ====================
// 网盘列表:优先取容器运行时最新对象(容器可能在插件加载后才注册网盘)
function listDrives() {
  const server = store.server;
  if (server && Array.isArray(server.drives) && server.drives.length) return server.drives;
  return Array.isArray(store.drives) ? store.drives : [];
}

function findDrive(flag, shareURL) {
  const drives = listDrives();
  const text = String(flag || "");
  if (text) {
    const hit = drives.find((drive) => {
      const key = String(drive.key || "").toLowerCase();
      return key && text.toLowerCase().startsWith(key);
    });
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

function findDriveByType(type) {
  const drives = listDrives();
  const wanted = normalizeDriveType(type);
  return drives.find((drive) => normalizeDriveType(drive.key) === wanted) || null;
}

// 解析 drive.getVod 返回的 vod_play_url("名$播放ID#名$播放ID$$$名$播放ID")
function parsePlayEpisodes(raw) {
  const out = [];
  const seen = new Set();
  for (const source of String(raw || "").split("$$$")) {
    for (const episode of String(source).split("#")) {
      const text = String(episode || "").trim();
      if (!text) continue;
      const index = text.indexOf("$");
      if (index < 0) continue;
      const name = text.slice(0, index).trim();
      const id = text.slice(index + 1).trim();
      if (!id || seen.has(id)) continue;
      seen.add(id);
      out.push({ name: name || "播放", id });
    }
  }
  return out;
}

// 带超时的 Promise:网盘 drive.getVod 卡死时不能拖垮详情/播放
function withTimeout(promise, ms, label) {
  let timer = null;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label || "操作"}超时(${Math.round(ms / 1000)}秒)`)), ms);
    if (timer && typeof timer.unref === "function") timer.unref();
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (timer) clearTimeout(timer);
  });
}

// 清掉分享枚举缓存(成功缓存 + 失败缓存),让下次重新解析
async function clearShareCache(shareURL) {
  const key = `jy:share:${md5(shareURL)}`;
  memCache.delete(key);
  memCache.delete(`${key}:fail`);
  try {
    // 写 null(软删):读取侧把 null/"" 都当未命中,清完能立刻重新枚举
    await cacheSet(key, null, 1);
    await cacheSet(`${key}:fail`, null, 1);
  } catch (error) {
    /* 忽略缓存清理失败 */
  }
}

// 用不夜容器的网盘 drive 枚举分享内的可播放分集
// ==================== 百度网盘分享匿名直连枚举(照页面同款 H5: verify 换 BDCLND -> yunData 拿 shareid/uk -> /share/list) ====================
// 背景: SDK 内部"分享信息"调用在百度侧偶发 errno=-21 持续失败(同一分享 verify 实测 errno=0 活着),
//   列表取不到就出"资源获取失败(瞬时原因)"占位。本节在插件侧按页面同款链路自己枚举:
// 目录导航与页面一致: 根 = root=1;子目录 = dir=<sharelink 形式完整路径> 且不带 root 参数——
//   实测 root=1 会把 dir 忽略,dir 带 owner 形式路径或纯 fs_id 都报 errno=2;
//   根层子目录路径按页面嵌入 file_list 同款拼 /sharelink{uk}-{fs_id}/{name}(实测可列),深层用列表返回的 sharelink 路径。
// 错误口径: -7/-8/空分享抛死分享原话(直连判定为准,详情照常判死);-9 提取码不正确、-3 目录未命中
//   (不带服务端原文防"文件不存在"字样误判死)等其余一律瞬时——loadShareEpisodes 捕获后回退容器 drive(死分享/提取码直抛,由外层 failKey 落占位卡)。
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
    httpsAgent: INSECURE_HTTPS_AGENT,
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
  log("info", `聚影 百度直连枚举成功: ${videos.length} 个视频`);
  return videos;
}

// 会话短缓存: verify+分享页两连击在详情/播放间复用;force=true 绕过缓存强刷(票据过期 9019/-11 时用)
async function baiduSessionCached(shareURL, info, force) {
  const key = `jy:bdsess:${shareURL}`;
  if (!force) {
    try {
      const cached = await cacheGet(key);
      if (cached && typeof cached === "object" && cached.shareid && cached.uk) return cached;
    } catch (error) {
      // 缓存读失败按未命中处理
    }
  }
  const session = await baiduAnonSession(info);
  try {
    await cacheSet(key, session, BAIDU_SESSION_TTL);
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
  const key = `jy:bdsign:${shareURL}`;
  if (!force) {
    try {
      const cached = await cacheGet(key);
      if (cached && typeof cached === "object" && cached.sign && cached.ts) return cached;
    } catch (error) {
      // 缓存读失败按未命中处理
    }
  }
  const signed = await baiduStreamSigned(session);
  try {
    await cacheSet(key, signed, BAIDU_SIGN_TTL);
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
  log("info", `聚影 百度流媒体取链成功(fid=${fid}, ${BAIDU_STREAM_TYPE})`);
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


function safeEpisodeName(value) {
  const text = String(value || "")
    .replace(/[$#\r\n\t]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return truncateText(text || "资源", 120);
}

async function loadShareEpisodes(shareURL) {
  // 123镜像域名兜底改写(缓存键也用改写后的链接,避免同分享两套缓存)
  shareURL = normalizePanShareURL(shareURL);
  const key = `jy:share:${md5(shareURL)}`;
  // 失败也短暂缓存,避免同一批详情里反复撞同一个坏链接
  const failKey = `${key}:fail`;
  const failHit = memGet(failKey);
  if (failHit) throw new Error(String(failHit));
  return cachedValue(key, SHARE_CACHE_EX, async () => {
    // 百度分享优先匿名直连枚举(容器百度"分享信息"偶发 -21 故障时 getVod 必挂);死分享/提取码直抛(外层 failKey 落占位),瞬时回退容器
    if (isBaiduShareURL(shareURL)) {
      try {
        const episodes = await baiduDirectEpisodes(shareURL);
        if (episodes.length) return { drive: "baidu", name: "", pic: "", content: "", episodes };
      } catch (error) {
        const message = errorText(error);
        if (isDeadShareError(message) || /提取码不正确|需要提取码/.test(message)) throw error;
        // 会话票据过期(-11): 作废会话缓存,下次换新会话
        if (/校验票据失效|errno=-11/.test(message)) await cacheSet(`jy:bdsess:${shareURL}`, "", 5);
        log("warn", `聚影 百度直连枚举失败,回退容器: ${truncateText(message, 300)}`);
      }
    }
    let lastError = null;
    // 1) 容器 drive 优先(非123网盘也走这条);123容器枚举常为空/失败
    const drive = findDrive("", shareURL);
    if (drive) {
      let vod = null;
      try {
        vod = await withTimeout(Promise.resolve(drive.getVod(shareURL)), ENUM_TIMEOUT_MS, "网盘解析");
      } catch (error) {
        lastError = error;
      }
      if ((!vod || !vod.vod_play_url) && hasExtractCode(shareURL)) {
        try {
          vod = await withTimeout(Promise.resolve(drive.getVod(stripExtractCode(shareURL))), ENUM_TIMEOUT_MS, "网盘解析");
        } catch (error) {
          lastError = error;
        }
      }
      const containerEpisodes = parsePlayEpisodes(vod && vod.vod_play_url);
      // 回填容器选集小标题的文件大小(仅对123直连有数据源;UC容器暂依赖容器端)
      let decoratedEpisodes = containerEpisodes;
      if (containerEpisodes.length && isPan123URL(shareURL)) {
        try {
          const direct = await pan123DirectEpisodes(shareURL);
          // 从 direct 选集 id 解码原始文件名->尺寸,再按原文件名回填容器选集
          const directMap = {};
          for (const ep of direct) {
            const rawIdStr = String(ep.id || "");
            if (rawIdStr.startsWith("p123:")) {
              try {
                const meta = decodePan123Episode(rawIdStr);
                if (meta && meta.name) directMap[String(meta.name || "").trim()] = meta.size || 0;
              } catch (e) { /* 忽略 */ }
            }
          }
          decoratedEpisodes = containerEpisodes.map((ep) => {
            const baseName = String(ep.name || "").trim();
            const sz = directMap[baseName] || 0;
            if (!(sz > 0)) return ep;
            return { ...ep, name: `[${formatFileSize(sz)}] ${baseName}` };
          });
        } catch (e) {
          // 无数据时静默退化到原名
          decoratedEpisodes = containerEpisodes;
        }
      }
      if (decoratedEpisodes.length) {
        return {
          drive: String(drive.key || ""),
          name: String((vod && vod.vod_name) || "").trim(),
          pic: String((vod && vod.vod_pic) || "").trim(),
          content: String((vod && vod.vod_content) || "").trim(),
          episodes: decoratedEpisodes,
        };
      }
      if (!lastError) lastError = new Error("容器网盘未返回可播放文件");
    } else {
      lastError = new Error(`未配置该网盘: ${truncateText(shareURL, 70)}`);
    }
    // 2) 123直连枚举兜底(容器123 drive实测从不出分集;直连走123官方分享列表API,匿名可读)
    if (isPan123URL(shareURL)) {
      try {
        const direct = await pan123DirectEpisodes(shareURL);
        if (direct.length) return { drive: "123", name: "", pic: "", content: "", episodes: direct };
      } catch (error) {
        log("warn", `聚影 123直连枚举兜底也失败: ${error.message}`);
        lastError = error;
      }
    }
    throw lastError || new Error("分享中未找到可播放的文件");
  }).catch((error) => {
    memSet(failKey, errorText(error), ENUM_FAIL_EX);
    throw error;
  });
}

// ==================== 资源线路分组 ====================
function groupByResourceType(list) {
  const groups = {};
  for (const item of Array.isArray(list) ? list : []) {
    const key = resourceType(item);
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return groups;
}

function orderedGroupKeys(groups) {
  const keys = Object.keys(groups || {}).filter((key) => (groups[key] || []).length);
  const ordered = [];
  // 先按容器里已配置网盘的顺序,再按聚影常用类型顺序
  for (const drive of listDrives()) {
    const type = normalizeDriveType(drive.key);
    if (!type) continue;
    for (const key of keys) {
      if (normalizeDriveType(key) === type && !ordered.includes(key)) ordered.push(key);
    }
  }
  for (const type of RESOURCE_ORDER) {
    for (const key of keys) {
      if (normalizeDriveType(key) === type && !ordered.includes(key)) ordered.push(key);
    }
  }
  for (const key of keys) if (!ordered.includes(key)) ordered.push(key);
  // 详情页网盘排序:DRIVE_ORDER 里靠前的类型整体提前(网盘 key 如 quark/a115 也能匹配)
  const rank = (key) => {
    const type = normalizeDriveType(key).toLowerCase();
    const idx = DRIVE_ORDER.findIndex((item) => item && (type === item || type.includes(item) || item.includes(type)));
    return idx < 0 ? DRIVE_ORDER.length + RESOURCE_ORDER.indexOf(type) : idx;
  };
  const pos = new Map(ordered.map((key, index) => [key, index]));
  return ordered.slice().sort((a, b) => rank(a) - rank(b) || pos.get(a) - pos.get(b));
}

// ==================== TMDB 补全 ====================
const tmdbState = { mirrorDownUntil: 0, hostDownUntil: 0, proxyDownUntil: 0, proxyFails: 0, failStreak: 0, lastWarnAt: 0 };

function warnThrottled(message, gapMs = 60000) {
  const now = Date.now();
  if (now - tmdbState.lastWarnAt < gapMs) return;
  tmdbState.lastWarnAt = now;
  log("warn", message);
}

function tmdbKey(query) {
  return `jy:tmdb:${query}`;
}

function parseProxyObject(raw) {
  try {
    const parsed = new URL(String(raw));
    const out = { host: parsed.hostname, port: parseInt(parsed.port || (parsed.protocol === "https:" ? "443" : "80"), 10) };
    if (parsed.username) out.auth = `${decodeURIComponent(parsed.username)}:${decodeURIComponent(parsed.password || "")}`;
    return out;
  } catch (error) {
    return null;
  }
}

async function tmdbFetch(path, params, totalTimeout = TMDB_TOTAL) {
  const started = Date.now();
  const proxyObj = BUILTIN_TMDB_PROXY ? parseProxyObject(BUILTIN_TMDB_PROXY) : null;
  const proxyUsable = Boolean(proxyObj) && Date.now() > tmdbState.proxyDownUntil;
  const attempts = [];
  const mirror = TMDB_MIRROR;
  const useMirror = Boolean(mirror) && Date.now() > tmdbState.mirrorDownUntil;
  const useHost = Date.now() > tmdbState.hostDownUntil;
  // 顺序:镜像(若配置且健康) -> 官方 api.tmdb.org 优先(api.themoviedb.org 在部分网络被 DNS 污染)
  if (useMirror) {
    attempts.push({ base: `${mirror}/3`, proxy: null, timeout: TMDB_MIRROR_TIMEOUT, tag: "mirror" });
  }
  if (useHost) {
    for (const host of TMDB_HOSTS) {
      if (proxyUsable) attempts.push({ base: `https://${host}/3`, proxy: proxyObj, timeout: TMDB_PROXY_TIMEOUT, tag: `${host}+proxy` });
      attempts.push({ base: `https://${host}/3`, proxy: null, timeout: TMDB_TIMEOUT, tag: host });
    }
  }

  for (const attempt of attempts) {
    const remain = totalTimeout - (Date.now() - started);
    if (remain < 500) break;
    const timeout = Math.min(attempt.timeout, remain);
    try {
      const res = await axios({
        url: `${attempt.base}${path}`,
        method: "GET",
        params: Object.assign({ api_key: TMDB_API_KEY, language: "zh-CN", include_adult: "false" }, params || {}),
        timeout,
        httpsAgent: new https.Agent({ rejectUnauthorized: false, keepAlive: true }),
        proxy: attempt.proxy || false,
        headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36" },
        validateStatus: (s) => s >= 200 && s < 300,
      });
      if (res.data && typeof res.data === "object") {
        tmdbState.failStreak = 0;
        tmdbState.proxyFails = 0;
        return { status: res.status, data: res.data };
      }
    } catch (error) {
      const status = error.response ? error.response.status : 0;
      if (status === 404) return { status: 404, data: null };
      if (status === 429) {
        log("warn", "TMDB 触发限流,短时间跳过");
        tmdbState.mirrorDownUntil = Date.now() + TMDB_MIRROR_DOWN * 1000;
        tmdbState.hostDownUntil = Date.now() + TMDB_DOWN * 1000;
        break;
      }
      // 镜像网络失败:立刻冷却,避免每次刮削都先等镜像超时
      if (attempt.tag === "mirror") {
        tmdbState.mirrorDownUntil = Date.now() + TMDB_MIRROR_DOWN * 1000;
        warnThrottled(`TMDB 镜像不可用,已冷却${TMDB_MIRROR_DOWN}秒: ${errorText(error)}`);
      }
      // 代理连不上(网关错误/超时):连续失败后冷却代理,后续走直连
      if (attempt.proxy && (!status || status >= 500)) {
        tmdbState.proxyFails += 1;
        if (tmdbState.proxyFails >= 2) {
          tmdbState.proxyDownUntil = Date.now() + TMDB_MIRROR_DOWN * 1000;
          warnThrottled("TMDB 代理连续失败,已冷却,改走直连");
        }
      }
    }
  }
  tmdbState.failStreak += 1;
  if (tmdbState.failStreak >= TMDB_FAIL_STREAK) {
    tmdbState.hostDownUntil = Date.now() + TMDB_DOWN * 1000;
    tmdbState.failStreak = 0;
    warnThrottled(`TMDB 全线路失败,已冷却${TMDB_DOWN}秒`);
  }
  return { status: 0, data: null };
}

function cleanQueryName(name) {
  let text = String(name || "")
    .replace(/【.*?】/g, " ")
    .replace(/[（(][^（()）]*[20-3][0-9]{3}[^（()）]*[)）]/g, " ")
    .replace(/(19|20)\d{2}/g, " ")
    .replace(/第[0-9一二三四五六七八九十百千]+季/g, " ")
    .replace(/第[0-9一二三四五六七八九十百千]+部/g, " ")
    .replace(/S\d{1,2}(?!.*\d)/gi, " ")
    .replace(/特别篇|特别版|剧场版|TV版|修复版|导演剪辑版/gi, " ")
    .replace(/中字|双语|国粤|国语|粤语|高清|蓝光|WEB-DL|BluRay|4K|HDR|杜比|未删减/gi, " ")
    .replace(/[·!！?？。，,、:：;；'"“”‘’~`@#$%^&*+=|\\/<>[\]{}()（）\s]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
  return text.slice(0, 60);
}

async function searchTmdb(query) {
  const cleaned = cleanQueryName(query);
  if (!cleaned || !TMDB_ENABLED || !TMDB_API_KEY) return null;
  const key = tmdbKey(`search|${cleaned}`);
  const hit = await cacheGet(key);
  // 负缓存存的是哨兵 {miss:1},识别后按未命中返回(不能把 null 当命中,否则负缓存失效)
  if (hit !== null) return hit && hit.miss ? null : hit;
  const res = await tmdbFetch("/search/multi", { query: cleaned, page: 1 });
  const pick = pickTmdbResult(res.data, cleaned);
  await cacheSet(key, pick || { miss: 1 }, pick ? TMDB_HIT_EX : TMDB_MISS_EX);
  return pick;
}

function pickTmdbResult(data, queryName) {
  // 只保留电影/剧集,排除 person(person 有 name 会被误选,后续按 movie 查详情必 404)
  const results = (data && Array.isArray(data.results) ? data.results : []).filter(
    (item) => item && (item.media_type === "movie" || item.media_type === "tv")
  );
  if (!results.length) return null;
  const q = cleanQueryName(queryName).toLowerCase();
  const scored = results.map((item) => {
    const title = String(item.title || item.name || "").toLowerCase();
    // 标题相似度权重高,其次热度与评分
    const match = q && title ? (title.includes(q) || q.includes(title) ? 2 : 0) : 0;
    return { item, score: match * 100 + (item.popularity || 0) * 0.1 + (item.vote_average || 0) };
  });
  scored.sort((a, b) => b.score - a.score);
  const top = scored[0].item;
  const mediaType = top.media_type === "tv" ? "tv" : "movie";
  return { tmdb_id: top.id, media_type: mediaType, name: top.title || top.name || "", year: (top.release_date || top.first_air_date || "").slice(0, 4) };
}

function tmdbImagePath(path) {
  const value = String(path || "");
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  const size = TMDB_IMAGE_SIZE || "w500";
  const rel = value.startsWith("/") ? value : `/${value}`;
  if (TMDB_IMAGE_MIRROR) return `${TMDB_IMAGE_MIRROR}/t/p/${size}${rel}`;
  return `https://image.tmdb.org/t/p/${size}${rel}`;
}

async function scrapeTmdb(entry) {
  if (!TMDB_ENABLED || !TMDB_API_KEY || !entry || !entry.tmdb_id) return null;
  const mediaType = entry.media_type === "tv" ? "tv" : "movie";
  const key = tmdbKey(`detail|${mediaType}|${entry.tmdb_id}`);
  const cached = await cacheGet(key);
  if (cached !== null) return cached && cached.miss ? null : cached;
  const res = await tmdbFetch(`/${mediaType}/${entry.tmdb_id}`, { append_to_response: "credits" });
  const data = res.data || null;
  await cacheSet(key, data || { miss: 1 }, data ? TMDB_HIT_EX : TMDB_MISS_EX);
  return data;
}

function applyTmdbPayload(vod, detail) {
  if (!vod || !detail) return;
  const pic = detail.poster_path || detail.backdrop_path || "";
  if (pic && (!vod.vod_pic || vod.vod_pic === panPic("others"))) vod.vod_pic = tmdbImagePath(pic);
  // 不写 detail.status(Released 等英文)到 vod_remarks,避免给用户展示英文
  const genres = Array.isArray(detail.genres) ? detail.genres.map((g) => g.name).filter(Boolean).join("/") : "";
  if (genres) vod.vod_genre = vod.vod_genre || genres;
  const overview = String(detail.overview || "").trim();
  if (overview && (!vod.vod_content || vod.vod_content.length < overview.length)) {
    vod.vod_content = overview;
  }
  const crew = (detail.credits && Array.isArray(detail.credits.crew) ? detail.credits.crew : []) || [];
  const director = crew.filter((c) => c && c.job === "Director").map((c) => c.name).filter(Boolean).join("、");
  if (director && !vod.vod_director) vod.vod_director = director;
  const cast = ((detail.credits && detail.credits.cast) || []).slice(0, 12).map((c) => c.name).filter(Boolean);
  if (cast.length && !vod.vod_actor) vod.vod_actor = cast.join("、");
  const score = detail.vote_average ? Number(detail.vote_average) : 0;
  if (score && !vod.vod_score) vod.vod_score = Math.round(score * 10) / 10;
}

// 优先使用站点自带的 tmdb_id 直查(免搜索、免猜),否则按片名搜索
async function loadTmdbFor(vod, queryName, meta) {
  if (!TMDB_ENABLED || !vod) return;
  try {
    let entry = null;
    const tmdbId = meta && (meta.tmdb_id || meta.tmdbId);
    const mediaType = meta && (meta.tmdb_media_type || meta.media_type);
    if (tmdbId) {
      entry = { tmdb_id: String(tmdbId), media_type: mediaType === "tv" ? "tv" : "movie" };
    } else if (queryName) {
      entry = await searchTmdb(queryName);
    }
    if (!entry) return;
    const detail = await scrapeTmdb(entry);
    if (detail) applyTmdbPayload(vod, detail);
  } catch (error) {
    warnThrottled(`TMDB 补全失败: ${error.message}`, 120000);
  }
}

// ==================== 详情构建 ====================
function withShareLink(desc, url) {
  // 先剥掉已有的"分享链接:"前缀,避免二次调用拼出重复前缀
  let body = String(desc || "").trim();
  if (/^分享链接\s*[:：]/.test(body)) {
    const rest = body.replace(/^分享链接\s*[:：]\s*/, "");
    const nl = rest.indexOf("\n");
    body = (nl >= 0 ? rest.slice(nl + 1) : "").trim();
  }
  const link = String(url || "").trim();
  if (!SHOW_SHARE_URL || !link) return body;
  // 分享链接放简介最前面,其余简介(影片剧情)完整排在后面
  return body ? `分享链接: ${truncateText(link, 160)}\n${body}` : `分享链接: ${truncateText(link, 160)}`;
}

function remarksOf(resources) {
  const counts = {};
  for (const item of Array.isArray(resources) ? resources : []) {
    const key = normalizeDriveType(resourceType(item));
    counts[key] = (counts[key] || 0) + 1;
  }
  const parts = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => `${(PAN_META[key] || PAN_META.others).short}${count}`);
  return truncateText(parts.join(" "), 40);
}

function toVod(base) {
  return Object.assign(
    {
      vod_id: "",
      vod_name: "",
      vod_pic: "",
      vod_remarks: "",
      vod_year: "",
      vod_area: "",
      vod_lang: "",
      vod_actor: "",
      vod_director: "",
      vod_genre: "",
      vod_content: "",
      vod_tag: "",
      vod_score: 0,
      vod_play_from: "",
      vod_play_url: "",
    },
    base || {}
  );
}

function optionValues(list, nameKey, valueKey) {
  const out = [];
  const seen = new Set();
  for (const item of Array.isArray(list) ? list : []) {
    if (!item || typeof item !== "object") continue;
    const name = String(
      item[nameKey] || item.display_name || item.label || item.resource_type_display || item[valueKey] || ""
    ).trim();
    const value = String(item[valueKey] || item.slug || item.key || item.resource_type || name).trim();
    if (name && value && !seen.has(value)) {
      seen.add(value);
      out.push({ name, value });
    }
  }
  return out;
}

// 首页分类筛选:结构与 聚影.js 保持一致(站点接口同源)
// 类型选项与 filters 键都从站点 type_stats 动态生成(实测 type=documentary 返回0,真实 key 是 doc)
function buildTypeOptions(source) {
  const stats = Array.isArray(source && source.type_stats) ? source.type_stats : [];
  const seen = new Set();
  const out = [{ name: "全部", value: "" }];
  for (const item of stats) {
    const key = String((item && item.key) || "").trim();
    const name = String((item && item.name) || key).trim();
    if (!key || !name || seen.has(key)) continue;
    seen.add(key);
    out.push({ name, value: key });
  }
  if (out.length === 1) {
    out.push(
      { name: "电影", value: "movie" },
      { name: "电视剧", value: "tv" },
      { name: "动漫", value: "anime" },
      { name: "纪录片", value: "doc" },
      { name: "综艺", value: "variety" },
      { name: "其他", value: "other" }
    );
  }
  return out;
}

function buildTypeIds(source, options) {
  const types = options || buildTypeOptions(source);
  return ["all"].concat(types.map((item) => item.value).filter((value) => value));
}

function buildFilters(overviewData) {
  const source = overviewData && typeof overviewData === "object" ? overviewData : {};
  const years = [{ name: "全部", value: "" }];
  const yearStats = Array.isArray(source.year_stats) ? source.year_stats : [];
  if (yearStats.length) {
    for (const item of yearStats.slice(0, 40)) {
      const key = String((item && (item.key || item.year)) || "").trim();
      if (key) years.push({ name: key, value: key });
    }
  } else {
    const currentYear = new Date().getFullYear();
    for (let year = currentYear + 2; year >= 1990; year -= 1) years.push({ name: String(year), value: String(year) });
  }

  const types = buildTypeOptions(source);
  const regions = [{ name: "全部", value: "" }].concat(optionValues(source.region_stats, "name", "key")).slice(0, 81);
  const tags = [{ name: "全部", value: "" }].concat(optionValues(source.tags, "name", "slug")).slice(0, 121);
  const categories = [{ name: "全部", value: "" }]
    .concat(optionValues(source.categories, "name", "slug"))
    .slice(0, 121);
  let disks = optionValues(source.resource_type_stats, "name", "key");
  if (!disks.length) {
    disks = [
      { name: "百度网盘", value: "baidu" },
      { name: "115网盘", value: "115" },
      { name: "123云盘", value: "123" },
      { name: "迅雷云盘", value: "xunlei" },
      { name: "阿里云盘", value: "aliyun" },
      { name: "磁力", value: "MagnetLink" },
    ];
  }
  const diskValues = [{ name: "全部", value: "" }].concat(disks).slice(0, 81);
  const sort = [
    { name: "最新", value: "-created_at" },
    { name: "最多资源", value: "-resource_count" },
    { name: "年份新", value: "-release_year" },
    { name: "热度", value: "-views" },
  ];

  // OK影视/FongMi 筛选格式:{key,name,value:[{n,v}]}(value 为选项数组,首项"全部"v="")
  const toGroup = (key, name, items) => ({
    key,
    name,
    value: (items || []).map((item) => ({ n: String(item.name), v: String(item.value) })),
  });

  const groups = [
    toGroup("type", "类型", types),
    toGroup("region", "国家", regions),
    toGroup("year", "年份", years),
    toGroup("tag", "标签", tags),
    toGroup("category", "分类", categories),
    toGroup("resource_type", "网盘", diskValues),
    toGroup("ordering", "排序", sort),
  ];

  const filters = {};
  for (const typeId of buildTypeIds(source, types)) {
    // "类型"筛选只在影视库(all)下有意义:具体分类(电影/剧集...)下用户选类型会被忽略(分类已限定),
    // 干脆不下发 type 组,避免出现"选了没反应"的筛选项
    filters[typeId] = typeId === "all" ? groups : groups.filter((group) => group.key !== "type");
  }
  return filters;
}

// 详情页线路名 -> 不夜容器 drive
function buildDriveGroupCards(groups, keys) {
  const out = [];
  for (const key of keys) {
    const items = groups[key] || [];
    if (!items.length) continue;
    const type = normalizeDriveType(key);
    out.push({ key, type, title: resourceName(key, items[0]), pic: panPic(type), count: items.length, items });
  }
  return out;
}

// 解析状态:apiBudget=access API 预算;mid 用于播放失败后的资源刷新
function newPlayState(mid, retried) {
  return {
    mid: String(mid || ""),
    apiBudget: MAX_ACCESS_PER_GROUP,
    resolveFailed: 0,
    deferred: 0,
    shareOk: 0,
    shareFail: 0,
    resolveRetried: Boolean(retried),
    firstShare: "",
  };
}

// 把线路分组转换成 vod_play_from / vod_play_url
// 网盘线路:解析分享 -> drive.getVod 枚举文件,每个文件一条选集(播放ID带分享URL可回退匹配);
// 直链/磁力:直接成条;超出解析预算的网盘资源退化为"分享整体"单条(播放时再枚举首文件)
async function buildPlaySources(groupCards, state) {
  const from = [];
  const url = [];
  // 枚举时间预算按整次详情共享(否则每条线路各给一次,线路多时详情会拖到几十秒)
  const enumStart = Date.now();
  for (const card of groupCards) {
    // apiBudget 按线路重置:每条网盘线路都有机会出分集,避免多网盘影片只有第一条线路枚举
    if (state) state.apiBudget = MAX_ACCESS_PER_GROUP;
    const parts = [];
    const seen = new Set();
    const push = (name, id) => {
      if (!id || seen.has(id) || parts.length >= MAX_EPISODES) return;
      seen.add(id);
      parts.push(`${clean(name)}$${id}`);
    };
    const panUrls = [];

    for (const item of card.items) {
      if (parts.length >= MAX_EPISODES) break;
      const mt = resourceType(item);
      if (isLazyResourceType(item)) {
        const raw = normalizePlayUrl(item.share_link || item.target || item.raw_share_link || "");
        const magnet = extractMagnet(raw) || (isMagnetUrl(raw) ? raw : "");
        const meta = { k: magnet ? "magnet" : "lazy", r: compactResource(item), u: magnet || raw, f: driveKeyToType(mt), mt };
        // 补 rid/mid,播放失败时 recoverShareFromResource 才能刷新资源链接自愈
        if (item.id) meta.rid = item.id;
        if (state && state.mid) meta.mid = state.mid;
        push(item.resource_description || item.title || panName(mt), encodeId("p", meta));
        continue;
      }
      const lazyId = (extra) =>
        encodeId("p", Object.assign({ k: "lazy", r: compactResource(item), u: "", f: driveKeyToType(mt), mt }, extra || {}));
      const lazyExtra = {};
      if (item.id) lazyExtra.rid = item.id;
      if (state && state.mid) lazyExtra.mid = state.mid;
      const needsApi = !item.target && !item.share_link && !item.raw_share_link && item.id && item.access_ticket;
      if (needsApi && state) {
        // access 预算/时间双重约束:超了不丢资源,降级成"播放时解析"(lazy 会补 access)
        if (state.apiBudget <= 0 || Date.now() - enumStart > ENUM_BUDGET_MS) {
          state.deferred += 1;
          push(item.resource_description || item.title || panName(mt), lazyId(lazyExtra));
          continue;
        }
      }
      let shared = "";
      try {
        shared = await accessResource(item);
      } catch (error) {
        log("warn", `聚影 解析资源失败: ${error.message}`);
      }
      if (needsApi && state) state.apiBudget -= 1;
      if (!shared) {
        if (state) state.resolveFailed += 1;
        // 解析失败也保留入口,播放时重试 access,避免详情里直接少一整条资源
        push(item.resource_description || item.title || panName(mt), lazyId(lazyExtra));
        continue;
      }
      if (isRawPlayable(shared)) {
        push(item.resource_description || item.title || panName(mt), encodeId("p", { k: "direct", u: shared, mt }));
      } else if (isPanShareUrl(shared) || isPanResourceKey(mt)) {
        if (state && !state.firstShare) state.firstShare = shared;
        panUrls.push({ item, mt, shared });
      } else {
        push(item.resource_description || item.title || panName(mt), lazyId(Object.assign({ u: shared }, lazyExtra)));
      }
    }

    // 网盘分享枚举文件:受单条线路总时间预算约束,超预算的退化为"播放时再枚举"
    const enumCount = Math.max(MAX_ACCESS_PER_GROUP, 4);
    const targets = panUrls.slice(0, enumCount);
    const rest = panUrls.slice(enumCount);
    for (let i = 0; i < targets.length; i++) {
      const row = targets[i];
      if (Date.now() - enumStart > ENUM_BUDGET_MS) {
        rest.push(...targets.slice(i));
        break;
      }
      let loaded = null;
      let error = null;
      try {
        loaded = await loadShareEpisodes(row.shared);
      } catch (err) {
        error = err;
      }
      const label = row.item.resource_description || row.item.title || panName(row.mt);
      if (loaded && loaded.episodes.length) {
        const flag = (findDriveByType(row.mt) || findDrive("", row.shared) || {}).key || driveKeyToType(row.mt) || row.mt;
        for (const ep of loaded.episodes) {
          const meta = { k: "ep", i: ep.id, f: flag, u: row.shared, mt: row.mt, n: ep.name || "" };
          if (row.item.id) meta.rid = row.item.id;
          if (state && state.mid) meta.mid = state.mid;
          push(ep.name || label, encodeId("p", meta));
        }
        if (state) state.shareOk += 1;
      } else {
        if (state) state.shareFail += 1;
        const meta = { k: "pan", u: row.shared, f: driveKeyToType(row.mt) || row.mt, mt: row.mt };
        if (row.item.id) meta.rid = row.item.id;
        if (state && state.mid) meta.mid = state.mid;
        push(label, encodeId("p", meta));
        log("warn", `聚影 分享枚举失败(${errorText(error || "未知错误")}): ${truncateText(row.shared, 70)}`);
      }
    }
    for (const row of rest) {
      const meta = { k: "pan", u: row.shared, f: driveKeyToType(row.mt) || row.mt, mt: row.mt };
      if (row.item.id) meta.rid = row.item.id;
      if (state && state.mid) meta.mid = state.mid;
      push(row.item.resource_description || row.item.title || panName(row.mt), encodeId("p", meta));
    }

    if (!parts.length) continue;
    from.push(clean(card.title));
    url.push(parts.join("#"));
  }
  if (state && (state.resolveFailed || state.deferred)) log("info", `聚影 链接解析: ${state.resolveFailed}个失败, ${state.deferred}个延后(预算/限流)`);
  return { from: from.join("$$$"), url: url.join("$$$") };
}

// mid=影片ID;rawId=原始编码ID(原样返回给前端);onlyGroup=只保留某网盘分组的线路
async function buildDetailByMid(mid, rawId, onlyGroup) {
  mid = String(mid || "");
  if (!mid) return null;
  const hintData = decodeId(rawId || "")[1] || {};
  const hint = hintData.n || "";
  const hintPic = hintData.p || "";
  const detailData = await movieDetailApi(mid);
  const meta = pickMovieMeta(detailData);
  const name = String(meta.title || meta.name || "").trim() || hint || "未知影片";
  const pics = [meta.stills_poster, meta.cover, meta.cover_url, meta.backdrop_url, meta.poster, meta.poster_path, meta.backdrop_path].find(Boolean) || hintPic;
  const pic = /^https?:\/\//i.test(String(pics)) ? String(pics) : panPic("others");
  const vod = toVod({
    vod_id: rawId || encodeId("m", { mid, n: name }),
    vod_name: name,
    vod_pic: pic,
    vod_remarks: truncateText(meta.tagline || meta.status || "", 24),
    vod_year: String(meta.year || meta.release_date || meta.first_air_date || "").slice(0, 4),
    vod_area: joinNames(meta.region || meta.regions || meta.country),
    vod_lang: joinNames(meta.language || meta.languages),
    vod_actor: joinNames(meta.actors || meta.cast || meta.actor),
    vod_director: joinNames(meta.director || meta.directors),
    vod_genre: joinNames(meta.genre || meta.genres || meta.category),
    vod_content: withShareLink(meta.summary || meta.description || meta.overview, ""),
    vod_score: Number(meta.vote_average || meta.score || 0) || 0,
  });
  vod.vod_tag = String(meta.tags || meta.tag || "");
  // 站点缺海报/简介/演职员时用 TMDB 补全(自带 tmdb_id 直查):与资源拉取并行,不拖慢详情打开
  const missingMeta =
    !vod.vod_pic ||
    vod.vod_pic === panPic("others") ||
    !vod.vod_content ||
    (!vod.vod_actor && !vod.vod_director);
  const tmdbTask = missingMeta ? loadTmdbFor(vod, hint || name, meta) : null;
  let firstShare = "";
  let resources = await resourceListApi(mid);
  // 站点限流时拿不到资源 ≠ 片库没资源:别渲染"暂无资源"
  const rateLimited = !resources.length && rateLimitRemaining(`/api/app/movie/${mid}/resources/`) > 0;
  if (onlyGroup && resources.length) {
    const filtered = resources.filter((item) => normalizeDriveType(resourceType(item)) === onlyGroup);
    // 分组内一条资源都不剩时回退全量,别让其他网盘的活资源被分组连坐(全灭时出全量总比开天窗好)
    if (filtered.length) resources = filtered;
  }
  if (resources.length) {
    const resourceRemarks = remarksOf(resources);
    if (resourceRemarks) vod.vod_remarks = resourceRemarks;
    const groups = groupByResourceType(resources);
    const keys = orderedGroupKeys(groups);
    const cards = buildDriveGroupCards(groups, keys);
    let state = newPlayState(mid, false);
    let sources = await buildPlaySources(cards, state);
    // 票据过期导致分享全枚举失败(shareOk=0 且有失败):刷新资源列表拿新票据重建一次
    // 注意失败资源也会 push lazy 入口,所以不能只看 sources.from 是否为空
    if (resources.length && state.shareOk === 0 && state.resolveFailed > 0 && !state.resolveRetried) {
      log("info", `聚影 链接解析全失败,刷新资源列表重试: mid=${mid}`);
      await invalidateResourceCache(mid);
      try {
        const fresh = await resourceListApi(mid);
        if (fresh.length) {
          const freshGroups = groupByResourceType(fresh);
          const freshCards = buildDriveGroupCards(freshGroups, orderedGroupKeys(freshGroups));
          state = newPlayState(mid, true);
          sources = await buildPlaySources(freshCards, state);
        }
      } catch (error) {
        log("warn", `聚影 刷新资源列表失败: ${error.message}`);
      }
    }
    if (sources.from) {
      vod.vod_play_from = sources.from;
      vod.vod_play_url = sources.url;
    } else if (resources.length) {
      vod.vod_play_from = "资源";
      vod.vod_play_url = rateLimited ? `刷新重试$${encodeId("e", {})}` : `暂无资源$${encodeId("e", {})}`;
    }
    if (state && state.firstShare) firstShare = state.firstShare;
  } else if (rateLimited) {
    vod.vod_remarks = truncateText("站点限流,稍后刷新", 24);
  }
  if (tmdbTask) await tmdbTask.catch(() => {});
  const intro = vod.vod_content || meta.description || meta.summary || "";
  vod.vod_content = withShareLink(intro, firstShare);
  return vod;
}

// ==================== 列表卡片 ====================
function toMovieCard(x) {
  if (!x || typeof x !== "object") return null;
  const pics = x.cover || x.cover_url || x.backdrop_url || x.poster || "";
  const pic = /^https?:\/\//i.test(String(pics)) ? String(pics) : panPic("others");
  const remarks = (() => {
    const parts = [];
    for (const key of ["movie_type_display", "release_year", "year", "category_name", "region"]) {
      if (x[key] === undefined || x[key] === null || String(x[key]) === "") continue;
      const value = String(x[key]);
      if (!parts.includes(value)) parts.push(value);
    }
    if (x.resource_count !== undefined && x.resource_count !== null) parts.push(`${x.resource_count}源`);
    return truncateText(parts.slice(0, 4).join(" / "), 40);
  })();
  const vod = toVod({
    vod_id: encodeId("m", { mid: String(x.id), n: String(x.title || x.name || ""), p: pic }),
    vod_name: x.title || x.name || "资源",
    vod_pic: pic,
    vod_remarks: remarks,
    vod_content: x.description || x.summary || "",
    vod_year: String(x.release_year || x.year || "").slice(0, 4),
  });
  // 多资源影片标记为目录:点击走 category 返回网盘分组/链接列表(OK影视对 detail 多条目不渲染)
  if (Number(x.resource_count) > 1) {
    vod.type_id = vod.vod_id;
    vod.vod_tag = "folder";
  }
  return vod;
}

function placeholderVod(rawId, name, note, remarks) {
  return toVod({
    vod_id: rawId,
    vod_name: String(name || "暂无资源"),
    vod_pic: panPic("others"),
    vod_remarks: String(remarks || "无资源"),
    vod_content: String(note || ""),
    vod_play_from: "",
    vod_play_url: "",
  });
}

// 站点限流时列表/搜索接口返回空首页,客户端会当成"到底了/没资源";
// 此时插一张占位卡说明是限流冷却,而不是片库为空(仅在结果为空且确在限流时生效)
function rateLimitListPlaceholder(results, path) {
  const list = Array.isArray(results) ? results : [];
  if (list.length || rateLimitRemaining(path) <= 0) return list;
  return [placeholderVod(encodeId("e", {}), "站点限流", "请求过于频繁,稍后刷新重试", "限流冷却中")];
}

// 二级目录条目:每个资源一条
function toResourceCard(item, mid, moviePic, movieName) {
  const key = resourceType(item);
  const id = encodeId("r", Object.assign(compactResource(item), { _mid: String(mid || ""), _pic: moviePic || "", _name: movieName || "" }));
  const name = clean(item.title || item.resource_description || movieName || resourceName(key, item));
  const pic = /^https?:\/\//i.test(String(moviePic || ""))
    ? String(moviePic)
    : /^https?:\/\//i.test(String(item.share_pic || ""))
      ? String(item.share_pic)
      : panPic(key);
  return toVod({
    vod_id: id,
    vod_name: name,
    vod_pic: pic,
    vod_remarks: truncateText(item.resource_description || resourceName(key, item), 30),
    vod_content: withShareLink(item.description || item.resource_description || "", item.share_link),
    type_name: resourceName(key, item),
  });
}

// ==================== 系列合集(站点 /series 页面) ====================
function toSeriesCard(x) {
  if (!x || typeof x !== "object" || !x.id) return null;
  const name = String(x.name || "").trim() || "系列";
  const raw = String(x.cover || "");
  const pic = /^https?:\/\//i.test(raw) ? raw : panPic("others");
  const id = encodeId("s", { sid: String(x.id), n: name, pic });
  const count = parseInt(x.movie_count, 10);
  return toVod({
    vod_id: id,
    vod_name: name,
    vod_pic: pic,
    vod_remarks: Number.isFinite(count) ? `${count}部` : "系列",
    vod_content: String(x.description || ""),
    vod_tag: "folder",
    type_id: id,
    type_name: "系列",
  });
}

async function seriesListPage(page) {
  const data = await apiCall("/api/app/series/", { params: { page, page_size: PAGE_SIZE } });
  const results = Array.isArray(data.results) ? data.results : [];
  const totalPages = parseInt(data.total_pages, 10);
  const pagecount = Number.isFinite(totalPages) && totalPages > 0 ? totalPages : page + (results.length ? 1 : 0);
  const total = parseInt(data.total_count, 10) || parseInt(data.count, 10) || results.length;
  return { list: results.map(toSeriesCard).filter(Boolean), page, pagecount, limit: PAGE_SIZE, total };
}

async function seriesMoviesPage(data, page) {
  const sid = String((data && data.sid) || "");
  if (!sid) return { list: [], page: toPage(page), pagecount: 0, limit: PAGE_SIZE, total: 0 };
  const res = await apiCall(`/api/app/series/${encodeURIComponent(sid)}/`);
  const series = (res && (res.series || res.data)) || {};
  const movies = (Array.isArray(series.movies) && series.movies.length ? series.movies : series.movies_with_resources) || [];
  const list = dedupe(movies).map(toMovieCard).filter(Boolean);
  const pagecount = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  const current = Math.max(1, Math.min(toPage(page), pagecount));
  const start = (current - 1) * PAGE_SIZE;
  return { list: list.slice(start, start + PAGE_SIZE), page: current, pagecount, limit: PAGE_SIZE, total: list.length };
}

// ==================== 对外接口 ====================
async function _home() {
  try {
    dailyCheckin().catch(() => {});
    // home-initial-data 已包含 categories/type_stats/年份地区标签等统计,正常一次请求即可;
    // 只有它缺失统计时才补请求 categories(省一半首屏时间)
    const initialData = await homeInitialApi();
    const overviewData =
      initialData && Array.isArray(initialData.type_stats) && Array.isArray(initialData.categories)
        ? initialData
        : await overviewApi();
    // 分类从站点 type_stats 动态生成(实测 key 为 movie/tv/variety/anime/doc/bundle/other)
    const classes = [
      { type_id: "all", type_name: "影视库" },
      { type_id: "series", type_name: "系列合集" },
    ].concat(
      buildTypeOptions(overviewData)
        .filter((item) => item.value)
        .map((item) => ({ type_id: item.value, type_name: item.name }))
    );
    const rawList = [];
    if (initialData && typeof initialData === "object") {
      for (const key of ["default_movies", "hero_candidates"]) {
        if (Array.isArray(initialData[key])) rawList.push(...initialData[key]);
      }
      // popular_sections/featured_sections 实测是 {movie:[],tv:[]} 对象,按对象展开
      for (const key of ["featured_sections", "popular_sections"]) {
        const sections = initialData[key];
        if (sections && typeof sections === "object" && !Array.isArray(sections)) {
          for (const name of Object.keys(sections)) {
            const value = sections[name];
            if (Array.isArray(value)) rawList.push(...value);
          }
        }
      }
    }
    const list = dedupe(rawList).slice(0, 24).map(toMovieCard).filter(Boolean);
    return { class: classes, list, filters: buildFilters(overviewData) };
  } catch (error) {
    log("error", `聚影 获取首页失败: ${error.message}`);
    return {
      class: [
        { type_id: "all", type_name: "影视库" },
        { type_id: "series", type_name: "系列合集" },
      ],
      list: [],
      filters: {},
    };
  }
}

// 站点历史筛选值兼容(实测 type=documentary 返回 0,真实 key 为 doc)
const TYPE_ALIAS = { documentary: "doc", variety_show: "variety", cartoon: "anime" };

async function movieCategoryPage(typeId, filters, page) {
  const query = {
    page,
    page_size: PAGE_SIZE,
    count: 1,
    ordering: String(filters.ordering || filters.sort || "-created_at"),
  };
  const typeValue = filters.type ? String(filters.type) : "";
  const effectiveTypeRaw = typeId && typeId !== "all" ? typeId : typeValue;
  const effectiveType = TYPE_ALIAS[effectiveTypeRaw] || effectiveTypeRaw;
  if (effectiveType && effectiveType !== "all") query.type = effectiveType;
  for (const key of ["category", "region", "tag", "year", "resource_type"]) {
    if (filters[key]) query[key] = filters[key];
  }
  const data = await apiCall("/api/app/movies/", { params: query });
  const results = Array.isArray(data.results) ? data.results : [];
  const totalPages = parseInt(data.total_pages, 10);
  const pagecount = Number.isFinite(totalPages) && totalPages > 0 ? totalPages : page + (results.length ? 1 : 0);
  const total = parseInt(data.total_count, 10) || parseInt(data.count, 10) || results.length;
  const list = rateLimitListPlaceholder(results.map(toMovieCard).filter(Boolean), "/api/app/movies/");
  return { list, page, pagecount, limit: PAGE_SIZE, total };
}

// 分组二级目录:该影片下某网盘类型的所有资源
async function groupCategoryPage(data, page) {
  const mid = String(data.mid || "");
  const resources = await resourceListApi(mid);
  const items = resources.filter((item) => normalizeDriveType(resourceType(item)) === normalizeDriveType(data.g));
  const total = items.length;
  const pagecount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const current = Math.max(1, Math.min(page, pagecount));
  const start = (current - 1) * PAGE_SIZE;
  let pic = data.p || data.pic || "";
  let name = data.n || "";
  if ((!pic || !name) && mid) {
    try {
      const meta = pickMovieMeta(await movieDetailApi(mid));
      if (!pic) {
        const pics = [meta.stills_poster, meta.cover, meta.cover_url, meta.backdrop_url, meta.poster, meta.poster_path, meta.backdrop_path].find(Boolean) || "";
        if (/^https?:\/\//i.test(String(pics))) pic = String(pics);
      }
      if (!name) name = String(meta.title || meta.name || "").trim();
    } catch (error) {
      log("warn", `聚影 分组取影片信息失败: ${error.message}`);
    }
  }
  const list = items
    .slice(start, start + PAGE_SIZE)
    .map((item) => toResourceCard(item, mid, pic, name))
    .filter((item) => item.vod_id);
  return { list, page: current, pagecount, limit: PAGE_SIZE, total };
}

// 影片级分类:多网盘返回分组卡片,单网盘直接返回资源列表
async function movieResourceCategoryPage(data, page) {
  const mid = String(data.mid || "");
  const resources = await resourceListApi(mid);
  const groups = groupByResourceType(resources);
  const keys = orderedGroupKeys(groups).filter((key) => (groups[key] || []).length);
  if (keys.length > 1) {
    const cards = keys.map((key) => {
      const items = groups[key] || [];
      const first = items[0] || {};
      const type = normalizeDriveType(key);
      const moviePic = data.p || data.pic || "";
      const name = resourceName(key, first);
      // 分组卡海报存进分组 id,供二级目录缺图时兜底(与 toResourceCard 的取图优先级一致)
      const idPic = /^https?:\/\//i.test(String(moviePic || ""))
        ? String(moviePic)
        : /^https?:\/\//i.test(String(first.share_pic || ""))
          ? String(first.share_pic)
          : panPic(resourceType(first));
      const id = encodeId("g", { mid, g: type, n: data.n || "", p: moviePic, pic: idPic });
      return toVod({
        vod_id: id,
        type_id: id,
        type_name: name,
        vod_name: clean(name),
        vod_pic: panPic(type),
        vod_remarks: `${items.length}个链接`,
        vod_tag: "folder",
      });
    });
    return { list: cards, page: 1, pagecount: 1, limit: Math.max(1, cards.length), total: cards.length };
  }
  return groupCategoryPage({ mid, g: keys[0] ? normalizeDriveType(keys[0]) : "", n: data.n || "", p: data.p || data.pic || "" }, page);
}

async function _category({ id, page, filters }) {
  const rawId = String(id === undefined || id === null ? "" : id).trim();
  // 壳可能传 "1"/"0" 这类老式数字分类,统一归到 all
  const typeId = !rawId || rawId === "1" || rawId === "0" ? "all" : rawId;
  try {
    if (typeId === "series") return await seriesListPage(page);
    const [typ, data] = decodeId(typeId);
    if (typ === "g") return await groupCategoryPage(data, page);
    if (typ === "m") return await movieResourceCategoryPage(data, page);
    if (typ === "s") return await seriesMoviesPage(data, page);
    if (typ) return { list: [], page: toPage(page), pagecount: 0, limit: PAGE_SIZE, total: 0 };
    return await movieCategoryPage(typeId, filters || {}, page);
  } catch (error) {
    log("error", `聚影 获取分类失败: ${error.message}`);
    return { list: [], page: toPage(page), pagecount: 0, limit: PAGE_SIZE, total: 0 };
  }
}

async function _search({ page, quick, wd }) {
  const keyword = String(wd || "").trim();
  if (!keyword) return { list: [], page: toPage(page), pagecount: 0, total: 0 };
  try {
    dailyCheckin().catch(() => {});
    const pageSize = quick ? Math.min(PAGE_SIZE, 12) : PAGE_SIZE;
    const data = await apiCall("/api/app/movies/", {
      params: { q: keyword, page, page_size: pageSize, count: 1, exact: quick ? 1 : undefined },
    });
    const results = Array.isArray(data.results) ? data.results : [];
    const totalPages = parseInt(data.total_pages, 10);
    const pagecount = Number.isFinite(totalPages) && totalPages > 0 ? totalPages : 0;
    const total = parseInt(data.total_count, 10) || parseInt(data.count, 10) || results.length;
    const list = rateLimitListPlaceholder(results.map(toMovieCard).filter(Boolean), "/api/app/movies/");
    return { list, page, pagecount, limit: pageSize, total };
  } catch (error) {
    log("error", `聚影 搜索失败: ${error.message}`);
    return { list: [], page, pagecount: 0, total: 0 };
  }
}

// 资源条目详情(二级目录点击进来):单资源成条
async function buildResourceVod(rawId) {
  const [typ, data] = decodeId(rawId);
  if (typ !== "r") return null;
  const item = Object.assign({}, data);
  const mid = String(item._mid || "");
  let meta = {};
  if (mid) {
    try {
      meta = pickMovieMeta(await movieDetailApi(mid));
    } catch (error) {
      log("warn", `聚影 资源详情取影片信息失败: ${error.message}`);
    }
  }
  const key = resourceType(item);
  const name = (meta.title && clean(meta.title)) || clean(item._name || item.title || item.resource_description || resourceName(key, item));
  const pics = [meta.stills_poster, meta.cover, meta.cover_url, meta.backdrop_url, meta.poster, meta.poster_path, meta.backdrop_path].find(Boolean) || "";
  const pic = /^https?:\/\//i.test(String(pics)) ? String(pics) : /^https?:\/\//i.test(String(item._pic || "")) ? String(item._pic) : panPic(key);
  const vod = toVod({
    vod_id: rawId,
    vod_name: name,
    vod_pic: pic,
    vod_remarks: truncateText(item.resource_description || resourceName(key, item), 30),
    vod_year: String(meta.year || meta.release_date || meta.first_air_date || "").slice(0, 4),
    vod_area: joinNames(meta.region || meta.regions || meta.country),
    vod_lang: joinNames(meta.language || meta.languages),
    vod_actor: joinNames(meta.actors || meta.cast || meta.actor),
    vod_director: joinNames(meta.director || meta.directors),
    vod_genre: joinNames(meta.genre || meta.genres || meta.category),
    // 简介用影片剧情(meta.description),资源短描述已放在 vod_remarks,不再抢简介位
    vod_content: withShareLink(meta.description || meta.summary || item.description || item.resource_description || "", ""),
    vod_score: Number(meta.vote_average || meta.score || 0) || 0,
  });
  const state = newPlayState(mid, false);
  const card = { key, type: normalizeDriveType(key), title: resourceName(key, item), items: [item] };
  let sources = await buildPlaySources([card], state);
  // 票据过期导致分享枚举失败:刷新资源列表拿新票据重建一次
  if (state.shareOk === 0 && state.resolveFailed > 0 && mid && item.id && !state.resolveRetried) {
    log("info", `聚影 资源链接解析失败,刷新资源列表重试: mid=${mid}`);
    await invalidateResourceCache(mid);
    try {
      const fresh = await resourceListApi(mid);
      const freshItem = fresh.find((entry) => entry && String(entry.id) === String(item.id)) || fresh.find((entry) => entry && resourceType(entry) === key);
      if (freshItem) {
        Object.assign(item, freshItem);
        sources = await buildPlaySources([{ key, type: normalizeDriveType(key), title: card.title, items: [item] }], newPlayState(mid, true));
      }
    } catch (error) {
      log("warn", `聚影 刷新资源列表失败: ${error.message}`);
    }
  }
  if (sources.from) {
    vod.vod_play_from = sources.from;
    vod.vod_play_url = sources.url;
  }
  // 简介最前面放已解析到的分享链接,其余简介排后
  const sharedUrl = (state && state.firstShare) || item.share_link || "";
  vod.vod_content = withShareLink(vod.vod_content || "", sharedUrl);
  if ((!vod.vod_pic || vod.vod_pic === panPic("others")) && !meta.title) {
    await loadTmdbFor(vod, item._name || name, meta);
  }
  return vod;
}

async function _detail({ id }) {
  const ids = Array.isArray(id) ? id : [id];
  const list = [];
  for (const rawId of ids) {
    const key = String(rawId || "").trim();
    if (!key) continue;
    const [typ, data] = decodeId(key);
    try {
      let vod = null;
      if (typ === "m" || typ === "g") vod = await buildDetailByMid(data.mid, rawId, typ === "g" ? normalizeDriveType(data.g) : "");
      if (typ === "s") {
        const seriesPic = String(data.pic || "");
        vod = toVod({
          vod_id: rawId,
          vod_name: String(data.n || "系列合集"),
          vod_pic: /^https?:\/\//i.test(seriesPic) ? seriesPic : panPic("others"),
          vod_remarks: "系列合集",
          vod_content: "该条目是系列目录,请返回列表选择具体影片",
          vod_tag: "folder",
        });
      }
      if (typ === "r") vod = await buildResourceVod(key);
      if (typ === "e") vod = placeholderVod(key, "暂无资源", "该条目没有可播放内容");
      // 兼容裸数字 mid(历史记录/外部引用传纯 id):按影片详情处理
      if (!vod && !typ && /^\d+$/.test(key)) vod = await buildDetailByMid(key, key, "");
      if (!vod && isMagnetUrl(key)) {
        vod = toVod({
          vod_id: key,
          vod_name: truncateText(key, 60),
          vod_pic: panPic("magnet"),
          vod_remarks: "磁力资源",
          vod_content: key,
          vod_play_from: "磁力",
          vod_play_url: `磁力资源$${encodeId("p", { k: "magnet", u: extractMagnet(key) || key })}`,
        });
      }
      if (vod) list.push(vod);
    } catch (error) {
      log("warn", `聚影 获取详情失败: ${truncateText(key, 60)}, ${error.message}`);
      // 占位卡也带分享链接: r 型条目(compactResource 保留 share_link/target 等)失败后仍可复制自取
      const failLink = String(
        (data && (data.share_link || data.raw_share_link || data.share_link_with_code || data.target || data.url || data.u)) || ""
      );
      list.push(placeholderVod(key, data.n || "获取失败", withShareLink(errorText(error), failLink), "获取失败"));
    }
  }
  return { list };
}

// ==================== 播放 ====================
// 找到 drive 后取真实播放地址,统一加超时防止网盘插件卡死
async function drivePlay(drive, episodeId, driveFlag) {
  const flag = driveFlag || drive.key;
  try {
    return normalizePlayResult(
      await withTimeout(Promise.resolve(drive.play(episodeId, flag)), PLAY_TIMEOUT_MS, "取播放地址")
    );
  } catch (error) {
    // 部分网盘 drive.play 会校验 flag 必须等于自身 key(如 a115):不一致时用 drive.key 再试一次
    // 但超时不重试(再等一遍只会更慢),只对校验/取址失败类错误重试
    const isTimeout = /超时/.test(String(error && error.message || ""));
    if (!isTimeout && drive.key && flag !== drive.key) {
      log("warn", `聚影 播放 flag 不匹配,改用 drive.key 重试: ${drive.key}`);
      return normalizePlayResult(
        await withTimeout(Promise.resolve(drive.play(episodeId, drive.key)), PLAY_TIMEOUT_MS, "取播放地址")
      );
    }
    throw error;
  }
}

async function playEpisode(episodeId, flag, shareURL, fallbackMeta) {
  // 123镜像域名兜底改写:findDrive/matchShare 才能识别
  shareURL = normalizePanShareURL(shareURL);
  // 123直连枚举的选集(p123:前缀):绕过容器drive,直接走123下载API
  if (String(episodeId || "").startsWith("p123:")) {
    log("info", `聚影 123直连播放: ${truncateText(episodeId, 80)}`);
    return await pan123DirectPlay(shareURL, episodeId);
  }
  // 百度直连枚举的选集(pbaidu:前缀):绕过容器drive,直接走页面同款流媒体链
  if (String(episodeId || "").startsWith("pbaidu:")) {
    log("info", `聚影 百度直连播放: ${truncateText(episodeId, 80)}`);
    return await baiduDirectPlay(episodeId);
  }
  const drive = findDrive(flag, shareURL) || (shareURL ? findDrive("", shareURL) : null) || findDriveByType(flag) || findDrive(flag, "");
  if (!drive) throw new Error(`未配置该网盘线路(${flag || "未知"}): ${truncateText(shareURL || episodeId, 70)}`);
  log("info", `聚影 播放: ${drive.key} -> ${truncateText(episodeId, 80)}`);
  try {
    return await drivePlay(drive, episodeId, flag);
  } catch (error) {
    if (!shareURL) throw error;
    // 百度容器drive偶发失败:先试匿名直连取播链(fs_id 直用/按分集名匹配);死分享/提取码直抛,其余回退刷新
    if (isBaiduShareURL(shareURL)) {
      try {
        return await baiduDirectPlayByEpisode(shareURL, episodeId, (fallbackMeta && fallbackMeta.n) || "");
      } catch (directError) {
        const message = errorText(directError);
        if (isDeadShareError(message) || /提取码不正确|需要提取码/.test(message)) throw directError;
        log("warn", `聚影 百度直连播放失败,回退刷新: ${truncateText(message, 100)}`);
      }
    }
    // 选集ID失效(分享被替换/文件被删):刷新分享缓存重新枚举,按名称匹配
    log("warn", `聚影 选集播放失败,刷新分享重试: ${error.message}`);
    await clearShareCache(shareURL);
    const meta = fallbackMeta || {};
    const loaded = await loadShareEpisodes(shareURL).catch(() => null);
    const episodes = (loaded && loaded.episodes) || [];
    const target =
      episodes.find((ep) => ep.id === episodeId) ||
      (meta.n ? episodes.find((ep) => clean(ep.name) === clean(meta.n)) : null) ||
      episodes[0];
    if (!target) throw error;
    if (String(target.id || "").startsWith("pbaidu:")) return await baiduDirectPlay(target.id);
    return await drivePlay(drive, target.id, flag);
  }
}

async function playShare(shareURL, flag) {
  // 123镜像域名兜底改写:findDrive/matchShare 才能识别
  shareURL = normalizePanShareURL(shareURL);
  const magnet = extractMagnet(shareURL);
  if (magnet) return { parse: 0, jx: 0, url: magnet, header: {} };
  if (isMagnetUrl(shareURL)) return { parse: 0, jx: 0, url: shareURL, header: {} };
  const loaded = await loadShareEpisodes(shareURL);
  const episode = (loaded.episodes || [])[0];
  if (!episode) throw new Error("分享中未找到可播放的文件");
  // 123直连枚举的选集:直接走123下载,不经容器drive
  if (String(episode.id || "").startsWith("p123:")) {
    log("info", `聚影 123直连播放: ${truncateText(episode.name || episode.id, 60)}`);
    return await pan123DirectPlay(shareURL, episode.id);
  }
  // 百度直连枚举的选集:直接走页面同款流媒体链,不经容器drive
  if (String(episode.id || "").startsWith("pbaidu:")) {
    log("info", `聚影 百度直连播放: ${truncateText(episode.name || episode.id, 60)}`);
    return await baiduDirectPlay(episode.id);
  }
  const drive = findDrive(flag, shareURL) || findDrive("", shareURL);
  if (!drive) throw new Error(`未配置该网盘线路: ${truncateText(shareURL, 80)}`);
  log("info", `聚影 播放分享: ${drive.key} -> ${truncateText(episode.name || episode.id, 60)}`);
  // 百度容器drive偶发失败:先试匿名直连取播链,死分享/提取码直抛,其余回退容器
  if (isBaiduShareURL(shareURL)) {
    try {
      return await baiduDirectPlayByEpisode(shareURL, "", episode.name || "");
    } catch (directError) {
      const message = errorText(directError);
      if (isDeadShareError(message) || /提取码不正确|需要提取码/.test(message)) throw directError;
      log("warn", `聚影 百度直连播放失败,回退容器: ${truncateText(message, 100)}`);
    }
  }
  return await drivePlay(drive, episode.id, flag || loaded.drive || drive.key);
}

// 播放失败后:用 mid+rid 重新拉资源列表换取新分享链接再试一次
async function recoverShareFromResource(data, driveFlag) {
  const mid = String(data.mid || "");
  const rid = data.rid;
  if (!mid || !rid) return null;
  try {
    await invalidateResourceCache(mid);
    const fresh = await resourceListApi(mid);
    const item = fresh.find((entry) => entry && String(entry.id) === String(rid));
    if (!item) return null;
    // force: 跳过 access 缓存,强制用新票据换新分享链接(旧链接可能已失效)
    const shared = await accessResource(item, true);
    if (!shared) return null;
    const magnet = extractMagnet(shared) || (isMagnetUrl(shared) ? shared : "");
    if (magnet) return { parse: 0, jx: 0, url: magnet, header: {} };
    if (isRawPlayable(shared)) return { parse: 0, jx: 0, url: shared, header: directHeader(shared) };
    await clearShareCache(shared);
    log("info", `聚影 已刷新资源链接重试: rid=${rid}`);
    return await playShare(shared, driveFlag);
  } catch (error) {
    log("warn", `聚影 刷新资源链接失败: ${error.message}`);
    return null;
  }
}

async function _play({ flag, id }) {
  const raw = String(id || "").trim();
  if (!raw) return emptyPlayResult();
  const [typ, data] = decodeId(raw);
  if (typ === "e") return emptyPlayResult();

  if (typ === "p") {
    const kind = String(data.k || "");
    const shareURL = String(data.u || "");
    const driveFlag = String(data.f || "") || flag || "";
    if (kind === "direct" || kind === "magnet") {
      const url = extractMagnet(shareURL) || shareURL;
      if (!url) return emptyPlayResult();
      return { parse: 0, jx: 0, url, header: kind === "magnet" ? {} : directHeader(url) };
    }
    if (kind === "ep") {
      if (!data.i) return await playShare(shareURL, driveFlag);
      try {
        return await playEpisode(String(data.i), driveFlag, shareURL, data);
      } catch (error) {
        const recovered = await recoverShareFromResource(data, driveFlag);
        if (recovered && recovered.url) return recovered;
        throw error;
      }
    }
    if (kind === "pan") {
      if (!shareURL) throw new Error("分享链接为空,无法播放");
      try {
        return await playShare(shareURL, driveFlag);
      } catch (error) {
        const recovered = await recoverShareFromResource(data, driveFlag);
        if (recovered && recovered.url) return recovered;
        await clearShareCache(shareURL);
        return await playShare(shareURL, driveFlag);
      }
    }
    if (kind === "lazy") {
      const resource = data.r && typeof data.r === "object" ? data.r : {};
      const inline = extractMagnet(shareURL) || (isMagnetUrl(shareURL) ? shareURL : "");
      if (inline) return { parse: 0, jx: 0, url: inline, header: {} };
      const described = extractMagnet(resource.description || resource.resource_description || "");
      if (described) return { parse: 0, jx: 0, url: described, header: {} };
      try {
        const resolved = await accessResource(resource);
        const magnet = extractMagnet(resolved) || (isMagnetUrl(resolved) ? resolved : "");
        if (magnet) return { parse: 0, jx: 0, url: magnet, header: {} };
        if (resolved && isRawPlayable(resolved)) return { parse: 0, jx: 0, url: resolved, header: directHeader(resolved) };
        if (resolved && isPanShareUrl(resolved)) return await playShare(resolved, driveFlag);
      } catch (error) {
        log("warn", `聚影 延迟解析失败: ${error.message}`);
      }
      // 票据/分享失效:按 rid+mid 重新拉资源拿新链接再试一次
      const recovered = await recoverShareFromResource(data, driveFlag);
      if (recovered && recovered.url) return recovered;
      const name = String(resource.title || resource.resource_description || "").trim();
      throw new Error(`未取到可播放地址${name ? `(${truncateText(name, 40)})` : ""},请刷新详情重试`);
    }
    return emptyPlayResult();
  }

  if (typ === "r") {
    const driveFlag = flag || driveKeyToType(resourceType(data));
    const tryLink = async (link) => {
      const value = normalizePlayUrl(String(link || ""));
      if (!value) return null;
      const magnet = extractMagnet(value) || (isMagnetUrl(value) ? value : "");
      if (magnet) return { parse: 0, jx: 0, url: magnet, header: {} };
      if (isRawPlayable(value)) return { parse: 0, jx: 0, url: value, header: directHeader(value) };
      return await playShare(value, driveFlag);
    };
    let firstError = null;
    const stored = normalizePlayUrl(data.share_link || data.target || data.raw_share_link || "");
    if (stored) {
      try {
        const ok = await tryLink(stored);
        if (ok) return ok;
      } catch (error) {
        firstError = error;
      }
      // 存量链接播放失败多半已陈旧: 强制刷新票据换新链接再试一次
      try {
        const ok = await tryLink(await accessResource(data, true));
        if (ok) return ok;
      } catch (error) {
        if (!firstError) firstError = error;
      }
    } else {
      try {
        const ok = await tryLink(await accessResource(data));
        if (ok) return ok;
      } catch (error) {
        firstError = error;
      }
    }
    // 仍失败: 按 rid+mid 重拉资源列表换新链接恢复
    const recovered = await recoverShareFromResource(data, driveFlag);
    if (recovered && recovered.url) return recovered;
    if (firstError) throw firstError;
    throw new Error("该资源未取到分享链接,请刷新详情重试");
  }

  const magnet = extractMagnet(raw);
  if (magnet) return { parse: 0, jx: 0, url: magnet, header: {} };
  if (isMagnetUrl(raw)) return { parse: 0, jx: 0, url: raw, header: {} };
  if (isRawPlayable(raw)) return { parse: 0, jx: 0, url: raw, header: directHeader(raw) };
  if (isPanShareUrl(raw)) return await playShare(raw, flag);
  const drive = findDrive(flag, raw);
  if (drive) {
    log("info", `聚影 播放直传: ${drive.key}`);
    return await drivePlay(drive, raw, flag);
  }
  return emptyPlayResult();
}

// ==================== 容器接入 ====================
async function init(server) {
  if (store.init) return;
  store.redis = (server && server.redis) || null;
  store.log = (server && server.log) || null;
  store.server = server || null;
  store.drives = (server && server.drives) || [];
  store.init = true;
  const cached = await redisGet("jy:token");
  if (cached) authToken = String(cached);
  tokenRestored = true;
  log(
    "info",
    `聚影不夜插件 v${VERSION} 已加载, 网盘数: ${listDrives().length}, TMDB: ${TMDB_ENABLED && TMDB_API_KEY ? "开" : "关"}, 镜像: ${TMDB_MIRROR || "无"}, 内置代理: ${BUILTIN_TMDB_PROXY || "无"}`
  );
}

module.exports = async (app, opt) => {
  app.get(store.meta.api, async (req, reply) => {
    if (!store.init) await init(req.server);
    const { t, ac, pg, ext, ids, flag, play, wd, quick } = req.query;
    const isQuick = /^(1|true)$/i.test(String(quick || ""));
    const parseFilters = () => {
      if (!ext) return {};
      try {
        // 查询串里的 "+" 会被框架解码成空格,还原后再解 base64,否则筛选可能静默失效
        const normalized = String(ext).trim().replace(/ /g, "+");
        return JSON.parse(Buffer.from(normalized, "base64").toString("utf8")) || {};
      } catch (error) {
        return {};
      }
    };
    if (play) {
      return await _play({ flag: flag || "", id: play });
    } else if (wd) {
      return await _search({ page: toPage(pg), quick: isQuick, wd });
    } else if (!ac) {
      return await _home();
    } else if (ac === "detail") {
      if (t) {
        return await _category({ id: t, page: toPage(pg), filters: parseFilters() });
      } else if (ids) {
        return await _detail({ id: String(ids).split(",").map((_id) => _id.trim()).filter(Boolean) });
      }
      // OK影视/FongMi type=4 首页请求是 ?ac=detail&filter=true(无 t/ids):按首页返回
      return await _home();
    } else if (ac === "class" || ac === "list" || ac === "videolist") {
      // 其它壳(原版 TVBox type=1 等):无 t 是首页,带 t 是分类
      if (t) return await _category({ id: t, page: toPage(pg), filters: parseFilters() });
      return await _home();
    }
    return req.query;
  });
  opt.sites.push(store.meta);
};
