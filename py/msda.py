# -*- coding: utf-8 -*-
VERSION = "1.0.0"
# msda.py —— FANZA METADATA INDEX (fanza.fastcdn.dpdns.org) 爬虫
# 参照 javdbui.py 结构：分类/筛选与网页端对齐；磁力 + 115 离线可播放。
# 网页板块：AV档案(/) / 无码档案(/uncensored) / FC2档案(/fc2) / 发售日历(/calendar)
# 列表页签：全部新作(lists/new) / 有磁链(lists/links) / 可播(lists/playable)
# 数据 API：fanza-api.fastcdn.dpdns.org/v1/*；播放解析：站点 /api/rv/v1/resolve
# 说明：Cloudflare 对普通 requests 直接 403，必须走 curl_cffi TLS 指纹。
import os
import re
import json
import time
import threading
import html as html_mod
import base64
import hashlib
import warnings
from urllib.parse import quote, unquote

try:
    import requests
except ImportError:
    requests = None

try:
    from curl_cffi import requests as creq
except ImportError:
    creq = None

try:
    from urllib3.exceptions import InsecureRequestWarning
    warnings.simplefilter("ignore", InsecureRequestWarning)
except Exception:
    pass


# ===========================================================================
# 配置区
# ===========================================================================
# (1) 网页代理：只管「爬虫抓网页/下图片」，播放地址由 App 自己去取。
# 默认留空（直连即可）；若直连被 Cloudflare 拦，可填 http://192.168.1.8:7890
PROXY = ""

# (2) 图片反代：图片显示不出来时再开（默认关闭）
IMG_PROXY = ""

# 站点 ext（TVBox 源里 ext 字段传 JSON）可覆盖上面两项及其它开关：
#   {
#     "proxy": "7890", "img": "https://...",
#     "host": "https://fanza.fastcdn.dpdns.org",
#     "api": "https://fanza-api.fastcdn.dpdns.org",
#     "cookie115": "", "enableOffline115": true,
#     "offlineSavePath": "0", "offlineAppVer": "4.8.2",
#     "offlineProxy": "", "offlineDebug": 1
#   }

# FANZA 元数据索引：前端 SPA + 独立数据 API
HOST = "https://fanza.fastcdn.dpdns.org"
API_BASE = "https://fanza-api.fastcdn.dpdns.org"

# 预览：DMM 官方免费预告反代（挂在 host 上，部分番号有）
PREVIEW_API = "/api/dmm/preview"
# 预览伪链前缀（真正地址在播放时逐候选探测）
PREVIEW_PREFIX = "http://msdapv/"
# 在线解析伪链前缀（/api/rv/v1/resolve，播放时取 variants）
RESOLVE_PREFIX = "http://msdars/"

PAGE_SIZE = 24
SEARCH_LIMIT = 30

# 网页板块 type_id → 上游 class 参数（注意：上游认 uncensored，不认 uc）
# resolve 的 type 参数另用 av/uc/fc2（前端 Hn 映射）
SECTION_CLASS = {"av": "av", "uncensored": "uncensored", "fc2": "fc2"}
# resolve type 映射（content_class → resolve?type=）
RESOLVE_TYPE = {"av": "av", "uncensored": "uc", "fc2": "fc2"}
# content_class 值域
CONTENT_CLASSES = ("av", "uncensored", "fc2")

HTTP_RETRY = 1
HTTP_RETRY_DELAY = 0.5
HTTP_RETRY_STATUS = (429, 500, 502, 503, 504)

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

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
# AI 封面解码成品磁盘缓存（跨重启，避免冷启动重解密；键=去 auth_key 后 URL 的 md5）
PIC_DISK_DIR = os.path.join(os.path.expanduser("~"), ".javdbui_pic_cache")


def _trace_write(text):
    try:
        with open(OFF_TRACE_FILE, "w", encoding="utf-8") as f:
            f.write(_to_text(text))
    except Exception:
        pass


def _prune_pic_cache(keep=400):
    """图片磁盘缓存按 mtime 裁到 keep 条：单张约 80KB，400 条约 32MB 封顶。"""
    try:
        paths = [os.path.join(PIC_DISK_DIR, n) for n in os.listdir(PIC_DISK_DIR)]
        if len(paths) <= keep:
            return
        paths.sort(key=os.path.getmtime)      # 最旧在前
        for p in paths[:len(paths) - keep]:
            try:
                os.remove(p)
            except Exception:
                pass
    except Exception:
        pass


def _fc(item):
    v = item.get("fc") if isinstance(item, dict) else None
    return "" if v is None else str(v).strip()


def _off_id_encode(magnet, title="", label="", number=""):
    payload = {"m": _to_text(magnet)}
    if _to_text(title):
        payload["t"] = _to_text(title)
    if _to_text(label):
        payload["l"] = _to_text(label)
    if _to_text(number):
        payload["n"] = _to_text(number)
    raw = json.dumps(payload, ensure_ascii=False)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def _off_id_decode(text):
    text = _to_text(text).strip().split("#")[0].split("?")[0]
    try:
        raw = base64.b64decode(text.encode("ascii")).decode("utf-8")
    except Exception:
        return "", "", "", ""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        if isinstance(data, dict):
            return (_to_text(data.get("m") or ""),
                    _to_text(data.get("t") or ""),
                    _to_text(data.get("l") or ""),
                    _to_text(data.get("n") or ""))
    return raw, "", "", ""


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


# 公共 tracker：磁力直连播放时附加，加速 DHT 找 peer（救活低种子片）。
# API 磁力字段不含 tracker/seed 数，播放器只能靠 DHT/PEX，慢且易超时失败。
MAGNET_TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://open.stealth.si:80/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.bt4g.com:2095/announce",
)


def _magnet_with_trackers(infohash):
    """infohash → 带公共 tracker 的磁力链接（加速 peer 发现）。"""
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
    # 保留 tr=（tracker）以加速 peer 发现；其它参数（dn 等）仍丢弃
    for tr in re.findall(r"[?&]tr=([^&]+)", magnet):
        base += "&tr=" + tr
    return base


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


def _magnet_label(g, idx):
    """磁力条目 → 播放列表显示名（高清/字幕/大小）；磁力源与 115 离线源共用"""
    parts = []
    if bool(g.get("hd")):
        parts.append("高清")
    if bool(g.get("cnsub")):
        parts.append("字幕")
    s = _format_size_mb(g.get("size"))
    if s:
        parts.append(s)
    return " ".join(parts) or ("磁力%d" % (idx + 1))


def _dur_match(d, bucket):
    """时长档客户端判定（服务端实体 key 不支持时长 → _entity_grid_dur 用）。
    档位边界对齐服务端实测：lt-45=10~44 / 45-90=45~90 / 90-120=91~120 / gt-120=121~。
    d<=0（缺时长）一律不命中，避免脏数据混入。"""
    try:
        d = int(d)
    except (TypeError, ValueError):
        return False
    if d <= 0:
        return False
    if bucket == "lt-45":
        return d < 45
    if bucket == "45-90":
        return 45 <= d <= 90
    if bucket == "90-120":
        return 90 < d <= 120
    if bucket == "gt-120":
        return d > 120
    return False


# ==================== 日期工具 ====================

def _today():
    return time.strftime("%Y-%m-%d")


def _shift_days(days):
    return time.strftime("%Y-%m-%d",
                         time.localtime(time.time() - days * 86400))


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


# ==================== AI 封面 AES-128-CBC ====================
# GET /api/v/drama/cover-key → {algorithm:"AES-128-CBC", padding:"none",
# input:"raw-bytes", key:"...", iv:"..."}；key/iv 是 **16 个 ASCII 字符**（不是 hex）。
# 后端优先级：cryptography → PyCryptodome → 纯 Python（TVBox 运行时可能两者皆无）。
_AES_BACKEND = []
_AES_SBOX_HEX = (
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16"
)
_AES_SBOX = [int(_AES_SBOX_HEX[i:i + 2], 16) for i in range(0, 512, 2)]
_AES_INV_SBOX = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_v] = _i


def _aes_backend():
    """可用的 AES-128-CBC 后端名；探测一次后缓存（纯 Python 恒可用）。
    顺序：Android/TVBox（Chaquopy）的 javax.crypto → cryptography → PyCryptodome
    → 纯 Python。盒子/电视上前两者通常都没有，纯 Python 约 110KB/s，一张 270KB
    封面要 2.5s，一页 6 张直接撞宿主 15s 超时 → AI 栏目整片无图；走 Java 侧
    native AES 只要几毫秒，是 AI 封面在真机上唯一能稳稳出图的路径。"""
    if _AES_BACKEND:
        return _AES_BACKEND[0]
    name = "pure"
    try:
        from javax.crypto import Cipher  # noqa: F401
        name = "java"
    except Exception:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher  # noqa: F401
            name = "cryptography"
        except Exception:
            try:
                from Crypto.Cipher import AES  # noqa: F401
                name = "crypto"
            except Exception:
                name = "pure"
    _AES_BACKEND.append(name)
    return name


def _aes_xtime(a):
    a <<= 1
    return (a ^ 0x11B) & 0xFF if a & 0x100 else a & 0xFF


def _aes_mul(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        a = _aes_xtime(a)
        b >>= 1
    return r


def _aes_expand(key):
    """AES-128 密钥扩展 → 176 字节轮密钥。"""
    w = list(key)
    rcon = 1
    while len(w) < 176:
        t = w[-4:]
        if len(w) % 16 == 0:
            t = [_AES_SBOX[t[1]] ^ rcon, _AES_SBOX[t[2]],
                 _AES_SBOX[t[3]], _AES_SBOX[t[0]]]
            rcon = _aes_xtime(rcon)
        for i in range(4):
            w.append(w[-16] ^ t[i])
    return w


_AES_MUL_TBL = {}
_AES_TD = None          # (Td0, Td1, Td2, Td3) 懒构建
_AES_TD_CACHE = {}      # key(16B) → (rk, td, rk_mix)


def _aes_mul_tbl():
    if not _AES_MUL_TBL:
        for n in (9, 11, 13, 14):
            _AES_MUL_TBL[n] = [_aes_mul(i, n) for i in range(256)]
    return _AES_MUL_TBL


def _aes_td_tables():
    """Td0..Td3：InvSubBytes+InvMixColumns 折叠成 4 张 256 项 32 位表（懒构建一次）。"""
    global _AES_TD
    if _AES_TD is None:
        t = _aes_mul_tbl()
        m9, m11, m13, m14 = t[9], t[11], t[13], t[14]
        inv = _AES_INV_SBOX
        Td0 = [0] * 256
        Td1 = [0] * 256
        Td2 = [0] * 256
        Td3 = [0] * 256
        for x in range(256):
            s = inv[x]
            # InvMixColumns 矩阵 [0e 0b 0d 09 / 09 0e 0b 0d / 0d 09 0e 0b / 0b 0d 09 0e]
            Td0[x] = (m14[s] | (m9[s] << 8) | (m13[s] << 16) | (m11[s] << 24))
            Td1[x] = (m11[s] | (m14[s] << 8) | (m9[s] << 16) | (m13[s] << 24))
            Td2[x] = (m13[s] | (m11[s] << 8) | (m14[s] << 16) | (m9[s] << 24))
            Td3[x] = (m9[s] | (m13[s] << 8) | (m11[s] << 16) | (m14[s] << 24))
        _AES_TD = (Td0, Td1, Td2, Td3)
    return _AES_TD


def _aes_inv_mix4(col, t):
    """单列 4 字节 InvMixColumns。"""
    m9, m11, m13, m14 = t[9], t[11], t[13], t[14]
    a, b, c, d = col
    return (m14[a] ^ m11[b] ^ m13[c] ^ m9[d],
            m9[a] ^ m14[b] ^ m11[c] ^ m13[d],
            m13[a] ^ m9[b] ^ m14[c] ^ m11[d],
            m11[a] ^ m13[b] ^ m9[c] ^ m14[d])


def _aes_prep(key):
    """展开轮密钥 + Td 表 + 预混轮密钥（InvMixColumns 线性，可提前混好）。"""
    rk = _aes_expand(key)
    td = _aes_td_tables()
    t = _aes_mul_tbl()
    rk_mix = [None] * 10          # 1..9 用
    for rnd in range(1, 10):
        k = rk[rnd * 16:(rnd + 1) * 16]
        mixed = []
        for c in range(4):
            mixed.extend(_aes_inv_mix4(k[c * 4:c * 4 + 4], t))
        rk_mix[rnd] = mixed
    return rk, td, rk_mix


def _aes_get_prep(key):
    cached = _AES_TD_CACHE.get(key)
    if cached is None:
        cached = _aes_prep(key)
        if len(_AES_TD_CACHE) > 8:
            _AES_TD_CACHE.clear()
        _AES_TD_CACHE[key] = cached
    return cached


def _aes_dec_block(rk, td, rk_mix, blk):
    """T-table 单块解密：AddRoundKey(10) → 9 轮 Td 查表+预混轮密钥 → 末轮。"""
    Td0, Td1, Td2, Td3 = td
    s0 = blk[0] ^ rk[160]; s1 = blk[1] ^ rk[161]
    s2 = blk[2] ^ rk[162]; s3 = blk[3] ^ rk[163]
    s4 = blk[4] ^ rk[164]; s5 = blk[5] ^ rk[165]
    s6 = blk[6] ^ rk[166]; s7 = blk[7] ^ rk[167]
    s8 = blk[8] ^ rk[168]; s9 = blk[9] ^ rk[169]
    s10 = blk[10] ^ rk[170]; s11 = blk[11] ^ rk[171]
    s12 = blk[12] ^ rk[172]; s13 = blk[13] ^ rk[173]
    s14 = blk[14] ^ rk[174]; s15 = blk[15] ^ rk[175]
    for rnd in range(9, 0, -1):
        # InvShiftRows
        s1, s5, s9, s13 = s13, s1, s5, s9
        s2, s6, s10, s14 = s10, s14, s2, s6
        s3, s7, s11, s15 = s7, s11, s15, s3
        km = rk_mix[rnd]
        # 列 0
        t = Td0[s0] ^ Td1[s1] ^ Td2[s2] ^ Td3[s3]
        s0 = (t & 0xFF) ^ km[0]; s1 = ((t >> 8) & 0xFF) ^ km[1]
        s2 = ((t >> 16) & 0xFF) ^ km[2]; s3 = ((t >> 24) & 0xFF) ^ km[3]
        # 列 1
        t = Td0[s4] ^ Td1[s5] ^ Td2[s6] ^ Td3[s7]
        s4 = (t & 0xFF) ^ km[4]; s5 = ((t >> 8) & 0xFF) ^ km[5]
        s6 = ((t >> 16) & 0xFF) ^ km[6]; s7 = ((t >> 24) & 0xFF) ^ km[7]
        # 列 2
        t = Td0[s8] ^ Td1[s9] ^ Td2[s10] ^ Td3[s11]
        s8 = (t & 0xFF) ^ km[8]; s9 = ((t >> 8) & 0xFF) ^ km[9]
        s10 = ((t >> 16) & 0xFF) ^ km[10]; s11 = ((t >> 24) & 0xFF) ^ km[11]
        # 列 3
        t = Td0[s12] ^ Td1[s13] ^ Td2[s14] ^ Td3[s15]
        s12 = (t & 0xFF) ^ km[12]; s13 = ((t >> 8) & 0xFF) ^ km[13]
        s14 = ((t >> 16) & 0xFF) ^ km[14]; s15 = ((t >> 24) & 0xFF) ^ km[15]
    # 末轮：InvShiftRows + InvSubBytes + AddRoundKey(0)
    s1, s5, s9, s13 = s13, s1, s5, s9
    s2, s6, s10, s14 = s10, s14, s2, s6
    s3, s7, s11, s15 = s7, s11, s15, s3
    inv = _AES_INV_SBOX
    return [inv[s0] ^ rk[0], inv[s1] ^ rk[1],
            inv[s2] ^ rk[2], inv[s3] ^ rk[3],
            inv[s4] ^ rk[4], inv[s5] ^ rk[5],
            inv[s6] ^ rk[6], inv[s7] ^ rk[7],
            inv[s8] ^ rk[8], inv[s9] ^ rk[9],
            inv[s10] ^ rk[10], inv[s11] ^ rk[11],
            inv[s12] ^ rk[12], inv[s13] ^ rk[13],
            inv[s14] ^ rk[14], inv[s15] ^ rk[15]]


def _aes_pure_decrypt(data, key, iv):
    """纯 Python AES-128-CBC 解密（padding none），T-table 加速，逐块与前块异或。"""
    rk, td, rk_mix = _aes_get_prep(key)
    out = bytearray(len(data))
    prev0, prev1, prev2, prev3 = iv[0], iv[1], iv[2], iv[3]
    prev4, prev5, prev6, prev7 = iv[4], iv[5], iv[6], iv[7]
    prev8, prev9, prev10, prev11 = iv[8], iv[9], iv[10], iv[11]
    prev12, prev13, prev14, prev15 = iv[12], iv[13], iv[14], iv[15]
    n = len(data)
    for off in range(0, n, 16):
        blk = data[off:off + 16]
        dec = _aes_dec_block(rk, td, rk_mix, blk)
        out[off] = dec[0] ^ prev0; out[off + 1] = dec[1] ^ prev1
        out[off + 2] = dec[2] ^ prev2; out[off + 3] = dec[3] ^ prev3
        out[off + 4] = dec[4] ^ prev4; out[off + 5] = dec[5] ^ prev5
        out[off + 6] = dec[6] ^ prev6; out[off + 7] = dec[7] ^ prev7
        out[off + 8] = dec[8] ^ prev8; out[off + 9] = dec[9] ^ prev9
        out[off + 10] = dec[10] ^ prev10; out[off + 11] = dec[11] ^ prev11
        out[off + 12] = dec[12] ^ prev12; out[off + 13] = dec[13] ^ prev13
        out[off + 14] = dec[14] ^ prev14; out[off + 15] = dec[15] ^ prev15
        prev0, prev1, prev2, prev3 = blk[0], blk[1], blk[2], blk[3]
        prev4, prev5, prev6, prev7 = blk[4], blk[5], blk[6], blk[7]
        prev8, prev9, prev10, prev11 = blk[8], blk[9], blk[10], blk[11]
        prev12, prev13, prev14, prev15 = blk[12], blk[13], blk[14], blk[15]
    return bytes(out)


def _aes128_cbc_decrypt(data, key, iv):
    """AES-128-CBC 解密（上游 padding none）。失败返回 b""。"""
    data = bytes(data or b"")
    key = bytes(key or b"")
    iv = bytes(iv or b"")
    if not data or len(data) % 16 or len(key) != 16 or len(iv) != 16:
        return b""
    backend = _aes_backend()
    if backend == "java":
        # Chaquopy：Java 侧 native AES，GIL 还会在此期间释放，多图并发不吃亏；
        # 失败（个别 ROM 缺 provider）就回落到纯 Python，不能直接返回空图。
        try:
            from javax.crypto import Cipher
            from javax.crypto.spec import SecretKeySpec, IvParameterSpec
            c = Cipher.getInstance("AES/CBC/NoPadding")
            c.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"),
                   IvParameterSpec(iv))
            out = c.doFinal(data)
            if isinstance(out, (bytes, bytearray)):
                return bytes(out)
            return bytes(bytearray(out))     # jarray('b') 兜底
        except Exception:
            return _aes_pure_decrypt(data, key, iv)
    try:
        if backend == "cryptography":
            from cryptography.hazmat.primitives.ciphers import (
                Cipher, algorithms, modes)
            d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            return d.update(data) + d.finalize()
        if backend == "crypto":
            from Crypto.Cipher import AES
            return AES.new(key, AES.MODE_CBC, iv).decrypt(data)
    except Exception:
        return _aes_pure_decrypt(data, key, iv)
    return _aes_pure_decrypt(data, key, iv)


# ==================== 自建封面 HTTP 服务 ====================
# 为什么不再依赖宿主：AI 封面是 AES 密文，只能由爬虫解密后交给 App，而可选交付方式
# 各有硬伤——data URI 在多数电视端图片库/播放器里不渲染（300KB 级 data URI 还会撞
# URL 长度上限）；宿主 localProxy 要求 App 把 ?do=py 路由到 Python 爬虫，部分 32 位
# 电视端根本没接这条路由，表现就是「别的分类有图、AI 栏目一张不出」。
# 这里直接用标准库起一个只监听 127.0.0.1 的图片服务：App 拿到的就是一条普普通通的
# 短 http 图片地址，和自己能出图的明文封面走完全相同的取图链路。
_PIC_SRV = {"tried": False, "base": "", "spider": None}
_PIC_SRV_LOCK = threading.Lock()


def _pic_server_base(spider):
    """惰性启动本地图片服务；成功返回 http://127.0.0.1:port，失败返回 ""。
    spider 每次都刷新：宿主 destroy 后重建实例时，服务线程要取到新会话。"""
    _PIC_SRV["spider"] = spider
    if _PIC_SRV["tried"]:
        return _PIC_SRV["base"]
    with _PIC_SRV_LOCK:
        if _PIC_SRV["tried"]:
            return _PIC_SRV["base"]
        _PIC_SRV["tried"] = True
        try:
            try:
                from http.server import (BaseHTTPRequestHandler,
                                         ThreadingHTTPServer)
            except ImportError:      # Python 3.6 没有 ThreadingHTTPServer
                import socketserver
                from http.server import BaseHTTPRequestHandler, HTTPServer

                class ThreadingHTTPServer(socketserver.ThreadingMixIn,
                                          HTTPServer):
                    daemon_threads = True

            class _PicHandler(BaseHTTPRequestHandler):
                server_version = "javdbui-pic"

                def log_message(self, fmt, *args):
                    pass                    # 电视端 stdout 很贵，别刷日志

                def _serve(self, with_body):
                    path = (self.path or "").split("?", 1)[0]
                    body, mime = b"", ""
                    if path.startswith("/pic/"):
                        tok = path[len("/pic/"):]
                        if tok.lower().endswith(".jpg"):   # 个别图片库认扩展名
                            tok = tok[:-4]
                        src = Spider._unpack_pic_token(tok)
                        cur = _PIC_SRV.get("spider")
                        if src and cur is not None:
                            try:
                                body, mime = cur._fetch_pic(src)
                            except Exception:
                                body, mime = b"", ""   # 单张失败只回 404，别打死线程
                    if not body:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", mime or "image/jpeg")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "public, max-age=1800")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    if with_body:
                        self.wfile.write(body)

                def do_GET(self):
                    self._serve(True)

                def do_HEAD(self):
                    self._serve(False)

            httpd = ThreadingHTTPServer(("127.0.0.1", 0), _PicHandler)
            httpd.daemon_threads = True
            t = threading.Thread(target=httpd.serve_forever,
                                 kwargs={"poll_interval": 0.2})
            t.daemon = True
            t.start()
            base = "http://127.0.0.1:%d" % httpd.server_address[1]
            # 回环自检：个别运行时会「绑定成功但连不上」，探到 404 才算服务活着。
            # 必须绕开 http_proxy：配了系统代理又没写 no_proxy 时，urllib 会把
            # 127.0.0.1 也丢给代理，探活会误判成「服务不可用」而白白退化。
            alive = False
            try:
                import urllib.request as _urlreq
                opener = _urlreq.build_opener(_urlreq.ProxyHandler({}))
                opener.open(base + "/pic/__probe__", timeout=3)
            except Exception as e:
                alive = getattr(e, "code", None) == 404
            if alive:
                _PIC_SRV["base"] = base
            else:
                try:
                    httpd.shutdown()
                except Exception:
                    pass
                _PIC_SRV["base"] = ""
        except Exception:
            _PIC_SRV["base"] = ""       # 端口/权限受限 → 走后面的兜底
        return _PIC_SRV["base"]


def _shrink_pic(data, mime, max_w=720):
    """Android（Chaquopy）上把 1440x1920 的大封面原生降采样后再缓存/交付。

    实测 AI 封面明文是 1440x1920，一张解码后的位图约 11MB；列表一屏十几张，
    电视盒子的堆内存和解码器扛不住，典型表现就是「一栏封面全白」。电影封面
    （c0 明文小图）没这个问题，所以只针对这张链路。非 Android 环境原样返回。
    inSampleSize 只能取 2 的幂，1440 → 720（位图 2.7MB、JPEG ~80KB），
    既压住内存又保留海报清晰度。
    """
    if not data or not mime.startswith("image/jpeg"):
        return data, mime
    try:
        from android.graphics import BitmapFactory, Bitmap
        from java.io import ByteArrayOutputStream
        probe = BitmapFactory.Options()
        probe.inJustDecodeBounds = True
        BitmapFactory.decodeByteArray(data, 0, len(data), probe)
        w = int(probe.outWidth or 0)
        if w <= 0 or w <= max_w:
            return data, mime
        sample = 1
        while (w // sample) > max_w:       # 取到「降完仍不超 max_w」的最小 2 的幂
            sample *= 2
        opts = BitmapFactory.Options()
        opts.inSampleSize = sample
        bmp = BitmapFactory.decodeByteArray(data, 0, len(data), opts)
        if bmp is None:
            return data, mime
        bos = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.JPEG, 82, bos)
        bmp.recycle()
        raw_out = bos.toByteArray()
        try:
            out = bytes(raw_out)
        except Exception:
            out = bytes(bytearray(raw_out))
        if out:
            return out, "image/jpeg"
    except Exception:
        pass
    return data, mime


# ==================== Spider ====================

class Spider:
    def __init__(self):
        self.s = None          # FANZA API 会话（curl_cffi 优先）
        self.s115 = None       # 115 接口会话
        self.api = API_BASE
        self.host = HOST
        self.ua = WEB_UA
        self.timeout = 20
        self.page_size = PAGE_SIZE
        self.search_limit = SEARCH_LIMIT
        self.enable_magnet = True
        self.enable_uncensored = True
        self.cookie = ""
        self.img_proxy = IMG_PROXY
        self.proxy = PROXY
        self.lang = "zh"
        self.verify = False
        self.img_proxy_off = False
        self._ext_site_key = ""

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
        self._vid_meta = {}       # id -> {number,title,pic,...}
        self._work_cache = {}     # id -> (ts, work dict)
        self._magnets_cache = {}  # code -> (ts, [link])
        self._dmm_cache = {}      # number -> (ts, [candidate])；空列表=确定无预览
        self._search_cache = {}   # "kw|class|page" -> (ts, list, total)
        self._search_last = 0.0
        self._search_block_until = 0.0
        self._cache_filters = {}
        self._host_locked = False
        self._probed = False
        self._off_last = ""
        self.preview_api = PREVIEW_API
        self.resolve_api = "/api/rv/v1/resolve"
        self._api_action = ""

        # FANZA 有 Cloudflare：curl_cffi TLS 指纹优先，requests 仅作兜底
        if creq is not None:
            try:
                self.s = creq.Session(impersonate="chrome")
                self.s.headers.update(LIST_HEADERS)
                self._apply_proxy()
            except Exception:
                self.s = None
        if self.s is None and requests:
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
        if extend.get("previewApi"):
            self.preview_api = str(extend["previewApi"]).strip()
        if extend.get("resolveApi"):
            self.resolve_api = str(extend["resolveApi"]).strip()
        if extend.get("img") or extend.get("imgProxy"):
            self.img_proxy = str(extend.get("img") or extend.get("imgProxy") or "").strip()
        if "imgProxyOff" in extend or "noImgProxy" in extend or "imgOff" in extend:
            self.img_proxy_off = bool(extend.get("imgProxyOff", extend.get("noImgProxy", extend.get("imgOff"))))
        if extend.get("key") or extend.get("siteKey"):
            self._ext_site_key = str(
                extend.get("key") or extend.get("siteKey") or "").strip()
        if extend.get("cookie"):
            self.cookie = str(extend["cookie"])
        if extend.get("lang"):
            self.lang = str(extend["lang"])
        if "enableMagnet" in extend:
            self.enable_magnet = bool(extend["enableMagnet"])
        if "enableUncensored" in extend:
            self.enable_uncensored = bool(extend["enableUncensored"])
        if "verify" in extend:
            self.verify = bool(extend["verify"])

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

    # ---------- FANZA API ----------
    def _http_get(self, url, params=None, headers=None, timeout=None,
                  as_json=True):
        """GET url → dict/list（失败返回 {} / []）。
        FANZA 有 Cloudflare：优先 curl_cffi TLS 指纹，requests 仅兜底。"""
        self._api_action = ""
        t = timeout or self.timeout
        hdrs = dict(LIST_HEADERS)
        if headers:
            hdrs.update(headers)
        if _to_text(self.cookie):
            hdrs["Cookie"] = self.cookie
        for attempt in range(HTTP_RETRY + 1):
            try:
                if creq is not None and getattr(self.s, "impersonate", None) is not None:
                    r = self.s.get(url, params=params or {}, headers=hdrs,
                                   timeout=t, verify=self.verify)
                elif self.s is not None:
                    r = self.s.get(url, params=params or {}, headers=hdrs,
                                   timeout=t, verify=self.verify)
                elif creq is not None:
                    r = creq.get(url, params=params or {}, headers=hdrs,
                                 timeout=t, verify=self.verify,
                                 impersonate="chrome")
                elif requests:
                    r = requests.get(url, params=params or {}, headers=hdrs,
                                     timeout=t, verify=self.verify)
                else:
                    return {}
                if r.status_code in HTTP_RETRY_STATUS and attempt < HTTP_RETRY:
                    time.sleep(HTTP_RETRY_DELAY)
                    continue
                if not as_json:
                    return {"status_code": r.status_code, "text": r.text or ""}
                data = r.json()
                if isinstance(data, dict):
                    return data
                if isinstance(data, list):
                    return {"items": data}
                return {}
            except Exception as e:
                self._api_action = _to_text(e)
                if attempt < HTTP_RETRY:
                    time.sleep(HTTP_RETRY_DELAY)
                    continue
                return {}
        return {}

    def _api_get(self, path, params=None, timeout=None):
        """GET API_BASE + path → data dict（FANZA 直接返回 JSON 本体）"""
        data = self._http_get(self.api + path, params=params, timeout=timeout)
        if not data:
            return {}
        # 兼容 {data:...} 包装与裸对象两种形态
        if "data" in data and isinstance(data.get("data"), (dict, list)) \
                and len(data) <= 3:
            inner = data.get("data")
            return inner if isinstance(inner, dict) else {"items": inner}
        return data

    def _site_get(self, path, params=None, timeout=None):
        """GET HOST + path（预览/resolve 等站点相对接口）"""
        return self._http_get(self.host + path, params=params, timeout=timeout)

    # ---------- work 对象 → vod item ----------
    def _movie_item(self, m):
        if not isinstance(m, dict):
            return None
        mid = _to_text(m.get("id") or "")
        if not mid:
            return None
        title = _to_text(m.get("title") or m.get("code") or "")
        number = _to_text(m.get("code") or "")
        pic = self._proxy_pic(_to_text(m.get("cover_url") or ""))
        date = _to_text(m.get("release_date") or "")
        playable = bool(m.get("playable"))
        remark_parts = []
        if number:
            remark_parts.append(number)
        if date:
            remark_parts.append(date[:10])
        if playable:
            remark_parts.append("可播")
        if m.get("playable_until"):
            remark_parts.append("限时")
        self._vid_meta[mid] = {
            "number": number,
            "title": title,
            "pic": pic,
            "duration": _safe_int(m.get("duration_sec"), 0),
            "release_date": date,
            "content_class": _to_text(m.get("content_class") or ""),
            "playable": playable,
        }
        return {
            "vod_id": mid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": " ".join(remark_parts),
            "type_name": number,
        }

    def _works_to_list(self, works):
        out = []
        seen = set()
        for m in works or []:
            item = self._movie_item(m)
            if item and item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                out.append(item)
        return out

    # 兼容旧名（部分路径仍调用）
    _movies_to_list = None  # 占位，下方立即赋值

    def _proxy_pic(self, url):
        """FANZA 封面为明文 URL：仅在配置了 img 时加反代，否则原样返回。"""
        if not url:
            return ""
        url = _to_text(url)
        if not url.startswith(("http://", "https://")):
            return url
        p = _to_text(self.img_proxy)
        if p:
            if "{url}" in p:
                return p.replace("{url}", quote(url, safe=""))
            return p + quote(url, safe="")
        return url

    def _pic_data_uri(self, url):
        if not url:
            return url
        data, mime = self._fetch_pic(url)
        if data:
            return "data:%s;base64,%s" % (
                mime or "image/jpeg",
                base64.b64encode(data).decode("ascii"))
        return url

    def _site_key(self):
        return _to_text(getattr(self, "_ext_site_key", "") or "")

    @staticmethod
    def _pic_proxy_base():
        try:
            from com.github.catvod import Proxy
        except Exception:
            return "proxy://do=py"
        try:
            port = int(Proxy.getPort() or 0)
        except Exception:
            port = 0
        if port > 0:
            return "http://127.0.0.1:%d/proxy?do=py" % port
        try:
            u = _to_text(Proxy.getUrl() or "")
            if u.startswith(("http://", "https://")):
                return u + ("&" if "?" in u else "?") + "do=py"
        except Exception:
            pass
        return "proxy://do=py"

    def _movies_to_list(self, works):
        return self._works_to_list(works)

    # ---------- 类别（对齐网页端导航） ----------
    @staticmethod
    def _classes():
        return [
            {"type_id": "av",         "type_name": "AV档案"},
            {"type_id": "uncensored", "type_name": "无码档案"},
            {"type_id": "fc2",        "type_name": "FC2档案"},
            {"type_id": "calendar",   "type_name": "发售日历"},
        ]

    @staticmethod
    def _tab_group(init="new"):
        """列表页签：全部新作 / 有磁链 / 可播（对齐网页分区 tab）"""
        return {"key": "tab", "name": "页签", "init": init,
                "value": [
                    {"n": "全部新作", "v": "new"},
                    {"n": "有磁链", "v": "links"},
                    {"n": "可播", "v": "playable"},
                ]}

    @staticmethod
    def _days_group():
        """新作时间窗（网页 days 参数）"""
        return {"key": "days", "name": "时间", "init": "7",
                "value": [
                    {"n": "今日", "v": "1"},
                    {"n": "近7日", "v": "7"},
                    {"n": "近14日", "v": "14"},
                    {"n": "近30日", "v": "30"},
                    {"n": "近90日", "v": "90"},
                ]}

    def homeContent(self, filter=None):
        classes = []
        for c in self._classes():
            if c["type_id"] == "uncensored" and not self.enable_uncensored:
                continue
            classes.append(dict(c))
        tab_days = [self._tab_group("new"), self._days_group()]
        filters = {}
        for tid in ("av", "uncensored", "fc2"):
            if tid == "uncensored" and not self.enable_uncensored:
                continue
            filters[tid] = list(tab_days)
        # 发售日历：网页 /calendar?date=YYYY-MM-DD
        today = _today()
        date_vals = [{"n": "今日", "v": today}]
        for d in range(1, 15):
            date_vals.append({"n": _shift_days(d), "v": _shift_days(d)})
        filters["calendar"] = [
            {"key": "date", "name": "日期", "init": today,
             "value": date_vals},
        ]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        # 首页推荐：AV 板块最新新作
        data = self._api_get("/v1/lists/new",
                             {"class": "av", "limit": 50, "page": 1})
        works = data.get("items") or data.get("works") or []
        lst = self._works_to_list(works)
        if not lst:
            data = self._api_get("/v1/search",
                                 {"q": "", "class": "av", "limit": 50})
            works = data.get("items") or data.get("works") or []
            lst = self._works_to_list(works)
        return {"list": lst[:50]}

    @staticmethod
    def _page_result(out, page, one_page=False):
        """TVBox 分页结果：有数据才给下一页"""
        if one_page:
            return {"list": out, "page": 1, "pagecount": 1,
                    "limit": len(out), "total": len(out)}
        return {"list": out, "page": page,
                "pagecount": page + 1 if out else page,
                "limit": len(out), "total": len(out)}

    def _list_params(self, fs, page, limit=None):
        """筛选 → lists/new|links|playable 查询参数"""
        limit = limit or self.page_size
        params = {"limit": limit, "page": page}
        tab = _to_text(fs.get("tab") or "new")
        days = _safe_int(fs.get("days"), 7)
        if days < 1:
            days = 7
        if tab == "links":
            path = "/v1/lists/links"
        elif tab == "playable":
            path = "/v1/lists/playable"
        else:
            path = "/v1/lists/new"
            # av 板块网页对「今日」用 since/until；其余用 days
            if days == 1:
                today = _today()
                params["since"] = today
                params["until"] = today
            else:
                params["days"] = days
        return path, params

    def _calendar_list(self, fs, page):
        """发售日历：/v1/calendar?date=YYYY-MM-DD
        items 字段为 {cid,code,cover_url,title,work_id}，需映射成 work id。"""
        date = _to_text(fs.get("date") or "") or _today()
        limit = self.page_size
        data = self._api_get("/v1/calendar",
                             {"date": date, "limit": limit * max(page, 1)})
        works = data.get("items") or data.get("works") or []
        norm = []
        for w in works:
            if not isinstance(w, dict):
                continue
            if not w.get("id") and w.get("work_id"):
                w = dict(w)
                w["id"] = w.get("work_id")
            norm.append(w)
        start = (page - 1) * limit
        chunk = norm[start:start + limit]
        out = self._works_to_list(chunk)
        return self._page_result(out, page, one_page=(len(norm) <= start + limit))

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        t = _to_text(tid)
        page = _safe_int(pg, 1)
        if page < 1:
            page = 1
        fs = {}
        for src in (filter, extend):
            if isinstance(src, dict):
                fs.update(src)

        # 发售日历
        if t == "calendar":
            return self._calendar_list(fs, page)

        # 三大板块：av / uncensored / fc2
        if t not in ("av", "uncensored", "fc2"):
            t = "av"
        if t == "uncensored" and not self.enable_uncensored:
            t = "av"

        path, params = self._list_params(fs, page)
        params["class"] = SECTION_CLASS.get(t, "av")
        data = self._api_get(path, params)
        works = data.get("items") or data.get("works") or []
        out = self._works_to_list(works)
        total = _safe_int(data.get("total"), 0)
        pagecount = page + 1 if out else page
        if total and self.page_size:
            pc = (total + self.page_size - 1) // self.page_size
            if pc > pagecount:
                pagecount = pc
        return {"list": out, "page": page, "pagecount": pagecount,
                "limit": len(out), "total": total or len(out)}

    # ---------- 磁力 / 预览 / 在线解析 ----------
    def _work_links(self, code, number=""):
        """GET /v1/links?code= → [{kind, uri, size_bytes, seeders, ...}]，120s 缓存。
        FANZA 磁力挂在 code（番号）上，不是 work id。"""
        code = _to_text(code or number).strip()
        if not code:
            return []
        now = time.time()
        hit = self._magnets_cache.get(code)
        if hit and now - hit[0] < 120:
            return hit[1]
        data = self._api_get("/v1/links", {"code": code})
        links = data.get("links") if isinstance(data, dict) else None
        out = []
        for g in links or []:
            if not isinstance(g, dict):
                continue
            uri = _to_text(g.get("uri") or "")
            if not uri:
                continue
            # 统一成 hash 字段，下游 _magnet_with_trackers/_magnet_label 可复用
            m = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", uri)
            item = dict(g)
            if m:
                item["hash"] = m.group(1).lower()
            item["name"] = _to_text(g.get("file_name") or "") or code
            item["size"] = _safe_int(g.get("size_bytes"), 0)
            out.append(item)
        self._magnets_cache[code] = (now, out)
        return out

    def _work_magnets(self, mid):
        """兼容旧名：按 work id 取磁力（先查缓存 meta 的 number/code）。"""
        cache = self._vid_meta.get(_to_text(mid)) or {}
        number = _to_text(cache.get("number") or "")
        if not number:
            # 作品详情拿 code
            work = self._get_work(mid)
            number = _to_text(work.get("code") or "")
        return self._work_links(number)

    def _get_work(self, vid, force=False):
        """GET /v1/works/{id}，300s 缓存；失败返回 {}。"""
        vid = _to_text(vid)
        if not vid:
            return {}
        now = time.time()
        hit = self._work_cache.get(vid)
        if hit and not force and now - hit[0] < 300:
            return hit[1]
        data = self._api_get("/v1/works/" + quote(vid, safe=""))
        work = data if isinstance(data, dict) else {}
        if work:
            # 顺手缓存列表期 meta
            self._vid_meta[vid] = {
                "number": _to_text(work.get("code") or ""),
                "title": _to_text(work.get("title") or ""),
                "pic": self._proxy_pic(_to_text(work.get("cover_url") or "")),
                "duration": _safe_int(work.get("duration_sec"), 0),
                "release_date": _to_text(work.get("release_date") or ""),
                "content_class": _to_text(work.get("content_class") or ""),
                "playable": bool(work.get("playable")),
            }
            self._work_cache[vid] = (now, work)
        return work

    def _get_work_by_code(self, code):
        """按番号反查 work（预览伪链播放时用），命中 _vid_meta 则直接取 id。"""
        code = _to_text(code or "").strip()
        if not code:
            return {}
        for vid, meta in list(self._vid_meta.items()):
            if _to_text(meta.get("number") or "").lower() == code.lower():
                return self._get_work(vid)
        # 兜底：search 拿 id 再取详情（带 60s 番号→work 缓存）
        now = time.time()
        hit = getattr(self, "_code_work_cache", None)
        if hit is None:
            self._code_work_cache = {}
            hit = self._code_work_cache
        ckey = code.lower()
        ch = hit.get(ckey)
        if ch and now - ch[0] < 60:
            return ch[1]
        work = {}
        try:
            data = self._api_get("/v1/search",
                                 {"q": code, "class": "av", "limit": 8})
            for w in data.get("items") or []:
                if not isinstance(w, dict):
                    continue
                if _to_text(w.get("code") or "").lower() != ckey:
                    continue
                wid = _to_text(w.get("id") or w.get("work_id") or "")
                if wid:
                    work = self._get_work(wid)
                    break
        except Exception:
            work = {}
        if work:
            hit[ckey] = (now, work)
        return work

    def _dmm_candidates(self, number):
        """DMM 免费预告候选（存在性检查）。3600s 缓存；404=确定无预览。"""
        number = _to_text(number).strip()
        if not number or self.s is None:
            return []
        now = time.time()
        hit = self._dmm_cache.get(number)
        if hit and now - hit[0] < 3600:
            return hit[1]
        out, definitive = [], False
        try:
            data = self._site_get(self.preview_api, params={"code": number},
                                  timeout=12)
            if data and isinstance(data.get("urls"), list):
                for c in data.get("urls") or []:
                    if not isinstance(c, dict):
                        continue
                    u = _to_text(c.get("url") or "")
                    if not u.startswith(("https://", "http://")):
                        continue
                    typ = _to_text(c.get("type") or "")
                    if typ not in ("mp4", "hls"):
                        typ = "hls" if ".m3u8" in u.lower() else "mp4"
                    out.append({"url": u, "type": typ,
                                "via": _to_text(c.get("via") or "")})
                definitive = True
            elif data.get("status_code") in (400, 404):
                definitive = True
            elif data.get("status_code") == 200 and not data.get("urls"):
                definitive = True
        except Exception:
            definitive = False
        if definitive:
            self._dmm_cache[number] = (now, out)
        return out

    def _probe_preview(self, number, work=None):
        """播放时逐候选探测预告。候选可用性会抖动，故不缓存探测结果。
        work 上的 sample_movie_url / sample_hls_url 作为 DMM API 之外的兜底。"""
        cands = list(self._dmm_candidates(number) or [])
        if work and isinstance(work, dict):
            seen = set(_to_text(c.get("url") or "") for c in cands)
            for key, typ in (("sample_movie_url", "mp4"),
                             ("sample_hls_url", "hls")):
                u = _to_text(work.get(key) or "")
                if u.startswith(("https://", "http://")) and u not in seen:
                    if typ == "hls" and ".m3u8" not in u.lower():
                        typ = "mp4"
                    cands.append({"url": u, "type": typ, "via": "work"})
                    seen.add(u)
        if not cands or self.s is None:
            return ""
        headers = {"User-Agent": self.ua, "Referer": self.host + "/",
                   "Accept": "*/*"}
        deadline = time.time() + 10
        for c in cands:
            remain = deadline - time.time()
            if remain <= 0:
                break
            t = min(4, remain)
            try:
                if c.get("type") == "hls":
                    r = self.s.get(c["url"], headers=headers, timeout=t,
                                   verify=self.verify)
                    ok = r.status_code in (200, 206) and \
                        r.content[:32].lstrip().startswith(b"#EXTM3U")
                else:
                    r = self.s.head(c["url"], headers=headers, timeout=t,
                                    verify=self.verify, allow_redirects=True)
                    ok = r.status_code in (200, 206)
                if ok:
                    return c["url"]
            except Exception:
                continue
        return ""

    def _resolve_variants(self, code, content_class="av"):
        """GET /api/rv/v1/resolve?code=&type= → variants[]（可能超时/404）。
        type 映射：av→av / uncensored→uc / fc2→fc2。"""
        code = _to_text(code)
        if not code:
            return []
        rtype = RESOLVE_TYPE.get(_to_text(content_class) or "av", "av")
        try:
            data = self._site_get(self.resolve_api,
                                  params={"code": code, "type": rtype},
                                  timeout=20)
        except Exception:
            return []
        variants = data.get("variants") if isinstance(data, dict) else None
        out = []
        for v in variants or []:
            if not isinstance(v, dict):
                continue
            u = _to_text(v.get("sourceUrl") or v.get("url") or "")
            if not u:
                continue
            out.append({
                "url": u,
                "label": _to_text(v.get("label") or v.get("variant") or "在线"),
                "poster": _to_text(v.get("poster") or ""),
            })
        return out

    def _data_uri_to_url(self, u):
        """data:application/vnd.apple.mpegurl,... → 解出 m3u8 文本里的首条 http 地址。
        data URI 本体播放器不认，必须还原。"""
        u = _to_text(u)
        if not u.startswith("data:"):
            return u
        try:
            if "," not in u:
                return ""
            header, body = u.split(",", 1)
            if ";base64" in header:
                text = base64.b64decode(body).decode("utf-8", "ignore")
            else:
                from urllib.parse import unquote as _un
                text = _un(body)
            # m3u8：取第一条绝对 http 行；否则整段当直链尝试
            for line in text.splitlines():
                line = line.strip()
                if line.startswith(("http://", "https://")):
                    return line
            if text.strip().startswith(("http://", "https://")):
                return text.strip()
        except Exception:
            return ""
        return ""

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        if not vid:
            return {"list": []}

        work = self._get_work(vid)
        cache = self._vid_meta.get(vid) or {}
        if not work and not cache:
            return {"list": []}

        number = _to_text(work.get("code") or cache.get("number") or "")
        title = _to_text(work.get("title") or cache.get("title") or number or vid)
        pic = self._proxy_pic(_to_text(
            work.get("cover_url") or cache.get("pic") or ""))
        date = _to_text(work.get("release_date") or cache.get("release_date") or "")
        content_class = _to_text(work.get("content_class") or cache.get("content_class") or "av")
        playable = bool(work.get("playable") or cache.get("playable"))
        playable_until = _to_text(work.get("playable_until") or "")
        dur = _safe_int(work.get("duration_sec") or cache.get("duration"), 0)
        desc = _to_text(work.get("description") or "")

        # 实体信息
        ents = work.get("entities") if isinstance(work.get("entities"), dict) else {}
        def _enames(kind):
            rows = ents.get(kind) or []
            out = []
            for a in rows:
                if isinstance(a, dict):
                    n = _to_text(a.get("name") or "")
                    if n:
                        out.append(n)
                elif isinstance(a, str) and a:
                    out.append(a)
            return out
        actors = _enames("actress")
        directors = _enames("director")
        genres = _enames("genre")
        labels = _enames("label")
        makers = _enames("maker")

        # 磁力
        links = self._work_links(number) if number else []
        magnets = [g for g in links if _to_text(g.get("uri") or "").startswith("magnet:")]
        if not magnets:
            magnets = [g for g in links if _to_text(g.get("hash") or "")]

        info_lines = []
        if number:
            info_lines.append("番号: %s" % number)
        if date:
            info_lines.append("发行: %s" % date[:10])
        if dur:
            info_lines.append("时长: %d分钟" % (dur // 60 if dur > 10000 else dur))
        if makers:
            info_lines.append("片商: %s" % "、".join(makers))
        if labels:
            info_lines.append("厂牌: %s" % "、".join(labels))
        if directors:
            info_lines.append("导演: %s" % "、".join(directors))
        if actors:
            info_lines.append("演员: %s" % "、".join(actors))
        if genres:
            info_lines.append("类别: %s" % "、".join(genres))
        if playable:
            until = ("至 %s" % playable_until[:16]) if playable_until else ""
            info_lines.append("在线可播%s" % until)
        if magnets:
            info_lines.append("磁力 %d 条" % len(magnets))
        elif number:
            info_lines.append("暂无磁力")
        if desc:
            info_lines.append(desc[:500])
        if self.enable_offline_115:
            info_lines.append("115离线：提交到115云端，完成后自动直连播放 (v%s)" % VERSION)

        # 播放源：预览 → 在线 → 磁力 → 115离线
        play_from = []
        play_url = []

        # 预览（伪链，playerContent 探测）：DMM 候选或 work 自带样片
        sample_mv = _to_text(work.get("sample_movie_url") or "")
        sample_hls = _to_text(work.get("sample_hls_url") or "")
        has_sample = bool(sample_mv.startswith(("http://", "https://"))
                          or sample_hls.startswith(("http://", "https://")))
        if number and (self._dmm_candidates(number) or has_sample):
            play_from.append("預覽")
            play_url.append("預覽$%s" % _sanitize_play(PREVIEW_PREFIX + number))

        # 在线解析（伪链，playerContent 取 variants）
        if playable and number:
            play_from.append("在线")
            play_url.append("在线$%s" % _sanitize_play(
                RESOLVE_PREFIX + "%s|%s" % (number, content_class)))

        # 磁力直链
        if self.enable_magnet and magnets:
            eps = []
            for i, g in enumerate(magnets):
                uri = _to_text(g.get("uri") or "")
                h = _to_text(g.get("hash") or "")
                mag = uri if uri.startswith("magnet:") else (
                    _magnet_with_trackers(h) if h else "")
                if not mag:
                    continue
                label = _magnet_label(g, i)
                eps.append("%s$%s" % (_sanitize_play(label), _sanitize_play(mag)))
            if eps:
                play_from.append("磁力")
                play_url.append("#".join(eps))

        # 115离线
        if self.enable_offline_115 and magnets:
            eps = []
            for i, g in enumerate(magnets):
                uri = _to_text(g.get("uri") or "")
                h = _to_text(g.get("hash") or "")
                mag = uri if uri.startswith("magnet:") else (
                    "magnet:?xt=urn:btih:" + h if h else "")
                if not mag:
                    continue
                label = _magnet_label(g, i)
                b64 = _off_id_encode(mag, title, label, number)
                eps.append("%s$%s%s?t=%d" % (
                    _sanitize_play(label), OFF_PREFIX_115, b64, int(time.time())))
            if eps:
                play_from.append("115离线")
                play_url.append("#".join(eps))

        _blurb = " | ".join([b for b in (
            number, (date or "")[:10],
            "、".join(actors[:4]),
            "、".join(makers[:1]),
        ) if b])

        class_name = {"av": "AV", "uncensored": "无码", "fc2": "FC2"}.get(
            content_class, content_class)
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": "\n".join(info_lines),
            "vod_blurb": _blurb,
            "vod_desc": "\n".join(info_lines),
            "vod_year": (date or "")[:4],
            "vod_director": "、".join(directors),
            "vod_actor": "、".join(actors),
            "vod_genre": "、".join(genres),
            "vod_remarks": number or class_name,
            "vod_tag": "",
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url) if play_url else "",
        }
        return {"list": [vod]}

    # ---------- 搜索（对齐网页：多 class 合并；上游无 offset → 客户端切片分页） ----------
    def searchContent(self, key, quick=False, pg="1"):
        page = _safe_int(pg, 1)
        if page < 1:
            page = 1
        keyword = _to_text(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.search_limit, "total": 0}

        ck = "%s|%d" % (keyword, page)
        now = time.time()
        hit = self._search_cache.get(ck)
        if hit and now - hit[0] < 300:
            lst, total = hit[1], hit[2]
            return {"list": lst, "page": page,
                    "pagecount": self._search_pagecount(total, page),
                    "limit": len(lst), "total": total}

        # /v1/search 只认 limit，不支持 offset/page → 拉 page*limit 后切片
        fetch_limit = self.search_limit * page
        classes = ["av"]
        if self.enable_uncensored:
            classes.append("uncensored")
        classes.append("fc2")

        merged = {}
        total_est = 0
        for cls in classes:
            data = self._api_get("/v1/search", {
                "q": keyword, "class": cls, "limit": fetch_limit,
            })
            works = data.get("items") or data.get("works") or []
            total_est += _safe_int(data.get("total"), len(works))
            for w in works:
                if not isinstance(w, dict):
                    continue
                wid = _to_text(w.get("id") or "")
                if wid and wid not in merged:
                    merged[wid] = w

        # 按 release_date 倒序（对齐网页）
        def _sort_key(w):
            return _to_text(w.get("release_date") or "")
        rows = sorted(merged.values(), key=_sort_key, reverse=True)

        start = (page - 1) * self.search_limit
        chunk = rows[start:start + self.search_limit]
        lst = self._works_to_list(chunk)
        total = total_est or len(rows)
        if len(self._search_cache) > 64:
            self._search_cache.clear()
        self._search_cache[ck] = (now, lst, total)
        return {"list": lst, "page": page,
                "pagecount": self._search_pagecount(total, page),
                "limit": len(lst), "total": total}

    @staticmethod
    def _search_pagecount(total, page):
        # search 无可靠 page 上限：有下一页数据就多给 1 页
        return page + 1 if total > page * 30 else page

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
            r = sess.post(url, data=body, headers=headers, timeout=12, verify=self.verify)
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
                              verify=self.verify)
            else:
                r = sess.get(url, params=params or {}, headers=headers,
                             timeout=timeout, verify=self.verify)
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
    def _offline_new_name(cls, title, orig, label="", number=""):
        title = cls._safe_name(title)
        orig = cls._safe_name(orig)
        label = cls._safe_name(label)
        number = cls._safe_name(number)
        if not title:
            name = orig
        elif label:
            ext = os.path.splitext(orig)[1]
            tail = label if (not ext or label.lower().endswith(ext.lower())) \
                else label + ext
            if tail == title:
                name = orig
            else:
                name = "%s_%s" % (title, tail)
                if len(name) > 140:
                    room = max(8, 140 - len(tail) - 1)
                    name = "%s_%s" % (title[:room], tail)
                if name == orig:
                    name = orig
        elif orig == title or orig.startswith(title + "_"):
            name = orig
        else:
            name = "%s_%s" % (title, orig)
        # 番号前置（ABF-390_xxx）；已带该番号则不重复加
        if number and name and not name.startswith(number):
            name = "%s_%s" % (number, name)
        return name

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

    def _tidy_file(self, info, name, title="", label="", deadline=0,
                   number=""):
        pc = info.get("pc") or info.get("pick_code") or ""
        fid = _to_text(info.get("fid") or "")
        orig = _to_text(info.get("n") or info.get("name") or name)
        new = self._offline_new_name(title, orig, label, number)
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
            }, headers=headers, timeout=10, verify=self.verify)
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

    def _tidy_folder(self, info, name, title, label="", deadline=0,
                     number=""):
        cid = _to_text(info.get("cid") or info.get("fid") or "")
        if deadline and time.time() >= deadline:
            return "", _to_text(name)
        video, _src = self._offline_find_video(cid, deadline=deadline) if cid else (None, "")
        if not video:
            return "", _to_text(name)
        fid = _to_text(video.get("fid") or "")
        vpc = _to_text(video.get("pc") or video.get("pick_code") or "")
        orig = _to_text(video.get("n") or video.get("name") or "")
        new = self._offline_new_name(title, orig, label, number)
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

    def _offline_tidy(self, pc, name, title="", label="", deadline=0,
                      number=""):
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
                return self._tidy_folder(info, name, title, label,
                                         deadline=deadline, number=number)
            return self._tidy_file(info, name, title, label,
                                   deadline=deadline, number=number)
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
                        allow_search=True, t0=None, number=""):
        name = _to_text(name).strip()
        title = _to_text(title).strip()
        label = _to_text(label).strip()
        number = _to_text(number).strip()
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
                                         deadline=deadline, number=number)
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

    def _play_offline_safe(self, magnet, title="", label="", number=""):
        t0 = time.time()
        try:
            res = self._submit_offline_115(magnet, title, label, number)
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

    def _submit_offline_115(self, magnet, title="", label="", number=""):
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
                                            allow_search=True, t0=t0,
                                            number=number)
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
                                            allow_search=True, t0=t0,
                                            number=number)
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
                                                allow_search=True, t0=t0,
                                                number=number)
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
                                       title=title, label=label, allow_search=True, t0=t0,
                                       number=number)
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
                                   title=title, label=label, allow_search=False, t0=t0,
                                   number=number)
        if res.get("url") or not early_fail:
            return res
        return early_fail

    # ==================== 播放 ====================

    def _offline_test_result(self):
        """二分实验：ext.offlineTestMp4 打开时，115 离线入口直接回公开测试片。

        noheader → url + format，不带 header（判断 result 结构本身能不能播）
        header   → 再带上 UA/Referer（判断 header 通道有没有被 App 吞掉）
        """
        mode = self.offline_test_mp4
        with_header = mode in ("header", "withheader", "1", "true", "yes")
        res = {"parse": 0, "jx": 0, "playUrl": "", "url": OFFLINE_TEST_MP4,
               "format": "video/mp4", "header": dict(OFFLINE_TEST_HEADER)
               if with_header else {}}
        res["desc"] = ("[实验] offlineTestMp4=%s（公开测试片，未走115）\n"
                       "能播 → result 结构没问题，锅在 115 直链/header；"
                       "不能播 → 结构/被 App 处理坏了" % mode)
        self._set_off_last("实验直链 offlineTestMp4=%s" % mode)
        return res

    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        self._set_off_last("收到播放请求：%s" % _to_text(vid)[:50])

        # 二分实验：只劫持 115 离线入口（占位 id / 演员列表的裸番号），其它一律不碰
        if self.offline_test_mp4 and (vid.startswith(OFF_PREFIX_115)
                                      or vid.startswith("115off:")
                                      or (len(vid) <= 12
                                          and re.match(r"^[A-Za-z0-9]+$", vid))):
            return self._offline_test_result()

        if vid.startswith(OFF_PREFIX_115):
            magnet, title, label, number = _off_id_decode(vid[len(OFF_PREFIX_115):])
            if not magnet:
                return _play_err("磁力解码失败")
            return self._play_offline_safe(magnet, title, label, number)

        if vid.startswith("115off:"):
            return self._play_offline_safe(vid[len("115off:"):].strip())

        # 预览伪链：详情页只存番号，真正地址在这里逐候选探测
        if vid.startswith(PREVIEW_PREFIX):
            code = vid[len(PREVIEW_PREFIX):].strip()
            work = self._get_work_by_code(code) if code else None
            url = self._probe_preview(code, work) if code else ""
            if url:
                return {
                    "parse": 0, "jx": 0, "playUrl": "", "url": url,
                    "header": {"User-Agent": self.ua,
                               "Referer": self.host + "/", "Accept": "*/*"},
                }
            return _play_err("预览暂不可用（候选全部失效），请稍后重试或改用磁力")

        # 在线解析伪链：msdars/{code}|{class} → resolve variants
        if vid.startswith(RESOLVE_PREFIX):
            payload = vid[len(RESOLVE_PREFIX):].strip()
            if "|" in payload:
                code, content_class = payload.split("|", 1)
            else:
                code, content_class = payload, "av"
            variants = self._resolve_variants(code, content_class)
            last_err = ""
            for v in variants:
                u = self._data_uri_to_url(v.get("url") or "")
                if not u:
                    last_err = "data URI 无法还原"
                    continue
                if u.startswith(("http://", "https://")):
                    return {
                        "parse": 0, "jx": 0, "playUrl": "", "url": u,
                        "header": {"User-Agent": self.ua,
                                   "Referer": self.host + "/", "Accept": "*/*"},
                    }
            return _play_err("在线解析暂不可用（%s），请改用磁力或115离线"
                             % (last_err or "无可用源"))

        if vid.startswith("magnet:"):
            m = _normalize_magnet(vid)
            return {
                "parse": 0, "jx": 0, "playUrl": "",
                "url": m or vid,
                "header": {"User-Agent": self.ua, "Accept": "*/*"},
            }

        # 预览片等直链（m3u8/mp4）：直接透传播放，不再落到空 url
        if vid.startswith(("http://", "https://")) \
                and re.search(r"\.(m3u8|mp4|flv|mkv|ts|avi)(\?|$)", vid, re.I):
            return {
                "parse": 0, "jx": 0, "playUrl": "",
                "url": vid,
                "header": {"User-Agent": self.ua, "Referer": self.host + "/",
                           "Accept": "*/*"},
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
                            magnet, title, label, number = _off_id_decode(
                                ep_id[len(OFF_PREFIX_115):].split("?")[0])
                            if magnet:
                                return self._play_offline_safe(magnet, title, label, number)
            except Exception:
                pass

        return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

    @staticmethod
    def _parse_proxy_param(param):
        """localProxy 入参兼容：dict / JSON 字符串 / query string（值做 urldecode）"""
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
        """token → 原图 URL（urlsafe base64，无 padding；失败返回空）"""
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
            body = self._offline_srt(param.get("v") or "")
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
                "X-Content-Type-Options": "nosniff",
            }]
        return [404, "text/plain", b"Not Found", {}]

    def _fetch_pic(self, url, max_raw=0):
        """下载封面并解码 XOR/AES 加密（localProxy kind=image 用；带内存+磁盘缓存）。
        - 缓存键去掉 ?auth_key= 查询串——cover 的 auth_key 会轮换，
          带着它做键会导致每次冷启动都重新下载+重新解密。
        - max_raw>0 时密文超限直接返回：AES-CBC padding-none 等长，
          2MB PNG 解完也超预算，先跳过可省掉十几秒白解。"""
        if not requests or not url.startswith(("http://", "https://")):
            return b"", ""
        cache = getattr(self, "_pic_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._pic_cache = cache
        ckey = url.split("?", 1)[0]
        hit = cache.get(ckey)
        now = time.time()
        if hit and now - hit[0] <= 1800:
            # LRU touch
            del cache[ckey]
            cache[ckey] = hit
            return hit[1], hit[2]
        # 磁盘缓存（跨重启；键=ckey 的 md5）。带 v2 后缀：旧版本缓存的是
        # 1440x1920 原图，换键后自动重下重解成降采样小图，老缓存自然废弃。
        dkey = hashlib.md5((ckey + "|v2").encode("utf-8")).hexdigest()
        dpath = os.path.join(PIC_DISK_DIR, dkey)
        # 磁盘里存的是解码后的成品，与 max_raw 无关，命中即回
        try:
            if os.path.isfile(dpath):
                with open(dpath, "rb") as f:
                    blob = f.read()
                # 文件头 4 字节存 mime 长度+mime，其余为图片数据
                if len(blob) > 4:
                    mlen = blob[0]
                    mime = blob[1:1 + mlen].decode("ascii", "ignore")
                    body = blob[1 + mlen:]
                    if body:
                        cache[ckey] = (now, body, mime)
                        return body, mime
        except Exception:
            pass
        headers = {
            "User-Agent": WEB_UA,
            "Referer": self.host + "/",
            "Accept": "image/*,*/*",
        }
        sess = self.s
        try:
            if sess is None:
                raise RuntimeError("no session")
            r = sess.get(url, headers=headers, timeout=self.timeout,
                         verify=self.verify)
        except Exception:
            # destroy 后会话被关 / 会话异常：临时直连兜底（自建图片服务不能因此断图）
            try:
                r = requests.get(url, headers=headers, timeout=self.timeout,
                                 verify=self.verify)
            except Exception:
                return b"", ""
        if r.status_code != 200 or not r.content:
            return b"", ""
        raw = r.content
        if max_raw and len(raw) > max_raw:
            # 密文等长于明文 → 解完也超限，不解直接留空
            return b"", ""
        body, mime = self._decode_pic(
            raw, _to_text(r.headers.get("Content-Type") or ""))
        if body:
            # Android 上把 1440x1920 的大封面降采样（缓存里也存小图）
            body, mime = _shrink_pic(body, mime)
            cache[ckey] = (now, body, mime)
            while len(cache) > 64:
                cache.pop(next(iter(cache)), None)
            try:
                if not os.path.isdir(PIC_DISK_DIR):
                    os.makedirs(PIC_DISK_DIR, exist_ok=True)
                mb = (mime or "image/jpeg").encode("ascii", "ignore")[:200]
                with open(dpath, "wb") as f:
                    f.write(bytes([len(mb)]) + mb + body)
                # 缓存不设上限会一路涨（盒子存储有限），每 64 张清一次最旧的
                self._pic_writes = getattr(self, "_pic_writes", 0) + 1
                if self._pic_writes % 64 == 0:
                    _prune_pic_cache()
            except Exception:
                pass
        return body, mime

    @staticmethod
    def _pic_mime(raw):
        if raw[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if raw[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if len(raw) > 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return "image/webp"
        if raw[:2] == b"BM":
            return "image/bmp"
        return ""

    @classmethod
    def _decode_pic(cls, raw, ctype=""):
        """网页端同款解码：① 首字节为 XOR 密钥 ② 0x7F 定值密钥（跳过 0..2）
        ③ AI 封面 AES-128-CBC（pic.drleao.cn，Content-Type: binary/octet-stream，
        密文长度必为 16 倍数）。
        解不出且 Content-Type 是图片则原样返回；否则返回空（404）。"""
        raw = bytes(raw or b"")
        if not raw:
            return b"", ""
        mime = cls._pic_mime(raw)
        if mime:
            return raw, mime
        if len(raw) > 16:
            key = raw[0]
            head = bytes(raw[i] ^ key for i in range(1, min(len(raw), 14)))
            if cls._pic_mime(head):
                dec = bytes(b ^ key for b in raw[1:])
                return dec, cls._pic_mime(dec)
            for skip in (0, 1, 2):
                head = bytes(raw[i] ^ 0x7F
                             for i in range(skip, min(len(raw), skip + 13)))
                if cls._pic_mime(head):
                    dec = bytes(raw[i] ^ 0x7F for i in range(skip, len(raw)))
                    return dec, cls._pic_mime(dec)
            if len(raw) % 16 == 0:
                # FANZA 封面一般为明文，AES 分支仅作旧缓存兼容（无密钥则跳过）
                pass
        ct = _to_text(ctype).split(";")[0].strip().lower()
        if ct.startswith("image/"):
            return raw, ct
        return b"", ""

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
        if u.startswith(PREVIEW_PREFIX) or u.startswith(RESOLVE_PREFIX):
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


# 命令行自检：python3 msda.py（不影响宿主加载）
if __name__ == "__main__":
    sp = Spider()
    sp.init("")
    print("VERSION", VERSION)
    hc = sp.homeContent()
    print("classes", [c.get("type_id") for c in (hc.get("class") or [])],
          "filters", list((hc.get("filters") or {}).keys()))
    for tid in ("av", "uncensored", "fc2", "calendar"):
        try:
            r = sp.categoryContent(tid, "1", {}, {}) or {}
            lst = r.get("list") or []
            print(tid, "n=%d" % len(lst),
                  "pagecount=%s" % r.get("pagecount"),
                  "sample=%s" % ((lst[0] or {}).get("vod_name", "")[:40] if lst else ""))
        except Exception as e:
            print(tid, "ERR", type(e).__name__, str(e)[:80])
    # tabs
    for tab in ("links", "playable"):
        try:
            r = sp.categoryContent("av", "1", {"tab": tab, "days": "7"}, {}) or {}
            print("av/%s" % tab, "n=%d" % len(r.get("list") or []))
        except Exception as e:
            print("av/%s" % tab, "ERR", type(e).__name__, str(e)[:80])
    # search
    try:
        r = sp.searchContent("SSIS") or {}
        print("search n=%d total=%s" % (len(r.get("list") or []), r.get("total")))
    except Exception as e:
        print("search ERR", type(e).__name__, str(e)[:80])
    # detail + magnet play sources
    try:
        lst = (sp.categoryContent("av", "1", {"tab": "new"}, {}) or {}).get("list") or []
        if lst:
            vid = lst[0].get("vod_id")
            d = sp.detailContent([vid]) or {}
            vod = (d.get("list") or [{}])[0]
            froms = _to_text(vod.get("vod_play_from") or "").split("$$$")
            plays = _to_text(vod.get("vod_play_url") or "").split("$$$")
            print("detail", vid, "name=", (vod.get("vod_name") or "")[:40])
            for i, f in enumerate(froms):
                eps = plays[i].split("#") if i < len(plays) else []
                print("  source", f, "eps", len(eps),
                      "sample", (eps[0].split("$")[0] if eps else "")[:40])
            # magnet direct play structure
            for i, f in enumerate(froms):
                if f == "磁力" and i < len(plays) and plays[i]:
                    mag = plays[i].split("#")[0].split("$", 1)[-1]
                    pr = sp.playerContent("磁力", [mag])
                    print("  player magnet url=", (pr.get("url") or "")[:50],
                          "err=", pr.get("msg") or "")
                    break
            # 115 off prefix structure
            for i, f in enumerate(froms):
                if f == "115离线" and i < len(plays) and plays[i]:
                    eid = plays[i].split("#")[0].split("$", 1)[-1]
                    print("  115off id ok=", eid.startswith(OFF_PREFIX_115))
                    break
    except Exception as e:
        print("detail ERR", type(e).__name__, str(e)[:80])
    print("SELFTEST DONE")
