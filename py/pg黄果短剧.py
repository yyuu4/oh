import re
import json
from urllib.parse import quote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object

BASE = "https://huangguo.video"
PAGE_SIZE = 20
VERSION = "1.3.0"
CATEGORIES = [
    {"type_id": "latest", "type_name": "最新发布"},
    {"type_id": "all", "type_name": "全部视频"},
    {"type_id": "1", "type_name": "MV/音乐剧"},
    {"type_id": "2", "type_name": "短片"},
    {"type_id": "3", "type_name": "连续剧"},
    {"type_id": "4", "type_name": "片段"},
    {"type_id": "photos", "type_name": "图集"},
    {"type_id": "roles", "type_name": "角色"},
    {"type_id": "ranking", "type_name": "排行榜"},
]

_RATING_OPTS = {"key": "rating", "name": "尺度分级", "init": "",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "安全", "v": "1"},
                    {"n": "裸露", "v": "2"},
                    {"n": "限制级", "v": "3"},
                ]}
_LATEST_SORT_OPTS = {"key": "sort", "name": "排序", "init": "newest",
                     "value": [
                         {"n": "最新发布", "v": "newest"},
                         {"n": "最多播放", "v": "views"},
                         {"n": "最多收藏", "v": "favorites"},
                     ]}
_VIDEO_SORT_OPTS = {"key": "sort", "name": "排序", "init": "newest",
                    "value": [
                        {"n": "最新发布", "v": "newest"},
                        {"n": "最多播放", "v": "views"},
                        {"n": "最多收藏", "v": "favorites"},
                    ]}
_PHOTO_SORT_OPTS = {"key": "sort", "name": "排序", "init": "newest",
                    "value": [
                        {"n": "最新发布", "v": "newest"},
                        {"n": "最多播放/浏览", "v": "views"},
                        {"n": "最多收藏", "v": "favorites"},
                    ]}
_ROLE_SORT_OPTS = {"key": "sort", "name": "排序", "init": "newest",
                   "value": [
                       {"n": "最新创建", "v": "newest"},
                       {"n": "最多作品", "v": "works"},
                       {"n": "最多播放", "v": "views"},
                   ]}
_RANKING_TIME_OPTS = {"key": "p", "name": "时间范围", "init": "24h",
                      "value": [
                          {"n": "6小时", "v": "6h"},
                          {"n": "24小时", "v": "24h"},
                          {"n": "7天", "v": "7d"},
                      ]}
_ROLE_TYPE_OPTS = {"key": "type", "name": "类型", "init": "",
                   "value": [
                       {"n": "全部", "v": ""},
                       {"n": "真人", "v": "1"},
                       {"n": "二次元", "v": "2"},
                   ]}
_ROLE_GENDER_OPTS = {"key": "gender", "name": "性别", "init": "",
                     "value": [
                         {"n": "全部", "v": ""},
                         {"n": "男", "v": "1"},
                         {"n": "女", "v": "2"},
                     ]}
_TAG_OPTS = {"key": "tags", "name": "情节标签（可多选，需同时满足）", "init": "", "multi": True,
             "value": [
                 {"n": "全部", "v": ""},
                 {"n": "都市", "v": "1"},
                 {"n": "人妻", "v": "2"},
                 {"n": "同人", "v": "4"},
                 {"n": "校园", "v": "5"},
                 {"n": "职场", "v": "6"},
                 {"n": "古风", "v": "7"},
                 {"n": "乱伦", "v": "8"},
                 {"n": "NTR", "v": "9"},
                 {"n": "玄幻", "v": "40"},
                 {"n": "欧美", "v": "57"},
                 {"n": "露出", "v": "42"},
                 {"n": "二次元", "v": "59"},
                 {"n": "女同", "v": "55"},
                 {"n": "男同", "v": "56"},
                 {"n": "穿越", "v": "39"},
                 {"n": "衍生", "v": "3"},
             ]}
_ROLE_TAG_OPTS = {"key": "tags", "name": "人设标签（可多选，需同时满足）", "init": "", "multi": True,
                  "value": [
                      {"n": "全部", "v": ""},
                      {"n": "知性", "v": "53"},
                      {"n": "御姐", "v": "43"},
                      {"n": "人妻", "v": "2"},
                      {"n": "冷艳", "v": "51"},
                      {"n": "清纯", "v": "49"},
                      {"n": "甜美", "v": "50"},
                      {"n": "活力", "v": "44"},
                      {"n": "傲娇", "v": "52"},
                      {"n": "大小姐", "v": "54"},
                      {"n": "学生", "v": "46"},
                      {"n": "年轻", "v": "48"},
                      {"n": "OL", "v": "47"},
                      {"n": "熟女", "v": "45"},
                      {"n": "网红", "v": "41"},
                  ]}
_FILTER_KEYS = ["sort", "rating", "tags", "type", "gender", "p"]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

CARD_RE = re.compile(r'<article class="(?:video-card|search-content-card|photo-card)[\s\S]*?</article>')
ROLE_CARD_RE = re.compile(r'<a[^>]*href="(/role/[a-z0-9-]+)"[^>]*class="[^"]*role-card[^"]*"[^>]*>')
TITLE_RE = re.compile(r'<p class="[^"]*font-display[^"]*"[^>]*>([^<]*)</p>')
PIC_RE = re.compile(r'<img[^>]*src="([^"]*)"')
REMARK_RE = re.compile(r'bg-black/55[^>]*>([^<]*)<')
HREF_RE = re.compile(r'<a[^>]+href="([^"]*)"')
H1_RE = re.compile(r'<h1[^>]*>([^<]*)</h1>')
DESC_RE = re.compile(r'<meta name="description" content="([^"]*)"')
OGIMG_RE = re.compile(r'<meta property="og:image" content="([^"]*)"')
POSTER_RE = re.compile(r'data-poster="([^"]*)"')
HLS_RE = re.compile(r'data-hls="([^"]*)"')
TOTAL_RE = re.compile(r'全(\d+)\s*集')
PAGER_RE = re.compile(r'href="[^"]*page=(\d+)"')
EP_CHIP_RE = re.compile(r'<a[^>]*href="/video/([a-z0-9-]+)"[^>]*class="[^"]*series-ep-chip[^"]*"[^>]*title="第(\d+)集[^"]*"')


def _okhttp_get(url, referer=None, retries=2):
    is_m3u8 = ".m3u8" in url.lower()
    if is_m3u8:
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": referer or BASE + "/",
        }
    else:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        if referer:
            headers["Referer"] = referer
    
    last_err = None
    for attempt in range(retries + 1):
        try:
            try:
                from com.github.catvod.net import OkHttp
                from java.util import HashMap
                from java.util.concurrent import TimeUnit

                hm = HashMap()
                for k, v in headers.items():
                    hm.put(k, v)
                call = OkHttp.newCall(url, hm)
                try:
                    call.timeout().timeout(20, TimeUnit.SECONDS)
                except Exception:
                    pass
                resp = call.execute()
                try:
                    body = resp.body()
                    return str(body.string()) if body is not None else ""
                finally:
                    try:
                        resp.close()
                    except Exception:
                        pass
            except ImportError:
                import urllib.request

                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    import gzip
                    data = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        data = gzip.decompress(data)
                    return data.decode("utf-8", "ignore")
        except Exception as e:
            last_err = e
            if attempt < retries:
                import time
                time.sleep(0.5 * (attempt + 1))
    raise last_err


def _http_get(url, referer=None):
    return _okhttp_get(url, referer=referer)


_variant_cache = {}

def _pick_variant(master_url):
    if master_url in _variant_cache:
        return _variant_cache[master_url]
    try:
        txt = _okhttp_get(master_url, referer=BASE + "/")
    except Exception:
        _variant_cache[master_url] = master_url
        return master_url
    if "#EXT-X-STREAM-INF" not in txt:
        _variant_cache[master_url] = master_url
        return master_url
    base_dir = master_url.rsplit("/", 1)[0] + "/"
    lines = txt.splitlines()
    variants = []
    for i, line in enumerate(lines):
        if "#EXT-X-STREAM-INF" in line:
            uri = ""
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    uri = lines[j].strip()
                    break
            if not uri:
                continue
            rm = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            res = int(rm.group(2)) if rm else 0
            bw = re.search(r"BANDWIDTH=(\d+)", line)
            bwv = int(bw.group(1)) if bw else 0
            variants.append((res, bwv, uri))
    if not variants:
        _variant_cache[master_url] = master_url
        return master_url
    variants.sort(key=lambda x: (x[0], x[1]), reverse=True)
    uri = variants[0][2]
    if uri.startswith("http://") or uri.startswith("https://"):
        result = uri
    elif uri.startswith("/"):
        result = BASE + uri
    else:
        result = base_dir + uri
    _variant_cache[master_url] = result
    return result


class Spider(BaseSpider):
    _hls_cache = {}
    _detail_cache = {}

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        else:
            self.options = {}
        self._hls_cache = self._hls_cache or {}
        self._detail_cache = self._detail_cache or {}

    def getName(self):
        return "黄果剧场"

    def homeContent(self, filter):
        result = {"class": CATEGORIES}
        if filter:
            result["filters"] = {
                "latest": [_LATEST_SORT_OPTS],
                "all": [_VIDEO_SORT_OPTS, _RATING_OPTS, _TAG_OPTS],
                "1": [_VIDEO_SORT_OPTS, _RATING_OPTS, _TAG_OPTS],
                "2": [_VIDEO_SORT_OPTS, _RATING_OPTS, _TAG_OPTS],
                "3": [_VIDEO_SORT_OPTS, _RATING_OPTS, _TAG_OPTS],
                "4": [_VIDEO_SORT_OPTS, _RATING_OPTS, _TAG_OPTS],
                "photos": [_PHOTO_SORT_OPTS, _RATING_OPTS, _TAG_OPTS],
                "roles": [_ROLE_SORT_OPTS, _ROLE_TYPE_OPTS, _ROLE_GENDER_OPTS, _ROLE_TAG_OPTS],
                "ranking": [_RANKING_TIME_OPTS],
            }
        return result

    def homeVideoContent(self):
        try:
            return self._list("latest", 1, "")
        except Exception as e:
            return {
                "list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE,
                "total": 0, "msg": "首页推荐加载失败：" + type(e).__name__,
            }

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        try:
            ext = {}
            if isinstance(extend, dict):
                ext = extend
            elif extend:
                try:
                    ext = json.loads(extend)
                except Exception:
                    ext = {}
            return self._list(str(tid), pg, "", ext)
        except Exception as e:
            return {
                "list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE,
                "total": 0, "msg": "分类加载失败：" + type(e).__name__,
            }

    def searchContent(self, key, quick, pg="1"):
        del quick
        try:
            return self._search(str(key or ""), pg)
        except Exception as e:
            return {
                "list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE,
                "total": 0, "msg": "搜索失败：" + type(e).__name__,
            }

    def _build_url(self, cat, pg, keyword, ext=None):
        if cat == "latest":
            url = "%s/videos" % BASE
        elif cat == "photos":
            url = "%s/photos" % BASE
        elif cat == "roles":
            url = "%s/roles" % BASE
        elif cat == "ranking":
            url = "%s/ranking" % BASE
        else:
            url = "%s/videos?category=%s" % (BASE, quote(cat))
        if keyword:
            sep = "&" if "?" in url else "?"
            url += sep + "q=" + quote(keyword)
        if ext:
            for k in _FILTER_KEYS:
                v = ext.get(k)
                if v:
                    sep = "&" if "?" in url else "?"
                    url += sep + "%s=%s" % (k, quote(str(v)))
            if cat == "ranking":
                p_val = ext.get("p")
                if p_val:
                    sep = "&" if "?" in url else "?"
                    url += sep + "p=%s" % quote(str(p_val))
        page = max(1, int(pg) if str(pg).isdigit() else 1)
        if page > 1:
            sep = "&" if "?" in url else "?"
            url += sep + "page=%d" % page
        return url

    def _search_url(self, keyword, pg):
        url = "%s/search?q=%s" % (BASE, quote(keyword))
        page = max(1, int(pg) if str(pg).isdigit() else 1)
        if page > 1:
            url += "&page=%d" % page
        return url

    def _list(self, cat, pg, keyword, ext=None):
        url = self._build_url(cat, pg, keyword, ext)
        html_text = _http_get(url, referer=BASE + "/")
        if cat == "roles":
            cards = []
            for m in ROLE_CARD_RE.finditer(html_text):
                code = m.group(1).rstrip("/").split("/")[-1]
                start = m.start()
                end = html_text.find("</a>", start)
                if end < 0:
                    continue
                inner = html_text[start:end]
                title_m = re.search(r'<p class="mt-2\.5 font-display[^"]*"[^>]*>([^<]*)</p>', inner)
                title = title_m.group(1).strip() if title_m else ""
                pic_m = re.search(r'background-image:url\(([^)]+)\)', inner)
                pic = ""
                if pic_m:
                    pic_url = pic_m.group(1).split(",")[0].strip()
                    pic = self._absolute(pic_url)
                remark_m = re.search(r'bg-black/55[^>]*>([^<]*)<', inner)
                remark = remark_m.group(1).strip() if remark_m else ""
                cards.append({
                    "vod_id": "role/%s" % code,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remark,
                    "vod_type": "角色",
                    "style": {"type": "rect", "ratio": 1.0},
                })
        else:
            cards = [self._parse_card(b) for b in CARD_RE.findall(html_text)]
            cards = [c for c in cards if c]
        pagecount = self._pagecount(html_text)
        return {
            "list": cards,
            "page": max(1, int(pg) if str(pg).isdigit() else 1),
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": len(cards) * pagecount if pagecount > 1 else len(cards),
        }

    def _search(self, keyword, pg):
        url = self._search_url(keyword, pg)
        html_text = _http_get(url, referer=BASE + "/")
        cards = [self._parse_card(b) for b in CARD_RE.findall(html_text)]
        cards = [c for c in cards if c]
        return {
            "list": cards,
            "page": max(1, int(pg) if str(pg).isdigit() else 1),
            "pagecount": self._pagecount(html_text),
            "limit": PAGE_SIZE,
            "total": len(cards),
        }

    def _parse_card(self, block):
        href_m = HREF_RE.search(block)
        if not href_m:
            return None
        href = href_m.group(1)
        if href.startswith("/series/"):
            kind = "series"
        elif href.startswith("/photo/"):
            kind = "photo"
        elif href.startswith("/role/"):
            kind = "role"
        else:
            kind = "video"
        code = href.rstrip("/").split("/")[-1]
        title_m = TITLE_RE.search(block)
        title = title_m.group(1).strip() if title_m else ""
        pic_m = PIC_RE.search(block)
        pic = self._absolute(pic_m.group(1)) if pic_m else ""
        remark_m = REMARK_RE.search(block)
        remark = remark_m.group(1).strip() if remark_m else ""
        type_map = {"series": "连续剧", "photo": "图集", "role": "角色", "video": "视频"}
        return {
            "vod_id": "%s/%s" % (kind, code),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark,
            "vod_type": type_map.get(kind, "视频"),
            "style": {"type": "rect", "ratio": 0.75},
        }

    def _pagecount(self, html_text):
        return 9999

    def detailContent(self, ids):
        ident = ids[0] if ids else ""
        if ident in self._detail_cache:
            return self._detail_cache[ident]
        try:
            item = self._parse_detail(ident)
            if not item.get("vod_play_url"):
                result = {"list": [item], "msg": "未能解析到播放地址"}
            else:
                result = {"list": [item]}
            self._detail_cache[ident] = result
            return result
        except Exception as e:
            return {"list": [], "msg": "详情加载失败：" + type(e).__name__}

    def _parse_detail(self, ident):
        parts = str(ident).split("/")
        kind = parts[0]
        code = parts[1] if len(parts) >= 2 else ident
        item = {
            "vod_id": ident,
            "vod_name": "",
            "vod_pic": "",
            "vod_play_from": "黄果剧场",
            "vod_play_url": "",
        }
        if kind == "series":
            text = _http_get("%s/series/%s" % (BASE, code), referer=BASE + "/")
            item["vod_name"] = self._first(H1_RE, text) or ""
            item["vod_pic"] = self._absolute(
                self._first(OGIMG_RE, text) or self._first(POSTER_RE, text)
            )
            item["vod_content"] = self._first(DESC_RE, text) or ""
            total_m = TOTAL_RE.search(text)
            eps = []
            for m in EP_CHIP_RE.finditer(text):
                eps.append((int(m.group(2)), m.group(1)))
            eps.sort()
            urls = []
            for ep_num, ep_code in eps:
                master = self._resolve_hls(ep_code)
                if master:
                    urls.append("第%d集$%s" % (ep_num, master))
            if not urls:
                master = self._resolve_hls(code)
                if master:
                    urls.append("正片$%s" % master)
            if total_m:
                item["vod_remark"] = "全%s集" % total_m.group(1)
            item["vod_play_url"] = "#".join(urls)
        else:
            text = _http_get("%s/video/%s" % (BASE, code), referer=BASE + "/")
            item["vod_name"] = self._first(H1_RE, text) or "正片"
            item["vod_pic"] = self._absolute(
                self._first(POSTER_RE, text) or self._first(OGIMG_RE, text)
            )
            item["vod_content"] = self._first(DESC_RE, text) or ""
            master = self._resolve_hls(code)
            item["vod_play_url"] = "正片$%s" % (master or "")
        return item

    def _resolve_hls(self, code):
        if code in self._hls_cache:
            return self._hls_cache[code]
        text = _http_get("%s/video/%s" % (BASE, code), referer=BASE + "/")
        m = HLS_RE.search(text)
        result = self._absolute(m.group(1)) if m else ""
        if result:
            self._hls_cache[code] = result
        return result

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        try:
            cur = str(id or "").split("#")[0]
            sep = cur.rfind("$")
            hls = cur[sep + 1:] if sep >= 0 else cur
            url = self._absolute(hls)
            if not url:
                return {"parse": 0, "jx": 0, "url": "", "msg": "空播放地址"}
            playable = _pick_variant(url)
            return {
                "parse": 0,
                "jx": 0,
                "url": playable,
                "header": {"Referer": BASE + "/"},
            }
        except Exception as e:
            return {"parse": 0, "jx": 0, "url": "", "msg": "播放失败：" + type(e).__name__}

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return str(url or "").split("?")[0].lower().endswith(
            (".m3u8", ".mpd", ".mp4", ".mkv", ".flv")
        )

    def destroy(self):
        self.options = {}
        self._hls_cache = {}
        self._detail_cache = {}

    @staticmethod
    def _absolute(url):
        v = str(url or "").strip()
        if not v:
            return ""
        if v.startswith("http://") or v.startswith("https://"):
            return v
        if v.startswith("/"):
            return BASE + v
        return v

    @staticmethod
    def _first(regex, text):
        m = regex.search(text)
        return m.group(1) if m else ""
