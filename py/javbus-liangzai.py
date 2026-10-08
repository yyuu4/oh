# -*- coding: utf-8 -*-
import os
import re
import json
import time
import html as _html
from urllib.parse import quote, unquote, urljoin

try:
    import requests
except ImportError:
    requests = None


HOST = "https://www.buscdn.casa"
HOST_UC = HOST + "/uncensored"
IMG_HOST = HOST

PAGE_SIZE = 30
SEARCH_LIMIT = 30

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

LIST_HEADERS = {
    "User-Agent": WEB_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
    "Referer": HOST + "/",
}

AJAX_HEADERS = {
    "User-Agent": WEB_UA,
    "Accept": "text/html, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": HOST + "/",
}

JAVBUS_CLASSES = [
    {"type_id": "jav_home",               "type_name": "有碼"},
    {"type_id": "jav_uncensored",          "type_name": "無碼"},
    {"type_id": "jav_genre",              "type_name": "有碼類別"},
    {"type_id": "jav_uncensored_genre",   "type_name": "無碼類別"},
    {"type_id": "jav_actress",            "type_name": "有碼女優"},
    {"type_id": "jav_uncensored_actress", "type_name": "無碼女優"},
]

# 女优筛选最多显示多少个
STAR_FILTER_LIMIT = 50


def _env(name, default=""):
    try:
        return os.environ.get(name, default) or default
    except Exception:
        return default


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


def _fix_url(url, host=HOST):
    if not url:
        return ""
    url = _to_text(url)
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(host.rstrip("/") + "/", url)


def _clean_text(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", str(s))
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _normalize_magnet(magnet):
    if not magnet:
        return ""
    m = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet)
    if not m:
        return magnet
    return "magnet:?xt=urn:btih:" + m.group(1)


def _extract_id(url):
    if not url:
        return ""
    m = re.search(r"/([A-Za-z0-9_\-\.]+)/?$", url)
    return m.group(1) if m else ""


class Spider:
    def __init__(self):
        self.s = self.session = self.sess = None
        self.host = HOST
        self.host_uc = HOST_UC
        self.img_host = IMG_HOST
        self.ua = WEB_UA
        self.timeout = 15
        self.page_size = PAGE_SIZE
        self.search_limit = SEARCH_LIMIT
        self.enable_magnet = True
        self.enable_uncensored = True
        self.cookie = ""
        self.img_proxy = ""
        self.lang = "zh"

        # filters / 默认值缓存
        self._cache_filters = {}

        if requests:
            self.s = self.session = self.sess = requests.Session()
            self.s.headers.update(LIST_HEADERS)

    def getDependence(self):
        return []

    def init(self, extend=""):
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}

        if extend.get("host"):
            self.host = str(extend["host"]).rstrip("/")
            self.host_uc = self.host + "/uncensored"
            self.img_host = self.host
        if extend.get("img") or extend.get("imgProxy"):
            self.img_proxy = str(extend.get("img") or extend.get("imgProxy") or "").strip()
        if extend.get("cookie"):
            self.cookie = str(extend["cookie"])
        if extend.get("lang"):
            self.lang = str(extend["lang"])
        if "enableMagnet" in extend:
            self.enable_magnet = bool(extend["enableMagnet"])
        if "enableUncensored" in extend:
            self.enable_uncensored = bool(extend["enableUncensored"])

        # 清空缓存
        self._cache_filters = {}

    # ========== 首页分类 ==========
    def homeContent(self, filter=None):
        classes = []
        for c in JAVBUS_CLASSES:
            if c["type_id"] in ("jav_uncensored", "jav_uncensored_genre",
                                "jav_uncensored_actress") and not self.enable_uncensored:
                continue
            classes.append(dict(c))

        filters = {}
        for c in classes:
            tid = c["type_id"]
            if tid == "jav_genre":
                filters[tid] = self._build_genre_filters(self.host + "/genre")
            elif tid == "jav_uncensored_genre":
                filters[tid] = self._build_genre_filters(self.host + "/uncensored/genre")
            elif tid == "jav_actress":
                filters[tid] = self._build_star_filters(self.host + "/actresses")
            elif tid == "jav_uncensored_actress":
                filters[tid] = self._build_star_filters(self.host + "/uncensored/actresses")
        return {"class": classes, "filters": filters}

    # ---------- 类别筛选 ----------
    def _build_genre_filters(self, index_url):
        cache_key = "genre:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
        except Exception:
            return []

        groups = self._parse_genre_groups(text)
        out = []
        for gname, items in groups:
            if not items:
                continue
            values = [{"n": "全部", "v": ""}]
            for it in items:
                values.append({"n": it["name"], "v": it["gid"]})
            out.append({
                "key": "genre_" + gname,
                "name": gname,
                "init": "",
                "value": values,
            })

        self._cache_filters[cache_key] = out
        return out

    def _parse_genre_groups(self, text):
        groups = []
        h4_iter = list(re.finditer(r"<h4>([^<]+)</h4>", text))
        if not h4_iter:
            return groups

        for i, m in enumerate(h4_iter):
            gname = _clean_text(m.group(1))
            start = m.end()
            end = h4_iter[i + 1].start() if i + 1 < len(h4_iter) else len(text)
            block = text[start:end]

            items = []
            seen = set()
            for gb in re.finditer(
                r'<div[^>]+class="[^"]*genre-box[^"]*"[^>]*>(.*?)</div>',
                block, re.S
            ):
                inner = gb.group(1)
                for a in re.finditer(
                    r'<a[^>]+href="([^"]*?/genre/([^"/]+))"[^>]*>([^<]+)</a>',
                    inner
                ):
                    gid = a.group(2)
                    name = _clean_text(a.group(3))
                    if not gid or not name or gid in seen:
                        continue
                    seen.add(gid)
                    items.append({"gid": gid, "name": name})
            if items:
                groups.append((gname, items))
        return groups

    # ---------- 女优筛选 ----------
    def _build_star_filters(self, index_url):
        cache_key = "star:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
        except Exception:
            return []

        values = [{"n": "全部", "v": ""}]
        seen = set()
        for m in re.finditer(
            r'<a[^>]+class="[^"]*avatar-box[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            text, re.S
        ):
            href = _fix_url(m.group(1), self.host)
            block = m.group(2)
            sid = _extract_id(href)
            name = ""
            nm = re.search(r"<span>([^<]+)</span>", block)
            if nm:
                name = _clean_text(nm.group(1))
            if not sid or not name or sid in seen:
                continue
            seen.add(sid)
            values.append({"n": name, "v": sid})
            if len(values) > STAR_FILTER_LIMIT:
                break

        if len(values) <= 1:
            self._cache_filters[cache_key] = []
            return []

        out = [{
            "key": "star",
            "name": "女優",
            "init": "",
            "value": values,
        }]
        self._cache_filters[cache_key] = out
        return out

    # ---------- 默认值（点分类未选筛选时用） ----------
    def _get_default_genre(self, index_url):
        """取类别页第一个类别作为默认"""
        cache_key = "default_genre:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
        except Exception:
            return ""

        groups = self._parse_genre_groups(text)
        for gname, items in groups:
            if items:
                gid = items[0]["gid"]
                self._cache_filters[cache_key] = gid
                return gid
        return ""

    def _get_default_star(self, index_url):
        """取女优页第一个女优作为默认"""
        cache_key = "default_star:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
        except Exception:
            return ""

        for m in re.finditer(
            r'<a[^>]+class="[^"]*avatar-box[^"]*"[^>]+href="([^"]+)"',
            text
        ):
            href = _fix_url(m.group(1), self.host)
            sid = _extract_id(href)
            if sid:
                self._cache_filters[cache_key] = sid
                return sid
        return ""

    def homeVideoContent(self):
        return {"list": []}

    # ========== 分类内容 ==========
    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        t = _to_text(tid)
        page = _safe_int(pg, 1)

        # 解析筛选
        genre_sel = {}
        star_sel = {}
        for src in (filter, extend):
            if isinstance(src, dict):
                for k, v in src.items():
                    k = _to_text(k)
                    v = _to_text(v)
                    if not v:
                        continue
                    if k.startswith("genre_"):
                        genre_sel[v] = True
                    elif k == "star":
                        star_sel[v] = True

        # 有码首页
        if t == "jav_home":
            if page <= 1:
                return self._list_page(self.host + "/", page)
            return self._list_page(self.host + "/page/%d" % page, page)

        # 无码首页
        if t == "jav_uncensored":
            if page <= 1:
                return self._list_page(self.host + "/uncensored", page)
            return self._list_page(self.host + "/uncensored/page/%d" % page, page)

        # 有码类别：选筛选 → 对应类别；否则 → 第一个默认类别
        if t == "jav_genre":
            if len(genre_sel) == 1:
                gid = list(genre_sel.keys())[0]
                return self._category_list(self.host + "/genre", gid, page)
            default_gid = self._get_default_genre(self.host + "/genre")
            if default_gid:
                return self._category_list(self.host + "/genre", default_gid, page)
            if page <= 1:
                return self._list_page(self.host + "/", page)
            return self._list_page(self.host + "/page/%d" % page, page)

        # 无码类别：选筛选 → 对应类别；否则 → 第一个默认类别
        if t == "jav_uncensored_genre":
            if len(genre_sel) == 1:
                gid = list(genre_sel.keys())[0]
                return self._category_list(self.host + "/uncensored/genre", gid, page)
            default_gid = self._get_default_genre(self.host + "/uncensored/genre")
            if default_gid:
                return self._category_list(self.host + "/uncensored/genre", default_gid, page)
            if page <= 1:
                return self._list_page(self.host + "/uncensored", page)
            return self._list_page(self.host + "/uncensored/page/%d" % page, page)

        # 有码女优：选女优 → 该女优影片；否则 → 第一个默认女优
        if t == "jav_actress":
            if len(star_sel) == 1:
                sid = list(star_sel.keys())[0]
                return self._star_list(self.host + "/star", sid, page)
            default_sid = self._get_default_star(self.host + "/actresses")
            if default_sid:
                return self._star_list(self.host + "/star", default_sid, page)
            if page <= 1:
                return self._list_page(self.host + "/", page)
            return self._list_page(self.host + "/page/%d" % page, page)

        # 无码女优：选女优 → 该女优影片；否则 → 第一个默认女优
        if t == "jav_uncensored_actress":
            if len(star_sel) == 1:
                sid = list(star_sel.keys())[0]
                return self._star_list(self.host + "/uncensored/star", sid, page)
            default_sid = self._get_default_star(self.host + "/uncensored/actresses")
            if default_sid:
                return self._star_list(self.host + "/uncensored/star", default_sid, page)
            if page <= 1:
                return self._list_page(self.host + "/uncensored", page)
            return self._list_page(self.host + "/uncensored/page/%d" % page, page)

        # 具体类别页
        if t.startswith("jav_genre_"):
            gid = t[len("jav_genre_"):]
            return self._category_list(self.host + "/genre", gid, page)

        if t.startswith("jav_uc_genre_"):
            gid = t[len("jav_uc_genre_"):]
            return self._category_list(self.host + "/uncensored/genre", gid, page)

        # 具体女优页
        if t.startswith("jav_star_"):
            sid = t[len("jav_star_"):]
            return self._star_list(self.host + "/star", sid, page)

        if t.startswith("jav_uc_star_"):
            sid = t[len("jav_uc_star_"):]
            return self._star_list(self.host + "/uncensored/star", sid, page)

        return {"list": [], "page": page, "pagecount": 1,
                "limit": self.page_size, "total": 0}

    def _category_list(self, base, gid, page):
        """类别列表页：/genre/xxx 或 /genre/xxx/2"""
        if page <= 1:
            url = "%s/%s" % (base.rstrip("/"), gid)
        else:
            url = "%s/%s/%d" % (base.rstrip("/"), gid, page)
        return self._list_page(url, page)

    def _star_list(self, base, sid, page):
        """女优列表页：/star/xxx 或 /star/xxx/2"""
        if page <= 1:
            url = "%s/%s" % (base.rstrip("/"), sid)
        else:
            url = "%s/%s/%d" % (base.rstrip("/"), sid, page)
        return self._list_page(url, page)

    # ========== 列表页解析 ==========
    def _list_page(self, url, page):
        seen = set()
        out = []
        try:
            text = self._get_html(url)
        except Exception:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.page_size, "total": 0}

        for m in re.finditer(
            r'<a[^>]+class="[^"]*movie-box[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            text, re.S
        ):
            try:
                href = _fix_url(m.group(1), self.host)
                block = m.group(2)

                img = re.search(
                    r'<img[^>]*(?:src|data-src|data-original)=["\']([^"\']+)',
                    block, re.I
                )
                pic = _fix_url(img.group(1), self.host) if img else ""

                title = ""
                tm = re.search(r'<img[^>]+title="([^"]+)"', block, re.I)
                if tm:
                    title = _clean_text(tm.group(1))
                if not title:
                    tm = re.search(r"<span>([^<]+)", block)
                    if tm:
                        title = _clean_text(tm.group(1))

                num = ""
                dates = re.findall(r"<date>([^<]+)</date>", block)
                if dates:
                    num = _clean_text(dates[0])

                vid = _extract_id(href)
                if not vid or vid in seen:
                    continue
                seen.add(vid)

                out.append({
                    "vod_id": vid,
                    "vod_name": title or num or vid,
                    "vod_pic": pic,
                    "vod_remarks": num or "",
                })
            except Exception:
                continue

        has_next = bool(re.search(r'<a[^>]+id="next"[^>]+href="[^"]+"', text))
        if not has_next:
            pag = re.search(
                r'<ul[^>]+class="[^"]*pagination[^"]*"[^>]*>(.*?)</ul>',
                text, re.S
            )
            if pag:
                nums = [
                    _safe_int(x)
                    for x in re.findall(r'href="[^"]*?/(\d+)"', pag.group(1))
                ]
                nums = [n for n in nums if n > 0]
                if nums and max(nums) > page:
                    has_next = True

        return {
            "list": out,
            "page": page,
            "pagecount": page + 1 if has_next else page,
            "limit": self.page_size,
            "total": len(out),
        }

    # ========== 详情 ==========
    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        if not vid:
            return {"list": []}

        # 兼容：如果框架把类别/女优 ID 传到 detailContent，直接返回空
        if vid.startswith(("jav_genre_", "jav_uc_genre_",
                           "jav_star_", "jav_uc_star_")):
            return {"list": []}

        url = _fix_url("/" + vid, self.host)
        try:
            text = self._get_html(url)
        except Exception:
            return {"list": []}

        title = ""
        tm = re.search(r"<title>([^<]+)</title>", text)
        if tm:
            title = _clean_text(tm.group(1)).replace(" - JavBus", "").strip()

        pic = ""
        pm = re.search(r'<a[^>]+class="bigImage"[^>]+href="([^"]+)"', text)
        if pm:
            pic = _fix_url(pm.group(1), self.host)
        if not pic:
            pm = re.search(r'<img[^>]+src="(/imgs/cover/[^"]+)"', text)
            if pm:
                pic = _fix_url(pm.group(1), self.host)
        if not pic:
            pm = re.search(r'<img[^>]+src="(/imgs/[^"]+\.jpg)"', text)
            if pm:
                pic = _fix_url(pm.group(1), self.host)
        pic = self._proxy_pic(pic)

        num = ""
        for pat in (
            r'識別碼:</span>\s*<span[^>]*>([^<]+)',
            r'識別碼[:：]\s*</span>\s*<span[^>]*>([^<]+)',
            r'<span[^>]*class="header"[^>]*>識別碼[:：]</span>\s*<span[^>]*>([^<]+)',
        ):
            nm = re.search(pat, text)
            if nm:
                num = _clean_text(nm.group(1))
                if num:
                    break

        date = ""
        for pat in (
            r'發行日期:</span>\s*([^<]+)',
            r'發行日期[:：]\s*</span>\s*([^<]+)',
            r'<span[^>]*class="header"[^>]*>發行日期[:：]</span>\s*([^<]+)',
        ):
            dm = re.search(pat, text)
            if dm:
                date = _clean_text(dm.group(1))
                if date:
                    break

        actors = re.findall(
            r'class="avatar-box"[^>]+href="[^"]+"[^>]*>\s*<div[^>]*>\s*<img[^>]+title="([^"]+)"',
            text
        )
        if not actors:
            actors = re.findall(
                r'<a[^>]+href="[^"]*star/[^"]+"[^>]*title="([^"]+)"',
                text
            )
        actors = [_clean_text(a) for a in actors if a]

        genres = re.findall(r'<a href="[^"]*genre/[^"]+">([^<]+)</a>', text)
        genres = [_clean_text(g) for g in genres if g]
        seen_g = set()
        genres = [g for g in genres if not (g in seen_g or seen_g.add(g))]

        info_lines = []
        if num:
            info_lines.append("番号: %s" % num)
        if date:
            info_lines.append("发行: %s" % date)
        if actors:
            info_lines.append("演员: %s" % "、".join(actors))
        if genres:
            info_lines.append("类别: %s" % "、".join(genres))

        magnets = []
        if self.enable_magnet:
            try:
                magnets = self._fetch_magnets(text, vid)
            except Exception:
                magnets = []

        froms, urls = [], []
        if magnets:
            eps = []
            for i, g in enumerate(magnets):
                label = self._magnet_label(g, i, num)
                magnet = g.get("magnet") or ""
                if not magnet:
                    continue
                eps.append("%s$%s" % (label, magnet))
            if eps:
                froms.append("磁力")
                urls.append("#".join(eps))

        item = {
            "vod_id": vid,
            "vod_name": (num + " " + title).strip(),
            "vod_pic": pic,
            "vod_year": (date or "")[:4],
            "vod_actor": "、".join(actors),
            "vod_content": "\n".join(info_lines),
        }
        if froms:
            item["vod_play_from"] = "$$$".join(froms)
            item["vod_play_url"] = "$$$".join(urls)
        return {"list": [item]}

    def _fetch_magnets(self, detail_html, vid):
        gid = ""
        for pat in (
            r"var\s+gid\s*=\s*(\d+)",
            r"gid\s*=\s*(\d+)",
            r'data-gid\s*=\s*"(\d+)"',
        ):
            gm = re.search(pat, detail_html)
            if gm:
                gid = gm.group(1)
                if gid:
                    break
        if not gid:
            return []

        img = ""
        im = re.search(r"var\s+img\s*=\s*'([^']+)'", detail_html)
        if im:
            img = im.group(1)

        uc = "1" if re.search(r"var\s+uc\s*=\s*1", detail_html) else "0"

        ajax_url = (
            "%s/ajax/uncledatoolsbyajax.php?gid=%s&lang=%s&img=%s&uc=%s&floor=%d"
            % (self.host, gid, self.lang, quote(img, safe=""), uc,
               int(time.time() * 1000) % 1000 + 1)
        )
        try:
            text = self._get_html(ajax_url, headers=AJAX_HEADERS)
        except Exception:
            return []
        if not text:
            return []

        out = []
        seen_hash = set()
        for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", text, re.S):
            block = m.group(1)
            am = re.search(r'href="(magnet:[^"]+)"', block)
            if not am:
                continue
            magnet = am.group(1).replace("&amp;", "&")

            hm = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet)
            if not hm:
                continue
            h = hm.group(1).lower()
            if h in seen_hash:
                continue
            seen_hash.add(h)

            name = ""
            nm = re.search(r"<a[^>]*>([^<]+)</a>", block)
            if nm:
                name = _clean_text(nm.group(1))

            size = ""
            sm = re.search(
                r"<td[^>]*>([^<]*?(?:GB|MB|TB|KB)[^<]*?)</td>",
                block, re.I
            )
            if sm:
                size = _clean_text(sm.group(1))

            out.append({
                "name": name,
                "size": size,
                "magnet": magnet,
            })

        def _size_key(g):
            s = g.get("size") or ""
            mm = re.search(r"([\d.]+)\s*(GB|MB|TB|KB)", s, re.I)
            if not mm:
                return 0
            try:
                n = float(mm.group(1))
            except Exception:
                return 0
            unit = mm.group(2).upper()
            mult = {"KB": 1.0 / 1024, "MB": 1.0, "GB": 1024.0, "TB": 1024.0 * 1024}.get(unit, 1.0)
            return n * mult

        out.sort(key=_size_key, reverse=True)
        return out

    @staticmethod
    def _magnet_label(g, i, num):
        raw = _to_text(g.get("name")) or num or ("资源%d" % (i + 1))
        safe = re.sub(r"[$#&\n\r\t]", " ", raw).strip()[:40]
        parts = [safe]
        if g.get("size"):
            parts.append(g["size"])
        return " ".join(parts) or ("资源%d" % (i + 1))

    def _proxy_pic(self, url):
        if not url:
            return ""
        p = (self.img_proxy or "").strip()
        if not p:
            return url
        try:
            return p + quote(url, safe="")
        except Exception:
            return url

    # ========== 搜索 ==========
    def searchContent(self, key, quick=False, pg="1"):
        page = _safe_int(pg, 1)
        keyword = _to_text(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.search_limit, "total": 0}

        seen = set()
        out = []
        urls = [
            "%s/search/%s&type=&parent=ce" % (self.host, quote(keyword)),
        ]
        if self.enable_uncensored:
            urls.append(
                "%s/uncensored/search/%s&type=0&parent=uc" % (self.host, quote(keyword))
            )

        for u in urls:
            try:
                text = self._get_html(u)
            except Exception:
                continue
            for m in re.finditer(
                r'<a[^>]+class="[^"]*movie-box[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                text, re.S
            ):
                try:
                    href = _fix_url(m.group(1), self.host)
                    block = m.group(2)
                    img = re.search(
                        r'<img[^>]*(?:src|data-src|data-original)=["\']([^"\']+)',
                        block, re.I
                    )
                    pic = _fix_url(img.group(1), self.host) if img else ""
                    title = ""
                    tm = re.search(r'<img[^>]+title="([^"]+)"', block, re.I)
                    if tm:
                        title = _clean_text(tm.group(1))
                    if not title:
                        tm = re.search(r"<span>([^<]+)", block)
                        if tm:
                            title = _clean_text(tm.group(1))
                    num = ""
                    dates = re.findall(r"<date>([^<]+)</date>", block)
                    if dates:
                        num = _clean_text(dates[0])
                    vid = _extract_id(href)
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)
                    out.append({
                        "vod_id": vid,
                        "vod_name": title or num or vid,
                        "vod_pic": pic,
                        "vod_remarks": num or "",
                    })
                except Exception:
                    continue

        return {
            "list": out,
            "page": page,
            "pagecount": page + 1 if len(out) >= self.search_limit else page,
            "limit": self.search_limit,
            "total": len(out),
        }

    # ========== 播放 ==========
    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")

        if vid.startswith("magnet:"):
            m = _normalize_magnet(vid)
            return {
                "parse": 0,
                "jx": 0,
                "playUrl": "",
                "url": m or vid,
                "header": {"User-Agent": self.ua, "Accept": "*/*"},
            }

        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": "",
            "header": {},
        }

    def localProxy(self, param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        if not isinstance(param, dict):
            param = {}
        return [404, "text/plain", b"Not Found", {}]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = _to_text(url).lower()
        if u.startswith("magnet:"):
            return True
        u = u.split("?")[0]
        return u.endswith((".mp4", ".m3u8", ".flv", ".mkv", ".ts", ".avi"))

    def action(self, action):
        return {}

    def destroy(self):
        return None

    def _headers(self, extra=None):
        h = dict(LIST_HEADERS)
        h["Referer"] = self.host + "/"
        if self.cookie:
            h["Cookie"] = self.cookie
        if extra:
            h.update(extra)
        return h

    def _get_html(self, url, headers=None):
        if not requests or self.s is None:
            raise RuntimeError("requests 不可用")
        r = self.s.get(url, headers=headers or self._headers(),
                       timeout=self.timeout, verify=False)
        r.encoding = "utf-8"
        return r.text or ""