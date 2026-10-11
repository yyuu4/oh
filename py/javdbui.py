VERSION = "1.1.0"
# -*- coding: utf-8 -*-
# javdbui.py —— JavDB Web UI (bbjavdb.emby.edu.kg) 爬虫 + 115 离线转存/直链播放
# 仿照 javbus-liangzai.py v1.2.14 重写；115 离线功能逐字节对齐，爬取层改用 JavDB JSON API。
import os
import re
import json
import time
import base64
import hashlib
import html as _html
import warnings
from urllib.parse import quote, urljoin, unquote

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
# (1) 网页代理：只管「爬虫抓网页」，图片和播放地址由 App 自己去取
PROXY = ""

# (2) 图片反代：图片显示不出来时再开（默认关闭）
IMG_PROXY = ""

# 站点 ext（TVBox 源里 ext 字段传 JSON）可覆盖上面两项及其它开关：
#   {
#     "proxy": "7890", "img": "https://...",
#     "host": "https://bbjavdb.emby.edu.kg", "noProbe": true,
#     "cookie115": "", "enableOffline115": true,
#     "offlineSavePath": "0", "offlineAppVer": "4.8.2",
#     "offlineProxy": "", "offlineDebug": 1
#   }

# JavDB Web UI 镜像（SPA，数据全走 JSON API）
HOST = "https://bbjavdb.emby.edu.kg"
API_BASE = "https://jdforrepam.com/api"

# API 签名常量（从前端 JS bundle 逆出）
JD_SALT = "lpw6vgqzsp"
JD_SECRET = ("71cf27bb3c0bcdf207b64abecddc970098c7421ee7203b9cdae54478478a199e7d5"
             "a6e1a57691123c1a931c057842fb73ba3b3c83bcd69c17ccf174081e3d8aa")

PAGE_SIZE = 30
SEARCH_LIMIT = 30

HTTP_RETRY = 1
HTTP_RETRY_DELAY = 0.5
HTTP_RETRY_STATUS = (429, 500, 502, 503, 504)

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

LIST_HEADERS = {
    "User-Agent": WEB_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
}

# ============ 115 离线 ============
DEFAULT_COOKIE_115 = ("UID=7090991_R1_1785487771; CID=3c1a3ab03cfc92b0b7c80db6efa950c6; "
                      "SEID=81ec0f1ad4aa99de925b609465a91c20d8894da910834a59f27cb239ebc5eb70412b456e8e91fff5654dc089a9d0c153f5fcec844b4cf7fa1b8aac84; "
                      "KID=bc573815d056010f1b8373db03247c3b")

OFF_PREFIX_115 = "http://115off/"
OFF_TRACE_FILE = os.path.join(os.path.expanduser("~"), "javbus_off_trace.txt")
OFF_PENDING_FILE = os.path.join(os.path.expanduser("~"), "javbus_off_pending.json")


def _trace_write(text):
    try:
        with open(OFF_TRACE_FILE, "w", encoding="utf-8") as f:
            f.write(_to_text(text))
    except Exception:
        pass


def _trace_read():
    try:
        with open(OFF_TRACE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _fc(item):
    v = item.get("fc") if isinstance(item, dict) else None
    return "" if v is None else str(v).strip()


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


def _play_err(msg):
    return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
            "msg": _to_text(msg)}


OFFLINE_UA = WEB_UA + " 115Browser/36.0.0"
OFFLINE_VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".ts", ".m4v",
                      ".wmv", ".rm", ".rmvb", ".iso", ".mpg", ".mpeg", ".3gp",
                      ".webm", ".m2ts", ".vob", ".mp2")
OFFLINE_ADD_API = "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls"
OFFLINE_LIST_API = "https://115.com/web/lixian/?ct=lixian&ac=task_lists"
OFFLINE_POLL_TIMEOUT = 15
OFFLINE_POLL_INTERVAL = 1
OFFLINE_FINISH_BUDGET = 9
OFFLINE_TEST_MP4 = ("https://commondatastorage.googleapis.com/gtv-videos-bucket/"
                    "sample/BigBuckBunny.mp4")
OFFLINE_TEST_HEADER = {
    "User-Agent": OFFLINE_UA,
    "Referer": "https://115.com/",
    "Accept": "*/*",
}

# ==================== 通用工具 ====================

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


_SIZE_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:TB|GB|MB|KB|B)(?![A-Za-z])", re.I)


def _extract_size_token(text):
    m = _SIZE_TOKEN_RE.search(_to_text(text) or "")
    return m.group(0).lower() if m else ""


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


def _sanitize_play(v):
    if not v:
        return v
    return (_to_text(v)
            .replace("#", "%23")
            .replace("$", "%24")
            .replace("\r", " ")
            .replace("\n", " "))


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


def _format_size_mb(mb):
    """JavDB 的 size 字段是 MB 整数 → 人类可读"""
    try:
        mb = float(mb)
    except Exception:
        return ""
    if mb >= 1024:
        return "%.2fGB" % (mb / 1024.0)
    if mb >= 1:
        return "%.0fMB" % mb
    return ""


# ==================== JavDB API 签名 ====================

def _jd_signature():
    """jdsignature 头 = ${unix_ts}.${SALT}.${md5(unix_ts+SECRET)}"""
    n = str(int(time.time()))
    digest = hashlib.md5((n + JD_SECRET).encode("utf-8")).hexdigest()
    return "%s.%s.%s" % (n, JD_SALT, digest)


# ==================== 115 加密工具 ====================

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
    return "; ".join(str(v).split(";")[0].strip() for v in set_cookie if str(v).split(";")[0].strip())


# ==================== Spider ====================

class Spider:
    def __init__(self):
        self.s = None          # JavDB API 会话
        self.s115 = None       # 115 接口会话
        self.api = API_BASE
        self.host = HOST
        self.ua = WEB_UA
        self.timeout = 15
        self.page_size = PAGE_SIZE
        self.search_limit = SEARCH_LIMIT
        self.enable_magnet = True
        self.enable_uncensored = True
        self.cookie = ""
        self.img_proxy = IMG_PROXY
        self.proxy = PROXY
        self.lang = "zh"
        self.verify = False

        # 115 离线
        self.cookie_115 = DEFAULT_COOKIE_115
        self.enable_offline_115 = True
        self.offline_save_path = "0"
        self.offline_app_ver = "4.8.2"
        self.offline_timeout = 10
        self.offline_proxy = ""
        self.offline_debug = True
        self.offline_test_mp4 = ""
        self.offline_local_proxy_cfg = ""
        self._off_pp_base = None
        self._off_cache = {}
        self._off_name = {}
        self._off_syn = {}
        self._off_verified = {}
        self._off_pending_trash = []
        try:
            with open(OFF_PENDING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._off_pending_trash = [_to_text(x) for x in data
                                           if _to_text(x)][:50]
        except Exception:
            pass
        self._vid_title = {}
        self._cache_filters = {}
        self._host_locked = False
        self._probed = False
        self._off_last = ""

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

        if extend.get("host"):
            self.host = str(extend["host"]).rstrip("/")
            self._host_locked = True
        if extend.get("api"):
            self.api = str(extend["api"]).rstrip("/")
        if extend.get("noProbe"):
            self._host_locked = True
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

        if "proxy" in extend:
            self.set_proxy(extend.get("proxy"))
        elif "proxyPort" in extend or "proxy_port" in extend:
            self.set_proxy(extend.get("proxyPort") or extend.get("proxy_port"))
        self._apply_proxy()

        # 115 cookie（Atvp 内不认 ext.cookie115）
        if self._in_atvp():
            self.cookie_115 = (
                _env("Y115_COOKIE")
                or _env("MY115_COOKIE")
                or DEFAULT_COOKIE_115
                or _to_text(extend.get("cookie115"))
            )
        else:
            self.cookie_115 = (
                _to_text(extend.get("cookie115"))
                or _env("Y115_COOKIE")
                or _env("MY115_COOKIE")
                or DEFAULT_COOKIE_115
            )
        if "enableOffline115" in extend:
            self.enable_offline_115 = bool(extend["enableOffline115"])
        if extend.get("offlineSavePath"):
            self.offline_save_path = str(extend["offlineSavePath"])
        if extend.get("offlineAppVer"):
            self.offline_app_ver = str(extend["offlineAppVer"])
        if "offlineProxy" in extend:
            self.offline_proxy = _to_text(extend.get("offlineProxy"))
        if self.s115 is not None:
            try:
                self.s115.close()
            except Exception:
                pass
        self.s115 = None
        self._off_last = ""
        if "offlineDebug" in extend:
            self.offline_debug = str(extend.get("offlineDebug")).lower() not in (
                "0", "false", "off", "no")
        self.offline_test_mp4 = _to_text(extend.get("offlineTestMp4")).strip().lower()
        self.offline_local_proxy_cfg = extend.get("local_proxy_config") or ""
        self._off_pp_base = None
        self._off_verified = {}

        self._cache_filters = {}
        try:
            self._reap_pending_trash()
        except Exception:
            pass

    def set_proxy(self, value):
        p = _norm_proxy(value)
        if p != self.proxy:
            self.proxy = p
            self._probed = False
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

    # ---------- JavDB API ----------
    def _api_get(self, path, params=None, timeout=None):
        """GET API_BASE + path → data dict（失败返回 {}）"""
        if not requests:
            return {}
        url = self.api + path
        headers = {
            "Accept": "application/json",
            "jdsignature": _jd_signature(),
            "Referer": self.host + "/",
        }
        t = timeout or self.timeout
        for attempt in range(HTTP_RETRY + 1):
            try:
                r = self.s.get(url, params=params or {}, headers=headers,
                               timeout=t, verify=False)
                if r.status_code in HTTP_RETRY_STATUS and attempt < HTTP_RETRY:
                    time.sleep(HTTP_RETRY_DELAY)
                    continue
                data = r.json()
                if isinstance(data, dict) and data.get("success"):
                    return data.get("data") or {}
                return {}
            except Exception:
                if attempt < HTTP_RETRY:
                    time.sleep(HTTP_RETRY_DELAY)
                    continue
                return {}
        return {}

    def _api_get_raw(self, path, params=None, timeout=None):
        """同 _api_get 但返回完整响应 dict（含 success/message）"""
        if not requests:
            return {}
        url = self.api + path
        headers = {
            "Accept": "application/json",
            "jdsignature": _jd_signature(),
            "Referer": self.host + "/",
        }
        t = timeout or self.timeout
        try:
            r = self.s.get(url, params=params or {}, headers=headers,
                           timeout=t, verify=False)
            data = r.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # ---------- movie 对象 → vod item ----------
    def _movie_item(self, m):
        if not isinstance(m, dict):
            return None
        mid = _to_text(m.get("id") or "")
        if not mid:
            return None
        title = _to_text(m.get("title") or m.get("number") or "")
        number = _to_text(m.get("number") or "")
        pic = self._proxy_pic(_to_text(m.get("cover_url") or m.get("thumb_url") or ""))
        magnets = _safe_int(m.get("magnets_count"), 0)
        score = _to_text(m.get("score") or "")
        date = _to_text(m.get("release_date") or "")
        remark_parts = []
        if number:
            remark_parts.append(number)
        if date:
            remark_parts.append(date[:10])
        if magnets:
            remark_parts.append("磁力%d" % magnets)
        if score:
            remark_parts.append("★%s" % score)
        return {
            "vod_id": mid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": " ".join(remark_parts),
            "type_name": number,
        }

    def _movies_to_list(self, movies):
        out = []
        seen = set()
        for m in movies or []:
            item = self._movie_item(m)
            if item and item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                out.append(item)
        return out

    def _proxy_pic(self, url):
        if not url:
            return ""
        url = _to_text(url)
        p = _to_text(self.img_proxy)
        if not p:
            return url
        if "{url}" in p:
            return p.replace("{url}", quote(url, safe=""))
        return p + quote(url, safe="")

    # ---------- 类别（对齐网页端导航） ----------
    @staticmethod
    def _classes():
        return [
            {"type_id": "hot",         "type_name": "热播"},
            {"type_id": "all",         "type_name": "全部"},
            {"type_id": "censored",    "type_name": "有码"},
            {"type_id": "uncensored",  "type_name": "无码"},
            {"type_id": "western",     "type_name": "欧美"},
            {"type_id": "fc2",         "type_name": "FC2"},
            {"type_id": "rankings",    "type_name": "排行榜"},
            {"type_id": "actors",      "type_name": "演员"},
            {"type_id": "series",      "type_name": "系列"},
            {"type_id": "makers",      "type_name": "片商"},
        ]

    def homeContent(self, filter=None):
        classes = []
        for c in self._classes():
            if c["type_id"] == "uncensored" and not self.enable_uncensored:
                continue
            classes.append(dict(c))
        # 筛选对齐网页端：可用性 + 排序
        availability = [
            {"key": "main", "name": "可用性", "init": "",
             "value": [
                 {"n": "全部", "v": ""},
                 {"n": "可播放", "v": "p"},
                 {"n": "含磁链", "v": "m"},
                 {"n": "含字幕", "v": "c"},
             ]},
        ]
        sort_opts = [
            {"key": "sort", "name": "排序", "init": "released",
             "value": [
                 {"n": "发布日期", "v": "released"},
                 {"n": "磁链更新", "v": "magnet-updated"},
             ]},
        ]
        rank_opts = [
            {"key": "period", "name": "周期", "init": "daily",
             "value": [
                 {"n": "每日", "v": "daily"},
                 {"n": "每周", "v": "weekly"},
                 {"n": "每月", "v": "monthly"},
             ]},
        ]
        actor_opts = [
            {"key": "amode", "name": "模式", "init": "recommend",
             "value": [
                 {"n": "推荐", "v": "recommend"},
                 {"n": "有码", "v": "censored"},
                 {"n": "无码", "v": "uncensored"},
             ]},
        ]
        series_opts = [
            {"key": "stype", "name": "类型", "init": "censored",
             "value": [
                 {"n": "有码", "v": "censored"},
                 {"n": "无码", "v": "uncensored"},
                 {"n": "全部", "v": "all"},
             ]},
        ]
        filters = {}
        for tid in ("all", "censored", "uncensored", "western", "fc2"):
            filters[tid] = list(availability) + list(sort_opts)
        filters["hot"] = list(availability)
        filters["rankings"] = list(rank_opts)
        filters["actors"] = list(actor_opts)
        filters["series"] = list(series_opts)
        filters["makers"] = list(series_opts)
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        data = self._api_get("/v1/movies/recommend")
        return {"list": self._movies_to_list(data.get("movies"))}

    # ---------- 分类内容（对齐网页端） ----------
    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        t = _to_text(tid)
        page = _safe_int(pg, 1)
        fs = {}
        for src in (filter, extend):
            if isinstance(src, dict):
                fs.update(src)
        main = _to_text(fs.get("main") or "")

        # ---- 排行榜 ----
        if t == "rankings":
            period = _to_text(fs.get("period") or "daily")
            # 网页端排行榜有 6 种模式，TVBox 里用热播(playback) 作为默认
            data = self._api_get("/v1/rankings",
                                 {"type": "playback", "period": period})
            lst = self._movies_to_list(data.get("movies") or [])
            return {"list": lst, "page": 1, "pagecount": 1,
                    "limit": len(lst), "total": len(lst)}

        # ---- 演员 ----
        if t == "actors":
            amode = _to_text(fs.get("amode") or "recommend")
            data = self._api_get("/v1/actors", {"type": amode, "page": page})
            out = []
            for a in data.get("actors") or []:
                aid = _to_text(a.get("id") or "")
                if not aid:
                    continue
                out.append({
                    "vod_id": "actor_" + aid,
                    "vod_name": _to_text(a.get("name") or ""),
                    "vod_pic": self._proxy_pic(_to_text(a.get("avatar_url") or "")),
                    "vod_remarks": "作品%d" % _safe_int(a.get("videos_count"), 0),
                })
            return {"list": out, "page": page, "pagecount": page + 1,
                    "limit": len(out), "total": 0}

        # ---- 系列 ----
        if t == "series":
            stype = _to_text(fs.get("stype") or "censored")
            data = self._api_get("/v1/series", {"type": stype, "page": page})
            out = []
            for sr in (data.get("series") or data.get("list") or []):
                sid = _to_text(sr.get("id") or "")
                if not sid:
                    continue
                out.append({
                    "vod_id": "series_" + sid,
                    "vod_name": _to_text(sr.get("name") or ""),
                    "vod_pic": "",
                    "vod_remarks": "作品%d" % _safe_int(sr.get("videos_count"), 0),
                })
            return {"list": out, "page": page, "pagecount": page + 1,
                    "limit": len(out), "total": 0}

        # ---- 片商（API 当前 500，留接口） ----
        if t == "makers":
            stype = _to_text(fs.get("stype") or "censored")
            data = self._api_get("/v1/makers", {"type": stype, "page": page})
            out = []
            for mk in (data.get("makers") or data.get("list") or []):
                mid = _to_text(mk.get("id") or "")
                if not mid:
                    continue
                out.append({
                    "vod_id": "maker_" + mid,
                    "vod_name": _to_text(mk.get("name") or ""),
                    "vod_pic": "",
                    "vod_remarks": "作品%d" % _safe_int(mk.get("videos_count"), 0),
                })
            return {"list": out, "page": page, "pagecount": page + 1,
                    "limit": len(out), "total": 0}

        # ---- 热播（推荐） ----
        if t == "hot":
            data = self._api_get("/v1/movies/recommend")
            lst = self._movies_to_list(data.get("movies") or [])
            return {"list": lst, "page": 1, "pagecount": 1,
                    "limit": len(lst), "total": len(lst)}

        # ---- 全部/有码/无码/欧美/FC2 ----
        fb = t if t in ("all", "censored", "uncensored", "western", "fc2") else "all"
        sort = _to_text(fs.get("sort") or "released")
        params = {"page": page, "filter_by": fb}
        if main:
            params["main"] = main
        if sort == "magnet-updated":
            # 磁链更新排序走 /v1/movies/tags
            tag_params = {"filter_by": fb, "sort_by": "magnets",
                          "order_by": "desc", "page": page, "limit": 30}
            if main:
                tag_params["filter_by_tags"] = main
            data = self._api_get("/v1/movies/tags", tag_params)
        else:
            data = self._api_get("/v1/movies/latest", params)
        lst = self._movies_to_list(data.get("movies"))
        return {"list": lst, "page": page, "pagecount": page + 1,
                "limit": len(lst), "total": 0}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        if not vid:
            return {"list": []}

        # 女優入口：actor_xxx → 列她的作品
        if vid.startswith("actor_"):
            return self._actor_detail(vid[len("actor_"):])
        if vid.startswith("maker_"):
            return self._entity_movies_detail("maker", vid[len("maker_"):])
        if vid.startswith("series_"):
            return self._entity_movies_detail("series", vid[len("series_"):])

        data = self._api_get("/v2/movies/" + quote(vid, safe=""))
        movie = data.get("movie") if isinstance(data, dict) else None
        if not isinstance(movie, dict):
            return {"list": []}

        title = _to_text(movie.get("title") or movie.get("number") or "")
        number = _to_text(movie.get("number") or "")
        pic = self._proxy_pic(_to_text(movie.get("cover_url") or movie.get("thumb_url") or ""))
        date = _to_text(movie.get("release_date") or "")
        score = _to_text(movie.get("score") or "")
        dur = _safe_int(movie.get("duration"), 0)
        maker = _to_text(movie.get("maker_name") or "")
        director = _to_text(movie.get("director_name") or "")
        series = _to_text(movie.get("series_name") or "")
        tags = [t.get("name") for t in (movie.get("tags") or []) if isinstance(t, dict)]
        actors = [a.get("name") for a in (movie.get("actors") or []) if isinstance(a, dict)]
        magnets = movie.get("magnets") or []

        info_lines = []
        if number:
            info_lines.append("番号: %s" % number)
        if date:
            info_lines.append("发行: %s" % date)
        if dur:
            info_lines.append("时长: %d分钟" % dur)
        if score:
            info_lines.append("评分: %s" % score)
        if maker:
            info_lines.append("片商: %s" % maker)
        if director:
            info_lines.append("导演: %s" % director)
        if series:
            info_lines.append("系列: %s" % series)
        if actors:
            info_lines.append("演员: %s" % "、".join(actors))
        if tags:
            info_lines.append("类别: %s" % "、".join(tags))
        if self.enable_offline_115:
            info_lines.append("115离线：提交到115云端，完成后自动直连播放 (v%s)" % VERSION)

        # 组装播放源
        play_from = []
        play_url = []

        # 115离线源
        if self.enable_offline_115 and magnets:
            eps = []
            for i, g in enumerate(magnets):
                h = _to_text(g.get("hash") or "")
                if not h:
                    continue
                mag = "magnet:?xt=urn:btih:" + h
                size_mb = g.get("size")
                size_str = _format_size_mb(size_mb)
                hd = bool(g.get("hd"))
                cnsub = bool(g.get("cnsub"))
                label_parts = []
                if hd:
                    label_parts.append("高清")
                if cnsub:
                    label_parts.append("字幕")
                if size_str:
                    label_parts.append(size_str)
                label = " ".join(label_parts) or ("磁力%d" % (i + 1))
                b64 = _off_id_encode(mag, title, label)
                eps.append("%s$%s%s?t=%d" % (
                    _sanitize_play(label), OFF_PREFIX_115, b64, int(time.time())))
            if eps:
                play_from.append("115离线")
                play_url.append("#".join(eps))

        # 磁力源（直链，交给 App 的磁力播放器）
        if self.enable_magnet and magnets:
            eps = []
            for i, g in enumerate(magnets):
                h = _to_text(g.get("hash") or "")
                if not h:
                    continue
                mag = "magnet:?xt=urn:btih:" + h
                size_mb = g.get("size")
                size_str = _format_size_mb(size_mb)
                hd = bool(g.get("hd"))
                cnsub = bool(g.get("cnsub"))
                label_parts = []
                if hd:
                    label_parts.append("高清")
                if cnsub:
                    label_parts.append("字幕")
                if size_str:
                    label_parts.append(size_str)
                label = " ".join(label_parts) or ("磁力%d" % (i + 1))
                eps.append("%s$%s" % (_sanitize_play(label), _sanitize_play(mag)))
            if eps:
                play_from.append("磁力")
                play_url.append("#".join(eps))

        # 预览片（m3u8）
        pv = _to_text(movie.get("preview_video_url") or "")
        if pv:
            play_from.append("預覽")
            play_url.append("預覽$%s" % _sanitize_play(pv))

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": "<br>".join(info_lines),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "#".join(play_url) if play_url else "",
        }
        return {"list": [vod]}

    def _actor_detail(self, aid):
        """女優详情：列她的作品"""
        data = self._api_get("/v1/actors/" + quote(aid, safe=""))
        actor = data.get("actor") if isinstance(data, dict) else None
        name = _to_text(actor.get("name") if isinstance(actor, dict) else "") or aid
        pic = self._proxy_pic(_to_text(actor.get("avatar_url") if isinstance(actor, dict) else ""))
        # 作品列表：/v1/movies/latest?actor_id=X&page=N
        movies_data = self._api_get("/v1/movies/latest", {
            "page": 1, "filter_by": "all", "actor_id": aid,
        })
        movies = movies_data.get("movies") or []
        eps = []
        for m in movies:
            mid = _to_text(m.get("id") or "")
            num = _to_text(m.get("number") or "")
            t = _to_text(m.get("title") or num)
            if not mid:
                continue
            eps.append("%s$%s" % (_sanitize_play(num or t[:30]), mid))
        vod = {
            "vod_id": "actor_" + aid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": "演员作品列表",
            "vod_play_from": "作品",
            "vod_play_url": "#".join(eps) if eps else "",
        }
        return {"list": [vod]}

    def _entity_movies_detail(self, kind, eid):
        """片商/系列详情：列作品"""
        path = "/v1/makers/" if kind == "maker" else "/v1/series/"
        data = self._api_get(path + quote(eid, safe=""))
        ent = data.get(kind) if isinstance(data, dict) else None
        name = _to_text(ent.get("name") if isinstance(ent, dict) else "") or eid
        movies_data = self._api_get("/v1/movies/latest", {
            "page": 1, "filter_by": "all", kind + "_id": eid,
        })
        movies = movies_data.get("movies") or []
        eps = []
        for m in movies:
            mid = _to_text(m.get("id") or "")
            num = _to_text(m.get("number") or "")
            if not mid:
                continue
            eps.append("%s$%s" % (_sanitize_play(num or mid), mid))
        vod = {
            "vod_id": kind + "_" + eid,
            "vod_name": name,
            "vod_pic": "",
            "vod_content": "%s作品列表" % ("片商" if kind == "maker" else "系列"),
            "vod_play_from": "作品",
            "vod_play_url": "#".join(eps) if eps else "",
        }
        return {"list": [vod]}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg="1"):
        page = _safe_int(pg, 1)
        keyword = _to_text(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.search_limit, "total": 0}
        data = self._api_get("/v2/search", {
            "q": keyword, "page": page, "type": "movie", "limit": self.search_limit,
        })
        lst = self._movies_to_list(data.get("movies"))
        return {"list": lst, "page": page, "pagecount": page + 1,
                "limit": len(lst), "total": 0}

    # ==================== 115 离线 ====================

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

    def _release_play_memory(self):
        if self.s115 is not None:
            try:
                self.s115.close()
            except Exception:
                pass
            self.s115 = None
        try:
            self._off_cache.clear()
            self._off_name.clear()
            self._off_syn.clear()
            self._off_verified.clear()
        except Exception:
            pass
        try:
            import gc
            gc.collect()
        except Exception:
            pass

    def _offline_headers(self):
        return {
            "Cookie": self.cookie_115,
            "User-Agent": OFFLINE_UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
        }

    @staticmethod
    def _magnet_hash(magnet):
        m = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet or "")
        return m.group(1).lower() if m else ""

    @staticmethod
    def _magnet_dn(magnet):
        m = re.search(r"[?&]dn=([^&]+)", magnet or "")
        if not m:
            return ""
        try:
            return unquote(m.group(1)).replace("+", " ").strip()
        except Exception:
            return ""

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
                      timeout=self.offline_timeout, verify=False)
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
                      timeout=self.offline_timeout, verify=False)
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

    @staticmethod
    def _guess_keyword_from_name(name):
        if not name:
            return ""
        name = _to_text(name).strip()
        if "@" in name:
            name = name.rsplit("@", 1)[-1].strip() or name
        name = re.sub(r"^[A-Za-z0-9-]{2,20}\.[A-Za-z]{2,10}[\s_]+", "",
                      name) or name
        base = os.path.splitext(name)[0]
        ext = os.path.splitext(name)[1].lower()
        if ext and ext in OFFLINE_VIDEO_EXTS:
            return (base.replace("_", " ").strip() or name)[:60]
        base = base.replace("_", " ").replace(".", " ").strip()
        m = re.search(r"(FC2)[- ]?(PPV)?[- ]?(\d{5,8})", base, re.I)
        if m:
            return "FC2-PPV-%s" % m.group(3)
        m = re.search(r"([A-Za-z]{2,10})[-_ ](\d{2,5})\b", base)
        if m:
            return "%s-%s" % (m.group(1).upper(), m.group(2))
        m = re.search(r"([A-Za-z]{2,6})(\d{2,5})\b", base)
        if m:
            return "%s-%s" % (m.group(1).upper(), m.group(2))
        return base[:40]

    def _find_pickcode_by_name(self, name, retries=3, interval=1, exact=""):
        keyword = self._guess_keyword_from_name(name)
        if not keyword:
            return ""
        exact = _to_text(exact)
        for _ in range(max(1, retries)):
            fallback = ""
            for stype in (4, 0):
                for it in self._search_rows(keyword, stype):
                    if int(it.get("fc") or 0) != 1:
                        continue
                    pc = it.get("pc") or it.get("pick_code") or it.get("pickcode")
                    if not pc:
                        continue
                    if exact and _to_text(it.get("n") or it.get("name")) == exact:
                        return pc
                    if not fallback:
                        fallback = pc
            if fallback:
                return fallback
            if interval:
                time.sleep(interval)
        return ""

    def _resolve_pickcode(self, pickcode):
        if not self.cookie_115:
            return _play_err("未配置115 Cookie（文件 DEFAULT_COOKIE_115 / ext.cookie115 / Y115_COOKIE）")
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
            r = sess.post(url, data=body, headers=headers, timeout=12, verify=False)
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
            r.headers.get("Set-Cookie") if hasattr(r.headers, "get") else None
        )
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
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": real_url,
            "header": {
                "User-Agent": OFFLINE_UA,
                "Cookie": final_cookie,
                "Referer": "https://115.com/",
            },
        }
        if fmt:
            result["format"] = fmt
        result["type"] = self._offline_no_proxy_type()
        return result

    @staticmethod
    def _offline_note(prefix, name=""):
        name = _to_text(name).strip()
        return "%s：%s" % (prefix, name) if name else prefix

    def _set_off_last(self, text):
        self._off_last = _to_text(text)
        _trace_write(self._off_last)

    def _off_cache_put(self, info_hash, pc, name=""):
        self._off_cache[info_hash] = pc
        if name:
            self._off_name[info_hash] = name
        while len(self._off_cache) > 64:
            old = next(iter(self._off_cache))
            self._off_cache.pop(old, None)
            self._off_name.pop(old, None)
            self._off_syn.pop(old, None)

    def _off_trace(self, phase, t0):
        el = time.time() - t0
        text = "115离线：%s（%.0fs）" % (_to_text(phase), el)
        self._set_off_last(text)
        if not self.offline_debug:
            return
        try:
            try:
                from com.github.catvod.utils import Notify
            except Exception:
                from com.github.catvod import Notify
            Notify.show(text)
        except Exception:
            pass

    @staticmethod
    def _offline_proxy_base():
        try:
            from com.github.catvod import Proxy
            port = int(Proxy.getPort() or 0)
        except Exception:
            port = 0
        return "http://127.0.0.1:%d/proxy?" % port if port > 0 else "proxy://"

    @staticmethod
    def _offline_alt_types():
        return ("THUNDER", "PAN123", "PAN139", "BAIDU", "GUANGYA",
                "UC", "QUARK", "ALI", "PAN115", "CLOUD189")

    def _offline_no_proxy_type(self):
        enabled = set()
        cfg = getattr(self, "offline_local_proxy_cfg", "") or ""
        try:
            if isinstance(cfg, str):
                c = cfg.strip()
                cfg = json.loads(c) if c.startswith("{") else {}
            if isinstance(cfg, dict):
                for k, v in cfg.items():
                    on = False
                    if isinstance(v, dict):
                        e = v.get("enabled")
                        if e is True or (isinstance(e, str) and e.strip().lower() == "true"):
                            try:
                                on = int(v.get("concurrency") or 0) > 0 \
                                     and int(v.get("chunk_size") or 0) > 0
                            except Exception:
                                on = False
                    if on:
                        enabled.add(_to_text(k).upper())
        except Exception:
            pass
        for t in self._offline_alt_types():
            if t not in enabled:
                return t
        return "__off115__"

    @staticmethod
    def _offline_srt(text):
        text = _to_text(text).strip() or "115离线完成"
        return "1\n00:00:00,000 --> 00:00:08,000\n%s\n\n" % text

    def _offline_hint(self, res, note, info_hash=""):
        syn = _to_text(self._off_syn.get(info_hash, "")) if info_hash else ""
        res["desc"] = (note + "\n\n" + syn) if syn else note
        try:
            key = _to_text(getattr(self, "siteKey", ""))
            q = "do=py" + ("&siteKey=%s" % quote(key) if key else "")
            url = self._offline_proxy_base() + q + "&k=offnote&v=%s" % quote(note)
            res["subs"] = [{"name": "115离线", "url": url, "lang": "zh",
                            "format": "application/x-subrip", "flag": 0}]
        except Exception:
            pass
        return res

    # ---------- 115 网盘整理 ----------

    def _offline_webapi(self, path, params=None, data=None, timeout=8):
        sess = self._offline_session()
        if sess is None:
            return {}
        url = "https://webapi.115.com" + path
        headers = {
            "Cookie": self.cookie_115,
            "User-Agent": WEB_UA,
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
            "Accept": "application/json, text/plain, */*",
        }
        try:
            if data is not None:
                headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
                r = sess.post(url, data=data, headers=headers, timeout=timeout,
                              verify=False)
            else:
                r = sess.get(url, params=params or {}, headers=headers,
                             timeout=timeout, verify=False)
        except Exception:
            return {}
        out = _safe_json(r.text, {})
        return out if isinstance(out, dict) else {}

    def _offline_info(self, pickcode):
        if not pickcode:
            return {}
        data = self._offline_webapi("/files/get_info",
                                    params={"pick_code": pickcode, "format": "json"})
        row = data.get("data")
        if isinstance(row, list):
            row = row[0] if row else {}
        return row if isinstance(row, dict) else {}

    def _offline_dir(self, cid, limit=1000, deadline=0):
        rows, offset, step = [], 0, 200
        while offset < limit:
            if deadline and time.time() >= deadline:
                break
            data = self._offline_webapi("/files", params={
                "aid": 1, "cid": _to_text(cid or "0"), "offset": offset,
                "limit": step, "show_dir": 1, "format": "json"})
            chunk = data.get("data")
            if not isinstance(chunk, list) or not chunk:
                break
            rows.extend(chunk)
            total = _safe_int(data.get("count"), 0)
            offset += len(chunk)
            if total and offset >= total:
                break
            if len(chunk) < step:
                break
        return rows

    @staticmethod
    def _is_video_name(name):
        n = _to_text(name).lower()
        return any(n.endswith(ext) for ext in OFFLINE_VIDEO_EXTS)

    @classmethod
    def _pick_video(cls, rows):
        videos = [r for r in rows if _fc(r) == "1"
                  and cls._is_video_name(r.get("n") or r.get("name") or "")]
        return max(videos, key=lambda r: _safe_int(r.get("s") or r.get("size") or 0, 0),
                   default=None)

    def _offline_find_video(self, cid, depth=1, deadline=0):
        if not cid or (deadline and time.time() >= deadline):
            return None, ""
        rows = self._offline_dir(cid, deadline=deadline)
        best = self._pick_video(rows)
        if best:
            return best, _to_text(cid)
        if depth > 0:
            subs = [r for r in rows if _fc(r) == "0"]
            for sub in subs[:5]:
                found, src = self._offline_find_video(
                    sub.get("cid") or sub.get("fid"), depth - 1, deadline=deadline)
                if found:
                    return found, src
        return None, ""

    @staticmethod
    def _safe_name(name):
        n = re.sub(r"\s+", " ", _to_text(name))
        n = re.sub(r'[\\/:*?"<>|\r\n\t]', "", n)
        return n.strip()[:120].strip(" .")

    @classmethod
    def _offline_new_name(cls, title, orig, label=""):
        title = cls._safe_name(title)
        orig = cls._safe_name(orig)
        label = cls._safe_name(label)
        if not title:
            return orig
        if label:
            ext = os.path.splitext(orig)[1]
            tail = label if (not ext or label.lower().endswith(ext.lower())) \
                else label + ext
            if tail == title:
                return orig
            name = "%s_%s" % (title, tail)
            if len(name) > 140:
                room = max(8, 140 - len(tail) - 1)
                name = "%s_%s" % (title[:room], tail)
            return orig if name == orig else name
        if orig == title or orig.startswith(title + "_"):
            return orig
        return "%s_%s" % (title, orig)

    def _offline_rename(self, fid, new_name):
        if not fid or not new_name:
            return False
        data = self._offline_webapi("/files/edit",
                                    data={"fid": fid, "file_name": new_name})
        return bool(data.get("state"))

    def _offline_move(self, pid, fid):
        if not fid:
            return False
        data = self._offline_webapi("/files/move", data={"pid": pid, "fid[0]": fid})
        return bool(data.get("state"))

    def _offline_trash(self, fid):
        if not fid:
            return False
        for i in range(2):
            data = self._offline_webapi("/rb/delete", data={"fid[0]": fid},
                                        timeout=4)
            if data.get("state"):
                return True
            if i == 0:
                time.sleep(0.3)
        return False

    def _pending_trash_save(self):
        try:
            with open(OFF_PENDING_FILE, "w", encoding="utf-8") as f:
                json.dump(self._off_pending_trash[:50], f)
        except Exception:
            pass

    def _pending_trash_add(self, fcid):
        fcid = _to_text(fcid)
        if not fcid or fcid in self._off_pending_trash:
            return
        self._off_pending_trash.append(fcid)
        self._off_pending_trash = self._off_pending_trash[:50]
        self._pending_trash_save()

    def _reap_pending_trash(self):
        if not self._off_pending_trash:
            return
        remaining = list(self._off_pending_trash)
        changed = False
        while remaining:
            fcid = remaining[0]
            ok = False
            try:
                ok = self._offline_trash(fcid)
            except Exception:
                ok = False
            if ok:
                remaining.pop(0)
                changed = True
            else:
                break
        if changed:
            self._off_pending_trash = remaining
            self._pending_trash_save()

    def _offline_parent(self, info, deadline=0):
        pid = _to_text(info.get("pid") or "")
        if pid:
            return pid
        cid = _to_text(info.get("cid") or "")
        if not cid:
            return ""
        for it in self._offline_dir("0", limit=500, deadline=deadline):
            if _to_text(it.get("cid") or it.get("fid") or "") == cid:
                return "0"
        return ""

    def _tidy_file(self, info, name, title="", label="", deadline=0):
        pc = info.get("pc") or info.get("pick_code") or ""
        fid = _to_text(info.get("fid") or "")
        orig = _to_text(info.get("n") or info.get("name") or name)
        new = self._offline_new_name(title, orig, label)
        if new and new != orig and self._offline_rename(fid, new):
            orig = new
        try:
            self._pull_out_of_task_folder(info, name, title, deadline=deadline)
        except Exception:
            pass
        return pc, orig or _to_text(name)

    def _search_rows(self, keyword, stype=0, limit=50):
        sess = self._offline_session()
        if sess is None or not keyword:
            return []
        headers = {
            "User-Agent": WEB_UA,
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
            "Accept": "application/json, text/plain, */*",
            "Cookie": self.cookie_115,
        }
        try:
            r = sess.get("https://webapi.115.com/files/search", params={
                "search_value": keyword, "type": stype, "offset": 0,
                "limit": limit, "aid": 1, "cid": 0, "format": "json",
            }, headers=headers, timeout=10, verify=False)
            chunk = _safe_json(r.text, {}).get("data")
            return chunk if isinstance(chunk, list) else []
        except Exception:
            return []

    def _dir_row(self, fcid, code="", deadline=0):
        fcid = _to_text(fcid)
        if not fcid:
            return None, ""
        if code:
            for it in self._search_rows(code, 0):
                if _fc(it) == "0" and _to_text(it.get("cid") or "") == fcid:
                    return it, _to_text(it.get("pid") or "") or "0"
        for r in self._offline_dir("0", limit=200, deadline=deadline):
            if _fc(r) != "0":
                continue
            if _to_text(r.get("cid") or "") == fcid:
                return r, "0"
            for c in self._offline_dir(_to_text(r.get("cid") or ""),
                                       limit=200, deadline=deadline):
                if _fc(c) == "0" and _to_text(c.get("cid") or "") == fcid:
                    return c, _to_text(r.get("cid") or "") or "0"
        return None, ""

    def _pull_out_of_task_folder(self, info, name, title="", deadline=0):
        if deadline and time.time() >= deadline:
            return
        fid = _to_text(info.get("fid") or "")
        fcid = _to_text(info.get("cid") or "")
        if not fid or not fcid:
            return
        code = self._guess_keyword_from_name(_to_text(title) or _to_text(name))
        want = _to_text(name).strip()
        folder, parent = self._dir_row(fcid, code, deadline=deadline)
        if folder is None:
            return
        fname = _to_text(folder.get("n") or "")
        if not ((want and fname == want)
                or (code and code.lower() in fname.lower())):
            return
        kids = self._offline_dir(fcid, limit=200, deadline=deadline)
        if not any(_to_text(k.get("fid") or "") == fid for k in kids):
            return
        if self._offline_move(parent or "0", fid):
            cur = ""
            try:
                cur = _to_text((self._offline_info(
                    _to_text(info.get("pc") or info.get("pick_code") or ""))
                    or {}).get("cid") or "")
            except Exception:
                cur = ""
            if cur and cur != fcid:
                if not self._offline_trash(fcid):
                    self._pending_trash_add(fcid)
            elif not cur:
                self._pending_trash_add(fcid)

    def _tidy_folder(self, info, name, title, label="", deadline=0):
        cid = _to_text(info.get("cid") or info.get("fid") or "")
        if deadline and time.time() >= deadline:
            return "", _to_text(name)
        video, _src = self._offline_find_video(cid, deadline=deadline) if cid else (None, "")
        if not video:
            return "", _to_text(name)
        fid = _to_text(video.get("fid") or "")
        vpc = _to_text(video.get("pc") or video.get("pick_code") or "")
        orig = _to_text(video.get("n") or video.get("name") or "")
        new = self._offline_new_name(title, orig, label)
        if new and new != orig and self._offline_rename(fid, new):
            orig = new
        pid = "" if (deadline and time.time() >= deadline) \
            else self._offline_parent(info, deadline)
        if pid and fid and self._offline_move(pid, fid):
            cur = ""
            if vpc:
                try:
                    cur = _to_text((self._offline_info(vpc) or {}).get("cid") or "")
                except Exception:
                    cur = ""
            if cur and cur != cid:
                if not self._offline_trash(cid):
                    self._pending_trash_add(cid)
            elif cur and cur == cid:
                time.sleep(0.3)
                cur2 = ""
                try:
                    cur2 = _to_text((self._offline_info(vpc) or {}).get("cid") or "")
                except Exception:
                    cur2 = ""
                if cur2 and cur2 != cid:
                    if not self._offline_trash(cid):
                        self._pending_trash_add(cid)
            else:
                time.sleep(0.3)
                cur2 = ""
                if vpc:
                    try:
                        cur2 = _to_text((self._offline_info(vpc) or {}).get("cid") or "")
                    except Exception:
                        cur2 = ""
                if cur2 and cur2 != cid:
                    if not self._offline_trash(cid):
                        self._pending_trash_add(cid)
                elif not cur2:
                    self._pending_trash_add(cid)
        return vpc or _to_text(info.get("pc") or ""), orig or _to_text(name)

    def _offline_tidy(self, pc, name, title="", label="", deadline=0):
        try:
            info = self._offline_info(pc) or {}
        except Exception:
            info = {}
        if not info:
            return pc, _to_text(name)
        fc = _fc(info)
        is_dir = (fc == "0") if fc else (not bool(info.get("fid")))
        try:
            if is_dir:
                return self._tidy_folder(info, name, title, label, deadline=deadline)
            return self._tidy_file(info, name, title, label,
                                   deadline=deadline)
        except Exception:
            return pc, _to_text(name)

    def _offline_real_name(self, pickcode):
        try:
            info = self._offline_info(pickcode) or {}
        except Exception:
            return ""
        return _to_text(info.get("n") or info.get("name") or "")

    def _pickcode_children(self, pickcode, deadline=0):
        if not pickcode:
            return ""
        try:
            info = self._offline_info(pickcode) or {}
        except Exception:
            info = {}
        if not info:
            return ""
        fc = _fc(info)
        is_dir = (fc == "0") if fc else (not bool(info.get("fid")))
        if not is_dir:
            return pickcode
        cid = _to_text(info.get("cid") or info.get("fid") or "")
        if not cid:
            return ""
        try:
            video, _src = self._offline_find_video(cid, depth=2, deadline=deadline)
        except Exception:
            video = None
        if video:
            return _to_text(video.get("pc") or video.get("pick_code") or "") or pickcode
        return ""

    def _pickcode_in_root(self, title="", label="", deadline=0):
        keys = []
        for kw in (label, title):
            code = self._guess_keyword_from_name(_to_text(kw))
            if code and code.lower() not in [k.lower() for k in keys]:
                keys.append(code)
        if not keys or (deadline and time.time() >= deadline):
            return ""
        try:
            rows = self._offline_dir("0", limit=1000, deadline=deadline)
        except Exception:
            return ""
        best, best_size = None, -1
        for r in rows:
            if _fc(r) != "1":
                continue
            n = _to_text(r.get("n") or r.get("name") or "")
            if not self._is_video_name(n):
                continue
            low = n.lower()
            if not any(k.lower() in low for k in keys):
                continue
            size = _safe_int(r.get("s") or r.get("size") or 0, 0)
            if size > best_size:
                best, best_size = r, size
        if best:
            return _to_text(best.get("pc") or best.get("pick_code") or "")
        return ""

    def _offline_finish(self, info_hash, pc, name, title="", label="",
                        allow_search=True, t0=None):
        name = _to_text(name).strip()
        title = _to_text(title).strip()
        label = _to_text(label).strip()
        t0 = t0 or time.time()
        try:
            self._reap_pending_trash()
        except Exception:
            pass
        deadline = time.time() + OFFLINE_FINISH_BUDGET
        play_pc, display, tidied = pc, name, False
        if time.time() < deadline:
            self._off_trace("整理网盘", t0)
            try:
                got = self._offline_tidy(pc, name, title, label,
                                         deadline=deadline)
                if got and got[0]:
                    play_pc, display = got[0], got[1]
                    tidied = True
            except Exception:
                play_pc, display = pc, name
        if not play_pc:
            play_pc, display = pc, name

        res = None
        if play_pc:
            self._off_trace("取直链", t0)
            res = self._resolve_pickcode(play_pc)
            if not res.get("url") and time.time() < deadline:
                child = self._pickcode_children(play_pc, deadline=deadline)
                if child and child != play_pc:
                    self._off_trace("文件夹里找视频", t0)
                    res = self._resolve_pickcode(child)
                    if res.get("url"):
                        play_pc = child
                        display = self._offline_real_name(child) or display
                        tidied = True
            if res.get("url"):
                if not tidied:
                    display = self._offline_real_name(play_pc) or display
                self._off_cache_put(info_hash, play_pc, display)
                return self._offline_hint(res,
                                          self._offline_note("115离线完成", display),
                                          info_hash)
        if allow_search:
            seen = set()
            for kw in (label, title, name):
                kw = _to_text(kw).strip()
                if not kw or kw in seen:
                    continue
                if time.time() >= deadline:
                    break
                seen.add(kw)
                self._off_trace("按名字搜索", t0)
                alt = self._find_pickcode_by_name(kw, retries=1, interval=0)
                if not alt or alt in (pc, play_pc):
                    continue
                res2 = self._resolve_pickcode(alt)
                if res2.get("url"):
                    shown = self._offline_real_name(alt) or display or kw
                    self._off_cache_put(info_hash, alt, shown)
                    return self._offline_hint(res2,
                                              self._offline_note("115离线完成", shown),
                                              info_hash)
                res = res2
            if time.time() < deadline:
                self._off_trace("根目录扫描", t0)
                alt = self._pickcode_in_root(title, label or name,
                                             deadline=deadline)
                if alt and alt not in (pc, play_pc):
                    res2 = self._resolve_pickcode(alt)
                    if res2.get("url"):
                        shown = self._offline_real_name(alt) or display or title
                        self._off_cache_put(info_hash, alt, shown)
                        return self._offline_hint(
                            res2,
                            self._offline_note("115离线完成", shown),
                            info_hash)
                    res = res2
        return res or _play_err("取直链失败（%.0fs），可重试" % (time.time() - t0))

    def _play_offline_safe(self, magnet, title="", label=""):
        t0 = time.time()
        try:
            res = self._submit_offline_115(magnet, title, label)
        except Exception as e:
            res = _play_err("115离线出错：%s" % e)
        if not isinstance(res, dict):
            res = _play_err("115离线返回异常")
        if res.get("url"):
            self._set_off_last("115离线：成功（%.0fs）" % (time.time() - t0))
            self._release_play_memory()
            return res
        if not res.get("msg"):
            res["msg"] = "115离线取直链失败，请重试"
        self._set_off_last("115离线：失败 %s" % res.get("msg"))
        return res

    def _search_video(self, title, label):
        title = _to_text(title).strip()
        label = _to_text(label).strip()
        if not (title or label):
            return "", ""
        terms, codes = [], []
        for kw in (label, title):
            kw = _to_text(kw).strip()
            if kw and kw.lower() not in [t.lower() for t in terms]:
                terms.append(kw)
            code = self._guess_keyword_from_name(kw)
            if not code:
                continue
            if code.lower() not in [c.lower() for c in codes]:
                codes.append(code)
            if code.lower() not in [t.lower() for t in terms]:
                terms.append(code)
        if not terms:
            return "", ""
        codes = [k for k in codes
                 if re.match(r"^[A-Za-z]{2,10}[-_ ]?\d{2,5}$", k)]
        rows = []
        for keyword in terms:
            for stype in (4, 0):
                for it in self._search_rows(keyword, stype):
                    if int(it.get("fc") or 0) != 1:
                        continue
                    pc = it.get("pc") or it.get("pick_code") or it.get("pickcode")
                    n = _to_text(it.get("n") or it.get("name") or "")
                    if pc and n:
                        rows.append((pc, n))
                if rows:
                    break
            if rows:
                break
        if label:
            low = label.lower()
            for pc, n in rows:
                if low in n.lower():
                    return pc, n
        size_tok = _extract_size_token(label)
        for pc, n in rows:
            low = n.lower()
            if codes and any(c.lower() in low for c in codes) \
                    and size_tok and size_tok in low:
                return pc, n
        return "", ""

    def _submit_offline_115(self, magnet, title="", label=""):
        if not self.enable_offline_115:
            return _play_err("115离线已关闭（ext.enableOffline115）")
        dn_hint = self._magnet_dn(magnet)
        magnet = _normalize_magnet(magnet)
        if not self.cookie_115:
            return _play_err("未配置115 Cookie（文件 DEFAULT_COOKIE_115 / ext.cookie115 / Y115_COOKIE），无法离线")
        if not requests or self._offline_session() is None:
            return _play_err("requests 模块不可用")

        t0 = time.time()
        self._off_trace("开始处理", t0)

        info_hash = self._magnet_hash(magnet)
        if not info_hash:
            return _play_err("无法从磁力中解析 info_hash")

        cached = self._off_cache.get(info_hash)
        if cached:
            self._off_trace("命中缓存，取直链", t0)
            res = self._resolve_pickcode(cached)
            if res.get("url"):
                return self._offline_hint(
                    res, self._offline_note("115离线命中缓存",
                                            self._off_name.get(info_hash, "")),
                    info_hash)
            self._off_cache.pop(info_hash, None)
            self._off_name.pop(info_hash, None)

        early_fail = None
        task = None
        task_name = ""

        if _to_text(title) or _to_text(label) or dn_hint:
            self._off_trace("先搜网盘", t0)
            pc1, name1 = self._search_video(_to_text(title) or dn_hint,
                                            _to_text(label) or dn_hint)
            if pc1:
                self._off_cache_put(info_hash, pc1, name1)
                res1 = self._offline_finish(info_hash, pc1, name1,
                                            title=title, label=label,
                                            allow_search=True, t0=t0)
                if res1.get("url"):
                    return res1
                if res1.get("msg"):
                    early_fail = res1

        try:
            task = self._offline_find_task(info_hash)
        except Exception:
            task = None
        task_name = _to_text(task.get("name") or task.get("file_name") or "") \
            if task else ""

        if task:
            done0, failed0, _msg0 = self._offline_task_state(task)
            pc0 = self._task_pickcode(task)
            if done0 and pc0:
                self._off_trace("任务已完成，整理并取直链", t0)
                res0 = self._offline_finish(info_hash, pc0, task_name,
                                            title=title, label=label,
                                            allow_search=True, t0=t0)
                if res0.get("url"):
                    return res0
                early_fail = res0
            elif failed0:
                task = None

        if not task:
            self._off_trace("提交离线任务", t0)
            try:
                add = self._offline_add(magnet)
            except Exception as e:
                return _play_err("提交离线失败：%s" % e)

            add_msg = _to_text(add.get("message") or add.get("error_msg")
                               or add.get("error"))
            existed = any(k in add_msg for k in ("已存在", "重复"))

            try:
                task = self._offline_find_task(info_hash)
            except Exception:
                task = None

            if not task and not add.get("state") and not existed:
                return _play_err("115离线提交失败：%s" % (add_msg or "提交失败"))

            task_name = _to_text(task.get("name") or task.get("file_name") or "") \
                if task else ""

            if task:
                done0, failed0, msg0 = self._offline_task_state(task)
                if failed0:
                    return _play_err("115离线失败：%s" % msg0)
                pc0 = self._task_pickcode(task)
                if done0 and pc0:
                    self._off_trace("任务已完成，整理并取直链", t0)
                    res0 = self._offline_finish(info_hash, pc0, task_name,
                                                title=title, label=label,
                                                allow_search=True, t0=t0)
                    if res0.get("url"):
                        return res0
                    early_fail = res0

        self._off_trace("等待离线完成", t0)
        done, name_or_msg = self._offline_wait_done(info_hash)
        if not done:
            return _play_err("已提交115离线，下载中（%s），请稍后重试"
                           % (name_or_msg or "等待完成"))

        name = _to_text(name_or_msg) or task_name
        try:
            task = self._offline_find_task(info_hash)
        except Exception:
            task = None
        pickcode = self._task_pickcode(task)
        if pickcode:
            res = self._offline_finish(info_hash, pickcode, name,
                                       title=title, label=label, allow_search=True, t0=t0)
            if res.get("url"):
                return res
            if early_fail:
                return early_fail
            return res

        pickcode = self._find_pickcode_by_name(name, retries=3, interval=1, exact=name)
        if not pickcode:
            return early_fail or _play_err(
                "离线已完成，但115网盘里还没搜到文件，请稍后重试")

        res = self._offline_finish(info_hash, pickcode, name,
                                   title=title, label=label, allow_search=False, t0=t0)
        if res.get("url") or not early_fail:
            return res
        return early_fail

    # ==================== 播放 ====================

    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        self._set_off_last("收到播放请求：%s" % _to_text(vid)[:50])

        if self.offline_test_mp4 and (vid.startswith(OFF_PREFIX_115)
                                      or vid.startswith("115off:")):
            return {
                "parse": 0, "jx": 0, "playUrl": "",
                "url": OFFLINE_TEST_MP4, "header": OFFLINE_TEST_HEADER,
            }

        if vid.startswith(OFF_PREFIX_115):
            magnet, title, label = _off_id_decode(vid[len(OFF_PREFIX_115):])
            if not magnet:
                return _play_err("磁力解码失败")
            return self._play_offline_safe(magnet, title, label)

        if vid.startswith("115off:"):
            return self._play_offline_safe(vid[len("115off:"):].strip())

        if vid.startswith("magnet:"):
            m = _normalize_magnet(vid)
            return {
                "parse": 0, "jx": 0, "playUrl": "",
                "url": m or vid,
                "header": {"User-Agent": self.ua, "Accept": "*/*"},
            }

        # 演员/片商/系列详情里点作品 → 作品 id 走 detail 拿磁力再播
        if not vid.startswith(OFF_PREFIX_115) and len(vid) <= 12 \
                and re.match(r"^[A-Za-z0-9]+$", vid):
            try:
                d = self.detailContent([vid])
                vod = (d.get("list") or [{}])[0]
                play_url = _to_text(vod.get("vod_play_url") or "")
                if play_url:
                    # 取 115离线源的第一个条目
                    sources = play_url.split("#")
                    for ep in sources:
                        if OFF_PREFIX_115 in ep:
                            _, ep_id = ep.split("$", 1)
                            magnet, title, label = _off_id_decode(
                                ep_id[len(OFF_PREFIX_115):].split("?")[0])
                            if magnet:
                                return self._play_offline_safe(magnet, title, label)
            except Exception:
                pass

        return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

    def localProxy(self, param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        if not isinstance(param, dict):
            param = {}
        if _to_text(param.get("k")) == "offnote":
            body = self._offline_srt(param.get("v") or "")
            return [200, "application/x-subrip", body.encode("utf-8"), {}]
        return [404, "text/plain", b"Not Found", {}]

    @staticmethod
    def _in_atvp():
        try:
            return __name__ == "atvp_inner_spider"
        except Exception:
            return False

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = _to_text(url).lower()
        if u.startswith("magnet:"):
            return True
        if u.startswith(OFF_PREFIX_115) or u.startswith("115off:"):
            return True
        u = u.split("?")[0]
        return u.endswith((".mp4", ".m3u8", ".flv", ".mkv", ".ts", ".avi"))

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
