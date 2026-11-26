# -*- coding: utf-8 -*-
VERSION = "1.0.6"
# msda.py —— FANZA METADATA INDEX (fanza.fastcdn.dpdns.org) 爬虫
# 参照 javdbui.py 结构：分类/筛选与网页端对齐；磁力 + 115 离线可播放。
# 网页板块：AV档案(/) / 无码档案(/uncensored) / FC2档案(/fc2) / 发售日历(/calendar)
# 列表页签：全部新作(lists/new) / 有磁链(lists/links) / 可播(lists/playable)
# 数据 API：fanza-api.fastcdn.dpdns.org/v1/*；播放解析：站点 /api/rv/v1/resolve
# 说明：Cloudflare 对普通 requests + Chrome UA 直接 403；优先 curl_cffi 指纹，无指纹时改 okhttp 头兜底。
# v1.0.6 在线 HLS data URI 落本机 .m3u8：_data_uri_to_text 完整解码校验 #EXTM3U，本地 ThreadingHTTPServer(/msda/<token>.m3u8) 交完整播放列表，修 OK影视 只播首分片；服务不可用回退 _play_err 不再取首分片。
# v1.0.5 115 离线选集标签：显示名改 [大小 格式 去码] 磁力文件名（_offline_episode_label，仅展示、off id 的 l 仍走 _magnet_label 短标签）；格式只认容器词（mp4/mkv/avi/mov/wmv/flv/ts/webm/rmvb/m2ts/m4v），h265/hevc/avc 等编码词不算，file_name 无容器词则不显示格式；tags 含 cracked 或文件名含 破解/Mosaic/去码 → 括号内加「去码」；展示名剥前导 [..] 块。
# v1.0.4 查验修复：①日历分页锁死 199（total 被 limit 截断）→ 单次拉 500 本地分页、total/pagecount 精确；②时长全链路缺失（duration_sec 在 versions[] 非顶层）→ _work_duration 取版本时长，恒秒转分废除 >10000 启发式（3664 分钟误显消失）；③FC2-* 反查硬编码 class=av 必空 → 按前缀选类+跨类兜底；④playerContent 裸番号分支只认 115 → 115→磁力→预览→在线 四级回退，终兜底带 msg 不再空 url 黑屏；⑤429 移出自动重试（对齐网页）；⑥task_del 删后确认 max_page=2 漏深页误判「已删」→ max_page=0 按 page_count 全页扫（上限 30 页）；⑦日历筛选补未来 14 天「预定」（接口实测有数据）；⑧has_source 消费为「有源」徽章；⑨分类名/顺序对齐网页（AV 档案→FC2 档案→无码档案）+ 筛选同步；⑩时间窗收敛 7/14/30；⑪删 _api_action 死字段；⑫_search_pagecount 用 search_limit、搜索 fetch 触顶 500、空页 pagecount 收口；⑬_vid_meta 超 128 淘汰最旧 1/4。
# v1.0.3 115 离线可用性：①失败任务不再永久卡死——ac=task_del(hash[0]) 删旧后自动重提；②/v1/links 失败/error 不写 120s 空缓存；③等待超时可配 ext.offlinePollTimeout（默认 20s），文案改为「云端下载中非失败」；④详情标注无做种/源站无磁链。
# v1.0.2 详情/磁力/115 对齐参照与网页：①size_bytes 误当 MB 致标签「7235174.40GB」→ 换算成 MB（6.90GB），115 命名不再带天文数字；②实体字段 name_ja（非 name）→ 演员/类别/简介恢复；③磁力只用 hash 重建+公共 tracker（去上游 dn=），115 用裸 btih，与 javdbui 同构；④vod_blurb 按 番号|日期|片商|导演|演员。
# v1.0.1 修复应用侧（无 curl_cffi）分类空列表：Chrome UA 被 CF 打回 403 HTML → 无指纹时用 okhttp 头，403/HTML/JSON 失败自动换头重试。
# v1.0.0 初版：板块/筛选/列表/详情/搜索/磁力+115 离线对齐网页端。
import os
import re
import json
import time
import datetime
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
# 日历单日全量上限：接口 total 被 limit 截断，一次拉全后本地分页才能拿到真实总量
CALENDAR_FETCH_MAX = 500
# 搜索单次拉取上限（page*limit 线性增长的护栏；30*17=510 → 深页封顶）
SEARCH_FETCH_MAX = 500
# 115 离线任务列表扫描上限（删除确认按 page_count 全页扫，防失控）
OFFLINE_FIND_MAX_PAGES = 30

# 网页板块 type_id → 上游 class 参数（注意：上游认 uncensored，不认 uc）
# resolve 的 type 参数另用 av/uc/fc2（前端 Hn 映射）
SECTION_CLASS = {"av": "av", "uncensored": "uncensored", "fc2": "fc2"}
# resolve type 映射（content_class → resolve?type=）
RESOLVE_TYPE = {"av": "av", "uncensored": "uc", "fc2": "fc2"}
# content_class 值域
CONTENT_CLASSES = ("av", "uncensored", "fc2")

HTTP_RETRY = 1
HTTP_RETRY_DELAY = 0.5
# 429 不自动重试（对齐网页端「HTTP 429 · 不自动重试」），避免限流时反复打接口
HTTP_RETRY_STATUS = (500, 502, 503, 504)

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

LIST_HEADERS = {
    "User-Agent": WEB_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
}
# 无 curl_cffi 指纹时：Chrome UA + Accept-Language 会被 Cloudflare 打回 403 HTML。
# 实测 okhttp / 简洁 Mozilla UA 可直接拿到 JSON，作 requests 兜底头。
LIST_HEADERS_PLAIN = {
    "User-Agent": "okhttp/3.12.1",
    "Accept": "application/json, text/plain, */*",
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
OFFLINE_POLL_TIMEOUT = 20
OFFLINE_POLL_INTERVAL = 1
OFFLINE_FINISH_BUDGET = 9
OFFLINE_TASK_DEL_API = "https://115.com/web/lixian/?ct=lixian&ac=task_del"
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


def _offline_episode_label(g, idx):
    """115 离线选集显示名：[大小 格式 去码] 磁力文件名。
    仅用于详情页展示；编入 off id 的功能标签仍走 _magnet_label。
    格式只认容器词（mp4/mkv/...），h265/hevc 等编码词不算；
    file_name 无容器词则不显示格式。去码 = tags 含 cracked 或
    文件名含 破解/Mosaic/去码。展示名剥前导 [..] 块。"""
    name = _to_text(g.get("name") or g.get("file_name") or "")
    raw = _safe_int(g.get("size_bytes"), 0)
    if raw <= 0:
        try:
            raw = int(float(g.get("size") or 0) * 1024 * 1024)
        except Exception:
            raw = 0
    parts = []
    if raw > 0:
        if raw >= 1024 ** 3:
            parts.append("%.1fG" % (raw / float(1024 ** 3)))
        else:
            parts.append("%.0fM" % (raw / float(1024 ** 2)))
    m = re.search(
        r"(?<![a-z0-9])(mp4|mkv|avi|mov|wmv|flv|ts|webm|rmvb|m2ts|m4v)(?![a-z0-9])",
        name, re.I)
    if m:
        parts.append(m.group(1).lower())
    tags = g.get("tags") or []
    cracked = (isinstance(tags, (list, tuple)) and
               any(_to_text(t).lower() == "cracked" for t in tags))
    if not cracked:
        cracked = bool(re.search(r"破解|mosaic|去码", name, re.I))
    if cracked:
        parts.append("去码")
    show = re.sub(r"^(?:\s*\[[^\]]*\])+\s*", "", name).strip() or name
    if parts and show:
        return "[%s] %s" % (" ".join(parts), show)
    if show:
        return show
    return _magnet_label(g, idx)


# ==================== 日期工具 ====================

def _today():
    # 固定 UTC+8（对齐网页浏览器时区；UTC 服务器凌晨 0-8 点不再差一天）
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + 8 * 3600))


def _shift_days(days):
    return time.strftime("%Y-%m-%d",
                         time.gmtime(time.time() - days * 86400 + 8 * 3600))


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


# ==================== 本地 HLS 播放列表服务 ====================
# 在线 resolve 返回的 data URI 是完整 M3U8（可达 128KB），播放器不认 data:，
# 也绝不能只取首行分片（那只是 4 秒片段）。这里把它缓存到内存，用本机
# ThreadingHTTPServer 交出真正的 .m3u8 地址；分片在列表里都是绝对 https，
# 播放器自行拉取，无需代理分片。参照 javdbui.py 自建图片服务同款做法。
_HLS_CACHE = {}            # token -> (ts, text)
_HLS_CACHE_MAX = 8
_HLS_TTL = 1800
_HLS_SRV = {"base": "", "tried": False}
_HLS_SRV_LOCK = threading.Lock()


def _hls_put(text):
    """缓存完整 m3u8 文本，返回 token（内容 sha1 前 16 位）。"""
    tok = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    now = time.time()
    for k in [k for k, (ts, _) in list(_HLS_CACHE.items())
              if now - ts >= _HLS_TTL]:
        _HLS_CACHE.pop(k, None)
    if len(_HLS_CACHE) >= _HLS_CACHE_MAX and tok not in _HLS_CACHE:
        oldest = min(_HLS_CACHE, key=lambda k: _HLS_CACHE[k][0])
        _HLS_CACHE.pop(oldest, None)
    _HLS_CACHE[tok] = (now, text)
    return tok


def _hls_server_base():
    """懒启动 127.0.0.1 本地服务，返回 base（http://127.0.0.1:port）或 ""。"""
    if _HLS_SRV["base"]:
        return _HLS_SRV["base"]
    if _HLS_SRV["tried"]:
        return ""
    with _HLS_SRV_LOCK:
        if _HLS_SRV["base"]:
            return _HLS_SRV["base"]
        if _HLS_SRV["tried"]:
            return ""
        _HLS_SRV["tried"] = True
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

            class _HlsHandler(BaseHTTPRequestHandler):
                server_version = "msda-hls"

                def log_message(self, fmt, *args):
                    pass                # 电视端 stdout 很贵，别刷日志

                def _serve(self, with_body):
                    path = (self.path or "").split("?", 1)[0]
                    body = b""
                    if path.startswith("/msda/") and path.endswith(".m3u8"):
                        tok = path[len("/msda/"):-len(".m3u8")]
                        ent = _HLS_CACHE.get(tok)
                        if ent and time.time() - ent[0] < _HLS_TTL:
                            body = ent[1].encode("utf-8")
                    if not body:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type",
                                     "application/vnd.apple.mpegurl")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    if with_body:
                        self.wfile.write(body)

                def do_GET(self):
                    self._serve(True)

                def do_HEAD(self):
                    self._serve(False)

            httpd = ThreadingHTTPServer(("127.0.0.1", 0), _HlsHandler)
            httpd.daemon_threads = True
            t = threading.Thread(target=httpd.serve_forever,
                                 kwargs={"poll_interval": 0.2})
            t.daemon = True
            t.start()
            base = "http://127.0.0.1:%d" % httpd.server_address[1]
            # 回环自检：绕开 http_proxy（配了代理没写 no_proxy 时
            # 127.0.0.1 会被丢给代理，探活误判成服务不可用）。
            alive = False
            try:
                import urllib.request as _urlreq
                opener = _urlreq.build_opener(_urlreq.ProxyHandler({}))
                opener.open(base + "/msda/__probe__.m3u8", timeout=3)
            except Exception as e:
                alive = getattr(e, "code", None) == 404
            if alive:
                _HLS_SRV["base"] = base
            else:
                try:
                    httpd.shutdown()
                except Exception:
                    pass
                _HLS_SRV["base"] = ""
        except Exception:
            _HLS_SRV["base"] = ""
        return _HLS_SRV["base"]


def _hls_local_url(text):
    """完整 m3u8 文本 → 本地短 URL；服务不可用返回 ""。"""
    base = _hls_server_base()
    if not base:
        return ""
    return "%s/msda/%s.m3u8" % (base, _hls_put(text))


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
        self.offline_poll_timeout = OFFLINE_POLL_TIMEOUT
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
        self._cal_cache = {}      # date -> (ts, norm list)；TTL 300s，翻页复用
        self._search_cache = {}   # "kw|class|page" -> (ts, list, total)
        self._search_last = 0.0
        self._search_block_until = 0.0
        self._cache_filters = {}
        self._host_locked = False
        self._probed = False
        self._off_last = ""
        self.preview_api = PREVIEW_API
        self.resolve_api = "/api/rv/v1/resolve"

        # FANZA 有 Cloudflare：curl_cffi TLS 指纹优先；无指纹时用 okhttp 头，避免 Chrome UA 403
        self._plain_ua = False
        if creq is not None:
            try:
                self.s = creq.Session(impersonate="chrome")
                self.s.headers.update(LIST_HEADERS)
                self._apply_proxy()
            except Exception:
                self.s = None
        if self.s is None and requests:
            self.s = requests.Session()
            self.s.headers.update(LIST_HEADERS_PLAIN)
            self._plain_ua = True
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
        if extend.get("offlinePollTimeout"):
            try:
                self.offline_poll_timeout = max(
                    5, int(extend["offlinePollTimeout"]))
            except Exception:
                pass
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
    def _has_impersonate(self):
        try:
            return (creq is not None
                    and getattr(self.s, "impersonate", None) is not None)
        except Exception:
            return False

    def _api_headers(self):
        """有 TLS 指纹用 Chrome 头；无指纹用 okhttp 头（Chrome UA 会 403）。"""
        if self._has_impersonate():
            return dict(LIST_HEADERS)
        return dict(LIST_HEADERS_PLAIN)

    def _http_get(self, url, params=None, headers=None, timeout=None,
                  as_json=True):
        """GET url → dict/list（失败返回 {} / []）。
        FANZA 有 Cloudflare：优先 curl_cffi TLS 指纹；无指纹用 okhttp 头，
        403/HTML 再换头重试一次，避免应用侧（无 curl_cffi）整页空列表。"""
        t = timeout or self.timeout
        base = self._api_headers()
        if _to_text(self.cookie):
            base["Cookie"] = self.cookie
        if headers:
            base.update(headers)
        attempts_plan = [base]
        if self._has_impersonate():
            alt = dict(LIST_HEADERS_PLAIN)
        else:
            alt = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        if _to_text(self.cookie):
            alt["Cookie"] = self.cookie
        if headers:
            alt.update(headers)
        if alt != base:
            attempts_plan.append(alt)

        def _do(hdrs):
            for i in range(HTTP_RETRY + 1):
                try:
                    if creq is not None and getattr(
                            self.s, "impersonate", None) is not None:
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
                        return None, "no http backend"
                    if r.status_code in HTTP_RETRY_STATUS and i < HTTP_RETRY:
                        time.sleep(HTTP_RETRY_DELAY)
                        continue
                    # Cloudflare 挑战页 / 非 JSON：换头重试信号
                    ctype = _to_text(
                        (getattr(r, "headers", None) or {}).get(
                            "Content-Type") or "").lower()
                    if r.status_code == 403 or ctype.startswith("text/html"):
                        return None, "cf_or_html_%s" % r.status_code
                    if not as_json:
                        return {"status_code": r.status_code,
                                "text": getattr(r, "text", "") or ""}, ""
                    try:
                        data = r.json()
                    except Exception as e:
                        return None, _to_text(e) or "bad_json"
                    if isinstance(data, dict):
                        return data, ""
                    if isinstance(data, list):
                        return {"items": data}, ""
                    return {}, ""
                except Exception as e:
                    if i < HTTP_RETRY:
                        time.sleep(HTTP_RETRY_DELAY)
                        continue
                    return None, _to_text(e)
            return None, "retries_exhausted"

        for hdrs in attempts_plan:
            data, _err = _do(hdrs)
            if data is not None:
                return data if isinstance(data, dict) else {}
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

    def _site_get_raw(self, path, params=None, timeout=None):
        """GET HOST + path → {status_code, text}（不解析 JSON）。
        供需要 HTTP 状态码判定的调用方（如 _dmm_candidates 负缓存）。"""
        return self._http_get(self.host + path, params=params, timeout=timeout,
                              as_json=False)

    # ---------- work 对象 → vod item ----------
    @staticmethod
    def _work_duration(work):
        """时长取值：FANZA 不在 work 顶层给 duration_sec，而在 versions[] 里
        （网页端取法：当前版本 → 首个有值的版本）。统一返回秒，无值 0。"""
        if not isinstance(work, dict):
            return 0
        d = _safe_int(work.get("duration_sec"), 0)
        if d > 0:
            return d
        for v in work.get("versions") or []:
            if isinstance(v, dict):
                d = _safe_int(v.get("duration_sec"), 0)
                if d > 0:
                    return d
        return 0

    def _vid_meta_put(self, vid, meta):
        """写 vid→meta：先删后写保证键序=访问序（dict 保序，首键即最旧）；
        超 128 条淘汰最旧 1/4，防长会话浏览时无界增长。"""
        self._vid_meta.pop(vid, None)
        self._vid_meta[vid] = meta
        if len(self._vid_meta) > 128:
            for _ in range(max(1, len(self._vid_meta) // 4)):
                if not self._vid_meta:
                    break
                self._vid_meta.pop(next(iter(self._vid_meta)), None)

    def _lru_put(self, cache, key, val, cap=256):
        """通用 LRU 写：先删后写（dict 保序，首键即最旧）；超 cap 淘汰最旧 1/4。"""
        cache.pop(key, None)
        cache[key] = val
        if len(cache) > cap:
            for _ in range(max(1, len(cache) // 4)):
                if not cache:
                    break
                cache.pop(next(iter(cache)), None)

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
        has_source = bool(m.get("has_source"))
        # playable_until 为毫秒时间戳（实测 1824694221058）；>1e11 判毫秒否则按秒
        pu_ms = _safe_int(m.get("playable_until"), 0)
        if pu_ms > 100000000000:
            pu_sec = pu_ms / 1000.0
        else:
            pu_sec = float(pu_ms)
        if playable and pu_ms > 0 and pu_ms <= int(time.time() * 1000):
            playable = False        # 已过期：对齐网页，摘掉可播徽章
        # 网页「● 可播」徽章 = (playable && 未过期) || has_source（磁力源也算可播）
        badge = playable or has_source
        remark_parts = []
        # 徽章置首（海报角标优先可见）；番号已在 type_name，不再塞入 remarks
        if badge:
            remark_parts.append("●可播")
        if playable and pu_ms > 0:
            remark_parts.append("限时 %s" % time.strftime(
                "%Y-%m-%d", time.localtime(pu_sec)))
        # 网页卡片附带字段：version_count → ×N；first_link_at 实测已是日期串
        vc = _safe_int(m.get("version_count"), 0)
        if vc > 1:
            remark_parts.append("×%d" % vc)
        fl = _to_text(m.get("first_link_at") or "")
        if fl:
            remark_parts.append("磁链 %s" % fl[:10])
        # main_svc 为来源站代号（digital/mono/fc2/uc_*），去 uc_ 前缀直出
        svc = _to_text(m.get("main_svc") or "")
        if svc.startswith("uc_"):
            svc = svc[3:]
        if svc:
            remark_parts.append(svc)
        # 无徽章且无其他状态时保留日期兜底（有徽章时日期不再占首屏）
        if not remark_parts and date:
            remark_parts.append(date[:10])
        self._vid_meta_put(mid, {
            "number": number,
            "title": title,
            "pic": pic,
            "duration": self._work_duration(m),
            "release_date": date,
            "content_class": _to_text(m.get("content_class") or ""),
            "playable": playable,
            "has_source": has_source,
            "playable_until": pu_ms,
        })
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

    def _site_key(self):
        return _to_text(getattr(self, "_ext_site_key", "") or "")

    def _movies_to_list(self, works):
        return self._works_to_list(works)

    # ---------- 类别（对齐网页端导航） ----------
    @staticmethod
    def _classes():
        # 网页导航顺序与用名：AV 档案 → FC2 档案 → 无码档案（带空格）
        return [
            {"type_id": "av",         "type_name": "AV 档案"},
            {"type_id": "fc2",        "type_name": "FC2 档案"},
            {"type_id": "uncensored", "type_name": "无码档案"},
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
        """新作时间窗（对齐网页 seg-tabs：仅 7/14/30，默认 7；仅 tab=new 生效）"""
        return {"key": "days", "name": "时间（仅新作）", "init": "7",
                "value": [
                    {"n": "7天", "v": "7"},
                    {"n": "14天", "v": "14"},
                    {"n": "30天", "v": "30"},
                ]}

    @staticmethod
    def _tag_flag_group(key, label):
        """磁力标签 0/1 子筛选（网页多选逗号连接；TVBox 无多选先例 →
        拆成 8 个独立 0/1 组，_list_params 收集 value=1 拼逗号串）。
        仅 tab=links 生效。"""
        return {"key": key, "name": "磁力·%s（仅有磁链）" % label,
                "init": "0",
                "value": [
                    {"n": "否", "v": "0"},
                    {"n": "是", "v": "1"},
                ]}

    @staticmethod
    def _tags_group():
        """兼容旧单选 tags 筛选（value 仍为标签键）。新路径用 _tag_flags()。"""
        return {"key": "tags", "name": "磁力标签（仅有磁链·单选）", "init": "",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "中字", "v": "zh_sub"},
                    {"n": "无码", "v": "uncensored"},
                    {"n": "破解", "v": "cracked"},
                    {"n": "LTX破解", "v": "ltx"},
                    {"n": "4K", "v": "4k"},
                    {"n": "FHD", "v": "fhd"},
                    {"n": "HD", "v": "hd"},
                    {"n": "VR", "v": "vr"},
                ]}

    @classmethod
    def _tag_flags(cls):
        """8 个磁力标签 0/1 子筛选（对齐网页多选）。"""
        keys = [("zh_sub", "中字"), ("uncensored", "无码"),
                ("cracked", "破解"), ("ltx", "LTX破解"),
                ("4k", "4K"), ("fhd", "FHD"), ("hd", "HD"), ("vr", "VR")]
        return [cls._tag_flag_group("tag_%s" % k, lab) for k, lab in keys]

    @staticmethod
    def _ltx_group():
        """LTX 破解（对齐网页 playable 分区 ltx=1）。仅 tab=playable 生效。"""
        return {"key": "ltx", "name": "LTX（仅可播）", "init": "0",
                "value": [
                    {"n": "全部", "v": "0"},
                    {"n": "仅LTX破解", "v": "1"},
                ]}

    def _calendar_days(self, today):
        """网页日期带：today-15 ~ today+15 连续 31 天升序（对齐 cal-strip te()）。
        不再请求 /v1/calendar/days（网页日历不用该接口，且返回的是有货日集合
        与网页连续窗口不一致）。标签：今日 / MM-DD / MM-DD 预定。"""
        try:
            y, m, d = map(int, today.split("-"))
            base = datetime.date(y, m, d)
        except Exception:
            base = datetime.date.today()
            today = base.isoformat()
        vals = []
        for off in range(-15, 16):
            day = base + datetime.timedelta(days=off)
            ds = day.isoformat()
            if ds == today:
                n = "今日"
            elif day > base:
                n = "%s-%s 预定" % (day.month, day.day)
            else:
                n = "%s-%s" % (day.month, day.day)
            vals.append({"n": n, "v": ds})
        return vals

    def homeContent(self, filter=None):
        classes = []
        for c in self._classes():
            if c["type_id"] == "uncensored" and not self.enable_uncensored:
                continue
            classes.append(dict(c))
        tab_days = [self._tab_group("new"), self._days_group()]
        tab_days.extend(self._tag_flags())   # 8×0/1 磁力标签（多选）
        tab_days.append(self._ltx_group())
        filters = {}
        for tid in ("av", "fc2", "uncensored"):
            if tid == "uncensored" and not self.enable_uncensored:
                continue
            # 浅拷贝：各板块 filters 独立，避免 TVBox 改一处牵连全部
            filters[tid] = [dict(x) for x in tab_days]
        # 发售日历：日期带 = 今日±15 连续 31 天（对齐网页 cal-strip）；
        # 筛选 = 全部/可播/有磁力/可播+有磁力（对齐网页 filter-chip 可叠加）
        today = _today()
        date_vals = self._calendar_days(today)
        filters["calendar"] = [
            {"key": "date", "name": "日期", "init": today,
             "value": date_vals},
            {"key": "cal", "name": "筛选", "init": "all",
             "value": [
                 {"n": "全部", "v": "all"},
                 {"n": "可播", "v": "playable"},
                 {"n": "有磁力", "v": "links"},
                 {"n": "可播+有磁力", "v": "both"},
             ]},
        ]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        # 首页推荐：AV 板块最新新作
        data = self._api_get("/v1/lists/new",
                             {"class": "av", "limit": 50, "page": 1})
        works = data.get("items") or data.get("works") or []
        lst = self._works_to_list(works)
        if not lst:
            # 空 q 直接 400（"q must be at least 2 characters (or use
            # playable=1 to browse playable works)"）→ 兜底走 playable 浏览
            data = self._api_get("/v1/search",
                                 {"q": "", "class": "av", "limit": 50,
                                  "playable": 1})
            works = data.get("items") or data.get("works") or []
            lst = self._works_to_list(works)
        return {"list": lst[:50]}

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
            # 网页 links 分区 tags 多选逗号连接：收集 8 个 tag_* =1 的子筛选
            tag_keys = ("zh_sub", "uncensored", "cracked", "ltx",
                        "4k", "fhd", "hd", "vr")
            selected = [k for k in tag_keys
                        if _to_text(fs.get("tag_" + k) or "") == "1"]
            # 兼容旧单选 tags / 直传逗号串
            legacy = _to_text(fs.get("tags") or "").strip().lower()
            if not selected and legacy:
                params["tags"] = legacy
            elif selected:
                params["tags"] = ",".join(selected)
        elif tab == "playable":
            path = "/v1/lists/playable"
            # 网页 playable 分区 ltx=1 仅 LTX 破解
            if _to_text(fs.get("ltx") or "") == "1":
                params["ltx"] = 1
        else:
            path = "/v1/lists/new"
            # av 板块网页对「今日」用 since/until；其余用 days
            # days==1：兼容旧 ext 直传 days=1（非 UI「今日」筛选也走 since/until）
            if days == 1:
                today = _today()
                params["since"] = today
                params["until"] = today
            else:
                params["days"] = days
        return path, params

    def _calendar_list(self, fs, page):
        """发售日历：/v1/lists/new?since=&until=（对齐网页 listNew，非 /v1/calendar）。
        筛选 cal=all|playable|links|both → playable=1 / links=1 可叠加。
        单日作品量小：按页拉全（接口单页上限 ~200，需循环）缓存完整列表，
        本地按 36/页分页（翻 page1/2/3 只产生网络请求的必要次数；
        缓存键 (date, cal) 不含 page）。total 取接口真实 total（非 len 截断值）。"""
        date = _to_text(fs.get("date") or "") or _today()
        cal = _to_text(fs.get("cal") or "all") or "all"
        limit = 36
        fetch_limit = 200   # 实测接口单页上限；>200 会被截断
        cache_key = "%s|%s" % (date, cal)
        now = time.time()
        hit = self._cal_cache.get(cache_key)
        if hit and now - hit[0] < 300:
            works, total = hit[1], hit[2]
        else:
            params = {"since": date, "until": date, "limit": fetch_limit,
                      "page": 1}
            if cal in ("playable", "both"):
                params["playable"] = 1
            if cal in ("links", "both"):
                params["links"] = 1
            data = self._api_get("/v1/lists/new", params)
            works = list(data.get("items") or data.get("works") or [])
            total = _safe_int(data.get("total"), len(works))
            # 接口单页截断时按页补齐（上限 10 页 = 2000 条，防失控）
            pg = 1
            while len(works) < total and pg < 10:
                pg += 1
                params["page"] = pg
                data = self._api_get("/v1/lists/new", params)
                chunk = data.get("items") or data.get("works") or []
                if not chunk:
                    break
                works.extend(chunk)
            self._cal_cache[cache_key] = (now, works, total)
            if len(self._cal_cache) > 16:
                self._cal_cache.pop(next(iter(self._cal_cache)), None)
        start = (page - 1) * limit
        chunk = works[start:start + limit]
        out = self._works_to_list(chunk)
        if not out and total > 0:
            page = max(1, min(page, (total + limit - 1) // limit or 1))
        return {"list": out, "page": page,
                "pagecount": max(1, (total + limit - 1) // limit),
                "limit": len(out), "total": total}

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
        # 接口失败 / {"error":...} / 非法响应：不写 120s 缓存，避免抖动后空窗两分钟
        if not isinstance(data, dict) or "error" in data or "links" not in data:
            return []
        # 网页端磁力是异步抓取队列：status ∈ hit/cooldown/disabled/queued/pending/
        # budget/queue_full/timeout/error。queued/pending 时 links 常为空但语义是
        # 「正在抓取」，不能当「暂无磁力」；在途态也不写 120s 缓存（否则下次进来
        # 两分钟内仍读到空）。状态与 other_works/refreshing 存 _links_meta 供详情消费。
        status = _to_text(data.get("status") or "hit")
        meta = getattr(self, "_links_meta", None)
        if meta is None:
            self._links_meta = {}
            meta = self._links_meta
        meta[code] = {
            "status": status,
            "other_works": _safe_int(data.get("other_works"), 0),
            "refreshing": bool(data.get("refreshing")),
        }
        links = data.get("links")
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
            # FANZA 给 size_bytes（字节）；_format_size_mb/JavDB 约定是 MB → 换算
            raw = _safe_int(g.get("size_bytes"), 0)
            item["size"] = (raw / (1024.0 * 1024)) if raw > 0 else 0
            item["size_bytes"] = raw
            out.append(item)
        # 仅稳定态缓存；在途/限流态（queued/pending/budget/queue_full/timeout）留待重查
        if status in ("hit", "cooldown", "disabled"):
            self._lru_put(self._magnets_cache, code, (now, out))
        return out

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
            self._vid_meta_put(vid, {
                "number": _to_text(work.get("code") or ""),
                "title": _to_text(work.get("title") or ""),
                "pic": self._proxy_pic(_to_text(work.get("cover_url") or "")),
                "duration": self._work_duration(work),
                "release_date": _to_text(work.get("release_date") or ""),
                "content_class": _to_text(work.get("content_class") or ""),
                "playable": bool(work.get("playable")),
            })
            self._lru_put(self._work_cache, vid, (now, work))
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
        # 优先网页同款 workByCode：GET /v1/works?code= 单次精确命中
        # （服务端归一化番号：NOSKN106 → NOSKN-106，search 精确比对会漏）。
        # 响应是列表包装 {count, items, ...}；items[0] 只有 15 字段，缺
        # entities/sample_*/sources → 必须再 _get_work 拿全字段。
        work = {}
        try:
            data = self._api_get("/v1/works", {"code": code})
            items = data.get("items") if isinstance(data, dict) else None
            w0 = (items[0] if isinstance(items, list) and items
                  and isinstance(items[0], dict) else None)
            if w0:
                wid = _to_text(w0.get("id") or w0.get("work_id") or "")
                if wid:
                    work = self._get_work(wid) or w0
        except Exception:
            work = {}
        if not work:
            # 兜底：search 拿 id 再取详情。按番号前缀定首选类
            # （FC2-* 在 fc2 类，硬编码 av 必空）→ 未命中再跨类兜底
            if ckey.startswith("fc2"):
                classes = ["fc2", "av", "uncensored"]
            else:
                classes = ["av", "uncensored", "fc2"]
            if not self.enable_uncensored:
                classes = [c for c in classes if c != "uncensored"]
            try:
                for cls in classes:
                    data = self._api_get("/v1/search",
                                         {"q": code, "class": cls, "limit": 8})
                    for w in data.get("items") or []:
                        if not isinstance(w, dict):
                            continue
                        if _to_text(w.get("code") or "").lower() != ckey:
                            continue
                        wid = _to_text(w.get("id") or w.get("work_id") or "")
                        if wid:
                            work = self._get_work(wid)
                            break
                    if work:
                        break
            except Exception:
                pass
        if work:
            self._lru_put(hit, ckey, (now, work))
        return work

    def _dmm_candidates(self, number):
        """DMM 免费预告候选（存在性检查）。确定性结果缓存 3600s；
        404/200无urls=确定无预览；网络失败等非确定空结果负缓存 60s，
        二次进详情不再打 preview。"""
        number = _to_text(number).strip()
        if not number or self.s is None:
            return []
        now = time.time()
        hit = self._dmm_cache.get(number)
        if hit:
            ttl = hit[2] if len(hit) > 2 else 3600
            if now - hit[0] < ttl:
                return hit[1]
        out, definitive = [], False
        try:
            data = self._site_get_raw(self.preview_api, params={"code": number},
                                      timeout=12)
            status = _safe_int((data or {}).get("status_code"), 0)
            text = _to_text((data or {}).get("text") or "")
            body = {}
            if text:
                try:
                    body = json.loads(text)
                except Exception:
                    body = {}
            if status in (400, 404):
                definitive = True
            elif status == 200 and isinstance(body, dict):
                urls = body.get("urls")
                if isinstance(urls, list):
                    for c in urls:
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
        except Exception:
            definitive = False
        if definitive:
            self._lru_put(self._dmm_cache, number, (now, out, 3600))
        elif not out:
            self._lru_put(self._dmm_cache, number, (now, out, 60))
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
                    # 部分 CDN 拒 HEAD（405/403）→ 回退 GET+Range 取前 1KB 验活
                    ok = False
                    try:
                        r = self.s.head(c["url"], headers=headers, timeout=t,
                                        verify=self.verify,
                                        allow_redirects=True)
                        ok = r.status_code in (200, 206)
                    except Exception:
                        ok = False
                    if not ok:
                        h2 = dict(headers)
                        h2["Range"] = "bytes=0-1023"
                        r = self.s.get(c["url"], headers=h2, timeout=t,
                                       verify=self.verify,
                                       allow_redirects=True)
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

    def _data_uri_to_text(self, u):
        """data:application/vnd.apple.mpegurl,... → 解码后的完整文本。
        非 data: 原样返回；失败返回 ""。"""
        u = _to_text(u)
        if not u.startswith("data:"):
            return u
        try:
            if "," not in u:
                return ""
            header, body = u.split(",", 1)
            if ";base64" in header:
                return base64.b64decode(body).decode("utf-8", "ignore")
            from urllib.parse import unquote as _un
            return _un(body)
        except Exception:
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
        # playable_until 为毫秒时间戳（实测 1824694221058）；>1e11 判毫秒否则按秒。
        # 网页端只拿它做过期判定（playable_until > Date.now()），过期即摘可播徽章。
        # works/{id} 可能不带该字段而列表期 meta 有 → 回退读 cache，避免过期误报可播
        pu_ms = _safe_int(
            work.get("playable_until") or cache.get("playable_until"), 0)
        if pu_ms > 100000000000:
            pu_sec = pu_ms / 1000.0
        else:
            pu_sec = float(pu_ms)
        playable_until_txt = (
            time.strftime("%Y-%m-%d %H:%M", time.localtime(pu_sec))
            if pu_ms > 0 else "")
        if playable and pu_ms > 0 and pu_ms <= int(time.time() * 1000):
            playable = False        # 已过期：对齐网页，不再列「在线可播」源
        dur = self._work_duration(work) or _safe_int(cache.get("duration"), 0)
        desc = _to_text(work.get("description") or "")

        # 实体信息
        ents = work.get("entities") if isinstance(work.get("entities"), dict) else {}
        def _enames(kind):
            rows = ents.get(kind) or []
            out = []
            for a in rows:
                if isinstance(a, dict):
                    # FANZA 实体用 name_ja / name_en，不是 JavDB 的 name
                    n = _to_text(a.get("name_ja") or a.get("name")
                                 or a.get("name_en") or a.get("name_kana") or "")
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
            # duration_sec 恒为秒（网页端 Math.round(e/60) 分钟）→ 四舍五入转分，勿再按值域猜
            info_lines.append("时长: %d分钟" % max(1, int(dur / 60.0 + 0.5)))
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
            until = ("至 %s" % playable_until_txt) if playable_until_txt else ""
            info_lines.append("在线可播%s" % until)
        if magnets:
            # 标注死链（seeders=0 / health=unknown），与「有做种」区分
            def _dead(g):
                return (_to_text(g.get("health") or "") == "unknown"
                        or _safe_int(g.get("seeders"), 0) <= 0)
            dead_n = sum(1 for g in magnets if _dead(g))
            if dead_n >= len(magnets):
                info_lines.append(
                    "磁力 %d 条（均无做种，115可能下不动）" % len(magnets))
            elif dead_n:
                info_lines.append(
                    "磁力 %d 条（%d 条无做种）" % (len(magnets), dead_n))
            else:
                info_lines.append("磁力 %d 条" % len(magnets))
        elif number:
            # 网页端磁力是异步队列：排队/限流 ≠ 真的「暂无」，按 status 分支文案
            lm = (getattr(self, "_links_meta", None) or {}).get(number) or {}
            st = _to_text(lm.get("status") or "")
            if st in ("queued", "pending") or lm.get("refreshing"):
                info_lines.append("磁力抓取中（网页端异步队列，稍后刷新）")
            elif st in ("budget", "queue_full"):
                info_lines.append("磁力抓取受限（额度/队列满，稍后重试）")
            elif st == "timeout":
                info_lines.append("磁力抓取超时（稍后重试）")
            elif st == "cooldown":
                info_lines.append("磁力抓取冷却中（稍后重试）")
            elif st == "disabled":
                info_lines.append("磁力服务未开放")
            else:
                msg = "暂无磁力（源站未提供磁链）"
                if _safe_int(lm.get("other_works"), 0) > 0:
                    msg += "；同番号其他作品有磁链"
                info_lines.append(msg)
        if desc:
            info_lines.append(desc[:500])
        if self.enable_offline_115:
            info_lines.append("115离线：提交到115云端，完成后自动直连播放 (v%s)" % VERSION)

        # 播放源：在线 → 预览 → 磁力 → 115离线
        # （网页端默认页签「完整影片」置顶，不受 playable 门控：实测 resolve 对
        #  playable=false 仍返回 HLS；playable 过期只影响 info 文案/徽章，不挡源。
        #  磁力/115 与 javdbui 同构）
        play_from = []
        play_url = []

        # 在线解析（伪链，playerContent 取 variants）：只要番号在就挂，
        # 播放时 resolve 无源再报错回退——对齐网页「完整影片」页签始终可见
        if number:
            play_from.append("在线")
            play_url.append("在线$%s" % _sanitize_play(
                RESOLVE_PREFIX + "%s|%s" % (number, content_class)))

        # 预览（伪链，playerContent 探测）：DMM 候选或 work 自带样片
        sample_mv = _to_text(work.get("sample_movie_url") or "")
        sample_hls = _to_text(work.get("sample_hls_url") or "")
        has_sample = bool(sample_mv.startswith(("http://", "https://"))
                          or sample_hls.startswith(("http://", "https://")))
        if number and (self._dmm_candidates(number) or has_sample):
            play_from.append("预览")
            play_url.append("预览$%s" % _sanitize_play(PREVIEW_PREFIX + number))

        # 磁力源（与 javdbui 一致：只用 hash 重建干净磁力，不带上游 dn=）
        if self.enable_magnet and magnets:
            eps = []
            for i, g in enumerate(magnets):
                h = _to_text(g.get("hash") or "")
                if not h:
                    continue
                mag = _magnet_with_trackers(h)
                label = _magnet_label(g, i)
                eps.append("%s$%s" % (_sanitize_play(label), _sanitize_play(mag)))
            if eps:
                play_from.append("磁力")
                play_url.append("#".join(eps))

        # 115离线源（与 javdbui 一致：裸 btih 磁力入 115，label/番号参与命名）
        if self.enable_offline_115 and magnets:
            eps = []
            for i, g in enumerate(magnets):
                h = _to_text(g.get("hash") or "")
                if not h:
                    continue
                mag = "magnet:?xt=urn:btih:" + h
                label = _magnet_label(g, i)
                b64 = _off_id_encode(mag, title, label, number)
                eps.append("%s$%s%s?t=%d" % (
                    _sanitize_play(_offline_episode_label(g, i)),
                    OFF_PREFIX_115, b64, int(time.time())))
            if eps:
                play_from.append("115离线")
                play_url.append("#".join(eps))

        # 一行摘要：对齐 javdbui（番号 | 日期 | 片商 | 导演 | 演员）
        _blurb = " | ".join([b for b in (
            number, (date or "")[:10],
            makers[0] if makers else "",
            directors[0] if directors else "",
            "、".join(actors[:4]),
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
            lst, total, pagecount = hit[1], hit[2], hit[3]
            return {"list": lst, "page": page, "pagecount": pagecount,
                    "limit": len(lst), "total": total}

        # /v1/search 只认 limit，不支持 offset/page → 拉 page*limit 后切片；
        # 触顶 SEARCH_FETCH_MAX（500）防深页请求体积膨胀
        fetch_limit = min(self.search_limit * page, SEARCH_FETCH_MAX)
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
        # 触顶 SEARCH_FETCH_MAX（500）时 total_est 含未抓取部分会虚高
        # → total 取实际已抓行数；未触顶才用接口 total 估计
        if self.search_limit * page >= SEARCH_FETCH_MAX:
            total = len(rows)
        else:
            total = total_est or len(rows)
        # 空 chunk = 没有下一页数据（fetch 触顶 500 或上游已空）→ 收口 pagecount，
        # 否则 total 仍是全量估计、深页会一直报 page+1
        pagecount = self._search_pagecount(total, page) if chunk else page
        if len(self._search_cache) > 64:
            self._search_cache.clear()
        self._search_cache[ck] = (now, lst, total, pagecount)
        return {"list": lst, "page": page,
                "pagecount": pagecount,
                "limit": len(lst), "total": total}

    def _search_pagecount(self, total, page):
        # search 无可靠 page 上限：有下一页数据就多给 1 页（用 self.search_limit，勿硬编码 30）
        return page + 1 if total > page * self.search_limit else page

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
        """按 info_hash 找离线任务。
        max_page<=0：按响应 page_count 全页扫描（上限 OFFLINE_FIND_MAX_PAGES），
        用于删除确认 / 已存在定位——任务在第 3 页外时小页数扫描会漏检、误判。"""
        info_hash = _to_text(info_hash or "").strip().lower()
        if not info_hash:
            return None
        cap = max_page
        page = 1
        while True:
            if cap > 0 and page > cap:
                break
            if page > OFFLINE_FIND_MAX_PAGES:
                break
            try:
                res = self._offline_list(page)
            except Exception:
                return None
            if page == 1 and cap <= 0:
                pc = _safe_int(res.get("page_count"), 0)
                cap = min(pc, OFFLINE_FIND_MAX_PAGES) if pc > 0 else 1
            tasks = res.get("tasks") or res.get("list") or []
            if not tasks:
                break
            for t in tasks:
                h = (t.get("info_hash") or t.get("hash") or "").lower()
                if h and h == info_hash:
                    return t
            page += 1
        return None

    def _offline_task_del(self, info_hash):
        """删除 115 离线任务（失败任务卡死时删旧重提）。
        web 端参数为 hash[0]=info_hash；del_source_file=0 不动已下完的源文件。"""
        info_hash = _to_text(info_hash or "").strip().lower()
        if not info_hash:
            return False
        sess = self._offline_session()
        if sess is None:
            return False
        data = {"hash[0]": info_hash, "del_source_file": "0"}
        try:
            r = sess.post(OFFLINE_TASK_DEL_API, data=data,
                          headers=self._offline_headers(),
                          timeout=self.offline_timeout, verify=self.verify)
            out = _safe_json(r.text, {})
            if not isinstance(out, dict):
                return False
            if out.get("state") or _safe_int(out.get("errcode"), -1) == 0:
                # 删后确认已不在列表（task_del 对不存在 hash 也可能回 suc）；
                # max_page=0 → 按 page_count 全页扫，任务在深页时小页数会漏检误判
                try:
                    return self._offline_find_task(info_hash, max_page=0) is None
                except Exception:
                    return True
        except Exception:
            return False
        return False

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

    def _offline_wait_done(self, info_hash, timeout=None):
        if timeout is None:
            timeout = getattr(self, "offline_poll_timeout",
                              OFFLINE_POLL_TIMEOUT)
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
            key = self._site_key()
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
                # 失败任务卡死：删旧后走下面重新 add（不再直接放弃）
                self._off_trace("删除失败任务以便重提", t0)
                try:
                    self._offline_task_del(info_hash)
                except Exception:
                    pass
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

            # 「已存在」但列表里其实是失败任务 → 删旧再提一次
            if task and not add.get("state"):
                _d, failed_x, _m = self._offline_task_state(task)
                if failed_x or existed:
                    self._off_trace("已存在且失败，删旧重提", t0)
                    try:
                        self._offline_task_del(info_hash)
                    except Exception:
                        pass
                    try:
                        add = self._offline_add(magnet)
                    except Exception as e:
                        return _play_err("提交离线失败：%s" % e)
                    add_msg = _to_text(
                        add.get("message") or add.get("error_msg")
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
                    return _play_err(
                        "115离线失败（可到115网盘删除该失败任务后重试）：%s"
                        % msg0)
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
            # 超时≠失败：115 云端仍在下载，明确告知避免误判
            return _play_err(
                "115云端下载中（%s），非失败；请稍后重试或到115网盘查看"
                % (name_or_msg or "排队/下载中"))

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
                text = self._data_uri_to_text(v.get("url") or "")
                if not text:
                    last_err = "data URI 无法还原"
                    continue
                if text.lstrip().startswith("#EXTM3U"):
                    # 完整 HLS 播放列表 → 落本机 .m3u8 服务，交整段给播放器
                    u = _hls_local_url(text)
                    if not u:
                        last_err = "本地 m3u8 服务不可用"
                        continue
                    return {
                        "parse": 0, "jx": 0, "playUrl": "", "url": u,
                        "format": "application/x-mpegURL",
                        "header": {"User-Agent": self.ua,
                                   "Referer": self.host + "/", "Accept": "*/*"},
                    }
                # 非播放列表：取首条 http 直链（原行为）
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith(("http://", "https://")):
                        return {
                            "parse": 0, "jx": 0, "playUrl": "", "url": line,
                            "header": {"User-Agent": self.ua,
                                       "Referer": self.host + "/", "Accept": "*/*"},
                        }
                if text.strip().startswith(("http://", "https://")):
                    return {
                        "parse": 0, "jx": 0, "playUrl": "", "url": text.strip(),
                        "header": {"User-Agent": self.ua,
                                   "Referer": self.host + "/", "Accept": "*/*"},
                    }
                last_err = "无可用直链"
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

        # 演员/片商/系列详情里点作品 → 作品 id 走 detail 拿源再播。
        # 源顺序：115离线 → 磁力 → 预览 → 在线；全失败走终兜底（带 msg，不再空 url 黑屏）
        if not vid.startswith(OFF_PREFIX_115) and len(vid) <= 12 \
                and re.match(r"^[A-Za-z0-9]+$", vid):
            try:
                d = self.detailContent([vid])
                vod = (d.get("list") or [{}])[0]
                froms = _to_text(vod.get("vod_play_from") or "").split("$$$")
                plays = _to_text(vod.get("vod_play_url") or "").split("$$$")

                # ① 115 离线：decode 后直连提交/播放
                for i, seg in enumerate(plays):
                    src = froms[i] if i < len(froms) else ""
                    if "115" not in src:
                        continue
                    for ep in seg.split("#"):
                        if OFF_PREFIX_115 not in ep:
                            continue
                        _, ep_id = ep.split("$", 1)
                        magnet, title, label, number = _off_id_decode(
                            ep_id[len(OFF_PREFIX_115):].split("?")[0])
                        if magnet:
                            return self._play_offline_safe(
                                magnet, title, label, number)

                # ② 磁力：取第一个 magnet: 直接播
                for i, seg in enumerate(plays):
                    src = froms[i] if i < len(froms) else ""
                    if "磁力" not in src:
                        continue
                    for ep in seg.split("#"):
                        if "$" not in ep:
                            continue
                        u = unquote(ep.split("$", 1)[1])
                        if u.startswith("magnet:"):
                            m = _normalize_magnet(u)
                            return {
                                "parse": 0, "jx": 0, "playUrl": "",
                                "url": m or u,
                                "header": {"User-Agent": self.ua,
                                           "Accept": "*/*"},
                            }

                # ③ 预览 / ④ 在线：把伪链交回 playerContent 前缀分支探测
                #    （失败带 msg 返回，继续下一源；全失败落终兜底）
                last_err = ""
                for i, seg in enumerate(plays):
                    src = froms[i] if i < len(froms) else ""
                    if not (src in ("预览", "在线") or "预览" in src):
                        continue
                    for ep in seg.split("#"):
                        if "$" not in ep:
                            continue
                        u = unquote(ep.split("$", 1)[1])
                        if not u.startswith((PREVIEW_PREFIX, RESOLVE_PREFIX)):
                            continue
                        r = self.playerContent(flag, [u])
                        if isinstance(r, dict) and r.get("url"):
                            return r
                        if r.get("msg"):
                            last_err = _to_text(r.get("msg"))
                if last_err:
                    return _play_err("该作品暂无可播源（%s）" % last_err)
            except Exception as e:
                return _play_err("解析作品源失败（%s）" % _to_text(e))

        return _play_err("无可用播放源（115离线/磁力/预览/在线均无），"
                         "请到详情页确认源列表")

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
