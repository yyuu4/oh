# -*- coding: utf-8 -*-
VERSION = "1.3.0"
# v1.0.0 初版：MacCMS 采集 API（list/detail/search），封面+详情+分页；hsckm3u8 直链 / hsckyun 分享页解 m3u8；分类筛选/搜索/详情/播放自检通过；
# v1.0.1 筛选修正：站点 API 实测仅 year 有效（filter_by/sort_by/area 等均被忽略），改为年份筛选——子类直查 year，父类经子类 API 合并；
# v1.1.0 三域名候选（hsckzy.vip / hsckzy.xyz / hsckzy001.com）自动测速切换——API 探测挑最快可用域名，失败自动跳过，extend.hosts 可覆盖；
# v1.1.1 多域名健壮性：校验 MacCMS 响应结构（排除 Cloudflare 错误页误判成功），坏域名失败自动切换下一候选；extend.hosts 保留用户指定顺序；
# v1.2.0 分类重构：只保留顶级分类，子分类（网红主播/国产传媒等）改为父分类下的「子分类」筛选组——选中子类直接 API 直查，选全部走父类聚合；
# v1.3.0 去广告：CDN 在正片 m3u8 头/尾拼接广告分片（独立 path+AES key，片头~22s/片尾固定~19s）——playerContent 走 localProxy 重写播放列表，
#          按主路径过滤只保留正片段；ext.stripAds=false 可关回直链；
# hsckvip.py —— 黄色仓库资源站 (MacCMS) 爬虫
# 数据走 /api.php/provide/vod/ 标准采集 API；播放源为 m3u8 直链（hsckm3u8）或分享页（hsckyun，播放时解出 m3u8）。
import os
import re
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
#     "host": "https://hsckzy.vip",
#     "hosts": ["https://hsckzy.vip", "https://hsckzy.xyz", "https://hsckzy001.com"],
#     "proxy": "http://127.0.0.1:7890",
#     "verify": false,
#     "cookie": "",
#     "preferM3u8": true
#   }

# 主域名（探测成功后会自动切到最快可用域名）
HOST = "https://hsckzy.vip"
# 多域名候选：逐个请求采集 API，能连上 + 能出 JSON 的优先，最快者胜；
# 全失败才回退 HOST。extend.host / extend.hosts 可覆盖。
HOST_CANDIDATES = [
    "https://hsckzy.vip",
    "https://hsckzy.xyz",
    "https://hsckzy001.com",
]

PAGE_SIZE = 20
SEARCH_LIMIT = 20

HTTP_RETRY = 1
HTTP_RETRY_DELAY = 0.5
HTTP_RETRY_STATUS = (429, 500, 502, 503, 504)

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


def _safe_json(text, fallback=None):
    try:
        return json.loads(str(text or ""))
    except Exception:
        return fallback if fallback is not None else {}


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


# ==================== Spider ====================

class Spider:
    def __init__(self):
        self.s = None
        self.host = HOST
        self.host_candidates = list(HOST_CANDIDATES)
        self.ua = WEB_UA
        self.timeout = 15
        self.page_size = PAGE_SIZE
        self.search_limit = SEARCH_LIMIT
        self.cookie = ""
        self.verify = False
        self.proxy = ""
        self.prefer_m3u8 = True
        self.strip_ads = False
        self._class_cache = []
        self._host_locked = False
        self._probed = False

        if requests:
            self.s = requests.Session()
            self.s.headers.update(LIST_HEADERS)
            self._apply_proxy()

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
            self._host_locked = True
        # 多域名候选（list 或 逗号分隔字符串）：host 层自动切换用
        hv = extend.get("hosts") or extend.get("hostList") or extend.get("hostCandidates")
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
        if extend.get("noProbe"):
            self._host_locked = True
        if extend.get("cookie"):
            self.cookie = str(extend["cookie"])
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

    def set_proxy(self, value):
        self.proxy = _norm_proxy(value)
        self._apply_proxy()
        return self.proxy

    def _apply_proxy(self):
        if not self.s:
            return
        if self.proxy:
            self.s.trust_env = False
            self.s.proxies = {"http": self.proxy, "https": self.proxy}
        else:
            self.s.trust_env = True
            self.s.proxies = {}

    # ---------- API ----------
    @property
    def _api(self):
        return self.host + "/api.php/provide/vod/"

    def _host_pool(self):
        """候选 host 池：当前 host + 内置/extend 候选，去重保序；
        锁定（extend.host / noProbe）时只用当前 host。"""
        if self._host_locked:
            return [self.host]
        pool = []
        for h in ([self.host] + list(self.host_candidates or [])):
            h = _to_text(h).rstrip("/")
            if h and h not in pool:
                pool.append(h)
        return pool or [HOST]

    def _api_alive(self, host, timeout=8):
        """探测 host 的采集 API 是否可用（MacCMS 结构 JSON 即视为可用）"""
        if not requests or not self.s:
            return False, 0.0
        url = host + "/api.php/provide/vod/"
        t0 = time.time()
        try:
            r = self.s.get(url, params={"ac": "list", "pg": 1},
                           timeout=timeout, verify=self.verify)
            dt = time.time() - t0
            if r.status_code != 200 or not r.content:
                return False, dt
            data = r.json()
            return self._is_maccms_json(data), dt
        except Exception:
            return False, time.time() - t0

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

    def _probe_host(self):
        """逐个候选 host 测速：能出 JSON 的最快者胜；全失败保持当前 host。
        返回最终选中的 host。"""
        best = None  # (耗时, host)
        for h in self._host_pool():
            ok, dt = self._api_alive(h)
            if not ok:
                continue
            if best is None or dt < best[0]:
                best = (dt, h)
        if best:
            self.host = best[1]
        self._probed = True
        return self.host

    def _ensure_host(self):
        if not self._probed and not self._host_locked:
            try:
                self._probe_host()
            except Exception:
                self._probed = True

    def _api_get(self, params=None, timeout=None):
        """GET /api.php/provide/vod/ → dict。
        首次调用先测速选最快域名；当前域名失败时自动切换候选重试。"""
        if not requests:
            return {}
        self._ensure_host()
        t = timeout or self.timeout
        pool = self._host_pool() if not self._host_locked else [self.host]
        # 当前 host 放最前，失败后再试其它
        ordered = [self.host] + [h for h in pool if h != self.host]
        for h in ordered:
            url = h + "/api.php/provide/vod/"
            for attempt in range(HTTP_RETRY + 1):
                try:
                    r = self.s.get(url, params=params or {}, timeout=t,
                                   verify=self.verify)
                    if r.status_code in HTTP_RETRY_STATUS and attempt < HTTP_RETRY:
                        time.sleep(HTTP_RETRY_DELAY)
                        continue
                    data = r.json()
                    if self._is_maccms_json(data):
                        # 切到可用域名
                        if h != self.host:
                            self.host = h
                        return data
                    break  # 非 API JSON / 空：换下一个 host
                except Exception:
                    if attempt < HTTP_RETRY:
                        time.sleep(HTTP_RETRY_DELAY)
                        continue
                    break  # 该 host 网络失败，换下一个
        return {}  # 所有候选都失败（不回传 Cloudflare 错误页等脏数据）

    def _classes_raw(self):
        """采集 class 分类树（缓存）"""
        if self._class_cache:
            return self._class_cache
        data = self._api_get({"ac": "list", "pg": 1})
        rows = data.get("class") or []
        out = []
        for c in rows:
            if not isinstance(c, dict):
                continue
            tid = _safe_int(c.get("type_id"), 0)
            if not tid:
                continue
            out.append({
                "type_id": str(tid),
                "type_pid": _safe_int(c.get("type_pid"), 0),
                "type_name": _to_text(c.get("type_name") or str(tid)),
            })
        self._class_cache = out
        return out

    def _children_of(self, pid):
        return [c for c in self._classes_raw() if c["type_pid"] == _safe_int(pid)]

    def _is_parent_type(self, tid):
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
    def _page_result(out, page, one_page=False):
        if one_page:
            return {"list": out, "page": 1, "pagecount": 1,
                    "limit": len(out), "total": len(out)}
        return {"list": out, "page": page,
                "pagecount": page + 1 if out else page,
                "limit": len(out), "total": len(out)}

    # ---------- 首页 ----------
    def homeContent(self, filter=None):
        # 只保留顶级分类；子分类做成父分类下的「子分类」筛选组
        classes = []
        for c in self._classes_raw():
            if c["type_pid"] == 0:
                classes.append({"type_id": c["type_id"],
                                "type_name": c["type_name"]})

        # 年份筛选（采集 API 实测仅 year 有效）
        year_now = time.localtime().tm_year
        year_vals = [{"n": "全部", "v": ""}]
        for y in range(year_now, year_now - 6, -1):
            year_vals.append({"n": str(y), "v": str(y)})

        filters = {}
        for c in classes:
            groups = []
            # 子分类筛选组（仅父分类有子类时才挂）
            children = self._children_of(c["type_id"])
            if children:
                sub_vals = [{"n": "全部", "v": ""}]
                for ch in children:
                    sub_vals.append({"n": ch["type_name"],
                                     "v": ch["type_id"]})
                groups.append({"key": "sub", "name": "子分类", "init": "",
                               "value": sub_vals})
            groups.append({"key": "year", "name": "年份", "init": "",
                           "value": list(year_vals)})
            filters[c["type_id"]] = groups
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
        """ac=detail 分页（带封面+播放源）"""
        q = dict(params or {})
        q["ac"] = "detail"
        q["pg"] = page
        data = self._api_get(q)
        lst = self._items_to_list(data.get("list"))
        return self._page_result(lst, page)

    def _list_page(self, params, page):
        """ac=list 分页（轻量，无封面）→ 再批量补 detail 封面"""
        q = dict(params or {})
        q["ac"] = "list"
        q["pg"] = page
        data = self._api_get(q)
        rows = data.get("list") or []
        ids = [str(_safe_int(r.get("vod_id"), 0)) for r in rows
               if isinstance(r, dict) and _safe_int(r.get("vod_id"), 0)]
        lst = self._enrich_details(ids) if ids else self._items_to_list(rows)
        return self._page_result(lst, page)

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
        """父分类 HTML 列表页（API t=父类 total=0，网页聚合子类）→ id 列表后批量补 detail"""
        if not requests:
            return self._page_result([], page)
        html = ""
        for h in self._host_pool():
            url = "%s/index.php/vod/type/id/%s/page/%d.html" % (h, tid, page)
            try:
                r = self.s.get(url, timeout=self.timeout, verify=self.verify)
                if r.status_code == 200 and r.text:
                    html = r.text or ""
                    self.host = h
                    break
            except Exception:
                continue
        if not html:
            return self._page_result([], page)
        ids = []
        seen = set()
        for m in re.finditer(r"/index\.php/vod/detail/id/(\d+)\.html", html):
            vid = m.group(1)
            if vid not in seen:
                seen.add(vid)
                ids.append(vid)
        if not ids:
            return self._page_result([], page)
        lst = self._enrich_details(ids)[: self.page_size]
        return self._page_result(lst, page)

    def _merged_children_page(self, tid, page, year=""):
        """父分类兜底：各子类第 1 页合并去重（year 筛选时经 API 合并）"""
        out, seen = [], set()
        for ch in self._children_of(tid)[:12]:
            q = {"ac": "detail", "t": ch["type_id"], "pg": 1}
            if year:
                q["year"] = year
            data = self._api_get(q)
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
        year = _to_text(fs.get("year") or "")
        if re.match(r"^\d{4}$", year):
            params["year"] = year

        # 子分类筛选：选中具体子类 → 直接走 API t=子类
        sub = _to_text(fs.get("sub") or "")
        if re.match(r"^\d+$", sub):
            params["t"] = sub
            return self._detail_page(params, page)

        # 数字分类 id
        if re.match(r"^\d+$", t):
            if self._is_parent_type(t):
                if year:
                    # 父分类 + 年份：经子类 API 合并（HTML 页不支持 year）
                    return self._merged_children_page(t, page, year=year)
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
        """vod_play_from / vod_play_url 拆分组装；preferM3u8 时 m3u8 源置顶"""
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
            pairs.sort(key=lambda p: 0 if "m3u8" in p[0].lower() else 1)
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
        return {"list": lst, "page": page,
                "pagecount": page + 1 if lst else page,
                "limit": len(lst), "total": len(lst)}

    # ---------- 播放 ----------
    def _proxy_base(self):
        """localProxy 基址：优先 Proxy.getPort()，退回 proxy://do=py"""
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
            q = Proxy.getUrl()
            if q and ("do=py" in str(q) or str(q).startswith("proxy://")):
                return str(q)
        except Exception:
            pass
        return "proxy://do=py"

    def _m3u8_proxy_url(self, src):
        """包装 m3u8 为 localProxy URL（token=urlsafe-b64）"""
        tok = base64.urlsafe_b64encode(_to_text(src).encode("utf-8")).decode("ascii")
        return "%s&kind=m3u8&token=%s" % (self._proxy_base(), quote(tok, safe=""))

    @staticmethod
    def _main_path_from_m3u8(url):
        """由 m3u8 URL 推导正片段路径前缀（不含文件名），如 /a3/20261013/HwsaAFv7"""
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
        广告段特征：路径不含正片 /a3/{date}/{id}/，独立 AES key。"""
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

    def _fetch_m3u8_from_share(self, url):
        """hsckyun 分享页 → 解析内嵌 m3u8（失败返回空）"""
        if not requests:
            return ""
        headers = {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Referer": self.host + "/",
        }
        # 分享页域名与站点 host 无关；若相对路径则补当前 host
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

    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        vid = _to_text(vid)
        if not vid:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

        # m3u8 / mp4 等直链
        if vid.startswith(("http://", "https://")):
            low = vid.lower().split("?")[0]
            if low.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi", ".m4v")):
                header = {"User-Agent": self.ua, "Referer": self.host + "/",
                          "Accept": "*/*"}
                # m3u8 默认走 localProxy 去广告（ext.stripAds=false 关回直链）
                if self.strip_ads and low.endswith(".m3u8"):
                    return {"parse": 0, "jx": 0, "playUrl": "",
                            "url": self._m3u8_proxy_url(vid), "header": header}
                return {"parse": 0, "jx": 0, "playUrl": "", "url": vid,
                        "header": header}
            # 分享页/其它网页：尝试解出 m3u8；成功则直链，失败交给 App 解析
            if "share" in vid or low.endswith((".html", ".htm", "/")):
                m3u8 = self._fetch_m3u8_from_share(vid)
                if m3u8:
                    header = {"User-Agent": self.ua,
                              "Referer": self.host + "/",
                              "Accept": "*/*"}
                    if self.strip_ads:
                        return {"parse": 0, "jx": 0, "playUrl": "",
                                "url": self._m3u8_proxy_url(m3u8),
                                "header": header}
                    return {"parse": 0, "jx": 0, "playUrl": "", "url": m3u8,
                            "header": header}
            return {"parse": 1, "jx": 0, "playUrl": "", "url": vid,
                    "header": {"User-Agent": self.ua, "Referer": self.host + "/"}}
        return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

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
        """kind=m3u8：token=base64(原始 m3u8 URL) → 返回去广告后的媒体列表"""
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
                # 清洗失败：回退直链内容不可得，返回空列表引导 App 重试
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
            if self.s is not None:
                self.s.close()
        except Exception:
            pass
        return None


# 命令行自检：python3 hsckvip.py（不影响宿主加载）
if __name__ == "__main__":
    sp = Spider()
    sp.init("")
    print("VERSION", VERSION)
    # 多域名测速
    print("hosts:", sp._host_pool())
    picked = sp._probe_host()
    print("picked host:", picked)
    for h in sp._host_pool():
        ok, dt = sp._api_alive(h)
        print("  probe %s %s %.0fms" % ("OK " if ok else "ERR", h, dt * 1000))
    hc = sp.homeContent()
    classes = hc.get("class") or []
    print("classes", len(classes), "filters", len(hc.get("filters") or {}))
    print("homeVideo", len((sp.homeVideoContent() or {}).get("list") or []))
    # 抽测几个分类
    tested = set()
    for c in classes:
        tid = c["type_id"]
        if tid in tested or len(tested) >= 8:
            continue
        tested.add(tid)
        try:
            n = len((sp.categoryContent(tid, "1", {}, {}) or {}).get("list") or [])
            print("cat", tid, c["type_name"], "->", n)
        except Exception as e:
            print("cat", tid, "ERR", type(e).__name__, str(e)[:60])
    try:
        lst = (sp.searchContent("巨乳") or {}).get("list") or []
        print("search", len(lst))
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
    except Exception as e:
        print("search ERR", type(e).__name__, str(e)[:80])
