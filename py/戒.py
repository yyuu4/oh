# -*- coding: utf-8 -*-
"""
TVBox Spider - jdforrepam.com (JavDB 系镜像)
分类：有码/无码/欧美/FC2（网页「类别」4 类）
filter_by：{类型}:t:{main}:{extra}:{year}:{duration}:{month}（网页同款）
"""
import json
import time
import hashlib
from urllib.parse import urljoin, quote, urlencode

try:
    import requests
except ImportError:
    requests = None

if requests is None:
    import urllib.request


API_BASE = "https://jdforrepam.com/api"
IMG_BASE = "https://c0.jdbstatic.com"
SALT = "lpw6vgqzsp"
KEY = ("71cf27bb3c0bcdf207b64abecddc970098c7421ee7203b9cdae544784"
       "78a199e7d5a6e1a57691123c1a931c057842fb73ba3b3c83bcd69c17cc"
       "f174081e3d8aa")
UA = ("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36")
TIMEOUT = 15
PAGE_SIZE = 48
MAGNET_LIMIT = 40

CLASSES = [
    {"type_id": "censored", "type_name": "有码"},
    {"type_id": "uncensored", "type_name": "无码"},
    {"type_id": "western", "type_name": "欧美"},
    {"type_id": "fc2", "type_name": "FC2"},
]

TYPE_NUM = {"censored": "0", "uncensored": "1", "western": "2", "fc2": "3",
            "anime": "4"}

SORT_FILTER = [
    {"n": "发布日期", "v": "released"},
    {"n": "磁链更新", "v": "magnet-updated"},
]

CORE_DIMS = ("main", "year", "month", "duration")

BASIC_MAIN = [{
    "key": "main", "name": "基本", "init": "",
    "value": [
        {"n": "全部", "v": ""},
        {"n": "可播放", "v": "p"},
        {"n": "可下載", "v": "m"},
        {"n": "含字幕", "v": "c"},
    ],
}]


class Spider:
    def __init__(self):
        self.s = None
        self.session = None
        self.sess = None
        self.api_base = API_BASE
        self.img_base = IMG_BASE
        self.img_proxy = ""
        self.ua = UA
        self._filters_cache = {}

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
        if extend.get("api"):
            self.api_base = str(extend["api"]).rstrip("/")
        if extend.get("img") or extend.get("imgProxy"):
            self.img_proxy = str(extend.get("img") or extend.get("imgProxy") or "").strip()
        if requests is not None:
            self.s = requests.Session()
            self.s.headers.update({
                "User-Agent": self.ua,
                "Accept": "application/json, text/plain, */*",
            })
            self.session = self.s
            self.sess = self.s

    def homeContent(self, filter=None):
        classes = [dict(c) for c in CLASSES]
        filters = {}
        for c in classes:
            tid = c["type_id"]
            type_n = TYPE_NUM.get(tid, "0")
            items = self._get_filters(type_n)
            if not items:
                items = [dict(x) for x in BASIC_MAIN]
            filters[tid] = ([{"key": "sort", "name": "排序", "init": "released",
                              "value": [dict(x) for x in SORT_FILTER]}]
                            + items)
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            page = int(pg)
        except Exception:
            page = 1

        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}
        if not isinstance(filter, dict):
            filter = {}

        def pick(k):
            v = filter.get(k)
            if v in (None, ""):
                v = extend.get(k)
            return str(v).strip() if v not in (None, "") else ""

        t = str(tid or "")
        sort = pick("sort") or "released"
        n = TYPE_NUM.get(t, t[7:] if (t.startswith("jav_tag") and t[7:].isdigit()) else "0")

        main_val = pick("main")
        year_val = pick("year")
        month_val = pick("month")
        duration_val = pick("duration")
        extra = ""
        for g in (self._get_filters(n) or []):
            gk = str(g.get("key") or "")
            if not gk or gk in CORE_DIMS:
                continue
            v = pick(gk)
            if v:
                extra = v
                break

        fb = "%s:t:%s:%s:%s:%s:%s" % (n, main_val, extra, year_val,
                                      duration_val, month_val)

        params = {
            "filter_by": fb, "page": page, "limit": PAGE_SIZE,
            "sort_by": "update" if sort == "magnet-updated" else "release",
            "order_by": "desc",
        }
        data = self._api_data("/v1/movies/tags", params)

        movies = data.get("movies") if isinstance(data, dict) else []
        if not isinstance(movies, list):
            movies = []

        seen, out = set(), []
        for m in movies:
            it = self._card(m)
            if it and it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                out.append(it)

        return {
            "list": out,
            "page": page,
            "pagecount": page + 1 if out else page,
            "limit": PAGE_SIZE,
            "total": len(out),
        }

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ""
        else:
            vid = str(ids or "")
        if not vid:
            return {"list": []}

        data = self._api_data("/v4/movies/" + quote(vid))
        movie = (data.get("movie")
                 if isinstance(data, dict) and isinstance(data.get("movie"), dict)
                 else data)
        if not isinstance(movie, dict):
            movie = {}

        magnets = []
        try:
            mg = self._api_data("/v1/movies/" + quote(vid) + "/magnets",
                                {"page": 1, "limit": MAGNET_LIMIT})
            if isinstance(mg, dict) and isinstance(mg.get("magnets"), list):
                magnets = mg["magnets"]
        except Exception:
            magnets = []

        num = str(movie.get("number") or "").strip()
        title = str(movie.get("title") or "").strip()
        actors = "、".join(a.get("name") or "" for a in (movie.get("actors") or [])
                           if isinstance(a, dict) and a.get("name"))
        tags = "、".join(t.get("name") or "" for t in (movie.get("tags") or [])
                         if isinstance(t, dict) and t.get("name"))

        info = []
        if num:
            info.append("番号: " + num)
        if movie.get("release_date"):
            info.append("发行: " + str(movie["release_date"]))
        if movie.get("duration"):
            info.append("时长: %s分钟" % movie["duration"])
        if movie.get("score"):
            info.append("评分: " + str(movie["score"]))
        if actors:
            info.append("演员: " + actors)
        if tags:
            info.append("标签: " + tags)

        froms, urls = [], []

        if movie.get("preview_video_url") or movie.get("has_preview_video"):
            froms.append("预告片")
            urls.append("预告片$preview:%s" % vid)

        eps, used = [], set()
        for i, g in enumerate(magnets):
            if not isinstance(g, dict):
                continue
            h = str(g.get("hash") or "").strip()
            if not h:
                continue
            eps.append("%s$magnet:?xt=urn:btih:%s"
                       % (self._magnet_label(g, i, num, used), h))
        if eps:
            froms.append("磁力")
            urls.append("#".join(eps))

        item = {
            "vod_id": vid,
            "vod_name": (num + " " + title).strip(),
            "vod_pic": self._jav_pic(vid, movie.get("cover_url") or movie.get("thumb_url") or ""),
            "vod_year": str(movie.get("release_date") or "")[:4],
            "vod_actor": actors,
            "vod_content": "\n".join(info),
        }
        if froms:
            item["vod_play_from"] = "$$$".join(froms)
            item["vod_play_url"] = "$$$".join(urls)
        return {"list": [item]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        data = self._api_data("/v2/search", {
            "q": key, "page": page, "type": "movie", "limit": PAGE_SIZE,
        })
        movies = data.get("movies") if isinstance(data, dict) else []
        if not isinstance(movies, list):
            movies = []
        seen, out = set(), []
        for m in movies:
            it = self._card(m)
            if it and it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                out.append(it)
        return {
            "list": out,
            "page": page,
            "pagecount": page + 1 if out else page,
            "limit": PAGE_SIZE,
            "total": len(out),
        }

    def playerContent(self, flag, ids, vipFlags=None):
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ""
        else:
            vid = str(ids or "")
        if vid.startswith("magnet:"):
            return {"parse": 0, "jx": 0, "playUrl": "", "url": vid,
                    "header": {"User-Agent": self.ua, "Accept": "*/*"}}
        if vid.startswith("preview:"):
            mid = vid[8:]
            data = self._api_data("/v4/movies/" + quote(mid))
            movie = (data.get("movie")
                     if isinstance(data, dict) and isinstance(data.get("movie"), dict)
                     else data)
            pv = ""
            if isinstance(movie, dict):
                pv = str(movie.get("preview_video_url") or "").strip()
            if pv.startswith("//"):
                pv = "https:" + pv
            return {"parse": 0, "jx": 0, "playUrl": "", "url": pv,
                    "header": {"User-Agent": self.ua, "Accept": "*/*"}}
        return {"parse": 1, "jx": 0, "playUrl": "", "url": "",
                "header": {"User-Agent": self.ua, "Accept": "*/*"}}

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
        u = str(url or "").lower().split("?")[0]
        return u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts"))

    def action(self, action):
        return {}

    def destroy(self):
        try:
            if self.s is not None:
                self.s.close()
        except Exception:
            pass
        self.s = self.session = self.sess = None
        return None

    def _jav_pic(self, mid, raw=""):
        m = str(mid or "").strip()
        url = ("%s/covers/%s/%s.jpg" % (self.img_base, m[:2].lower(), m)) if m else (raw or "")
        p = (self.img_proxy or "").strip()
        if p and url:
            try:
                return p + quote(url, safe="")
            except Exception:
                return url
        return url

    def _get_filters(self, type_n):
        if type_n in self._filters_cache:
            return [dict(f) for f in self._filters_cache[type_n]]

        data = self._api_data("/v2/tags", {"type": type_n})
        rows = data.get("tags") if isinstance(data, dict) else None
        groups = []
        if isinstance(rows, list) and rows:
            core_rows = [g for cid in CORE_DIMS for g in rows
                         if isinstance(g, dict) and g.get("category_id") == cid]
            rest_rows = [g for g in rows
                         if isinstance(g, dict) and g.get("category_id") not in CORE_DIMS]
            for g in core_rows + rest_rows:
                gkey = str(g.get("category_id") or "").strip()
                if not gkey:
                    continue
                gname = str(g.get("category") or gkey).strip()
                first_n = "全部" if gkey == "main" else ("全部" + gname)
                vals = [{"n": first_n, "v": ""}]
                for tg in (g.get("tags") or []):
                    if not isinstance(tg, dict):
                        continue
                    nm = str(tg.get("name") or "").strip()
                    tg_id = str(tg.get("id") or "").strip()
                    if not nm or not tg_id:
                        continue
                    vals.append({"n": nm, "v": tg_id})
                if len(vals) < 2:
                    continue
                groups.append({"key": gkey, "name": gname,
                               "init": "", "value": vals})

        self._filters_cache[type_n] = [dict(f) for f in groups]
        return groups

    def _sign(self):
        ts = str(int(time.time()))
        return "%s.%s.%s" % (ts, SALT,
                             hashlib.md5((ts + KEY).encode("utf-8")).hexdigest())

    def _api_data(self, path, params=None):
        url = (path if path.startswith("http")
               else urljoin(self.api_base + "/", path.lstrip("/")))
        headers = {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "jdsignature": self._sign(),
        }
        try:
            if self.s is not None:
                r = self.s.get(url, params=params or {}, headers=headers,
                               timeout=TIMEOUT)
                js = r.json()
            else:
                if params:
                    url = url + ("&" if "?" in url else "?") + urlencode(params)
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    js = json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception:
            return {}
        if not isinstance(js, dict):
            return {}
        d = js.get("data")
        return d if isinstance(d, dict) else js

    def _card(self, m):
        if not isinstance(m, dict):
            return None
        mid = m.get("id")
        if not mid:
            return None
        num = str(m.get("number") or "").strip()
        title = str(m.get("title") or "").strip()
        marks = []
        if m.get("can_play"):
            marks.append("可播")
        if m.get("has_cnsub"):
            marks.append("中字")
        if (m.get("magnets_count") or 0) > 0:
            marks.append("磁链%d" % m["magnets_count"])
        return {
            "vod_id": str(mid),
            "vod_name": (num + " " + title).strip(),
            "vod_pic": self._jav_pic(mid, m.get("cover_url") or m.get("thumb_url") or ""),
            "vod_remarks": " ".join(marks) or str(m.get("release_date") or ""),
        }

    @staticmethod
    def _magnet_label(g, i, num, used):
        raw = str(g.get("name") or "").strip() or num or ("资源%d" % (i + 1))
        safe = "".join(" " if c in "$#&?=:|\\/\n\r\t" else c for c in raw)
        safe = " ".join(safe.split())[:40] or ("资源%d" % (i + 1))
        size = g.get("size")
        try:
            size = float(size or 0)
        except Exception:
            size = 0
        if size >= 1024:
            safe += " %.1fG" % (size / 1024.0)
        elif size > 0:
            safe += " %dM" % int(size)
        if safe not in used:
            used.add(safe)
            return safe
        h = str(g.get("hash") or "")[:8]
        cand = "%s [%s]" % (safe, h) if h else safe
        if cand not in used:
            used.add(cand)
            return cand
        n = 2
        while True:
            cand2 = "%s (%d)" % (cand, n)
            if cand2 not in used:
                used.add(cand2)
                return cand2
            n += 1