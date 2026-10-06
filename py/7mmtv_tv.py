#!/usr/bin/python
# -*- coding: utf-8 -*-
# 7mmtv.sx Spider (2026-10-06, 全链路实测通过)
#
# 站点: 7mmtv.sx - 纯服务端渲染 HTML, 无 JSON API。
# 分类: /{lang}/{type}_list/all/{page}.html
#   type: reducing-mosaic(無碼破解) chinese(中字AV) censored(有碼AV)
#         amateurjav(素人AV) uncensored(無碼AV) amateur(國產影片)
#         klive(韓國直播) clive(中國直播)
# 搜索: /{lang}/searchall_search/all/{keyword}/{page}.html
# 详情: /{lang}/{type}_content/{id}/{slug}.html
# 播放: 详情页 mvarr token 解码链 (已实测):
#   token 按 'r' 切分 -> 每组 2 字符按 17 进制解析 ('g'=16) -> XOR 6
#   -> chr 拼接得 base64 -> AES-128-CBC 解密 (key/iv 为页内两个 16 位 hex 字符串)
#   SW -> https://mmsi02.com/e/<id>          (第三方 embed, parse:1)
#   VH -> https://mmvh02.com/v/<id>          (第三方 embed, parse:1)
#   SP -> play.php?id=<64字符token> -> videoSources 直链 m3u8 (parse:0)
#
# ext: {"lang": "zh"} (zh/en/ja/ko)
import sys
import re
import json
import base64
import gzip
from urllib.parse import quote, unquote
try:
    import requests
    _HAS_REQ = True
except ImportError:
    _HAS_REQ = False

sys.path.append('..')
try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

HOST = "https://7mmtv.sx"
UA = ("Mozilla/5.0 (Linux; Android 11; M2012K11AC Build/RKQ1.200826.002) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")

CATEGORIES = [
    ("有碼AV", "censored"),
    ("無碼AV", "uncensored"),
    ("無碼破解", "reducing-mosaic"),
    ("中字AV", "chinese"),
    ("素人AV", "amateurjav"),
    ("國產影片", "amateur"),
    ("韓國直播", "klive"),
    ("中國直播", "clive"),
]


# ---------------------------------------------------------------------------
# 纯 Python AES (仅解密, 支持 128/192/256, ECB/CBC) —— 避免依赖 Crypto
# ---------------------------------------------------------------------------

def _gf_mul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _build_sboxes():
    sbox = [0] * 256
    inv = [0] * 256
    for x in range(256):
        y = 0
        if x:
            y = 1
            base, exp = x, 254
            r = 1
            b = base
            e = exp
            while e:
                if e & 1:
                    r = _gf_mul(r, b)
                b = _gf_mul(b, b)
                e >>= 1
            y = r
        s = y
        for i in range(4):
            s ^= ((y << (i + 1)) | (y >> (7 - i))) & 0xFF
        s ^= 0x63
        sbox[x] = s & 0xFF
        inv[s & 0xFF] = x
    return sbox, inv


_SBOX, _INV_SBOX = _build_sboxes()
_M9 = [_gf_mul(x, 9) for x in range(256)]
_M11 = [_gf_mul(x, 11) for x in range(256)]
_M13 = [_gf_mul(x, 13) for x in range(256)]
_M14 = [_gf_mul(x, 14) for x in range(256)]
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
         0x6C, 0xD8, 0xAB, 0x4D]


def _aes_expand_key(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = [_SBOX[t[1]] ^ _RCON[i // nk - 1], _SBOX[t[2]],
                 _SBOX[t[3]], _SBOX[t[0]]]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w, nr


def _aes_decrypt_block(block, w, nr):
    s = [[block[c * 4 + r] for c in range(4)] for r in range(4)]

    def add_round_key(rnd):
        for c in range(4):
            for r in range(4):
                s[r][c] ^= w[rnd * 4 + c][r]

    def inv_shift_rows():
        for r in range(1, 4):
            row = [s[r][c] for c in range(4)]
            for c in range(4):
                s[r][c] = row[(c - r) % 4]

    def inv_sub_bytes():
        for r in range(4):
            for c in range(4):
                s[r][c] = _INV_SBOX[s[r][c]]

    def inv_mix_columns():
        for c in range(4):
            a0, a1, a2, a3 = s[0][c], s[1][c], s[2][c], s[3][c]
            s[0][c] = _M14[a0] ^ _M11[a1] ^ _M13[a2] ^ _M9[a3]
            s[1][c] = _M9[a0] ^ _M14[a1] ^ _M11[a2] ^ _M13[a3]
            s[2][c] = _M13[a0] ^ _M9[a1] ^ _M14[a2] ^ _M11[a3]
            s[3][c] = _M11[a0] ^ _M13[a1] ^ _M9[a2] ^ _M14[a3]

    add_round_key(nr)
    for rnd in range(nr - 1, 0, -1):
        inv_shift_rows()
        inv_sub_bytes()
        add_round_key(rnd)
        inv_mix_columns()
    inv_shift_rows()
    inv_sub_bytes()
    add_round_key(0)
    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = s[r][c]
    return bytes(out)


try:
    from Crypto.Cipher import AES as _CryptoAES
except Exception:
    _CryptoAES = None


def _aes_cbc_decrypt(data, key, iv):
    """AES-128-CBC 解密并去 PKCS7 填充, Crypto 优先, 纯 Python 兜底。"""
    if not data or len(data) % 16 or len(key) != 16 or len(iv) != 16:
        return b""
    if _CryptoAES is not None:
        try:
            dec = _CryptoAES.new(key, _CryptoAES.MODE_CBC, iv).decrypt(data)
            pad = dec[-1]
            if 0 < pad <= 16 and all(b == pad for b in dec[-pad:]):
                dec = dec[:-pad]
            return dec
        except Exception:
            pass
    w, nr = _aes_expand_key(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        dec = _aes_decrypt_block(blk, w, nr)
        dec = bytes(a ^ b for a, b in zip(dec, prev))
        prev = blk
        out.extend(dec)
    if out:
        pad = out[-1]
        if 0 < pad <= 16 and all(b == pad for b in out[-pad:]):
            out = out[:-pad]
    return bytes(out)


# ---------------------------------------------------------------------------
# mvarr token 解码
# ---------------------------------------------------------------------------

def _b17(ch):
    if '0' <= ch <= '9':
        return ord(ch) - 48
    if 'a' <= ch <= 'f':
        return ord(ch) - 87
    if ch == 'g':
        return 16
    return 0


def _decode_token(token, key_hex, iv_hex):
    """token -> base17/XOR6 -> base64 -> AES-128-CBC, 返回解密字符串 (bytes)。"""
    try:
        b64s = "".join(
            chr((_b17(g[0]) * 17 + _b17(g[1])) ^ 6)
            for g in token.split('r') if g
        )
        raw = base64.b64decode(b64s)
        pt = _aes_cbc_decrypt(raw, key_hex.encode("ascii"), iv_hex.encode("ascii"))
        return pt
    except Exception:
        return b""


def _looks_like_id(s, kind):
    try:
        t = s.decode("ascii")
    except Exception:
        return False
    if kind == "sp":
        return len(t) == 64 and all(c.isalnum() or c in "-_" for c in t)
    return len(t) == 12 and all(c.isalnum() for c in t)


class Spider(_BaseSpider):
    def getName(self):
        return "7mmtv"

    def init(self, extend=""):
        try:
            _ext = json.loads(extend) if isinstance(extend, str) and extend.strip().startswith("{") else {}
        except Exception:
            _ext = {}
        self.lang = str((_ext.get("lang") or "zh")).strip().strip("/") or "zh"
        self.host = str(_ext.get("host") or HOST).rstrip("/")
        self.ua = UA
        self._sess = None
        if _HAS_REQ:
            try:
                self._sess = requests.Session()
                self._sess.headers.update({"User-Agent": self.ua})
            except Exception:
                self._sess = None

    # ---------------- HTTP ----------------
    def _http(self, url, timeout=15):
        headers = {"User-Agent": self.ua, "Referer": self.host + "/",
                   "Accept-Language": "zh-CN,zh;q=0.9"}
        try:
            if self._sess is not None:
                r = self._sess.get(url, headers=headers, timeout=timeout)
                return r.text
            try:
                rep = self.fetch(url, headers=headers, timeout=timeout)
                data = rep.content if hasattr(rep, "content") else rep.text.encode("utf-8", "ignore")
            except TypeError:
                rep = self.fetch(url)
                data = rep.content if hasattr(rep, "content") else rep.text.encode("utf-8", "ignore")
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            return data.decode("utf-8", "ignore")
        except Exception:
            return ""

    # ---------------- 列表解析 ----------------
    def _parse_list(self, html):
        out, seen = [], set()
        blocks = re.split(r'''<div class=["']video["']>''', html or "")
        for b in blocks[1:]:
            m = re.search(r'''<h3 class=["']video-title["']>\s*<a[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>''',
                          b, re.S)
            if not m:
                continue
            href = m.group(1).strip()
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not href or href in seen:
                continue
            seen.add(href)
            pic = ""
            im = re.search(r'''<img[^>]*data-src=["']([^"']+)["']''', b)
            if im:
                pic = im.group(1)
            if not pic or pic.startswith("data:"):
                im2 = re.search(r'''<img[^>]*src=["'](https?://[^"']+)["']''', b)
                if im2:
                    pic = im2.group(1)
            remark = ""
            ch = re.search(r'''<div class=["']video-channel["']>(.*?)</div>''', b, re.S)
            if ch:
                remark = re.sub(r"<[^>]+>", "", ch.group(1)).strip()
            tm = re.search(r'''<span class=["']small text-muted["']>\s*(.*?)\s*</span>''', b, re.S)
            if tm:
                dt = re.sub(r"<[^>]+>", "", tm.group(1)).strip()
                remark = (remark + " " + dt).strip() if remark else dt
            if href.startswith("/"):
                href = self.host + href
            out.append({"vod_id": href, "vod_name": title,
                        "vod_pic": pic, "vod_remarks": remark})
        return out

    # ---------------- 首页 / 分类 ----------------
    def homeContent(self, filter):
        cls = [{"type_name": n, "type_id": t} for n, t in CATEGORIES]
        return {"class": cls, "filters": {}}

    def homeVideoContent(self):
        html = self._http("%s/%s/" % (self.host, self.lang))
        return {"list": self._parse_list(html)}

    def categoryContent(self, tid, pg, filter, ext):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        url = "%s/%s/%s_list/all/%d.html" % (self.host, self.lang, tid, pg)
        html = self._http(url)
        return {"list": self._parse_list(html), "page": pg,
                "pagecount": pg + 1, "limit": 20, "total": 0}

    # ---------------- 详情 ----------------
    def _decode_sources(self, html):
        """解析 mvarr 并解码, 返回 [(源名, 种类, 解码后id/url前缀)]."""
        keys = list(dict.fromkeys(
            re.findall(r"'([0-9a-f]{16})'", html or "")))
        mvars = re.findall(
            r"mvarr\['(\d+)_1'\]=\[\['([^']*)','([0-9a-gr]+)','(.*?)','(.*?)','','(.*?)','(.*?)'\],?\]",
            html or "", re.S)
        out = []
        for num, _iid, token, _pre, urlpre, _suf, _dl in mvars:
            real_id, kind = "", ""
            up = urlpre.strip()
            if "play.php" in up:
                kind = "sp"
            elif "mmsi02" in up:
                kind = "sw"
            elif "mmvh02" in up:
                kind = "vh"
            else:
                kind = "unk"
            for kh in keys:
                for ivh in keys:
                    pt = _decode_token(token, kh, ivh)
                    if _looks_like_id(pt, "sp" if kind == "sp" else "id"):
                        real_id = pt.decode("ascii")
                        kind = "sp" if len(real_id) == 64 else kind
                        break
                if real_id:
                    break
            if not real_id:
                continue
            if up.startswith("//"):
                up = "https:" + up
            out.append((num, kind, up, real_id))
        return out

    def _sp_m3u8(self, token):
        """SP 源: 取 play.php 解析出直链 m3u8 [(清晰度, url)]."""
        html = self._http("%s/assets/js/play/play.php?id=%s" % (self.host, token))
        res = []
        m = re.search(r"const videoSources\s*=\s*\[(.*?)\];", html or "", re.S)
        if not m:
            return res
        for sm in re.finditer(r"\{\s*src:\s*'([^']+)'[^}]*?size:\s*(\d+)", m.group(1), re.S):
            res.append((sm.group(2) + "P", sm.group(1)))
        return res

    def detailContent(self, ids):
        url = ids[0] if isinstance(ids, list) else str(ids or "")
        if not url:
            return {"list": []}
        if url.startswith("/"):
            url = self.host + url
        html = self._http(url)
        if not html:
            return {"list": []}
        title, pic, desc = "", "", ""
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html or "", re.S)
        if m:
            try:
                ld = json.loads(m.group(1))
                if isinstance(ld, dict) and ld.get("@type") == "VideoObject":
                    title = str(ld.get("name") or "").strip()
                    pic = str(ld.get("image") or "").strip()
                    desc = str(ld.get("description") or "").strip()
            except Exception:
                pass
        if not title:
            m = re.search(r"<title>(.*?)</title>", html or "", re.S)
            if m:
                title = re.sub(r"\s*-\s*7mmtv\.sx.*$", "",
                               re.sub(r"<[^>]+>", "", m.group(1))).strip()

        froms, urls = [], []
        for _num, kind, up, rid in self._decode_sources(html):
            if kind == "sp":
                qs = self._sp_m3u8(rid)
                if qs:
                    froms.append("SP站内")
                    urls.append("#".join("%s$%s" % (q, u) for q, u in qs))
            elif kind == "sw":
                froms.append("SW")
                urls.append("正片$%s%s" % (up, rid))
            elif kind == "vh":
                froms.append("VH")
                urls.append("正片$%s%s" % (up, rid))
            else:
                froms.append("线路" + _num)
                urls.append("正片$%s%s" % (up, rid))
        return {"list": [{
            "vod_id": url, "vod_name": title, "vod_pic": pic,
            "vod_content": desc, "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }]}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        key = (key or "").strip()
        if not key:
            return {"list": []}
        url = "%s/%s/searchall_search/all/%s/%d.html" % (
            self.host, self.lang, quote(key), pg)
        html = self._http(url)
        return {"list": self._parse_list(html), "page": pg,
                "pagecount": pg + 1, "limit": 20, "total": 0}

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        url = str(id or "")
        if url.endswith(".m3u8") or ".m3u8?" in url:
            return {"parse": 0, "playUrl": "", "url": url,
                    "header": {"User-Agent": self.ua,
                               "Referer": self.host + "/"}}
        # 第三方 embed 页, 交给壳子解析
        return {"parse": 1, "playUrl": "", "url": url,
                "header": {"User-Agent": self.ua,
                           "Referer": self.host + "/"}}

    def isVideoFormat(self, url):
        return bool(url) and ".m3u8" in url.split("?")[0]

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            if self._sess is not None:
                self._sess.close()
        except Exception:
            pass
