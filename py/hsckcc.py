# -*- coding: utf-8 -*-
VERSION = "1.0.6"
# v1.0.6 清理冗余 + 越界页一致性：删掉从未使用的 _safe_json/_api、从未生效的 ext.cookie，
#          收敛 ext 别名（hostList/hostCandidates/eagerProbe 并入 hosts/probe）；
#          父分类越界页码夹到末页（站点对越界 vodtype 本就返回末页内容）；
#          网页搜索回退越界时夹到末页重取（站点对越界搜索页返回近空页）；
#          修配置区注释与实际行为的漂移（懒探测/直链默认、noProbe 补文档）。
# v1.0.5 播放默认走直链（再修 OK影视 转圈）：CDN 实测无 UA/Referer 校验、m3u8 无广告无 DRM，
#          localProxy 在播放关键路径上只会增加不确定性（部分宿主 do=py 参数路由/多 & 截断）——
#          默认 stripAds=false 直链播放；要清洗可 ext.stripAds=true（拿不到 127.0.0.1 端口自动回退直链）；
#          playerContent 兼容旧版/App 缓存的 proxy 播放地址：从 token 还原真实 m3u8 直接播。
# v1.0.4 修播放转圈圈（OK影视等宿主）：playerContent 不再返回 proxy://do=py——
#          部分宿主不转换该协议的视频请求（hsckvip v1.3.1 同款问题）；
#          改为优先 http://127.0.0.1:{port}/proxy?do=py（Proxy.getPort()），
#          拿不到端口/基址则回退 m3u8 直链——本站无广告分片，直链即可播（能播优先）。
# v1.0.3 磁盘缓存（warm 提速）：TVBox 每次调用都是新进程，内存缓存活不过一次调用——
#          把「入口→真实站」映射（TTL 24h）和「type_id→父分类」pid 表（TTL 7d）写进
#          /tmp/hsckcc_cache.json（原子写 tmp+replace；不可写/损坏 → 静默降级为纯内存）。
#          warm 后 homeContent 省掉 301 解析与全部分类探测，实测 ~8s → ~1.5s；
#          ac=list 分类列表与所有列表/详情/搜索仍实时请求；解析失败走已有 fresh 重解析兜底，
#          pid 表只信「pid 仍在当前分类集合里」的条目，改版/新增 id 只重探那几个；
#          ext.noCache=true 可关掉磁盘缓存。
# v1.0.2 懒探测（冷启动提速）：默认不再预跑三入口测速——实测三入口解析后仅差 20%
#          （449/561/470ms）且内容同源，先用默认入口、请求失败时 _api_get 自动切候选即可；
#          ext.probe=true 可恢复「先测速选最快」；
#          _probe_types 探测前先解析 host，避免懒探测下命中 301 网关拿不到 JSON；
#          _resolve 的探测请求改打 API_PATH（网关同样 301，但省掉整页 HTML：实测 3s → 0.4s）。
# v1.0.0 参照 hsckvip.py 的功能骨架（MacCMS 采集 API：分类/列表/详情/搜索/播放/localProxy）
#          移植到新站点三入口域名：444.ablck.cc / 222.1eck.cc / 444.ahlck.cc
#          ①入口域名是 301 网关且跳转时会丢掉路径（/xxx → 只跳到裸域名），必须先「解析」出真实站点域名再请求；
#            三个入口逐个解析+测采集 API，能连上且能出 JSON 的最快者胜，失败自动切下一个（extend.hosts 可覆盖）；
#          ②站点 class 没有 type_pid，改用各分类 detail 首条的 type_id_1 反推父子关系（并发探测，缓存），
#            空分类（无内容且无子类，如「广告」「PA」）自动剔除；
#          ③父分类 API t= 空，走网页聚合列表 /vodtype/{id}-{page}.html 取 id 再批量补 detail，失败回退子类 API 合并；
#          ④该站 vod_year 全空、采集 API 忽略 year 参数 → 去掉年份筛选组，只保留「子分类」筛选组；
#          ⑤播放源是 m3u8 直链（无广告分片时 localProxy 原样透传），ext.stripAds=false 可关回直链；
# v1.0.1 全面体检修复：
#          ①翻页页数改用站方真实值：API 取 pagecount/page（实测 4830/13762/642 均准确、越界自动夹取），
#            网页取「尾页」链接（不再 max(页号,当前页)，否则越界页会一直 +1 翻过头）；
#          ②网页搜索回退改用站点自身分页格式 /vodsearch/{关键词}----------{页}---1.html——
#            原 /vodsearch/-------------{页}.html 站点不认，pg2/pg3/pg400 全返回同一批（等于不翻页）；
#          ③双候选：301 解析出的真实站域名并入候选池（同一后端去重不重复测速），
#            网关整体挂掉时可直连后端；解析缓存随 init 重置、换后端时清除旧映射；
#          ④三入口改并发测速（每线程独立 Session，Session 非线程安全）：冷启动 16.6s → 3.7s；
#          ⑤修 _is_parent_type(0) 误判——_children_of(0) 会命中全部顶级分类，
#            导致 tid=0 被当父分类去抓 /vodtype/0-1.html；现在 tid/sub=0 一律当「全部」。
# hsckcc.py —— 黄色仓库新域名 (MacCMS) 爬虫
# 数据走 /api.php/provide/vod/ 标准采集 API；播放源为 m3u8 直链。
import re
import os
import json
import time
import base64
from urllib.parse import quote, unquote, urljoin

try:
    import requests
except ImportError:
    requests = None

try:
    from urllib3.exceptions import InsecureRequestWarning
    import warnings
    warnings.simplefilter("ignore", InsecureRequestWarning)
except Exception:
    pass


# ===========================================================================
# 配置区
# ===========================================================================
# 站点 ext（TVBox 源里 ext 字段传 JSON）可覆盖：
#   {
#     "host": "https://444.ablck.cc",
#     "hosts": ["https://444.ablck.cc", "https://222.1eck.cc", "https://444.ahlck.cc"],
#     "proxy": "http://127.0.0.1:7890",
#     "verify": false,
#     "noProbe": false,    # true=锁定 host，不做候选切换
#     "stripAds": false,   # true=播放走 localProxy 清洗（默认直链：本站无广告且部分宿主不认代理地址）
#     "probe": false,      # true=先测速选最快入口（默认懒探测）
#     "noCache": false     # true=关掉磁盘缓存（/tmp/hsckcc_cache.json）
#   }

# 入口域名（301 网关且跳转丢路径；默认懒探测：先用它，失败自动切候选并记住真实域名）
HOST = "https://444.ablck.cc"
# 三入口候选（ext.probe=true 时才并发测速选最快）；extend.host / extend.hosts 可覆盖。
HOST_CANDIDATES = [
    "https://444.ablck.cc",
    "https://222.1eck.cc",
    "https://444.ahlck.cc",
]

# 采集 API 路径（所有入口解析后共用）
API_PATH = "/api.php/provide/vod/"

PAGE_SIZE = 20
SEARCH_LIMIT = 20

HTTP_RETRY = 1
HTTP_RETRY_DELAY = 0.5
HTTP_RETRY_STATUS = (429, 500, 502, 503, 504)
REDIRECT_STATUS = (301, 302, 303, 307, 308)

# 磁盘缓存（可选增强）：TVBox 每次调用新起进程，靠它摊薄 301 解析与分类探测成本
CACHE_FILE = "/tmp/hsckcc_cache.json"
RESOLVE_TTL = 24 * 3600      # 入口→真实站映射有效期
PID_TTL = 7 * 24 * 3600      # 分类 pid 表有效期

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

LIST_HEADERS = {
    "User-Agent": WEB_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
}

# ==================== 通用工具 ====================


def _to_text(v):
    return str(v or "").strip()


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(str(v or "").strip() or default)
        except Exception:
            return default


def _norm_proxy(v):
    p = _to_text(v)
    if not p:
        return ""
    if p.lower() in ("0", "off", "none", "no", "false", "直连", "disable", "disabled"):
        return ""
    if p.isdigit():
        return "http://127.0.0.1:%s" % p
    if "://" not in p:
        return "http://" + p
    return p


def _sanitize_play(v):
    if not v:
        return v
    return (_to_text(v)
            .replace("#", "%23")
            .replace("$", "%24")
            .replace("\r", " ")
            .replace("\n", " "))


def _strip_tags(html):
    s = re.sub(r"<[^>]+>", "", _to_text(html))
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    s = s.replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    return re.sub(r"\s+", " ", s).strip()


def _origin(url):
    """取 URL 的 scheme://host[:port]（301 Location 只给域名时也能拿到）"""
    m = re.match(r"^(https?://[^/?#]+)", _to_text(url).strip())
    return m.group(1).rstrip("/") if m else ""


# ==================== Spider ====================

class Spider:
    def __init__(self):
        self.s = None
        self.host = HOST            # 当前生效域名（301 解析后的最终域名）
        self.gateway = ""           # 当前生效入口域名（HOST_CANDIDATES 之一）
        self.host_candidates = list(HOST_CANDIDATES)
        self.ua = WEB_UA
        self.timeout = 15
        self.page_size = PAGE_SIZE
        self.search_limit = SEARCH_LIMIT
        self.verify = False
        self.proxy = ""
        self.prefer_m3u8 = True
        self.strip_ads = False  # 本站 m3u8 无广告分片 → 默认直链（localProxy 只作 ext.stripAds=true 可选）
        self._class_cache = []
        self._host_locked = False
        self._probed = False
        self.eager_probe = False   # ext.probe=true 才先测速选最快入口（默认懒探测）
        self._resolve_cache = {}    # 入口域名 → 真实站点域名
        self._resolved_extra = []   # 解析出来的真实站域名（并入候选，网关挂了可直连）
        self._disk = {"resolve": {}, "pids": {}}
        self._disk_dirty = False
        self.no_disk_cache = False  # ext.noCache=true 时置 True

        if requests:
            self.s = self._new_session()

    def getDependence(self):
        return []

    # ---------- extend 解析 ----------
    @staticmethod
    def _parse_extend(extend):
        if isinstance(extend, dict):
            return extend
        if isinstance(extend, str):
            s = extend.strip()
            if not s:
                return {}
            for cand in (s, unquote(s)):
                if cand.strip().startswith("{"):
                    try:
                        d = json.loads(cand)
                    except Exception:
                        d = None
                    if isinstance(d, dict):
                        return d
            if "=" in s and "{" not in s:
                out = {}
                for part in s.split("&"):
                    if "=" not in part:
                        continue
                    k, v = part.split("=", 1)
                    k = unquote(k).strip()
                    v = unquote(v).strip()
                    if not k:
                        continue
                    try:
                        out[k] = json.loads(v)
                    except Exception:
                        out[k] = v
                if out:
                    return out
        return {}

    def init(self, extend=""):
        extend = self._parse_extend(extend)
        self._host_locked = False
        self._probed = False
        if extend.get("host"):
            self.host = str(extend["host"]).rstrip("/")
            self.gateway = self.host
            self._host_locked = True
        # 多域名候选（list 或 逗号分隔字符串）：host 层自动切换用
        hv = extend.get("hosts")
        if hv:
            if isinstance(hv, (list, tuple)):
                cand = [_to_text(x).rstrip("/") for x in hv]
            else:
                cand = [_to_text(hv).strip().rstrip("/")]
            cand = [h for h in cand if h]
            if cand:
                # 用户显式配置时把首个排到最前，再并入内置候选
                self.host_candidates = cand + [
                    h for h in self.host_candidates if h not in cand]
                if not extend.get("host"):
                    self.host = cand[0]
                    self.gateway = cand[0]
        if extend.get("noProbe"):
            self._host_locked = True
        # 默认懒探测（首请求失败才切候选）；ext.probe=true 恢复先测速选最快
        self.eager_probe = bool(extend.get("probe"))
        if "verify" in extend:
            self.verify = bool(extend["verify"])
        if "preferM3u8" in extend:
            self.prefer_m3u8 = bool(extend["preferM3u8"])
        if "stripAds" in extend:
            self.strip_ads = bool(extend["stripAds"])
        if "proxy" in extend:
            self.set_proxy(extend.get("proxy"))
        elif "proxyPort" in extend or "proxy_port" in extend:
            self.set_proxy(extend.get("proxyPort") or extend.get("proxy_port"))
        self._apply_proxy()
        self._class_cache = []
        # 换配置后重新解析（旧后端映射一并丢弃）
        self._resolve_cache = {}
        self._resolved_extra = []
        # 磁盘缓存：读回「解析映射 + pid 表」，懒探测下首个请求可省一次 301
        self.no_disk_cache = bool(extend.get("noCache"))
        self._cache_load()
        now = time.time()
        for h, e in list((self._disk.get("resolve") or {}).items()):
            base = _to_text((e or {}).get("base") or "")
            try:
                ts = float((e or {}).get("ts") or 0)
            except Exception:
                ts = 0
            if not base.startswith(("http://", "https://")) or now - ts > RESOLVE_TTL:
                continue
            h = _to_text(h).rstrip("/")
            if not h:
                continue
            self._resolve_cache[h] = base
            if base != h and base not in self._resolved_extra:
                self._resolved_extra.append(base)

    def set_proxy(self, value):
        self.proxy = _norm_proxy(value)
        self._apply_proxy()
        return self.proxy

    def _new_session(self):
        """新建带站点头/代理的 Session（并发测速时每线程独立一个，Session 非线程安全）"""
        s = requests.Session()
        s.headers.update(LIST_HEADERS)
        if self.proxy:
            s.trust_env = False
            s.proxies = {"http": self.proxy, "https": self.proxy}
        else:
            s.trust_env = True
            s.proxies = {}
        return s

    def _apply_proxy(self):
        if not self.s:
            return
        if self.proxy:
            self.s.trust_env = False
            self.s.proxies = {"http": self.proxy, "https": self.proxy}
        else:
            self.s.trust_env = True
            self.s.proxies = {}

    def _proxies_kw(self):
        """给线程内裸 requests 用的 proxies 参数（与 Session 保持一致）"""
        if self.proxy:
            return {"http": self.proxy, "https": self.proxy}
        try:
            if self.s is not None and not self.s.trust_env:
                return {}
        except Exception:
            pass
        return None  # 跟随环境变量

    # ---------- 入口解析 / API ----------
    def _host_pool(self):
        """候选入口池：当前入口 + 内置/extend 候选 + 已解析出的真实站，去重保序；
        锁定（extend.host / noProbe）时只用当前 host。"""
        if self._host_locked:
            return [self.host]
        pool = []
        for h in ([self.gateway, self.host] + list(self.host_candidates or [])
                  + list(self._resolved_extra or [])):
            h = _to_text(h).rstrip("/")
            if h and h not in pool:
                pool.append(h)
        return pool or [HOST]

    # ---------- 磁盘缓存（可选：/tmp 不可写/损坏 → 静默降级为纯内存） ----------
    def _cache_load(self):
        """读磁盘缓存（resolve 映射 + 分类 pid 表）。任何失败当空处理。"""
        self._disk = {"resolve": {}, "pids": {}}
        self._disk_dirty = False
        if self.no_disk_cache or not os:
            return
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                for key in ("resolve", "pids"):
                    v = d.get(key)
                    if isinstance(v, dict):
                        self._disk[key] = v
        except Exception:
            self._disk = {"resolve": {}, "pids": {}}

    def _cache_save(self):
        """原子写回磁盘缓存（tmp + os.replace），任何失败静默忽略。"""
        if self.no_disk_cache or not self._disk_dirty or not os:
            return
        try:
            payload = {"v": 1,
                       "resolve": self._disk.get("resolve") or {},
                       "pids": self._disk.get("pids") or {}}
            tmp = CACHE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, CACHE_FILE)
        except Exception:
            pass
        self._disk_dirty = False

    def _cache_put_resolve(self, host, base):
        """记住入口→真实站映射（TTL 在读取/预热时校验）"""
        if self.no_disk_cache or not host or not base:
            return
        try:
            m = self._disk.setdefault("resolve", {})
            m[_to_text(host)] = {"base": _to_text(base), "ts": time.time()}
            self._disk_dirty = True
        except Exception:
            pass

    def _cache_pid_get(self, tid):
        """取分类 pid 表条目：仅未过期且 pid 非负才返回（pid 是否仍合法由调用方对照
        当前分类集合判断，改版/新增 id 只重探那几个）。"""
        if self.no_disk_cache:
            return None
        e = (self._disk.get("pids") or {}).get(str(_safe_int(tid, 0)))
        if not isinstance(e, dict):
            return None
        try:
            ts = float(e.get("ts") or 0)
        except Exception:
            return None
        if time.time() - ts > PID_TTL:
            return None
        pid = _safe_int(e.get("pid"), -1)
        if pid < 0:
            return None
        return {"pid": pid, "total": _safe_int(e.get("total"), 0)}

    def _cache_put_pid(self, tid, pid, total):
        tid = _safe_int(tid, 0)
        if self.no_disk_cache or not tid:
            return
        try:
            m = self._disk.setdefault("pids", {})
            m[str(tid)] = {"pid": _safe_int(pid, 0),
                           "total": _safe_int(total, 0), "ts": time.time()}
            self._disk_dirty = True
        except Exception:
            pass

    def _resolve(self, host, timeout=8, fresh=False, sess=None):
        """入口域名是 301 网关且跳转不带路径 → 先解析出真实站点域名（带缓存）。
        非跳转入口原样返回。sess 供并发测速传入线程独立 Session。"""
        host = _to_text(host).rstrip("/")
        if not host:
            return ""
        if not fresh and self._resolve_cache.get(host):
            return self._resolve_cache[host]
        s = sess or self.s
        if not requests or not s:
            return host
        base = host
        got = False
        for _ in range(5):
            try:
                # 探 API_PATH 而非 /：网关同样 301，但省掉整页 HTML（实测 3s → <0.3s）
                r = s.get(base + API_PATH, timeout=timeout, verify=self.verify,
                          allow_redirects=False)
            except Exception:
                break
            got = True
            if r.status_code not in REDIRECT_STATUS:
                break
            loc = _to_text(r.headers.get("Location"))
            nxt = _origin(urljoin(base + "/", loc)) if loc else ""
            if not nxt or nxt == base:
                break
            base = nxt
        if got:
            old = self._resolve_cache.get(host)
            if old and old != base and old in self._resolved_extra:
                self._resolved_extra.remove(old)  # 后端换域名 → 丢弃旧映射
            self._resolve_cache[host] = base
            if base and base != host and base not in self._resolved_extra:
                self._resolved_extra.append(base)  # 真实站并入候选（网关挂了可直连）
            if base:
                self._cache_put_resolve(host, base)
        return base

    @staticmethod
    def _is_maccms_json(data):
        """是否 MacCMS 采集 API 正常响应（排除 Cloudflare 错误页等非 API JSON）"""
        if not isinstance(data, dict) or not data:
            return False
        # 正常：有 list（哪怕空列表）或 class，或 code+msg 组合
        if "list" in data or "class" in data:
            return True
        if "code" in data and "msg" in data:
            return True
        return False

    def _api_once(self, gw, params, timeout=None, fresh=False, sess=None):
        """请求某入口的采集 API：解析 301 → 取 MacCMS JSON。
        成功返回 (data, 最终域名)，失败返回 (None, 最终域名)。"""
        s = sess or self.s
        if not requests or not s:
            return None, ""
        t = timeout or self.timeout
        base = self._resolve(gw, timeout=min(t, 8), fresh=fresh, sess=sess)
        if not base:
            return None, ""
        attempt = 0
        redirects = 0
        while attempt <= HTTP_RETRY:
            try:
                r = s.get(base + API_PATH, params=params or {}, timeout=t,
                          verify=self.verify, allow_redirects=False)
            except Exception:
                attempt += 1
                if attempt <= HTTP_RETRY:
                    time.sleep(HTTP_RETRY_DELAY)
                continue
            if r.status_code in REDIRECT_STATUS:
                redirects += 1
                if redirects > 2:
                    return None, base
                nb = self._resolve(gw, timeout=min(t, 8), fresh=True, sess=sess)
                if not nb or nb == base:
                    nb = _origin(urljoin(base + "/",
                                         _to_text(r.headers.get("Location"))))
                if nb:
                    base = nb
                continue
            if r.status_code in HTTP_RETRY_STATUS and attempt < HTTP_RETRY:
                attempt += 1
                time.sleep(HTTP_RETRY_DELAY)
                continue
            if r.status_code != 200:
                return None, base
            try:
                data = r.json()
            except Exception:
                return None, base
            if self._is_maccms_json(data):
                return data, base
            return None, base
        return None, base

    def _probe(self, gw, timeout=8, sess=None):
        """测一个入口：解析 + 采集 API 探测 → (是否可用, 耗时, 最终域名)"""
        t0 = time.time()
        data, base = self._api_once(gw, {"ac": "list", "pg": 1},
                                    timeout=timeout, sess=sess)
        return data is not None, (time.time() - t0), (base or gw)

    def _probe_parallel(self, gws, timeout=8):
        """并发测多个入口（每线程独立 Session），返回 [(入口, 可用, 耗时, 最终域名)]"""
        if not gws:
            return []
        if len(gws) == 1 or not requests:
            gw = gws[0]
            ok, dt, base = self._probe(gw, timeout=timeout)
            return [(gw, ok, dt, base)]
        results = [None] * len(gws)

        def run(i):
            gw = gws[i]
            sess = None
            try:
                sess = self._new_session()
                ok, dt, base = self._probe(gw, timeout=timeout, sess=sess)
                results[i] = (gw, ok, dt, base)
            except Exception:
                results[i] = (gw, False, 0.0, gw)
            finally:
                try:
                    if sess is not None:
                        sess.close()
                except Exception:
                    pass

        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(len(gws), 4)) as ex:
                for f in [ex.submit(run, i) for i in range(len(gws))]:
                    f.result()
        except Exception:  # 线程池不可用 → 串行兜底
            results = [None] * len(gws)
            for i, gw in enumerate(gws):
                ok, dt, base = self._probe(gw, timeout=timeout)
                results[i] = (gw, ok, dt, base)
        return [r for r in results if r]

    def _probe_host(self):
        """并发测速三入口（含 301 解析）：能出 JSON 的最快者胜；全失败保持当前 host。
        同后端去重：已被某入口解析到的真实站首轮不重复测，入口全挂时再补测。"""
        gws = []
        for gw in self._host_pool():
            gw = _to_text(gw).rstrip("/")
            if gw and gw not in gws:
                gws.append(gw)
        reached = set(self._resolve_cache.values())  # 已知「入口 → 后端」映射
        first = [gw for gw in gws if gw not in reached]
        skipped = [gw for gw in gws if gw in reached]
        results = self._probe_parallel(first)
        if not any(r[1] for r in results) and skipped:
            results += self._probe_parallel(skipped)
        best = None  # (耗时, 入口, 最终域名)
        for gw, ok, dt, base in results:
            if not ok:
                continue
            if best is None or dt < best[0]:
                best = (dt, gw, base)
        if best:
            self.gateway, self.host = best[1], best[2]
        self._probed = True
        return self.host

    def _ensure_host(self):
        """懒探测：默认不预跑三入口测速（省 3s+），首个请求失败时 _api_get 自动切候选；
        ext.probe=true 才先测速选最快入口。"""
        if self._probed or self._host_locked:
            return
        self._probed = True
        if self.eager_probe:
            try:
                self._probe_host()
            except Exception:
                pass

    def _api_get(self, params=None, timeout=None):
        """GET /api.php/provide/vod/ → dict。
        首次调用先测速选最快入口；当前入口失败时自动切换候选重试。"""
        if not requests:
            return {}
        self._ensure_host()
        ordered = []
        # 当前已解析域名优先（省一次 301 解析），再入口网关，最后其余候选
        for gw in [self.host, self.gateway] + self._host_pool():
            gw = _to_text(gw).rstrip("/")
            if gw and gw not in ordered:
                ordered.append(gw)
        for gw in ordered:
            data, base = self._api_once(gw, params, timeout=timeout)
            if data is None:
                # 解析缓存可能过期（网关换后端域名）→ 强制重新解析再试
                data, base = self._api_once(gw, params, timeout=timeout, fresh=True)
            if data is not None:
                # 切到可用入口/域名
                self.gateway, self.host = gw, (base or self.host)
                return data
        return {}  # 所有候选都失败（不回传 Cloudflare 错误页等脏数据）

    # ---------- 分类树 ----------
    def _probe_types(self, ids):
        """并发探测各分类：ac=detail&t={id} → (条目数, type_id_1 父分类)。
        详情首条的 type_id_1 是本站唯一可靠的父子关系来源（class 无 type_pid）。"""
        out = {}
        if not requests or not ids:
            return out
        # 懒探测下 self.host 可能还是 301 网关 → 先解析成真实站再并发请求
        base = self._resolve(self.host or HOST) or (self.host or HOST)
        url = base + API_PATH
        proxies = self._proxies_kw()

        def one(tid):
            try:
                kw = {"params": {"ac": "detail", "t": str(tid), "pg": 1},
                      "timeout": self.timeout, "headers": LIST_HEADERS,
                      "verify": self.verify, "allow_redirects": False}
                if proxies is not None:
                    kw["proxies"] = proxies
                r = requests.get(url, **kw)
                data = r.json()
                if not self._is_maccms_json(data):
                    return tid, None
                lst = data.get("list") or []
                pid = 0
                if lst and isinstance(lst[0], dict):
                    pid = _safe_int(lst[0].get("type_id_1"), 0)
                return tid, {"total": _safe_int(data.get("total"), len(lst)),
                             "pid": pid}
            except Exception:
                return tid, None

        try:
            from concurrent.futures import ThreadPoolExecutor
            # 14 个分类探测全并发（只读 GET），冷启动省 3~4s
            with ThreadPoolExecutor(max_workers=min(10, len(ids))) as ex:
                for tid, res in ex.map(one, ids):
                    if res:
                        out[tid] = res
        except Exception:
            for tid in ids:
                _, res = one(tid)
                if res:
                    out[tid] = res
        return out

    def _classes_raw(self):
        """采集 class 分类树 + 父子关系（缓存）
        父分类 = 被某些分类的 type_id_1 指向；空分类（无内容且无子类）剔除。"""
        if self._class_cache:
            return self._class_cache
        data = self._api_get({"ac": "list", "pg": 1})
        rows = data.get("class") or []
        types = []
        for c in rows:
            if not isinstance(c, dict):
                continue
            tid = _safe_int(c.get("type_id"), 0)
            if not tid or tid in [t[0] for t in types]:
                continue
            types.append((tid, _to_text(c.get("type_name") or str(tid))))
        if not types:
            return []
        known = set(t[0] for t in types)
        # 磁盘 pid 表命中（未过期且 pid 仍合法）的分类不再探测；只探未知/过期/改版的
        info = {}
        need = []
        for tid, _name in types:
            hit = self._cache_pid_get(tid)
            pid = _safe_int((hit or {}).get("pid"), -1)
            if hit is not None and (pid == 0 or pid in known):
                info[tid] = {"pid": pid,
                             "total": _safe_int((hit or {}).get("total"), 0)}
            else:
                need.append(tid)
        if need:
            probed = self._probe_types(need)
            info.update(probed)
            for tid, r in probed.items():
                if r:
                    self._cache_put_pid(tid, _safe_int(r.get("pid"), 0),
                                        _safe_int(r.get("total"), 0))
        children = {}
        for tid, r in info.items():
            pid = _safe_int((r or {}).get("pid"), 0)
            if pid and pid in known and pid != tid:
                children.setdefault(pid, []).append(tid)
        out = []
        for tid, name in types:
            r = info.get(tid) or {}
            pid = _safe_int(r.get("pid"), 0)
            if pid not in known or pid == tid:
                pid = 0
            if r and not r.get("total") and tid not in children:
                continue  # 空分类（如「广告」「PA」）：无内容且无子类
            out.append({
                "type_id": str(tid),
                "type_pid": pid,
                "type_name": name,
            })
        self._class_cache = out
        return out

    def _children_of(self, pid):
        return [c for c in self._classes_raw() if c["type_pid"] == _safe_int(pid)]

    def _is_parent_type(self, tid):
        tid = _safe_int(tid, -1)
        if tid <= 0:
            return False  # 0/非法 id 不是父分类（_children_of(0) 会命中所有顶级分类）
        return bool(self._children_of(tid))

    # ---------- item → vod ----------
    def _vod_item(self, m):
        if not isinstance(m, dict):
            return None
        mid = _safe_int(m.get("vod_id"), 0)
        if not mid:
            return None
        title = _to_text(m.get("vod_name") or "")
        pic = _to_text(m.get("vod_pic") or m.get("vod_pic_thumb") or "")
        remark = _to_text(m.get("vod_remarks") or "")
        type_name = _to_text(m.get("type_name") or "")
        vtime = _to_text(m.get("vod_time") or "")
        if not remark and vtime:
            remark = vtime[:10]
        elif vtime:
            remark = (remark + " " + vtime[:10]).strip()
        hits = _safe_int(m.get("vod_hits"), 0)
        if hits >= 10000:
            remark = (remark + " 热%.1f万" % (hits / 10000.0)).strip()
        elif hits >= 1000 and not remark:
            remark = "热%d" % hits
        return {
            "vod_id": str(mid),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark,
            "type_name": type_name,
        }

    def _items_to_list(self, rows):
        out, seen = [], set()
        for m in rows or []:
            item = self._vod_item(m)
            if item and item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                out.append(item)
        return out

    @staticmethod
    def _page_result(out, page, one_page=False, pagecount=None):
        """pagecount 传站方真实值（API pagecount / 网页尾页号）时直接采用，
        不再与 page 取 max——否则越界页会把页数顶高，导致一直能翻下去。"""
        if one_page:
            return {"list": out, "page": 1, "pagecount": 1,
                    "limit": len(out), "total": len(out)}
        pc = _safe_int(pagecount, 0)
        if pc > 0:
            return {"list": out, "page": _safe_int(page, 1), "pagecount": pc,
                    "limit": len(out), "total": len(out)}
        return {"list": out, "page": page,
                "pagecount": page + 1 if out else page,
                "limit": len(out), "total": len(out)}

    # ---------- 首页 ----------
    def homeContent(self, filter=None):
        # 只保留顶级分类；子分类做成父分类下的「子分类」筛选组
        # （本站无年份数据、采集 API 忽略 year → 不做年份筛选）
        classes = []
        for c in self._classes_raw():
            if c["type_pid"] == 0:
                classes.append({"type_id": c["type_id"],
                                "type_name": c["type_name"]})

        filters = {}
        for c in classes:
            children = self._children_of(c["type_id"])
            if not children:
                continue
            sub_vals = [{"n": "全部", "v": ""}]
            for ch in children:
                sub_vals.append({"n": ch["type_name"], "v": ch["type_id"]})
            filters[c["type_id"]] = [{"key": "sub", "name": "子分类", "init": "",
                                      "value": sub_vals}]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        # 首页推荐：最新资源（ac=detail 带封面/播放地址，首页点击可直接进详情）
        data = self._api_get({"ac": "detail", "pg": 1, "pagesize": self.page_size})
        lst = self._items_to_list(data.get("list"))
        if not lst:
            data = self._api_get({"ac": "list", "pg": 1})
            lst = self._items_to_list(data.get("list"))
        return {"list": lst[:50]}

    # ---------- 分类 ----------
    def _detail_page(self, params, page):
        """ac=detail 分页（带封面+播放源）；
        页数/总页数用 API 返回的 page/pagecount（站方已夹取越界页，实测准确）"""
        q = dict(params or {})
        q["ac"] = "detail"
        q["pg"] = page
        data = self._api_get(q)
        lst = self._items_to_list(data.get("list"))
        real_page = _safe_int(data.get("page"), 0) or page
        return self._page_result(lst, real_page,
                                 pagecount=_safe_int(data.get("pagecount"), 0))

    def _enrich_details(self, ids):
        """按 ids 批量取 detail 补封面/备注（保留原顺序）"""
        out = []
        step = 20
        detail_map = {}
        for i in range(0, len(ids), step):
            chunk = ids[i:i + step]
            data = self._api_get({"ac": "detail", "ids": ",".join(chunk)})
            for m in data.get("list") or []:
                item = self._vod_item(m)
                if item:
                    detail_map[item["vod_id"]] = item
        for vid in ids:
            if vid in detail_map:
                out.append(detail_map[vid])
        return out

    def _parent_html_list(self, tid, page):
        """父分类网页聚合列表 /vodtype/{id}-{page}.html（API t=父类 total=0）
        → 取 id 列表后批量补 detail，并从「尾页」链接取总页数"""
        if not requests:
            return self._page_result([], page)
        html = ""
        for gw in self._host_pool():
            base = self._resolve(gw)
            if not base:
                continue
            url = "%s/vodtype/%s-%d.html" % (base, tid, page)
            try:
                r = self.s.get(url, timeout=self.timeout, verify=self.verify,
                               allow_redirects=False)
                if r.status_code in REDIRECT_STATUS:
                    base = self._resolve(gw, fresh=True)
                    url = "%s/vodtype/%s-%d.html" % (base, tid, page)
                    r = self.s.get(url, timeout=self.timeout,
                                   verify=self.verify, allow_redirects=False)
                if r.status_code == 200 and r.text:
                    html = r.text or ""
                    self.gateway, self.host = gw, base or self.host
                    break
            except Exception:
                continue
        if not html:
            return self._page_result([], page)
        ids = []
        seen = set()
        for m in re.finditer(r"/v\d+/(\d+)-\d+-\d+\.html", html):
            vid = m.group(1)
            if vid not in seen:
                seen.add(vid)
                ids.append(vid)
        if not ids:
            return self._page_result([], page)
        pagecount = 0
        # 总页数取「尾页」链接（每个分页条都有，含越界访问时也给真实末页）
        m = re.search(r'href="[^"]*vodtype/\d+-(\d+)\.html"[^>]*>\s*尾页', html)
        if m:
            pagecount = _safe_int(m.group(1), 0)
        if not pagecount:  # 无尾页链接则退回分页号最大值
            for n in re.findall(r"/vodtype/\d+-(\d+)\.html", html):
                pagecount = max(pagecount, _safe_int(n, 0))
        lst = self._enrich_details(ids)
        if pagecount and page > pagecount:
            page = pagecount  # 越界：站点对越界 vodtype 直接返回末页内容，页码夹到末页即可
        return self._page_result(lst, page, pagecount=pagecount)

    def _merged_children_page(self, tid, page):
        """父分类兜底：各子类第 1 页合并去重"""
        out, seen = [], set()
        for ch in self._children_of(tid)[:12]:
            data = self._api_get({"ac": "detail", "t": ch["type_id"], "pg": 1})
            for m in data.get("list") or []:
                item = self._vod_item(m)
                if item and item["vod_id"] not in seen:
                    seen.add(item["vod_id"])
                    out.append(item)
        out.sort(key=lambda x: x.get("vod_remarks") or "", reverse=True)
        return self._page_result(out[: self.page_size], page, one_page=True)

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        t = _to_text(tid)
        page = _safe_int(pg, 1)
        if page < 1:
            page = 1
        fs = {}
        for src in (filter, extend):
            if isinstance(src, dict):
                fs.update(src)

        params = {}

        # 子分类筛选：选中具体子类 → 直接走 API t=子类（sub=0 视同全部）
        sub = _to_text(fs.get("sub") or "")
        if re.match(r"^\d+$", sub) and _safe_int(sub, 0) > 0:
            params["t"] = sub
            return self._detail_page(params, page)

        # 数字分类 id
        if re.match(r"^\d+$", t):
            if self._is_parent_type(t):
                res = self._parent_html_list(t, page)
                if res.get("list"):
                    return res
                return self._merged_children_page(t, page)
            params["t"] = t
            return self._detail_page(params, page)

        # 兜底：最新
        return self._detail_page(params, page)

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        vid = vid.strip()
        if not vid or not re.match(r"^\d+$", vid):
            return {"list": []}
        data = self._api_get({"ac": "detail", "ids": vid})
        rows = data.get("list") or []
        if not rows:
            return {"list": []}
        m = rows[0]
        if not isinstance(m, dict):
            return {"list": []}

        title = _to_text(m.get("vod_name") or "")
        pic = _to_text(m.get("vod_pic") or m.get("vod_pic_thumb") or "")
        content = _strip_tags(m.get("vod_content") or m.get("vod_blurb") or "")
        blurb = _strip_tags(m.get("vod_blurb") or content)
        score = _to_text(m.get("vod_score") or "")
        year = _to_text(m.get("vod_year") or "")
        area = _to_text(m.get("vod_area") or "")
        lang = _to_text(m.get("vod_lang") or "")
        director = _to_text(m.get("vod_director") or "")
        actor = _to_text(m.get("vod_actor") or "")
        genre = _to_text(m.get("vod_class") or m.get("type_name") or "")
        remarks = _to_text(m.get("vod_remarks") or "")
        vtime = _to_text(m.get("vod_time") or m.get("vod_pubdate") or "")
        type_name = _to_text(m.get("type_name") or "")
        duration = _to_text(m.get("vod_duration") or "")
        hits = _safe_int(m.get("vod_hits"), 0)

        info_lines = []
        if type_name:
            info_lines.append("分类: %s" % type_name)
        if year:
            info_lines.append("年份: %s" % year)
        if area:
            info_lines.append("地区: %s" % area)
        if lang:
            info_lines.append("语言: %s" % lang)
        if duration:
            info_lines.append("时长: %s" % duration)
        if score:
            info_lines.append("评分: %s" % score)
        if director:
            info_lines.append("导演: %s" % director)
        if actor:
            info_lines.append("演员: %s" % actor)
        if genre:
            info_lines.append("标签: %s" % genre)
        if vtime:
            info_lines.append("更新: %s" % vtime)
        if hits:
            info_lines.append("热度: %d" % hits)
        if content:
            info_lines.append(content)

        play_from, play_url = self._build_play(m)
        if remarks:
            blurb = (remarks + " | " + blurb).strip(" |")

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": "\n".join(info_lines),
            "vod_blurb": blurb,
            "vod_desc": "\n".join(info_lines),
            "vod_scoring": score,
            "vod_score": score,
            "vod_year": year,
            "vod_area": area,
            "vod_director": director,
            "vod_actor": actor,
            "vod_genre": genre,
            "vod_remarks": remarks,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url) if play_url else "",
        }
        return {"list": [vod]}

    def _build_play(self, m):
        """vod_play_from / vod_play_url 拆分组装；preferM3u8 时 m3u8 源置顶。
        本站 vod_play_url 多为裸 m3u8 直链（无 集名$url 形式）→ 记为「正片」。"""
        raw_from = _to_text(m.get("vod_play_from") or "")
        raw_url = _to_text(m.get("vod_play_url") or "")
        if not raw_url:
            return [], []
        sources = [x for x in raw_from.split("$$$")]
        groups = [x for x in raw_url.split("$$$")]
        pairs = []
        for i, g in enumerate(groups):
            name = _to_text(sources[i]) if i < len(sources) else ("播放%d" % (i + 1))
            eps = []
            for ep in g.split("#"):
                if not ep:
                    continue
                if "$" in ep:
                    ep_name, ep_url = ep.split("$", 1)
                else:
                    ep_name, ep_url = "正片", ep
                ep_name = _to_text(ep_name) or "正片"
                ep_url = _to_text(ep_url)
                if ep_url:
                    eps.append((ep_name, ep_url))
            if eps:
                pairs.append((name, eps))
        if self.prefer_m3u8:
            pairs.sort(key=lambda p: 0 if "m3u8" in p[0].lower()
                       or "m3u8" in "".join(u for _, u in p[1]).lower() else 1)
        play_from, play_url = [], []
        for name, eps in pairs:
            play_from.append(name)
            play_url.append("#".join(
                "%s$%s" % (_sanitize_play(n), _sanitize_play(u)) for n, u in eps))
        return play_from, play_url

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg="1"):
        page = _safe_int(pg, 1)
        keyword = _to_text(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.search_limit, "total": 0}
        data = self._api_get({"ac": "detail", "wd": keyword, "pg": page})
        lst = self._items_to_list(data.get("list"))
        if lst:
            # 总页数用 API 的 pagecount（实测准确，越界页站方自动夹取）
            real_page = _safe_int(data.get("page"), 0) or page
            pc = _safe_int(data.get("pagecount"), 0)
            return {"list": lst, "page": real_page,
                    "pagecount": pc or (real_page + 1),
                    "limit": len(lst), "total": len(lst)}
        # API 搜不到/失败 → 网页搜索回退（自带尾页页数，越界自动夹到末页）
        res = self._search_html(keyword, page)
        lst = res.get("list") or []
        pc = _safe_int(res.get("pagecount"), 0)
        real_page = _safe_int(res.get("page"), 0) or page
        return {"list": lst, "page": real_page,
                "pagecount": pc or (real_page + 1 if lst else real_page),
                "limit": len(lst), "total": len(lst)}

    def _search_html(self, keyword, page):
        """网页搜索回退：站点自身分页格式 /vodsearch/{关键词}----------{页}---1.html。
        注意 /vodsearch/-------------{页}.html 站点不认（pg1/2/3 返回同一批，等于不翻页）。
        返回 {"list": [...], "pagecount": 总页数, "page": 实际页码}。"""
        if not requests or not self.s:
            return {"list": [], "pagecount": 0}
        path = "/vodsearch/%s----------%d---1.html" % (quote(keyword, safe=""), page)
        html = ""
        for gw in self._host_pool():
            base = self._resolve(gw)
            if not base:
                continue
            try:
                r = self.s.get(base + path, timeout=self.timeout,
                               verify=self.verify, allow_redirects=False)
                if r.status_code in REDIRECT_STATUS:
                    base = self._resolve(gw, fresh=True)
                    r = self.s.get(base + path, timeout=self.timeout,
                                   verify=self.verify, allow_redirects=False)
                if r.status_code == 200 and r.text:
                    html = r.text or ""
                    self.gateway, self.host = gw, base or self.host
                    break
            except Exception:
                continue
        if not html:
            return {"list": [], "pagecount": 0}
        ids, seen = [], set()
        for m in re.finditer(r"/v\d+/(\d+)-\d+-\d+\.html", html):
            vid = m.group(1)
            if vid not in seen:
                seen.add(vid)
                ids.append(vid)
        pagecount = 0
        m = re.search(r'----------(\d+)---1\.html"[^>]*>\s*尾页', html)
        if m:
            pagecount = _safe_int(m.group(1), 0)
        if pagecount and page > pagecount:
            # 越界页站点返回近空页（不像 vodtype 直接给末页）→ 夹到末页重取
            return self._search_html(keyword, pagecount)
        return {"list": self._enrich_details(ids)[: self.page_size],
                "pagecount": pagecount, "page": page}

    # ---------- 播放 ----------
    def _proxy_base(self):
        """localProxy 基址：优先 http://127.0.0.1:port/proxy?do=py（播放器可直接播），
        退回 Proxy.getUrl() 的 http(s) 形式；拿不到返回 None（调用方回退直链）。
        部分宿主（OK影视等）不转换 proxy:// 视频请求，故绝不发 proxy://。"""
        try:
            from com.github.catvod import Proxy
            p = Proxy.getPort()
            port = int(p) if str(p).isdigit() else 0
        except Exception:
            port = 0
        if port > 0:
            return "http://127.0.0.1:%s/proxy?do=py" % port
        try:
            from com.github.catvod import Proxy
            q = str(Proxy.getUrl() or "").strip()
            if q.startswith("http://") or q.startswith("https://"):
                if "do=py" not in q:
                    q += ("&" if "?" in q else "?") + "do=py"
                return q
        except Exception:
            pass
        return None

    def _m3u8_proxy_url(self, src):
        """包装 m3u8 为 localProxy URL（token=urlsafe-b64）；拿不到基址返回 None"""
        base = self._proxy_base()
        if not base:
            return None
        tok = base64.urlsafe_b64encode(_to_text(src).encode("utf-8")).decode("ascii")
        return "%s&kind=m3u8&token=%s" % (base, quote(tok, safe=""))

    def _m3u8_play_url(self, src):
        """去广告包装：拿得到 localProxy 则代理 URL，否则回退直链（能播优先）。
        返回 (url, used_proxy)"""
        if not self.strip_ads:
            return _to_text(src), False
        proxy = self._m3u8_proxy_url(src)
        if proxy:
            return proxy, True
        return _to_text(src), False

    def _src_from_proxy_url(self, url):
        """从 localProxy 播放地址（…/proxy?…&kind=m3u8&token=b64 或旧版 proxy://…）
        还原真实 m3u8。用于兼容旧版/App 缓存下来的播放串。"""
        u = _to_text(url)
        if u.startswith("proxy://"):
            qs = u[len("proxy://"):]
        elif "?" in u:
            qs = u.split("?", 1)[1]
        else:
            return ""
        p = self._parse_proxy_param(qs)
        tok = _to_text(p.get("token") or "")
        if not tok:
            return ""
        pad = "=" * (-len(tok) % 4)
        try:
            src = base64.urlsafe_b64decode(tok + pad).decode("utf-8")
        except Exception:
            return ""
        return src if src.startswith(("http://", "https://")) else ""

    @staticmethod
    def _main_path_from_m3u8(url):
        """由 m3u8 URL 推导正片段路径前缀（不含文件名）"""
        try:
            from urllib.parse import urlparse
            path = urlparse(_to_text(url).split("?")[0]).path or ""
        except Exception:
            path = _to_text(url).split("?")[0]
        if not path or "/" not in path:
            return ""
        path = path.rsplit("/", 1)[0]  # 去掉文件名
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 3 and parts[0] == "a3":
            return "/" + "/".join(parts[:3])
        if parts:
            return "/" + "/".join(parts)
        return ""

    @staticmethod
    def _strip_m3u8_ads(text, main_path):
        """过滤 m3u8：只保留路径含 main_path 的分片；无匹配则原样返回。
        广告段特征：路径不含正片路径、独立 AES key。"""
        if not text or not main_path:
            return text
        lines = text.splitlines()
        header = []
        segs = []  # [(tags, url)]
        cur_tags = []
        for line in lines:
            s = line.strip()
            if not s:
                continue
            if s.startswith("#EXTINF") or s.startswith("#EXT-X-DISCONTINUITY") \
                    or s.startswith("#EXT-X-KEY"):
                cur_tags.append(s)
            elif s.startswith("#"):
                # VERSION/STREAM-INF/MEDIA-SEQUENCE 等放 header（流独立时）
                if not segs:
                    header.append(s)
                else:
                    cur_tags.append(s)
            else:
                segs.append((cur_tags, s))
                cur_tags = []
        kept = [(tags, url) for tags, url in segs if main_path in url]
        if not kept:
            return text
        out = header[:]
        prev_key = None
        emitted = False
        for tags, url in kept:
            for t in tags:
                if t.startswith("#EXT-X-KEY"):
                    if t == prev_key:
                        continue
                    prev_key = t
                if t.startswith("#EXT-X-DISCONTINUITY") and not emitted:
                    continue
                out.append(t)
            out.append(url)
            emitted = True
        if any(l.strip() == "#EXT-X-ENDLIST" for l in lines):
            out.append("#EXT-X-ENDLIST")
        return "\n".join(out) + "\n"

    def _clean_m3u8(self, src):
        """拉取 m3u8（master 则跟到首个 media），按主路径去广告分片。
        失败返回 None（调用方回退直链）。"""
        if not requests or not self.s:
            return None
        headers = {
            "User-Agent": self.ua,
            "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,*/*",
            "Referer": self.host + "/",
        }
        try:
            r = self.s.get(src, headers=headers, timeout=self.timeout,
                           verify=self.verify)
            if r.status_code != 200 or not r.content:
                return None
            text = r.content.decode("utf-8", "ignore")
        except Exception:
            return None
        if "#EXT-X-STREAM-INF" in text:
            # master → 解析首个媒体 m3u8
            media = ""
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    media = line if line.startswith("http") else urljoin(src, line)
                    break
            if not media:
                return None
            try:
                r2 = self.s.get(media, headers=headers, timeout=self.timeout,
                                verify=self.verify)
                if r2.status_code != 200 or not r2.content:
                    return None
                media_text = r2.content.decode("utf-8", "ignore")
            except Exception:
                return None
            main_path = self._main_path_from_m3u8(media)
            cleaned = self._strip_m3u8_ads(media_text, main_path)
            return cleaned
        main_path = self._main_path_from_m3u8(src)
        return self._strip_m3u8_ads(text, main_path)

    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        vid = _to_text(vid)
        if not vid:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

        # 旧版/App 缓存下来的 localProxy 播放地址 → 还原真实 m3u8 直接播
        # （proxy:// 绝不交给播放器：OK影视等宿主不转换该协议）
        if vid.startswith("proxy://") or "kind=m3u8" in vid or "/proxy?" in vid:
            real = self._src_from_proxy_url(vid)
            if real:
                vid = real

        # m3u8 / mp4 等直链
        if vid.startswith(("http://", "https://")):
            low = vid.lower().split("?")[0]
            if low.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi", ".m4v")):
                header = {"User-Agent": self.ua, "Referer": self.host + "/",
                          "Accept": "*/*"}
                # m3u8 优先走 localProxy（ext.stripAds=false 关回直链）；
                # 拿不到可用基址时回退直链——能播优先，绝不发 proxy://（OK影视等不认）
                if self.strip_ads and low.endswith(".m3u8"):
                    play_url, used_proxy = self._m3u8_play_url(vid)
                    if used_proxy:
                        header = {"User-Agent": self.ua, "Accept": "*/*"}
                    return {"parse": 0, "jx": 0, "playUrl": "", "url": play_url,
                            "header": header}
                return {"parse": 0, "jx": 0, "playUrl": "", "url": vid,
                        "header": header}
            # 分享页/其它网页：尝试解出 m3u8；成功则直链，失败交给 App 解析
            if "share" in vid or low.endswith((".html", ".htm", "/")):
                m3u8 = self._fetch_m3u8_from_share(vid)
                if m3u8:
                    if self.strip_ads:
                        play_url, used_proxy = self._m3u8_play_url(m3u8)
                        header = ({"User-Agent": self.ua, "Accept": "*/*"}
                                  if used_proxy else
                                  {"User-Agent": self.ua,
                                   "Referer": self.host + "/", "Accept": "*/*"})
                        return {"parse": 0, "jx": 0, "playUrl": "",
                                "url": play_url, "header": header}
                    return {"parse": 0, "jx": 0, "playUrl": "", "url": m3u8,
                            "header": {"User-Agent": self.ua,
                                       "Referer": self.host + "/",
                                       "Accept": "*/*"}}
            return {"parse": 1, "jx": 0, "playUrl": "", "url": vid,
                    "header": {"User-Agent": self.ua, "Referer": self.host + "/"}}
        return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

    def _fetch_m3u8_from_share(self, url):
        """分享页 → 解析内嵌 m3u8（失败返回空）"""
        if not requests:
            return ""
        headers = {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Referer": self.host + "/",
        }
        try:
            r = self.s.get(url, headers=headers, timeout=self.timeout,
                           verify=self.verify)
        except Exception:
            return ""
        text = ""
        try:
            text = r.content.decode("utf-8", "ignore")
        except Exception:
            text = r.text or ""
        if not text:
            return ""
        m = re.search(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', text, re.I)
        return m.group(0) if m else ""

    def _parse_proxy_param(self, param):
        if isinstance(param, dict):
            return {str(k): _to_text(v) for k, v in param.items()}
        s = _to_text(param or "").strip()
        if not s:
            return {}
        if s.startswith("{"):
            try:
                d = json.loads(s)
                if isinstance(d, dict):
                    return {str(k): _to_text(v) for k, v in d.items()}
            except Exception:
                pass
        s = s.lstrip("?")
        out = {}
        for part in s.split("&"):
            if not part:
                continue
            if "=" in part:
                k, v = part.split("=", 1)
            else:
                k, v = part, ""
            k = unquote(k.strip())
            if not k:
                continue
            out[k] = unquote(v.strip())
        return out

    def localProxy(self, param):
        """kind=m3u8：token=base64(原始 m3u8 URL) → 返回过滤广告后的媒体列表"""
        try:
            p = self._parse_proxy_param(param)
            kind = _to_text(p.get("kind") or "").lower()
            if kind != "m3u8":
                return [404, "text/plain", b"Not Found", {}]
            token = _to_text(p.get("token") or "")
            if not token:
                return [400, "text/plain", b"missing token", {}]
            # base64.urlsafe 解码（补齐 padding）
            pad = "=" * (-len(token) % 4)
            try:
                src = base64.urlsafe_b64decode(token + pad).decode("utf-8")
            except Exception:
                return [400, "text/plain", b"bad token", {}]
            if not src.startswith(("http://", "https://")):
                return [400, "text/plain", b"bad src", {}]
            cleaned = self._clean_m3u8(src)
            if cleaned is None:
                # 清洗失败：上游取不到 m3u8 → 502 提示重试（可 ext.stripAds=false 直连）
                return [502, "text/plain", b"upstream failed", {}]
            body = cleaned.encode("utf-8")
            return [200, "application/vnd.apple.mpegurl", body,
                    {"Cache-Control": "no-cache",
                     "Access-Control-Allow-Origin": "*"}]
        except Exception:
            return [404, "text/plain", b"Not Found", {}]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = _to_text(url).lower().split("?")[0]
        return u.endswith((".mp4", ".m3u8", ".flv", ".mkv", ".ts", ".avi", ".m4v"))

    def action(self, action):
        return {}

    def destroy(self):
        try:
            self._cache_save()
        except Exception:
            pass
        try:
            if self.s is not None:
                self.s.close()
        except Exception:
            pass
        return None


# 命令行自检：python3 hsckcc.py（不影响宿主加载）
if __name__ == "__main__":
    sp = Spider()
    sp.init("")
    print("VERSION", VERSION)
    # 默认懒探测：首个 homeContent 自行解析入口（不预跑测速，冷启动省 3s+）
    t0 = time.time()
    hc = sp.homeContent()
    print("lazy homeContent %.1fs -> %d 分类, %d 筛选组" %
          (time.time() - t0, len(hc.get("class") or []),
           len(hc.get("filters") or {})))
    print("picked:", sp.gateway, "->", sp.host)
    for gw in sp.host_candidates:
        print("  resolve %s -> %s" % (gw, sp._resolve_cache.get(gw, "(未解析)")))
    print("candidates:", sp._host_pool())
    classes = hc.get("class") or []
    print("classes", len(classes), [c["type_name"] for c in classes])
    print("filters", {k: [x["name"] for x in v] for k, v in (hc.get("filters") or {}).items()})
    print("homeVideo", len((sp.homeVideoContent() or {}).get("list") or []))
    # 抽测几个分类（父分类走网页聚合、子分类走 API）
    tested = set()
    for c in classes:
        tid = c["type_id"]
        if tid in tested or len(tested) >= 8:
            continue
        tested.add(tid)
        try:
            r = sp.categoryContent(tid, "1", {}, {}) or {}
            print("cat", tid, c["type_name"], "->", len(r.get("list") or []),
                  "pagecount", r.get("pagecount"))
            if r.get("list"):
                sub = sp._children_of(tid)
                if sub:
                    r2 = sp.categoryContent(tid, "1", {"sub": sub[0]["type_id"]}, {}) or {}
                    print("   sub", sub[0]["type_name"], "->", len(r2.get("list") or []))
                    break
        except Exception as e:
            print("cat", tid, "ERR", type(e).__name__, str(e)[:60])
    try:
        s1 = sp.searchContent("巨乳")
        lst = s1.get("list") or []
        print("search", len(lst), "page", s1.get("page"), "pagecount", s1.get("pagecount"))
        s2 = sp.searchContent("巨乳", pg="2")
        print("search p2", len((s2 or {}).get("list") or []),
              "pagecount", (s2 or {}).get("pagecount"))
        # 网页搜索回退（独立于 API）
        h1 = sp._search_html("巨乳", 1)
        h2 = sp._search_html("巨乳", 2)
        ids1 = set(x["vod_id"] for x in h1["list"])
        ids2 = set(x["vod_id"] for x in h2["list"])
        print("html search p1/p2", len(h1["list"]), "/", len(h2["list"]),
              "pc", h1.get("pagecount"), "交集", len(ids1 & ids2))
        if lst:
            vid = lst[0]["vod_id"]
            d = sp.detailContent([vid])
            vod = (d.get("list") or [{}])[0]
            print("detail", vid, (vod.get("vod_name") or "")[:40],
                  "play_from", vod.get("vod_play_from"),
                  "play_url", (vod.get("vod_play_url") or "")[:120])
            # 取第一源第一条测 player（先按 $$$ 分源，再按 # 分集）
            first = ""
            for g in (vod.get("vod_play_url") or "").split("$$$"):
                ep = g.split("#")[0]
                if "$" in ep:
                    first = ep.split("$", 1)[1]
                    break
            if first:
                print("player", sp.playerContent("正片", [first]))
                # localProxy 清洗自检
                import base64 as _b64
                tok = _b64.urlsafe_b64encode(first.encode("utf-8")).decode("ascii")
                res = sp.localProxy("kind=m3u8&token=" + quote(tok, safe=""))
                body = res[2] if isinstance(res, (list, tuple)) else b""
                print("proxy", res[0] if isinstance(res, (list, tuple) ) else res,
                      "len", len(body),
                      "head", body[:60].decode("utf-8", "ignore").replace("\n", " | "))
    except Exception as e:
        print("search ERR", type(e).__name__, str(e)[:80])
    # 对照：ext.probe=true 时先测速选最快入口
    try:
        sp2 = Spider()
        sp2.init({"probe": True})
        t0 = time.time()
        picked = sp2._probe_host()
        print("eager probe(ext.probe=true) %.1fs -> %s -> %s" %
              (time.time() - t0, sp2.gateway, picked))
        sp2.destroy()
    except Exception as e:
        print("eager probe ERR", type(e).__name__, str(e)[:80])
    sp.destroy()
    # 磁盘缓存 warm 自检：新实例（模拟 TVBox 下一次调用）读缓存后应明显更快
    try:
        size = os.path.getsize(CACHE_FILE) if os.path.exists(CACHE_FILE) else -1
        print("cache", CACHE_FILE, ("%dB" % size) if size >= 0 else "(未生成)")
    except Exception as e:
        print("cache stat ERR", type(e).__name__, str(e)[:80])
    try:
        sp3 = Spider()
        sp3.init("")
        t0 = time.time()
        hc3 = sp3.homeContent()
        print("warm homeContent(新实例读缓存) %.1fs -> %d 分类, %d 筛选组" %
              (time.time() - t0, len(hc3.get("class") or []),
               len(hc3.get("filters") or {})))
        print("warm resolve 预热:", sp3._resolve_cache.get(
            "https://444.ablck.cc", "(未缓存)"))
        sp3.destroy()
    except Exception as e:
        print("warm ERR", type(e).__name__, str(e)[:80])
