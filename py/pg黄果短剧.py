"""黄果剧场 (huangguo.video) Python 点播爬虫（fongmi / OK影视 适配，Chaquopy）

站点结构：
- 列表/分类：/videos?category=all|1|2|3|4&page=N，卡片 <article class="video-card">
- 最新发布：/videos（不带 category，即网页首页「最新发布」区块内容）
- 搜索：/search?q=xx，结果卡片 <article class="search-content-card">
- 视频详情：/video/xxx，播放地址在 data-hls（.../master.m3u8），海报在 data-poster
- 连续剧详情：/series/xxx，剧集列表为 a.series-ep-chip（title="第N集 · 时长"）
- 播放链路：data-hls 是 master.m3u8（目前仅 480p 一个 variant，绝对地址在 cdn.huangguo.video，
  整条流 AES-128 加密）。播放器直接吃 master 常因不跟随 variant 而黑屏，故在 playerContent 里
  解析 master、挑一个具体 variant 播放列表返回。CDN 段与 /api/hls_key 均无需 Referer 即可 200。

网络层：优先使用 fongmi 提供的 OkHttp Java 桥（com.github.catvod.net.OkHttp），
这是 Chaquopy 环境下唯一稳定可用的出站 HTTP 方式；仅在本地无 OkHttp 时回退 urllib。
请求超时 20 秒，失败自动重试 2 次（间隔递增）。m3u8 请求使用简化请求头避免 CDN 防护。
缓存机制：HLS 地址、variant 解析结果、详情页均缓存，重复请求 0 延迟。
任何一步失败都会把错误放进 msg 返回，而不是静默空白/永久转圈。

配置示例（放进 TVBox 主配置 "sites" 数组，把本文件放到 ./vod/ 目录）：
[
  {
    "key": "huangguo",
    "name": "黄果剧场",
    "type": 3,
    "api": "./vod/huangguo_spider.py",
    "lang": "zh-CN",
    "searchable": 1,
    "quickSearch": 1,
    "filterable": 0,
    "changeable": 0,
    "style": { "type": "rect", "ratio": 0.75 }
  }
]

分类由 homeContent() 动态返回（最新发布/全部视频/MV/音乐剧/短片/连续剧/片段），无需写死 classes。
该站含限制级内容，卡片会把标记透传到 vod_remarks，可自行过滤。
"""

import re
import json
from urllib.parse import quote

try:
    from base.spider import Spider as BaseSpider
except Exception:  # 独立运行（本机校验）时兜底
    BaseSpider = object

BASE = "https://huangguo.video"
PAGE_SIZE = 20
# 第一个栏目 = 最新发布（映射到 /videos 不带 category）
CATEGORIES = [
    {"type_id": "latest", "type_name": "最新发布"},
    {"type_id": "all", "type_name": "全部视频"},
    {"type_id": "1", "type_name": "MV/音乐剧"},
    {"type_id": "2", "type_name": "短片"},
    {"type_id": "3", "type_name": "连续剧"},
    {"type_id": "4", "type_name": "片段"},
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

CARD_RE = re.compile(r'<article class="(?:video-card|search-content-card)[\s\S]*?</article>')
TITLE_RE = re.compile(r'<p class="[^"]*font-display[^"]*"[^>]*>([^<]*)</p>')
PIC_RE = re.compile(r'<img[^>]*src="([^"]*)"')
REMARK_RE = re.compile(r'bg-black/55[^>]*>([^<]*)<')
HREF_RE = re.compile(r'<a[^>]+href="([^"]*)"')
H1_RE = re.compile(r'<h1[^>]*>([^<]*)</h1>')
DESC_RE = re.compile(r'<meta name="description" content="([^"]*)"')
OGIMG_RE = re.compile(r'<meta property="og:image" content="([^"]*)"')
POSTER_RE = re.compile(r'data-poster="([^"]*)"')
HLS_RE = re.compile(r'data-hls="([^"]*)"')
TOTAL_RE = re.compile(r'(\d+)\s*集')
PAGER_RE = re.compile(r'href="[^"]*page=(\d+)"')
EP_CHIP_RE = re.compile(r'<a[^>]*href="/video/([a-z0-9]+)"[^>]*class="[^"]*series-ep-chip[^"]*"[^>]*title="第(\d+)集[^"]*"')


def _okhttp_get(url, referer=None, retries=2):
    """优先 fongmi OkHttp 桥；否则回退 urllib（仅本地测试）。返回 HTML 文本。
    
    Args:
        url: 请求地址
        referer: 来源页
        retries: 失败重试次数
    """
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
    """模块内统一同步入口（list / detail 调用）。实际走 _okhttp_get。

    这样即便运行环境没有注入全局 _http_get，也能正常工作，不依赖外部全局符号。
    """
    return _okhttp_get(url, referer=referer)


_variant_cache = {}

def _pick_variant(master_url):
    """解析 master.m3u8，挑一个具体 variant 播放列表（绝对地址）返回；失败回退 master。"""
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
        self._hls_cache = {}
        self._detail_cache = {}

    def getName(self):
        return "黄果剧场"

    def homeContent(self, filter):
        result = {"class": CATEGORIES}
        if filter:
            result["filters"] = {}
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
        del filter, extend
        try:
            return self._list(str(tid), pg, "")
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

    def _build_url(self, cat, pg, keyword):
        if cat == "latest":
            url = "%s/videos" % BASE
        else:
            url = "%s/videos?category=%s" % (BASE, quote(cat))
        if keyword:
            sep = "&" if "?" in url else "?"
            url += sep + "q=" + quote(keyword)
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

    def _list(self, cat, pg, keyword):
        url = self._build_url(cat, pg, keyword)
        html_text = _http_get(url, referer=BASE + "/")
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
        kind = "series" if href.startswith("/series/") else "video"
        code = href.rstrip("/").split("/")[-1]
        title_m = TITLE_RE.search(block)
        title = title_m.group(1).strip() if title_m else ""
        pic_m = PIC_RE.search(block)
        pic = self._absolute(pic_m.group(1)) if pic_m else ""
        remark_m = REMARK_RE.search(block)
        remark = remark_m.group(1).strip() if remark_m else ""
        return {
            "vod_id": "%s/%s" % (kind, code),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark,
            "vod_type": "连续剧" if kind == "series" else "视频",
            "style": {"type": "rect", "ratio": 0.75},
        }

    def _pagecount(self, html_text):
        pages = [int(n) for n in PAGER_RE.findall(html_text)]
        return max(1, max(pages)) if pages else 1

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
        """取视频页的 data-hls（master.m3u8）绝对地址；不在此处解析 variant，留给播放时解析。"""
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
            # master -> 具体 variant，避免播放器不跟随 variant 导致黑屏
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
