# -*- coding: utf-8 -*-
VERSION = "1.0.2"
# v1.0.0，基础版：首页/分类(base64导航)、列表分页、详情(play.php m3u8 / torrent磁力)、
#   搜索(视频+磁力)、磁力公共 tracker、可选115离线、封面 localProxy。
# v1.0.1，修复搜索sid误取导航分类id(改用redirect最终URL)；分页pagecount不再卡在当前页；
#   _total_pages只统计当前tid页码，不再混入其它分类；磁力播放/详情统一附公共tracker；
#   torrent在enableMagnet/offline都关时仍回退磁力，避免空播放源；115缓存上限64；
#   默认写入115 Cookie并默认开启离线(与javdbui一致)。
# v1.0.2，分类筛选kind：按满页预筛结果算pagecount，筛选后空页仍可翻下一页；
#   磁力/在线分类只展示对应筛选项；_detail_magnet的115离线ID改用干净磁力(不带tracker)；
#   115提交前强制去tracker；resolve补type/flv；统一走_off_cache_put；
#   视频详情仅磁力且双关时回退磁力源，避免空播放源。
import os
import re
import json
import time
import base64
import warnings
from urllib.parse import quote, unquote, urljoin

try:
    import requests
except ImportError:
    requests = None

try:
    from urllib3.exceptions import InsecureRequestWarning
    warnings.simplefilter("ignore", InsecureRequestWarning)
except Exception:
    pass


# ===========================================================================
# 配置区
# ===========================================================================
# 网页/图片代理（可选）。也可在 ext 里传 {"proxy": "http://127.0.0.1:7890"}
PROXY = ""

# 站点
HOST = "https://hscka.cc"

HTTP_RETRY = 2
HTTP_RETRY_DELAY = 0.6
HTTP_RETRY_STATUS = (429, 500, 502, 503, 504)

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

HTML_HEADERS = {
    "User-Agent": WEB_UA,
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}

# ============ 115 离线（对齐 javdbui 核心链路） ============
# 默认 Cookie 与 javdbui.py 一致；可用 ext.cookie115 / Y115_COOKIE 覆盖
DEFAULT_COOKIE_115 = ("UID=7090991_R1_1785487771; CID=3c1a3ab03cfc92b0b7c80db6efa950c6; "
                      "SEID=81ec0f1ad4aa99de925b609465a91c20d8894da910834a59f27cb239ebc5eb70412b456e8e91fff5654dc089a9d0c153f5fcec844b4cf7fa1b8aac84; "
                      "KID=bc573815d056010f1b8373db03247c3b")

OFF_PREFIX_115 = "http://115off/"

OFFLINE_UA = WEB_UA + " 115Browser/36.0.0"
OFFLINE_ADD_API = "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls"
OFFLINE_LIST_API = "https://115.com/web/lixian/?ct=lixian&ac=task_lists"
OFFLINE_POLL_TIMEOUT = 15
OFFLINE_POLL_INTERVAL = 1


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


def _safe_json(text, fallback=None):
    try:
        return json.loads(str(text or ""))
    except Exception:
        return fallback if fallback is not None else {}


def _norm_proxy(v):
    p = _to_text(v)
    if not p:
        return ""
    if p.lower() in ("0", "off", "none", "no", "false", "直连",
                     "disable", "disabled"):
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


def _play_err(msg):
    return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
            "msg": _to_text(msg)}


# 公共 tracker：磁力直连播放时附加，加速 DHT 找 peer
MAGNET_TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://open.stealth.si:80/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.bt4g.com:2095/announce",
)


def _magnet_with_trackers(infohash):
    m = "magnet:?xt=urn:btih:" + _to_text(infohash)
    for tr in MAGNET_TRACKERS:
        m += "&tr=" + quote(tr, safe=":/")
    return m


def _normalize_magnet(magnet):
    if not magnet:
        return ""
    m = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet)
    if not m:
        return magnet
    base = "magnet:?xt=urn:btih:" + m.group(1)
    for tr in re.findall(r"[?&]tr=([^&]+)", magnet):
        base += "&tr=" + tr
    return base


def _magnet_hash(magnet):
    m = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet or "")
    return m.group(1).lower() if m else ""


def _magnet_clean(magnet):
    """仅保留 btih，去掉 tracker 等参数（115 离线提交用，避免 hash 匹配问题）。"""
    h = _magnet_hash(magnet)
    return ("magnet:?xt=urn:btih:" + h) if h else _normalize_magnet(magnet)


def _magnet_play_url(magnet):
    """规范化磁力并附公共 tracker（加速 DHT 找 peer）。"""
    h = _magnet_hash(magnet)
    if h:
        return _magnet_with_trackers(h)
    return _normalize_magnet(magnet)


def _off_id_encode(magnet, title="", label=""):
    payload = {"m": _to_text(magnet)}
    if _to_text(title):
        payload["t"] = _to_text(title)
    if _to_text(label):
        payload["l"] = _to_text(label)
    raw = json.dumps(payload, ensure_ascii=False)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def _off_id_decode(text):
    text = _to_text(text).strip().split("#")[0].split("?")[0]
    try:
        raw = base64.b64decode(text.encode("ascii")).decode("utf-8")
    except Exception:
        return "", "", ""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        if isinstance(data, dict):
            return (_to_text(data.get("m") or ""),
                    _to_text(data.get("t") or ""),
                    _to_text(data.get("l") or ""))
    return raw, "", ""


# ==================== 115 加密（javdbui 同款 RSA/XOR） ====================

RSA_N = 0x8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683
RSA_E = 0x10001
KEY_TABLE = bytes([
    240, 229, 105, 174, 191, 220, 191, 138, 26, 69, 232, 190, 125, 166, 115, 184,
    222, 143, 231, 196, 69, 218, 134, 196, 155, 100, 139, 20, 106, 180, 241, 170,
    56, 1, 53, 158, 38, 105, 44, 134, 0, 107, 79, 165, 54, 52, 98, 166,
    42, 150, 104, 24, 242, 74, 253, 189, 107, 151, 143, 77, 143, 137, 19, 183,
    108, 142, 147, 237, 14, 13, 72, 62, 215, 47, 136, 216, 254, 254, 126, 134,
    80, 149, 79, 209, 235, 131, 38, 52, 219, 102, 123, 156, 126, 157, 122, 129,
    50, 234, 182, 51, 222, 58, 169, 89, 52, 102, 59, 170, 186, 129, 96, 72,
    185, 213, 129, 156, 248, 108, 132, 119, 255, 84, 120, 38, 95, 190, 232, 30,
    54, 159, 52, 128, 92, 69, 44, 155, 118, 213, 27, 143, 204, 195, 184, 245,
])


def _chunks(start, end, step=1):
    out = []
    nxt = start + step
    while nxt < end:
        out.append((start, nxt))
        start = nxt
        nxt += step
    if start != end:
        out.append((start, end))
    return out


def _bytes_to_int(b):
    out = 0
    for byte in b:
        out = (out << 8) | byte
    return out


def _int_to_bytes(value, length=None):
    if length is None:
        length = max(1, (value.bit_length() + 7) // 8)
    out = bytearray(length)
    for i in range(length - 1, -1, -1):
        out[i] = value & 0xFF
        value >>= 8
    return bytes(out)


def _xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def _xor_by_key(input_bytes, key):
    out = bytearray(len(input_bytes))
    head = len(input_bytes) & 3
    if head:
        out[0:head] = _xor_bytes(input_bytes[0:head], key[0:head])
    for (f, t) in _chunks(head, len(input_bytes), len(key)):
        seg = input_bytes[f:t]
        klen = len(key)
        for i in range(len(seg)):
            out[f + i] = seg[i] ^ key[i % klen]
    return bytes(out)


def _mod_pow(base, exp, mod):
    if mod == 1:
        return 0
    result = 1
    base %= mod
    while exp:
        if exp & 1:
            result = (result * base) % mod
        exp >>= 1
        base = (base * base) % mod
    return result


def _encode_block(input_bytes):
    block = bytearray(128)
    fill_end = 127 - len(input_bytes)
    for i in range(1, max(1, fill_end)):
        block[i] = 2
    block[0] = 0
    block[128 - len(input_bytes):128] = input_bytes
    return _bytes_to_int(bytes(block))


def _table_key(seed, length):
    out = bytearray(length)
    n = length * (length - 1)
    s = 0
    for i in range(length):
        mixed = (seed[i] + KEY_TABLE[s]) & 255
        out[i] = KEY_TABLE[n] ^ mixed
        n -= length
        s += length
    return bytes(out)


def _encrypt_payload(value):
    input_bytes = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    step1 = _xor_by_key(input_bytes, bytes([141, 165, 165, 141]))
    step2 = step1[::-1]
    step3 = _xor_by_key(step2, bytes([120, 6, 173, 76, 51, 134, 93, 24, 76, 1, 63, 70]))
    padded = bytes(16) + step3
    blocks = _chunks(0, len(padded), 117)
    out = bytearray(len(blocks) * 128)
    pos = 0
    for (f, t) in blocks:
        enc = _mod_pow(_encode_block(padded[f:t]), RSA_E, RSA_N)
        out[pos:pos + 128] = _int_to_bytes(enc, 128)
        pos += 128
    return base64.b64encode(bytes(out)).decode("ascii")


def _decrypt_payload(value):
    raw = base64.b64decode(value)
    merged = bytearray()
    for (f, t) in _chunks(0, len(raw), 128):
        dec = _int_to_bytes(_mod_pow(_bytes_to_int(raw[f:t]), RSA_E, RSA_N))
        idx = dec.find(b"\x00")
        merged.extend(dec[idx + 1:] if idx >= 0 else dec)
    if len(merged) < 16:
        return ""
    seed = merged[0:16]
    key = _table_key(seed, 12)
    body = _xor_by_key(merged[16:], key)[::-1]
    plain = _xor_by_key(body, bytes([141, 165, 165, 141]))
    try:
        return plain.decode("utf-8")
    except Exception:
        return ""


def _build_downurl_body(payload_dict):
    enc = _encrypt_payload(json.dumps(payload_dict, separators=(",", ":")))
    return "data=" + quote(enc, safe="")


def _extract_encrypted(data):
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except Exception:
            return data, None
        return _extract_encrypted(parsed)
    if isinstance(data, dict):
        enc = ""
        d = data.get("data")
        if isinstance(d, str):
            enc = d
        elif isinstance(d, dict) and isinstance(d.get("data"), str):
            enc = d["data"]
        return enc, data
    return "", data


def _decode_downurl_response(data):
    enc, payload = _extract_encrypted(data)
    if not enc:
        return payload or {}
    try:
        return json.loads(_decrypt_payload(enc))
    except Exception:
        if isinstance(payload, dict):
            return payload
        raise


def _find_url_deep(obj):
    if not isinstance(obj, dict):
        return ""
    u = obj.get("url")
    if isinstance(u, str) and u:
        return u
    if isinstance(u, dict) and isinstance(u.get("url"), str) and u["url"]:
        return u["url"]
    d = obj.get("data")
    if isinstance(d, dict) and isinstance(d.get("url"), str) and d["url"]:
        return d["url"]
    for v in obj.values():
        hit = _find_url_deep(v)
        if hit:
            return hit
    return ""


def _find_msg_deep(obj):
    if not isinstance(obj, dict):
        return ""
    for key in ("msg", "message", "error"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for v in obj.values():
        hit = _find_msg_deep(v)
        if hit:
            return hit
    return ""


def _set_cookie_text(set_cookie):
    if not set_cookie:
        return ""
    if isinstance(set_cookie, str):
        set_cookie = [set_cookie]
    return "; ".join(str(v).split(";")[0].strip()
                     for v in set_cookie if str(v).split(";")[0].strip())


# ==================== Spider ====================

class Spider:
    def __init__(self):
        self.s = None
        self.s115 = None
        self.host = HOST
        self.ua = WEB_UA
        self.timeout = 15
        self.verify = False
        self.proxy = PROXY
        self.cookie_115 = DEFAULT_COOKIE_115
        self.enable_magnet = True
        self.enable_offline_115 = True
        self.offline_save_path = "0"
        self.offline_app_ver = "4.8.2"
        self.offline_timeout = 12
        self.offline_proxy = ""
        self.offline_debug = True

        self._categories_cache = None
        self._off_cache = {}
        self._off_name = {}
        self._search_list_id = {}
        self._pic_cache = {}
        self._off_last = ""
        self.img_proxy = ""

        if requests:
            self.s = requests.Session()
            self.s.headers.update(HTML_HEADERS)
            self._apply_proxy()

    def getDependence(self):
        return []

    # ---------- extend ----------
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
        if extend.get("host"):
            self.host = str(extend["host"]).rstrip("/")
        if "proxy" in extend:
            self.set_proxy(extend.get("proxy"))
        elif "proxyPort" in extend or "proxy_port" in extend:
            self.set_proxy(extend.get("proxyPort") or extend.get("proxy_port"))
        if "enableMagnet" in extend:
            self.enable_magnet = bool(extend["enableMagnet"])
        if "enableOffline115" in extend:
            self.enable_offline_115 = bool(extend["enableOffline115"])
        if extend.get("cookie115"):
            self.cookie_115 = str(extend["cookie115"])
        elif os.environ.get("Y115_COOKIE") or os.environ.get("MY115_COOKIE"):
            self.cookie_115 = (os.environ.get("Y115_COOKIE")
                               or os.environ.get("MY115_COOKIE"))
        if extend.get("offlineSavePath"):
            self.offline_save_path = str(extend["offlineSavePath"])
        if extend.get("offlineAppVer"):
            self.offline_app_ver = str(extend["offlineAppVer"])
        if "offlineProxy" in extend:
            self.offline_proxy = _to_text(extend.get("offlineProxy"))
        if "offlineDebug" in extend:
            self.offline_debug = str(extend.get("offlineDebug")).lower() not in (
                "0", "false", "off", "no")
        if "verify" in extend:
            self.verify = bool(extend["verify"])
        if extend.get("img") or extend.get("imgProxy"):
            self.img_proxy = str(
                extend.get("img") or extend.get("imgProxy") or "").strip()
        self._apply_proxy()
        if self.s is not None:
            try:
                self.s.headers.update(HTML_HEADERS)
            except Exception:
                pass
        # 预加载分类
        try:
            home = self._fetch(self.host + "/")
            if home:
                self._load_categories(home)
        except Exception:
            pass

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

    # ---------- HTTP ----------
    def _headers(self, referer=None):
        h = dict(HTML_HEADERS)
        ref = _to_text(referer) or self.host
        if not ref.endswith("/"):
            ref += "/"
        h["Referer"] = ref
        return h

    def _fetch(self, url, referer=None, retries=None):
        text, _final = self._fetch_ex(url, referer=referer, retries=retries)
        return text

    def _fetch_ex(self, url, referer=None, retries=None):
        """返回 (text, final_url)；search 用 final_url 提取 sid，避免误取导航分类 id。"""
        if not requests:
            return "", ""
        retries = HTTP_RETRY if retries is None else retries
        ref = referer if referer is not None else (self.host + "/")
        headers = self._headers(ref)
        for attempt in range(retries + 1):
            try:
                if attempt:
                    time.sleep(HTTP_RETRY_DELAY)
                r = self.s.get(url, headers=headers, timeout=self.timeout,
                               verify=self.verify, allow_redirects=True)
                if r.status_code in HTTP_RETRY_STATUS and attempt < retries:
                    continue
                if r.status_code != 200:
                    return "", ""
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text, _to_text(r.url)
            except Exception:
                if attempt < retries:
                    continue
                return "", ""
        return "", ""

    @staticmethod
    def _decode_b64(encoded_str):
        try:
            raw = base64.b64decode(encoded_str)
            return raw.decode("utf-8")
        except Exception:
            return _to_text(encoded_str)

    def _clean_text(self, s):
        s = re.sub(r"<[^>]+>", "", _to_text(s))
        return s.strip()

    # ---------- 分类 ----------
    def _load_categories(self, text):
        if not text:
            return self._categories_cache or []
        cats = []
        seen = set()
        pattern = (r'href="(/list/\d+-\d+\.html)"[^>]*>\s*'
                   r"<script[^>]*>document\.write\(d\('([A-Za-z0-9+/=]+)'\)\);</script>")
        for path, b64_name in re.findall(pattern, text, re.S):
            name = self._clean_text(self._decode_b64(b64_name))
            if not name or name in seen:
                continue
            seen.add(name)
            tid = path.split("/")[-1].split("-")[0]
            cats.append({"type_id": tid, "type_name": name})
        # 首页/热播 置顶
        out = [{"type_id": "hot", "type_name": "热播"}] + cats
        self._categories_cache = cats or self._categories_cache
        return out

    def _category_name(self, tid):
        for cat in (self._categories_cache or []):
            if cat["type_id"] == tid:
                return cat["type_name"]
        return _to_text(tid)

    # ---------- 列表解析 ----------
    def _parse_list(self, html, magnet_kind=False):
        items = []
        if not html:
            return items
        cards = re.findall(
            r'<div class="item item-post">\s*(.*?)\s*</div>',
            html, re.S)
        for card in cards:
            a_match = re.search(r'<a href="([^"]+)"', card)
            if not a_match:
                continue
            href = a_match.group(1).strip()
            img_match = re.search(
                r'<img[^>]+(?:data-original|src)="([^"]+)"', card)
            pic = img_match.group(1) if img_match else ""
            if pic.startswith("/"):
                pic = self.host + pic

            title = ""
            title_match = re.search(r'<h3 class="name">(.*?)</h3>', card, re.S)
            if title_match:
                title_raw = title_match.group(1)
                b64 = re.search(
                    r"document\.write\(d\('([A-Za-z0-9+/=]+)'\)\)", title_raw)
                if b64:
                    title = self._clean_text(self._decode_b64(b64.group(1)))
                else:
                    title = self._clean_text(title_raw)

            if href.startswith("magnet:"):
                items.append({
                    "vod_id": href,
                    "vod_name": title or "磁力资源",
                    "vod_pic": self._proxy_pic(pic),
                    "vod_remarks": "磁力",
                })
            elif "/torrent/" in href:
                vid = href.rstrip("/").split("/")[-1]
                if vid.endswith(".html"):
                    vid = vid[:-5]
                items.append({
                    "vod_id": "t:" + vid,
                    "vod_name": title,
                    "vod_pic": self._proxy_pic(pic),
                    "vod_remarks": "磁力",
                })
            elif "/video/" in href:
                vid = href.rstrip("/").split("/")[-1]
                if vid.endswith(".html"):
                    vid = vid[:-5]
                items.append({
                    "vod_id": "v:" + vid,
                    "vod_name": title,
                    "vod_pic": self._proxy_pic(pic),
                    "vod_remarks": "在线" if not magnet_kind else "",
                })
        return items

    def _total_pages(self, html, tid=None):
        """只统计当前 tid（或搜索 sid）的页码，避免混入导航里其它分类的 -N.html。"""
        if not html:
            return 1
        if tid:
            pat = r"/list/%s-(\d+)\.html" % re.escape(_to_text(tid))
            pages = [int(p) for p in re.findall(pat, html)]
        else:
            pages = [int(p) for p in re.findall(r"/list/\d+-(\d+)\.html", html)]
        return max(pages) if pages else 1

    def _get_list(self, tid, page):
        url = "%s/list/%s-%d.html" % (self.host, tid, page)
        html = self._fetch(url, referer="%s/list/%s-1.html" % (self.host, tid))
        if not html:
            return [], page
        mag = "磁力" in self._category_name(tid)
        items = self._parse_list(html, magnet_kind=mag)
        # 每页都能从分页链接拿到总页数（含 >1 页时的上一页/页码）
        total = self._total_pages(html, tid)
        return items, total

    # ---------- 图片 ----------
    def _proxy_pic(self, url):
        url = _to_text(url)
        if not url:
            return ""
        p = _to_text(getattr(self, "img_proxy", ""))
        if p:
            if "{url}" in p:
                return p.replace("{url}", quote(url, safe=""))
            return p + quote(url, safe="")
        try:
            from com.github.catvod import Proxy
        except Exception:
            return url
        try:
            port = int(Proxy.getPort() or 0)
        except Exception:
            port = 0
        tok = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
        if port > 0:
            return "http://127.0.0.1:%d/proxy?do=py&kind=image&token=%s" % (port, quote(tok, safe=""))
        try:
            getter = getattr(Proxy, "getUrl", None)
            u = _to_text(getter() if getter else "")
            if u.startswith(("http://", "https://")):
                base = u + ("&" if "?" in u else "?") + "do=py"
                return base + "&kind=image&token=%s" % quote(tok, safe="")
        except Exception:
            pass
        return "proxy://do=py&kind=image&token=%s" % quote(tok, safe="")

    @staticmethod
    def _parse_proxy_param(param):
        if isinstance(param, dict):
            return param
        if isinstance(param, str):
            raw = param.strip()
            if raw.startswith("{"):
                try:
                    d = json.loads(raw)
                    if isinstance(d, dict):
                        return d
                except Exception:
                    pass
            d = {}
            for kv in raw.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    try:
                        v = unquote(v)
                    except Exception:
                        pass
                    d[k] = v
            return d
        return {}

    @staticmethod
    def _unpack_pic_token(tok):
        try:
            s = _to_text(tok or "").strip()
            if not s:
                return ""
            s = s.replace("-", "+").replace("_", "/")
            s += "=" * (-len(s) % 4)
            u = base64.b64decode(s).decode("utf-8", "ignore")
            return u if u.startswith(("http://", "https://")) else ""
        except Exception:
            return ""

    def localProxy(self, param):
        param = self._parse_proxy_param(param)
        kind = _to_text(param.get("kind") or param.get("k") or "").lower()
        if kind == "offnote":
            text = _to_text(param.get("v") or "").strip() or "115离线完成"
            body = "1\n00:00:00,000 --> 00:00:08,000\n%s\n\n" % text
            return [200, "application/x-subrip", body.encode("utf-8"), {}]
        if kind in ("img", "image"):
            src = _to_text(param.get("token") or param.get("u") or "")
            if src and not src.startswith(("http://", "https://")):
                src = self._unpack_pic_token(src) or src
            body, mime = self._fetch_pic(src)
            if not body:
                return [404, "text/plain", b"Not Found", {}]
            return [200, mime, body, {
                "Cache-Control": "public, max-age=1800",
                "Access-Control-Allow-Origin": "*",
                "Content-Length": str(len(body)),
            }]
        return [404, "text/plain", b"Not Found", {}]

    def _fetch_pic(self, url):
        if not requests or not url.startswith(("http://", "https://")):
            return b"", ""
        cache = self._pic_cache
        hit = cache.get(url)
        now = time.time()
        if hit and now - hit[0] <= 1800:
            del cache[url]
            cache[url] = hit
            return hit[1], hit[2]
        headers = {
            "User-Agent": WEB_UA,
            "Referer": self.host + "/",
            "Accept": "image/*,*/*",
        }
        if self.s is None:
            return b"", ""
        try:
            r = self.s.get(url, headers=headers, timeout=self.timeout,
                           verify=self.verify)
        except Exception:
            return b"", ""
        if r.status_code != 200 or not r.content:
            return b"", ""
        mime = self._pic_mime(r.content) or \
            _to_text(r.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
        cache[url] = (now, r.content, mime)
        while len(cache) > 64:
            cache.pop(next(iter(cache)), None)
        return r.content, mime

    @staticmethod
    def _pic_mime(raw):
        raw = bytes(raw or b"")
        if raw[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if raw[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if len(raw) > 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return "image/webp"
        return ""

    # ---------- 首页 ----------
    def homeContent(self, filter=None):
        classes = []
        filters = {}
        try:
            text = self._fetch(self.host + "/")
            if text:
                classes = self._load_categories(text)
        except Exception:
            pass
        if not classes:
            classes = [{"type_id": "hot", "type_name": "热播"}]
        # 按分类实际内容定制筛选：磁力分类只出磁力，视频分类只出在线，混合给全部
        for c in classes:
            tid = c["type_id"]
            name = _to_text(c.get("type_name") or "")
            if tid == "hot" or "磁力" in name:
                opts = [
                    {"n": "全部", "v": ""},
                    {"n": "磁力", "v": "magnet"},
                ]
            else:
                opts = [
                    {"n": "全部", "v": ""},
                    {"n": "在线", "v": "video"},
                    {"n": "磁力", "v": "magnet"},
                ]
            filters[tid] = [{
                "key": "kind", "name": "内容", "init": "",
                "value": opts,
            }]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        # 优先首页推荐列表（站点首页已有视频卡片）
        html = self._fetch(self.host + "/")
        lst = self._parse_list(html) if html else []
        if not lst and self._categories_cache:
            lst, _ = self._get_list(self._categories_cache[0]["type_id"], 1)
        if not lst:
            lst, _ = self._get_list("39765797", 1)
        return {"list": lst[:50]}

    # ---------- 分类 ----------
    @staticmethod
    def _page_result(out, page, pagecount=None):
        if pagecount is None:
            pagecount = page + 1 if out else page
        return {"list": out, "page": page, "pagecount": pagecount,
                "limit": len(out), "total": len(out)}

    def _list_page_result(self, items, page, page_size=20, full_page=False):
        """分页结果：站点分页窗是滑动的（只显示邻近约4页），
        HTML 里的最大页码不是真实总数，不可信。
        策略：源页满页(full_page) → 乐观 page+1；未满/空 → 当前页即末页。
        full_page 须在 kind 筛选前判断，避免筛选后空页卡死翻页。"""
        if not items:
            if full_page:
                return self._page_result([], page, page + 1)
            return self._page_result([], page, page)
        if full_page or len(items) >= page_size:
            return self._page_result(items, page, page + 1)
        return self._page_result(items, page, page)

    def _filter_kind(self, items, kind):
        kind = _to_text(kind)
        if not kind:
            return items
        out = []
        for it in items:
            vid = _to_text(it.get("vod_id") or "")
            if kind == "magnet" and (vid.startswith("magnet:") or vid.startswith("t:")):
                out.append(it)
            elif kind == "video" and vid.startswith("v:"):
                out.append(it)
        return out

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        t = _to_text(tid)
        page = max(1, _safe_int(pg, 1))
        fs = {}
        for src in (filter, extend):
            if isinstance(src, dict):
                fs.update(src)
        try:
            if t == "hot":
                html = self._fetch(self.host + "/")
                items = self._parse_list(html) if html else []
                items = self._filter_kind(items, fs.get("kind"))
                return self._page_result(items[:50], 1, 1)
            raw, _total = self._get_list(t, page)
            full_page = len(raw) >= 20
            kind = _to_text(fs.get("kind") or "")
            items = self._filter_kind(raw, kind) if kind else raw
            return self._list_page_result(items, page, full_page=full_page)
        except Exception as e:
            try:
                print("[hsck] categoryContent ERR", e)
            except Exception:
                pass
            return self._page_result([], page, page)

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg="1"):
        page = max(1, _safe_int(pg, 1))
        keyword = _to_text(key)
        if not keyword:
            return self._page_result([], page, 1)
        # 站点搜索会 302 到 /list/{sid}-1.html（page 参数被忽略）。
        # sid 必须从 redirect 最终 URL 提取；HTML 里第一条 /list/ 是导航分类，不能用。
        sid = self._search_list_id.get(keyword)
        first_html = ""
        if not sid:
            for stype in ("1", "2"):
                url = "%s/search.php?content=%s&type=%s&page=1" % (
                    self.host, quote(keyword), stype)
                html, final = self._fetch_ex(url, referer=self.host + "/")
                if not html:
                    continue
                m = re.search(r"/list/(\d+)-\d+\.html", final or "")
                if not m:
                    continue
                items = self._parse_list(html)
                if not items:
                    continue  # 空结果不缓存 sid，继续试 type=2
                sid = m.group(1)
                self._search_list_id[keyword] = sid
                first_html = html
                break
        if not sid:
            return self._page_result([], page, page)
        if page == 1:
            html = first_html or self._fetch(
                "%s/list/%s-1.html" % (self.host, sid),
                referer=self.host + "/")
        else:
            html = self._fetch("%s/list/%s-%d.html" % (self.host, sid, page),
                               referer=self.host + "/")
        items = self._parse_list(html) if html else []
        full_page = len(items) >= 20
        return self._list_page_result(items, page, full_page=full_page)

    # ---------- 详情 ----------
    def _split_id(self, vid):
        vid = _to_text(vid)
        if vid.startswith("magnet:"):
            return "magnet", vid
        if vid.startswith("v:"):
            return "video", vid[2:]
        if vid.startswith("t:"):
            return "torrent", vid[2:]
        return "video", vid

    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        if not vid:
            return {"list": []}
        kind, raw = self._split_id(vid)
        try:
            if kind == "magnet" or raw.startswith("magnet:"):
                return {"list": [self._detail_magnet(raw if raw.startswith("magnet:") else vid)]}
            if kind == "torrent":
                return {"list": [self._detail_torrent(raw)]}
            return {"list": [self._detail_video(raw)]}
        except Exception as e:
            try:
                print("[hsck] detailContent ERR", e)
            except Exception:
                pass
            return {"list": []}

    def _detail_magnet(self, magnet):
        clean = _magnet_clean(magnet)
        play_mag = _magnet_play_url(clean)
        play_from = []
        play_url = []
        if self.enable_magnet:
            play_from.append("磁力")
            play_url.append("磁力$%s" % _sanitize_play(play_mag))
        if self.enable_offline_115:
            b64 = _off_id_encode(clean, "磁力资源", "磁力")
            play_from.append("115离线")
            play_url.append("磁力$%s%s?t=%d" % (
                OFF_PREFIX_115, b64, int(time.time())))
        if not play_from:
            # 双关时仍回退磁力，避免空播放源
            play_from.append("磁力")
            play_url.append("磁力$%s" % _sanitize_play(play_mag))
        return {
            "vod_id": clean,
            "vod_name": "磁力资源",
            "vod_pic": "",
            "vod_content": "磁力链接（可配合云播放/115离线使用）",
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }

    def _detail_torrent(self, tid):
        url = "%s/torrent/%s.html" % (self.host, tid)
        html = self._fetch(url, referer=self.host + "/")
        title = ""
        m = re.search(r"<title>([^<]+)</title>", html or "")
        if m:
            title = self._clean_text(m.group(1))
        if not title:
            for m in re.finditer(
                    r"document\.write\(d\('([A-Za-z0-9+/=]+)'\)\)", html or ""):
                t = self._clean_text(self._decode_b64(m.group(1)))
                if t and "document.write" not in t:
                    title = t
                    break
        magnets = re.findall(
            r'(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\s"\'<>]*)', html or "")
        # 去重保序
        seen = set()
        uniq = []
        for mag in magnets:
            h = _magnet_hash(mag)
            if h and h in seen:
                continue
            if h:
                seen.add(h)
            uniq.append(_normalize_magnet(mag))
        play_from = []
        play_url = []
        eps = []
        off_eps = []
        for i, mag in enumerate(uniq):
            clean = _magnet_clean(mag)
            play_mag = _magnet_play_url(clean)
            label = "磁力%d" % (i + 1) if len(uniq) > 1 else "磁力"
            eps.append("%s$%s" % (_sanitize_play(label), _sanitize_play(play_mag)))
            if self.enable_offline_115:
                b64 = _off_id_encode(clean, title, label)
                off_eps.append("%s$%s%s?t=%d" % (
                    _sanitize_play(label), OFF_PREFIX_115, b64, int(time.time())))
        if eps:
            if self.enable_magnet or not off_eps:
                play_from.append("磁力")
                play_url.append("#".join(eps))
            if off_eps:
                play_from.append("115离线")
                play_url.append("#".join(off_eps))
        if not play_from:
            # 无磁力时回退一个空源，避免 vod_play_url 为空
            play_from.append("磁力")
            play_url.append("磁力$")
        return {
            "vod_id": "t:" + tid,
            "vod_name": title or ("磁力 " + tid),
            "vod_pic": "",
            "vod_content": title or "",
            "vod_remarks": "磁力%d" % len(uniq) if uniq else "磁力",
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }

    def _detail_video(self, vid):
        url = "%s/video/%s.html" % (self.host, vid)
        html = self._fetch(url, referer=self.host + "/")
        title = ""
        # 优先取播放器上方 h2 标题（导航分类也用 document.write，勿误取）
        m = re.search(
            r"<h2><script[^>]*>document\.write\(d\('([A-Za-z0-9+/=]+)'\)\);</script></h2>",
            html or "")
        if m:
            title = self._clean_text(self._decode_b64(m.group(1)))
        if not title:
            m = re.search(r"<title>([^<]+)</title>", html or "")
            if m:
                title = self._clean_text(m.group(1))
        if not title:
            for m in re.finditer(
                    r"document\.write\(d\('([A-Za-z0-9+/=]+)'\)\)", html or ""):
                t = self._clean_text(self._decode_b64(m.group(1)))
                if t and "document.write" not in t and len(t) > 6:
                    title = t
                    break

        # play.php 播放地址（详情页多源、带 Referer 可直接出 m3u8）
        play_links = []
        for link in re.findall(
                r"playFilteredHLS\(\s*'video'\s*,\s*'([^']+)'", html or ""):
            if link not in play_links:
                play_links.append(link)
        for link in re.findall(
                r"(https?://[^\"'\s]*play\.php[^\"'\s]*)", html or ""):
            if link not in play_links:
                play_links.append(link)
        for link in re.findall(
                r"href=[\"']?(/[^\"'<>\s]*play\.php[^\"'<>\s]*)", html or ""):
            full = urljoin(self.host + "/", link)
            if full not in play_links:
                play_links.append(full)

        magnets = set(re.findall(
            r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\s\"'<>]*)", html or ""))
        media = set(re.findall(
            r"https?://[^\s\"'<>]+\.(?:m3u8|mp4|flv|ts)(?:\?[^\s\"'<>]*)?",
            html or ""))

        play_from = []
        play_url = []
        if play_links:
            eps = []
            for i, link in enumerate(play_links):
                label = "播放" if len(play_links) == 1 else "播放%d" % (i + 1)
                eps.append("%s$%s" % (_sanitize_play(label), _sanitize_play(link)))
            play_from.append("在线")
            play_url.append("#".join(eps))
        if media:
            eps = []
            for i, link in enumerate(sorted(media)):
                label = "直链%d" % (i + 1)
                eps.append("%s$%s" % (_sanitize_play(label), _sanitize_play(link)))
            play_from.append("直链")
            play_url.append("#".join(eps))
        if magnets and self.enable_magnet:
            eps = []
            for i, mag in enumerate(sorted(magnets)):
                clean = _magnet_clean(mag)
                play_mag = _magnet_play_url(clean)
                label = "磁力%d" % (i + 1)
                eps.append("%s$%s" % (_sanitize_play(label), _sanitize_play(play_mag)))
            play_from.append("磁力")
            play_url.append("#".join(eps))
        if magnets and self.enable_offline_115:
            off_eps = []
            for i, mag in enumerate(sorted(magnets)):
                clean = _magnet_clean(mag)
                label = "磁力%d" % (i + 1)
                b64 = _off_id_encode(clean, title, label)
                off_eps.append("%s$%s%s?t=%d" % (
                    _sanitize_play(label), OFF_PREFIX_115, b64, int(time.time())))
            play_from.append("115离线")
            play_url.append("#".join(off_eps))
        if magnets and not play_from:
            # 视频详情里只有磁力、且磁力/离线都关时，回退磁力避免空源
            eps = []
            for i, mag in enumerate(sorted(magnets)):
                clean = _magnet_clean(mag)
                play_mag = _magnet_play_url(clean)
                label = "磁力%d" % (i + 1)
                eps.append("%s$%s" % (_sanitize_play(label), _sanitize_play(play_mag)))
            play_from.append("磁力")
            play_url.append("#".join(eps))

        return {
            "vod_id": "v:" + vid,
            "vod_name": title or vid,
            "vod_pic": "",
            "vod_content": title or "",
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }

    # ---------- 搜索（番号/标题） ----------
    # （searchContent 已实现）

    # ---------- 播放 ----------
    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        if vid.startswith(OFF_PREFIX_115):
            magnet, title, label = _off_id_decode(vid[len(OFF_PREFIX_115):])
            if not magnet:
                return _play_err("磁力解码失败")
            return self._play_offline(magnet, title, label)
        if vid.startswith("115off:"):
            return self._play_offline(vid[len("115off:"):].strip())
        if vid.startswith("magnet:"):
            m = _magnet_play_url(vid)
            return {
                "parse": 0, "jx": 0, "playUrl": "",
                "url": m or vid,
                "header": {"User-Agent": self.ua, "Accept": "*/*",
                           "Referer": self.host + "/"},
            }
        if vid.startswith(("http://", "https://")):
            hdr = {
                "User-Agent": self.ua,
                "Referer": self.host + "/",
                "Accept": "*/*",
            }
            # play.php 出 m3u8，带站点 Referer 更稳
            if "play.php" in vid:
                hdr["Referer"] = self.host + "/"
            return {"parse": 0, "jx": 0, "playUrl": "", "url": vid, "header": hdr}
        return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

    # ---------- 115 离线（精简核心链路） ----------
    def _offline_session(self):
        if self.s115 is not None:
            return self.s115
        if not requests:
            return None
        s = requests.Session()
        s.trust_env = False
        p = _norm_proxy(self.offline_proxy)
        if p:
            s.proxies = {"http": p, "https": p}
        self.s115 = s
        return s

    def _offline_headers(self):
        return {
            "Cookie": self.cookie_115,
            "User-Agent": OFFLINE_UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
        }

    def _offline_add(self, magnet):
        sess = self._offline_session()
        if sess is None:
            return {}
        data = {
            "url[0]": magnet,
            "wp_save_path": self.offline_save_path,
            "appVer": self.offline_app_ver,
        }
        r = sess.post(OFFLINE_ADD_API, data=data, headers=self._offline_headers(),
                      timeout=self.offline_timeout, verify=self.verify)
        try:
            return r.json()
        except Exception:
            return {}

    def _offline_list(self, page=1):
        sess = self._offline_session()
        if sess is None:
            return {}
        data = {"page": page, "appVer": self.offline_app_ver}
        r = sess.post(OFFLINE_LIST_API, data=data, headers=self._offline_headers(),
                      timeout=self.offline_timeout, verify=self.verify)
        try:
            return r.json()
        except Exception:
            return {}

    def _offline_find_task(self, info_hash, max_page=2):
        for page in range(1, max_page + 1):
            try:
                res = self._offline_list(page)
            except Exception:
                return None
            tasks = res.get("tasks") or res.get("list") or []
            if not tasks:
                break
            for t in tasks:
                h = (t.get("info_hash") or t.get("hash") or "").lower()
                if h and h == info_hash.lower():
                    return t
        return None

    @staticmethod
    def _task_pickcode(task):
        if not task:
            return ""
        return _to_text(task.get("pick_code") or task.get("pickcode")
                        or task.get("pc") or "")

    def _offline_task_state(self, task):
        if not task:
            return False, False, "任务未找到"
        status = task.get("status")
        if status is None:
            status = task.get("stat")
        try:
            status = int(status)
        except Exception:
            status = -1
        percent = task.get("percent")
        if percent is None:
            percent = task.get("percentDone", task.get("display_percent"))
        try:
            percent = float(percent)
        except Exception:
            percent = 0.0
        name = task.get("name") or task.get("file_name") or ""
        if status == 2 or percent >= 100:
            return True, False, name
        if status in (3, 4, -1):
            return False, True, (task.get("error_msg") or task.get("error")
                                 or task.get("message") or "离线任务失败")
        return False, False, name

    def _offline_wait_done(self, info_hash, timeout=OFFLINE_POLL_TIMEOUT):
        deadline = time.time() + timeout
        last_name = ""
        while time.time() < deadline:
            try:
                task = self._offline_find_task(info_hash, max_page=1)
            except Exception:
                task = None
            done, failed, msg = self._offline_task_state(task)
            if done:
                return True, msg or last_name
            if failed:
                return False, msg
            if msg:
                last_name = msg
            time.sleep(OFFLINE_POLL_INTERVAL)
        return False, last_name

    def _resolve_pickcode(self, pickcode):
        if not self.cookie_115:
            return _play_err("未配置115 Cookie（ext.cookie115 / Y115_COOKIE）")
        sess = self._offline_session()
        if not requests or sess is None:
            return _play_err("requests 模块不可用")
        body = _build_downurl_body({"pickcode": pickcode})
        url = "https://proapi.115.com/app/chrome/downurl?t=%d" % int(time.time())
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
            "Cookie": self.cookie_115,
            "User-Agent": OFFLINE_UA,
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
        }
        try:
            r = sess.post(url, data=body, headers=headers, timeout=12,
                          verify=self.verify)
        except Exception as e:
            return _play_err("115 取直链失败: %s" % e)
        try:
            decoded = _decode_downurl_response(r.text)
        except Exception as e:
            return _play_err("115 解密失败: %s" % e)
        real_url = _find_url_deep(decoded)
        if not real_url:
            msg = _find_msg_deep(decoded) or "未发现下载链接"
            return _play_err("115 限制: %s" % msg)
        new_cookie = _set_cookie_text(
            r.headers.get("Set-Cookie") if hasattr(r.headers, "get") else None)
        final_cookie = "; ".join(c for c in (self.cookie_115, new_cookie) if c)
        fmt = ""
        lower = real_url.lower().split("?")[0]
        if lower.endswith(".m3u8"):
            fmt = "application/x-mpegURL"
        elif lower.endswith(".mp4"):
            fmt = "video/mp4"
        elif lower.endswith(".flv"):
            fmt = "video/x-flv"
        result = {
            "parse": 0, "jx": 0, "playUrl": "", "url": real_url,
            "header": {
                "User-Agent": OFFLINE_UA,
                "Cookie": final_cookie,
                "Referer": "https://115.com/",
            },
            # 115 直链走云盘专用通道，避免被本地代理劫持
            "type": "THUNDER",
        }
        if fmt:
            result["format"] = fmt
        return result

    def _off_cache_put(self, info_hash, pc, name=""):
        self._off_cache[info_hash] = pc
        if name:
            self._off_name[info_hash] = name
        while len(self._off_cache) > 64:
            old = next(iter(self._off_cache))
            self._off_cache.pop(old, None)
            self._off_name.pop(old, None)

    def _play_offline(self, magnet, title="", label=""):
        t0 = time.time()
        # 115 提交用干净磁力（仅 btih，不带 tracker，避免 hash 匹配问题）
        magnet = _magnet_clean(magnet)
        info_hash = _magnet_hash(magnet)
        if not info_hash:
            return _play_err("无法从磁力中解析 info_hash")
        if not self.enable_offline_115:
            return _play_err("115离线已关闭（ext.enableOffline115）")
        if not self.cookie_115:
            return _play_err("未配置115 Cookie（ext.cookie115 / Y115_COOKIE）")

        cached = self._off_cache.get(info_hash)
        if cached:
            res = self._resolve_pickcode(cached)
            if res.get("url"):
                return res
            self._off_cache.pop(info_hash, None)
            self._off_name.pop(info_hash, None)

        task = None
        try:
            task = self._offline_find_task(info_hash)
        except Exception:
            task = None
        done0, failed0, _ = self._offline_task_state(task)
        if task and done0:
            pc0 = self._task_pickcode(task)
            if pc0:
                self._off_cache_put(info_hash, pc0)
                return self._resolve_pickcode(pc0)
        if task and not failed0:
            pass
        else:
            try:
                add = self._offline_add(magnet)
            except Exception as e:
                return _play_err("提交离线失败：%s" % e)
            add_msg = _to_text(add.get("message") or add.get("error_msg")
                               or add.get("error"))
            if not add.get("state") and not any(
                    k in add_msg for k in ("已存在", "重复")):
                try:
                    task = self._offline_find_task(info_hash)
                except Exception:
                    task = None
                if not task:
                    return _play_err("115离线提交失败：%s" % (add_msg or "提交失败"))
            try:
                task = self._offline_find_task(info_hash)
            except Exception:
                task = None

        done, name_or_msg = self._offline_wait_done(info_hash)
        if not done:
            return _play_err("已提交115离线，下载中（%s），请稍后重试"
                             % (name_or_msg or "等待完成"))
        try:
            task = self._offline_find_task(info_hash)
        except Exception:
            task = None
        pickcode = self._task_pickcode(task)
        if not pickcode:
            return _play_err("离线已完成，但未取到 pickcode，请稍后重试")
        self._off_cache_put(info_hash, pickcode, name_or_msg)
        res = self._resolve_pickcode(pickcode)
        if res.get("url") and self.offline_debug:
            try:
                note = "115离线完成（%.0fs）%s" % (
                    time.time() - t0,
                    ("\n" + _to_text(name_or_msg)) if name_or_msg else "")
                res["desc"] = note
                # 字幕提示（复用 localProxy offnote），部分播放器可显示
                try:
                    from com.github.catvod import Proxy
                    port = int(Proxy.getPort() or 0)
                except Exception:
                    port = 0
                if port > 0:
                    q = "do=py&k=offnote&v=%s" % quote(note, safe="")
                    res["subs"] = [{
                        "name": "115离线",
                        "url": "http://127.0.0.1:%d/proxy?%s" % (port, q),
                        "lang": "zh",
                        "format": "application/x-subrip",
                        "flag": 0,
                    }]
            except Exception:
                pass
        return res

    # ---------- 基础接口 ----------
    def isVideoFormat(self, url):
        u = _to_text(url).lower()
        if u.startswith("magnet:"):
            return True
        if u.startswith(OFF_PREFIX_115) or u.startswith("115off:"):
            return True
        u = u.split("?")[0]
        return u.endswith((".mp4", ".m3u8", ".flv", ".mkv", ".ts", ".avi"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def destroy(self):
        try:
            if self.s is not None:
                self.s.close()
        except Exception:
            pass
        try:
            if self.s115 is not None:
                self.s115.close()
        except Exception:
            pass
        return None


# 命令行自检：python3 hsck.py
if __name__ == "__main__":
    sp = Spider()
    sp.init("")
    print("VERSION", VERSION)
    print("cookie115", "SET" if sp.cookie_115 else "EMPTY",
          "| offline", sp.enable_offline_115, "| magnet", sp.enable_magnet)
    hc = sp.homeContent()
    print("classes", [(c["type_id"], c["type_name"]) for c in (hc.get("class") or [])])
    hv = sp.homeVideoContent()
    print("homeVideo", len(hv.get("list") or []),
          (hv.get("list") or [{}])[0].get("vod_name", "")[:40])
    for c in (hc.get("class") or []):
        tid = c["type_id"]
        try:
            r = sp.categoryContent(tid, "1", {}, {})
            lst = r.get("list") or []
            print("cat", tid, c["type_name"], "n=%d" % len(lst),
                  "pages=%s" % r.get("pagecount"),
                  (lst[0].get("vod_name") if lst else "")[:40])
        except Exception as e:
            print("cat", tid, "ERR", type(e).__name__, str(e)[:80])
    try:
        r = sp.categoryContent("39765797", "2", {}, {})
        print("cat page2", len(r.get("list") or []),
              "page", r.get("page"), "pagecount", r.get("pagecount"))
    except Exception as e:
        print("cat page2 ERR", e)
    try:
        d = sp.detailContent(["v:1261888829"])
        vod = (d.get("list") or [{}])[0]
        print("detail video", vod.get("vod_name", "")[:50])
        print("  play_from", vod.get("vod_play_from"))
        print("  play_url", (vod.get("vod_play_url") or "")[:160])
    except Exception as e:
        print("detail video ERR", e)
    try:
        d = sp.detailContent(["t:2210799145153817"])
        vod = (d.get("list") or [{}])[0]
        print("detail torrent", vod.get("vod_name", "")[:50])
        print("  play_from", vod.get("vod_play_from"))
        print("  play_url", (vod.get("vod_play_url") or "")[:200])
        # 115 线路应为干净磁力
        if "115离线" in (vod.get("vod_play_from") or ""):
            off = [p for p in (vod.get("vod_play_url") or "").split("#")
                   if OFF_PREFIX_115 in p]
            if off:
                mag_d, _, _ = _off_id_decode(
                    off[0].split("$")[-1][len(OFF_PREFIX_115):])
                print("  115 magnet clean?", "&tr=" not in mag_d)
    except Exception as e:
        print("detail torrent ERR", e)
    try:
        d = sp.detailContent(["v:1261888829"])
        pu = (d.get("list") or [{}])[0].get("vod_play_url") or ""
        if pu:
            ep = pu.split("#")[0].split("$")[-1]
            pc = sp.playerContent("在线", ep)
            print("player online", pc.get("url", "")[:100], "parse", pc.get("parse"))
            mag = "magnet:?xt=urn:btih:0031149b158074e0162bbaac05c88dfde236437a"
            pm = sp.playerContent("磁力", mag)
            print("player magnet trackers?", "&tr=" in (pm.get("url") or ""))
    except Exception as e:
        print("player ERR", e)
    # 115 解码链路（不真正提交） + 双关回退 + tracker + 分类筛选
    try:
        mag0 = "magnet:?xt=urn:btih:0031149b158074e0162bbaac05c88dfde236437a"
        b64 = _off_id_encode(mag0, "T", "L")
        dec = _off_id_decode(b64 + "?t=1")
        print("115 id roundtrip", dec[0].startswith("magnet:"), dec[1], dec[2])
        print("magnet_play_url trackers?", "&tr=" in _magnet_play_url(mag0))
        print("magnet_clean no tracker?", "&tr=" not in _magnet_clean(
            _magnet_play_url(mag0)))
        # _detail_magnet 的 115 id 应为干净磁力
        sp4 = Spider()
        sp4.init("")
        d4 = sp4.detailContent(["magnet:?xt=urn:btih:" + "0" * 40])
        v4 = d4["list"][0]
        pu4 = v4.get("vod_play_url") or ""
        if "115离线" in (v4.get("vod_play_from") or ""):
            off_ep = [p for p in pu4.split("#") if OFF_PREFIX_115 in p]
            if off_ep:
                raw = off_ep[0].split("$")[-1]
                mag_d, _, _ = _off_id_decode(raw[len(OFF_PREFIX_115):])
                print("detail_magnet 115 clean?", "&tr=" not in mag_d)
        sp3 = Spider()
        sp3.init("")
        sp3.enable_magnet = False
        sp3.enable_offline_115 = False
        d3 = sp3.detailContent(["t:2210799145153817"])
        v3 = d3["list"][0]
        print("dual-off fallback from", v3.get("vod_play_from"),
              "url?", bool(v3.get("vod_play_url")))
        # 分类筛选 pagecount
        rf = sp.categoryContent("39765797", "1", {"kind": "magnet"}, {})
        print("filter magnet on video cat", len(rf.get("list") or []),
              "pc", rf.get("pagecount"))
        rf2 = sp.categoryContent("39765797", "1", {"kind": "video"}, {})
        print("filter video on video cat", len(rf2.get("list") or []),
              "pc", rf2.get("pagecount"))
        hc = sp.homeContent()
        f_m = (hc.get("filters") or {}).get("39755828") or []
        vals = [x.get("v") for g in f_m for x in g.get("value", [])]
        print("magnet cat filter opts", vals)
        f_v = (hc.get("filters") or {}).get("39775797") or []
        vals2 = [x.get("v") for g in f_v for x in g.get("value", [])]
        print("video cat filter opts", vals2)
    except Exception as e:
        print("115/fallback/filter ERR", e)
    for key in ("探花", "麻豆"):
        try:
            r = sp.searchContent(key, False, "1")
            print("search", key, len(r.get("list") or []),
                  "pages", r.get("pagecount"),
                  (r.get("list") or [{}])[0].get("vod_name", "")[:40])
        except Exception as e:
            print("search", key, "ERR", type(e).__name__, str(e)[:80])
    try:
        r = sp.searchContent("探花", False, "2")
        print("search page2", len(r.get("list") or []), "pagecount", r.get("pagecount"))
    except Exception as e:
        print("search page2 ERR", e)
    # 空关键词 / 无效关键词：站点对无结果也可能302到默认列表，sid 仍应缓存（可翻页）
    try:
        r = sp.searchContent("", False, "1")
        print("empty keyword", len(r.get("list") or []), "pagecount", r.get("pagecount"))
        r = sp.searchContent("zzzznotexist999", False, "1")
        print("nonsense search", len(r.get("list") or []),
              "sid cached?", "zzzznotexist999" in sp._search_list_id)
    except Exception as e:
        print("empty search ERR", e)
    sp.destroy()
    print("DONE")
