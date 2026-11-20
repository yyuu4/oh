# -*- coding: utf-8 -*-
"""蜗牛 - wn4k.com 通用 CatVod Python 蜘蛛

业务参照: omn蜗牛.js (MacCMS panlian_dark/mxone, 网盘资源分组)
分组参照: omnibox觅盘.js (encodeId: mp|type|base64url(JSON))

分组 ID（trae 三级：m → 分组卡 g → 分享列表 r）:
  mp|m|...  影片 -> 按网盘类型拆成多张分组卡
  mp|g|...  影片+网盘类型 -> 分享链接列表（每条展开选集）
  mp|r|...  分享链接资源详情（多集展开选集）
  mp|e|...  指定集播放 id（u/f/n/h）
  mp|k|...  搜索关键词+网盘类型 -> 链接列表
  纯数字    站点影片 ID

播放: playerContent 将分享链接 resolve 成真视频流（m3u8/mp4）；
      解析失败返回空 url+msg，绝不回退分享页 HTML（避免 ExoPlayer container unsupported）。
选集: 单分享内多文件 → # 连接，名带 [大小 格式] 前缀（如 [1.5G mp4] 文件名），
      按季/集排序去重；播放id = encode_id("e", {u,f,n,h}) 或 分享链接|fid。
"""
import base64
import json
import os
import re
import threading
import time
from html import unescape
from urllib.parse import quote, unquote, urljoin

try:
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.ssl_ import create_urllib3_context
except Exception:
    requests = None
    HTTPAdapter = object
    create_urllib3_context = None

try:
    from lxml import html as lxml_html
except Exception:
    lxml_html = None

try:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    from Crypto.Util.number import bytes_to_long, long_to_bytes
    _HAS_CRYPTO = True
except Exception:
    RSA = None
    PKCS1_v1_5 = None
    bytes_to_long = None
    long_to_bytes = None
    _HAS_CRYPTO = False


# ==================== 配置 ====================
def _split_cfg(value):
    return [x.strip() for x in re.split(r"[;,]", str(value or "")) if x.strip()]


WEB_SITES = _split_cfg(os.environ.get("WEB_SITE_WONIU4K", "https://wn4k.com/"))
if not WEB_SITES:
    WEB_SITES = ["https://wn4k.com/"]

SITE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
VERSION = "1.0.0"
PAGE_SIZE = 20

STATIC_CLASSES = [
    {"type_id": "0", "type_name": "首页"},
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "连续剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
]

LOGIN_USERNAME = (
    os.environ.get("WONIU4K_USERNAME")
    or os.environ.get("WONIU4K_USER")
    or "raaaee"
).strip()
LOGIN_PASSWORD = (
    os.environ.get("WONIU4K_PASSWORD")
    or os.environ.get("WONIU4K_PASS")
    or "kisser123"
).strip()
WONIU4K_COOKIE = (
    os.environ.get("WONIU4K_COOKIE") or os.environ.get("WONIU4K_COOKIES") or ""
).strip()
CAPTCHA_SERVICE_URL = (os.environ.get("DDDDOCR_API") or "").rstrip("/")

# ---- 网盘 Cookie（playerContent 按分享链接类型注入对应 Cookie）----
# 115 网盘 Cookie：浏览器登录 115 后 F12 -> Network -> 任意请求 -> Request Headers -> Cookie 整串粘贴
COOKIE_115 = (
    os.environ.get("DRIVE_COOKIE_115")
    or os.environ.get("PAN_COOKIE_115")
    or "UID=7090991_R1_1785487771; CID=3c1a3ab03cfc92b0b7c80db6efa950c6; SEID=81ec0f1ad4aa99de925b609465a91c20d8894da910834a59f27cb239ebc5eb70412b456e8e91fff5654dc089a9d0c153f5fcec844b4cf7fa1b8aac84; KID=bc573815d056010f1b8373db03247c3b"
).strip()
# 百度网盘 Cookie：浏览器登录百度网盘后 F12 -> Network -> 任意请求 -> Request Headers -> Cookie 整串粘贴
# 至少需含 BDUSS（分享页公开访问可不填；解析/下载通常需要）
COOKIE_BAIDU = (
    os.environ.get("DRIVE_COOKIE_BAIDU")
    or os.environ.get("PAN_COOKIE_BAIDU")
    or "XFI=5a3aacd5-1882-383f-9c13-6fbd8fc45616; XFCS=6934486FF35D07B993DE7A3D39C61F9257A9B98486E6D660D5ED9B8B1ED3B540; XFT=kkuwSdMMmttM7GFwy/yfPs4Q45NbUUISVippBlCCBic=; csrfToken=CrD-pvP-vceUgIEsOoFIXXz1; BAIDUID=90B996B2BCB42015D7470F897FBF7BFB:FG=1; Hm_lvt_7a3960b6f067eb0085b7f96ff5e660b0=1775418321; HMACCOUNT=EBEA8556F8CD8755; Hm_lpvt_7a3960b6f067eb0085b7f96ff5e660b0=1775418389; BAIDUID_REF=90B996B2BCB42015D7470F897FBF7BFB:FG=1; H_WISE_SIDS=110085_656456_661764_667680_673675_681439_685375_686052_660927_686285_690306_690304_690575_690335_687554_691367_691536_692755_692780_692124_692900_690140_693135_693222_693152_693362_693404_693433_693386_693658_690883_693896_692094_693945_693938_692187_691305_693392_694167_693882_693994_694313_693890_694342_694409_691557_694697_694780_694782_694890_694912_694995_694990_695085_695032_695119_694839_695137_695180_695222_694712_695218_695274_695240_695111_695263_688609_695329_695278_694865_695215_695374_695404_690651_694609_695418_692377_695452_695457_694951_695599_691406_695630_695824_695886_695894_695890_694174_695987_695899_695627_696154_696149_696145_696166_696066_696071_694359_696304_696291_695715_696128_8000064_8000101_8000125_8000141_8000150_8000163_8000166_8000184_8000185; delPer=0; PSINO=1; H_WISE_SIDS_BFESS=110085_656456_661764_667680_673675_681439_685375_686052_660927_686285_690306_690304_690575_690335_687554_691367_691536_692755_692780_692124_692900_690140_693135_693222_693152_693362_693404_693433_693386_693658_690883_693896_692094_693945_693938_692187_691305_693392_694167_693882_693994_694313_693890_694342_694409_691557_694697_694780_694782_694890_694912_694995_694990_695085_695032_695119_694839_695137_695180_695222_694712_695218_695274_695240_695111_695263_688609_695329_695278_694865_695215_695374_695404_690651_694609_695418_692377_695452_695457_694951_695599_691406_695630_695824_695886_695894_695890_694174_695987_695899_695627_696154_696149_696145_696166_696066_696071_694359_696304_696291_695715_696128_8000064_8000101_8000125_8000141_8000150_8000163_8000166_8000184_8000185; AFD_IP=123.161.131.206; BDORZ=AE84CDB3A529C0F8A2B9DCDD1D18B695; TWIE=2c1406016562687f0c402ab89c1acfcfd5dd4f75; BA_HECTOR=ak0k0104800ka5a0a0akq18lal81001kt5f1i27; ZFY=InaOdiWY7Vc1kBfxNcJWIVTID57swVMFBJMsXogZISw:C; PSCBD=22%3A1%3A3_31%3A1%3A3; SE_LAUNCH=5%3A1775418413_22%3A29590306%3A3_31%3A29590306%3A3; PANWEB=1; Hm_lvt_e6c5e9705447b840241ebab6dbdb5fda=1775418436; Hm_lpvt_e6c5e9705447b840241ebab6dbdb5fda=1775418436; __bid_n=19d5f2f75411152f6810ea; fuid=FOCoIC3q5fKa8fgJnwzbE3sZaS3poGTofPItBD67MTHOloTQtOTfZukshuG%2BjikLybArGBMGkcl3D0n7OfYYBeeuMJbyvedtMOkHUXMQ%2FwcvUmvSFoFnt6cL142DvIB%2Ffx8gRLk7JeWDA3kj4XzAejClZZ9eRAnDz%2F0Cw7lDZU6%2BdzYmUcYiUZLxWrbPg4Dz5zjC6J2VZADEQ1e1sq%2Fzq4nfXktmQlxVo4DI6UwJAk2vaZmouLIwdB2TeZfY9lwsOCQTO9Od0PlMgkxI%2BxYHeILcwPvQ%2BSSsagGp9hRSGn9n9cPgTbFGfmOa7igyYqKa7Uad26lBYGHjZD92i0E%2BZGIwIfAPMn7frNweEbSkbvFc4wWHN1WTvAtxSSj3%2F1aTNmR9zbVoccdRrfytLDEvOxloaHF6z6eWPHrwPHt6udHcEuGg0AJIhaOSArAjPD1lDocf5LvdCPD1XFodWK9agrguQ9X7tNE4swbRXqvQD77ORY52MWLLV4P%2FRHwdxFZi0SwHTBzijU3UiD16FDlUvtD7%2F%2FB2ufpJTPtrS8QybtCoaoEkkgsZyEL9kzRrGKeJVErHhHdypWlNU2pM%2FW1YacYa78BUtLc1w8Xdd6YmRnKLovQE8DrrUkOPSWZkiBwIebSUY4OhhbO4vtkOLMGbR3wEkglRLWVQ4815uODk4KPCRKrXqDriC6Cs786E35eNx60PK%2FdPPTpYZ4xHikqR35OQpKVjqdV6%2FwyFpPcBQ%2FB35PlBM3%2BPfapqEoUehtzp54HMSn6tTlOHCkgqonyEhkAxjRer%2Ba3slsL588nOBR8k3P8Ux6dOE9QtywAx3XFwVaSI9A67EzF%2Bygjtpnv9ghZYlkcjMyoe5PmJ1%2Bmc7wkckxzjF65GDtt%2BkRj%2B%2FBuhHnXd8JWxbTSPch7DGWO4LIHeDpCtd6RMvOgbCfDNICl4LYr1IDPAY5dZv6ZINErg8p7Vi3a5jMXGWL4Mkr0ksENkLZvBJChyDMkf14Hx56V%2Bb2nRqUTK6NqmhPLvsfMNYCRyESom9rukNSbUImRNUXXv70cfMSn4OrmEd%2B59Ab34CROfim3rsAsgLyURlANnLmWXsBWli69uhbNnAbZYcg7J3StkKJM1%2BqRuxH0Yc%2BuOjXvNDpUk6G7%2B2ze2ETmdC%2FraD10QaC9KnqXjbt698Q%3D%3D; BAIDUID_BFESS=90B996B2BCB42015D7470F897FBF7BFB:FG=1; Hm_lvt_182d6d59474cf78db37e0b2248640ea5=1775418576; newlogin=1; ploganondeg=1; ppfuid=FOCoIC3q5fKa8fgJnwzbE3sZaS3poGTofPItBD67MTHOloTQtOTfZukshuG+jikLybArGBMGkcl3D0n7OfYYBeeuMJbyvedtMOkHUXMQ/wcvUmvSFoFnt6cL142DvIB/fx8gRLk7JeWDA3kj4XzAejClZZ9eRAnDz/0Cw7lDZU6+dzYmUcYiUZLxWrbPg4Dz5zjC6J2VZADEQ1e1sq/zq4nfXktmQlxVo4DI6UwJAk2vaZmouLIwdB2TeZfY9lwsOCQTO9Od0PlMgkxI+xYHeILcwPvQ+SSsagGp9hRSGn9n9cPgTbFGfmOa7igyYqKa7Uad26lBYGHjZD92i0E+ZGIwIfAPMn7frNweEbSkbvFc4wWHN1WTvAtxSSj3/1aTNmR9zbVoccdRrfytLDEvOxloaHF6z6eWPHrwPHt6udHcEuGg0AJIhaOSArAjPD1lDocf5LvdCPD1XFodWK9agrguQ9X7tNE4swbRXqvQD77ORY52MWLLV4P/RHwdxFZi0SwHTBzijU3UiD16FDlUvtD7//B2ufpJTPtrS8QybtCoaoEkkgsZyEL9kzRrGKeJVErHhHdypWlNU2pM/W1YacYa78BUtLc1w8Xdd6YmRnKLovQE8DrrUkOPSWZkiBwIebSUY4OhhbO4vtkOLMGbR3wEkglRLWVQ4815uODk4KPCRKrXqDriC6Cs786E35eNx60PK/dPPTpYZ4xHikqR35OQpKVjqdV6/wyFpPcBQ/B35PlBM3+PfapqEoUehtzp54HMSn6tTlOHCkgqonyEhkAxjRer+a3slsL588nOBR8k3P8Ux6dOE9QtywAx3XFwVaSI9A67EzF+ygjtpnv9ghZYlkcjMyoe5PmJ1+mc7wkckxzjF65GDtt+kRj+/BuhHnXd8JWxbTSPch7DGWO4LIHeDpCtd6RMvOgbCfDNICl4LYr1IDPAY5dZv6ZINErg8p7Vi3a5jMXGWL4Mkr0ksENkLZvBJChyDMkf14Hx56V+b2nRqUTK6NqmhPLvsfMNYCRyESom9rukNSbUImRNUXXv70cfMSn4OrmEd+59Ab34CROfim3rsAsgLyURlANnLmWXsBWli69uhbNnAbZYcg7J3StkKJM1+qRuxH0Yc+uOjXvNDpUk6G7+2ze2ETmdC/raD10QaC9KnqXjbt698Q==; XFI=c70e1bf0-3163-11f1-b489-2dadfe6cde41; XFCS=695FBCC5D7DBD962C5D6DC2E48C236F15408E81FF0D00C786890B62D0BB96DB0; XFT=Gv9S50jW8Dsti0Pz3zFxK9Ve/hIn8ukc/h6sbzitoVo=; BDUSS=ERPZTRtVVlpaXVuWHZsZXBmMVF6d0Y0VDREUVFUd1NsUENwRnczbkplNWdyZnBwRVFBQUFBJCQAAAAAAAAAAAEAAABxDzMHtePQx7DJAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGAg02lgINNpN; BDUSS_BFESS=ERPZTRtVVlpaXVuWHZsZXBmMVF6d0Y0VDREUVFUd1NsUENwRnczbkplNWdyZnBwRVFBQUFBJCQAAAAAAAAAAAEAAABxDzMHtePQx7DJAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGAg02lgINNpN; STOKEN=c731a7472f0ea4328ca9fe063bc9ac1e3b7629ff8a434d37466e0b1ef1cba6d5; ndut_fmt=91E3099FC2A1F4B2AE025B2794C8B295A231617201B7757703A3EBB2339DBC95; ab_sr=1.0.1_NjM2YzQ0YjYxYzg2Njk4M2Q1MjZhOGM2NzVhMmUwNWRhYjQ0YTNiOWE0NTU0NDg0OWI2OTg2M2EwZTIzZDU2MGFkZDA2MGNhZjJjMGQzMjQxYzBiZmYwMWJkMGJmMWFkYWMwYWIwOTdlMDdkYzI2MzQ3YWMxNDRkMzBkYzExZmI3OGMyOTk0MDIxMTRhZTkzZTY4MjFiYWNjNzk4M2EwZDIyYWU0ZWQ1NWVjNDg4NDc1N2E2MWE2YWM0YzU5NmY4ZmRjM2ZmOGFlYWQ4ODU4NmY3NjQ4OTEzMzU1ZDY2ZjE=; PANPSC=3445149947565138879%3AN%2BPEInrc9NWV4VG606Eco1cS2d9ns3O5C61tf8CKQkg7dT1BfV14cyNfm7R%2FsRJCyOIAxPrXaQpB3Y7%2FFyFzG7koUQnE6IY91zhKvcy%2B6ReZWV1LKJofoWjKBn0niB9o2fNZfjs7wBb2j4TVvzwIkOwaD5dJfjitc4vRdeSBy8z7ChwBYhqyMmYhU1y6mfSpu1tPRVPr6y6VHXzozvQa4TYwU1Xo84sw8BLdi%2B4atdWYJ9TOrOjxYeshvc%2FmBFdoRzFCRrWG2Ixyx4n1zr2IJ7VutOF4Vhht26muO7WOw27o824g1Xiy7ZKxVlqrIDxM; Hm_lpvt_182d6d59474cf78db37e0b2248640ea5=1775444160"
).strip()

# 网盘类型 -> Cookie 映射（键为 normalize_drive_type 规范名）
PAN_COOKIES = {
    "115": COOKIE_115,
    "baidu": COOKIE_BAIDU,
}


def pan_cookie(drive_type=""):
    """取指定网盘的 Cookie；未配置返回空串。"""
    return PAN_COOKIES.get(normalize_drive_type(drive_type), "") or ""


DRIVE_ORDER = [
    x.lower()
    for x in _split_cfg(
        os.environ.get("DRIVE_ORDER", "115;baidu;quark;uc;tianyi;xunlei;ali;123pan")
    )
]

PAN_META = {
    "baidu": {"name": "百度网盘", "short": "百度"},
    "aliyun": {"name": "阿里云盘", "short": "阿里"},
    "quark": {"name": "夸克网盘", "short": "夸克"},
    "tianyi": {"name": "天翼云盘", "short": "天翼"},
    "uc": {"name": "UC网盘", "short": "UC"},
    "115": {"name": "115网盘", "short": "115"},
    "xunlei": {"name": "迅雷网盘", "short": "迅雷"},
    "pan123": {"name": "123云盘", "short": "123"},
    "cmcc": {"name": "移动云盘", "short": "移动"},
    "others": {"name": "其他网盘", "short": "其他"},
}

PAN_PICS = {
    "aliyun": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/ali.jpg",
    "quark": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/quark.png",
    "uc": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/uc.png",
    "xunlei": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/thunder.png",
    "pan123": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/123.png",
    "tianyi": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/189.png",
    "cmcc": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/139.jpg",
    "115": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/115.jpg",
    "baidu": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/baidu.jpg",
    "others": "https://gh-proxy.org/https://github.com//power721/alist-tvbox/raw/refs/heads/master/web-ui/public/folder.png",
}

FILTER_KEY_NAME_MAP = {
    "class": "类型",
    "area": "地区",
    "lang": "语言",
    "year": "年份",
    "letter": "字母",
    "by": "排序",
    "sort": "排序",
    "id": "分类",
}

PAN_URL_RE = re.compile(
    r"https?://(?:115cdn\.com|115\.com|anxia\.com|pan\.quark\.cn|www\.aliyundrive\.com|"
    r"www\.alipan\.com|pan\.baidu\.com|drive\.uc\.cn|fast\.uc\.cn|cloud\.189\.cn|"
    r"www\.123pan\.com|pan\.xunlei\.com|yun\.139\.com)/[^\s\"'<>]+",
    re.I,
)
IS_PAN_SHARE_RE = re.compile(
    r"115|quark|aliyun|alipan|baidu|uc\.cn|123pan|189\.cn|xunlei|anxia|139\.com",
    re.I,
)
ID_HREF_RE = re.compile(
    r"/voddetail/(\d+)/?|/vodplay/(\d+)-\d+-\d+/?"
    r"|/vod/detail/id/(\d+)\.html|/index\.php/vod/detail/id/(\d+)\.html",
    re.I,
)


# ==================== encodeId / decodeId (觅盘) ====================
def _b64url_encode(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")


def _b64url_decode(text):
    s = str(text or "").replace("-", "+").replace("_", "/")
    s += "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def encode_id(typ, data):
    try:
        raw = json.dumps(data or {}, ensure_ascii=False, separators=(",", ":"))
        return "mp|%s|%s" % (typ, _b64url_encode(raw.encode("utf-8")))
    except Exception:
        return ""


def decode_id(raw):
    parts = str(raw or "").split("|")
    if len(parts) < 3 or parts[0] != "mp":
        return "", {}
    try:
        data = json.loads(_b64url_decode("|".join(parts[2:])).decode("utf-8"))
        if not isinstance(data, dict):
            return "", {}
        return parts[1], data
    except Exception:
        return "", {}


def normalize_drive_type(raw):
    value = str(raw or "").lower().strip()
    if not value:
        return "others"
    if "baidu" in value or "百度" in value:
        return "baidu"
    if "aliyun" in value or "alipan" in value or "ali" in value or "阿里" in value:
        return "aliyun"
    if "quark" in value or "夸克" in value:
        return "quark"
    if "tianyi" in value or "189" in value or "天翼" in value:
        return "tianyi"
    if "115" in value:
        return "115"
    if "xunlei" in value or "thunder" in value or "迅雷" in value:
        return "xunlei"
    if "pan123" in value or "123pan" in value or value == "123":
        return "pan123"
    if "cmcc" in value or "139" in value or "移动" in value:
        return "cmcc"
    if "uc" in value:
        return "uc"
    return "others"


def pan_name(drive_type):
    key = normalize_drive_type(drive_type)
    return PAN_META.get(key, PAN_META["others"])["name"]


def pan_pic(drive_type):
    key = normalize_drive_type(drive_type)
    return PAN_PICS.get(key, PAN_PICS["others"])


def sort_drive_keys(keys):
    if not keys or len(keys) <= 1 or not DRIVE_ORDER:
        return list(keys)
    order_map = {name: i for i, name in enumerate(DRIVE_ORDER)}

    def _key(k):
        return order_map.get(normalize_drive_type(k), 10 ** 9)

    return sorted(keys, key=_key)


def infer_drive_type_from_share_url(share_url=""):
    raw = str(share_url or "").lower()
    if not raw:
        return ""
    if "pan.quark.cn" in raw or "drive.quark.cn" in raw:
        return "quark"
    if "drive.uc.cn" in raw or "fast.uc.cn" in raw:
        return "uc"
    if "pan.baidu.com" in raw:
        return "baidu"
    if "cloud.189.cn" in raw:
        return "tianyi"
    if "yun.139.com" in raw:
        return "cmcc"
    if "aliyundrive.com" in raw or "alipan.com" in raw:
        return "aliyun"
    if "pan.xunlei.com" in raw:
        return "xunlei"
    if "115.com" in raw or "115cdn.com" in raw or "anxia.com" in raw:
        return "115"
    if any(x in raw for x in ("123pan.com", "123684.com", "123865.com", "123912.com")):
        return "pan123"
    return ""


# ==================== 工具 ====================
def remove_trailing_slash(url):
    return str(url or "").rstrip("/")


def abs_url(url, base_url=""):
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if re.match(r"^https?://", url, re.I):
        return url
    # 站点 img.php?url=... 代理常 404：目标为完整 http(s) 时改直连
    if "img.php" in url:
        m = re.search(r"[?&]url=(https?%3A%2F%2F[^&]+|https?://[^&]+)", url, re.I)
        if m:
            target = unquote(m.group(1))
            if re.match(r"^https?://", target, re.I):
                return target
    # 以页面 URL 为 base 做标准解析：
    # - 以 / 开头的绝对路径 → 挂到源站根（避免 /vodsearch/xxx + /upload/... 错拼）
    # - 相对路径 → 相对当前页面目录
    base = base_url or (WEB_SITES[0] if WEB_SITES else "")
    if not base:
        base = "https://wn4k.com/"
    if not base.endswith("/"):
        base = base + "/"
    return urljoin(base, url)


def get_id_from_href(href):
    m = ID_HREF_RE.search(str(href or ""))
    if not m:
        return ""
    return next((g for g in m.groups() if g), "")


def normalize_video_id(video_id=""):
    raw = str(video_id or "").strip()
    if not raw:
        return ""
    if re.match(r"^https?://", raw, re.I) or raw.startswith("/"):
        return get_id_from_href(raw) or raw
    return raw


def normalize_share_url(url):
    u = str(url or "").strip().replace("&amp;", "&")
    if not u:
        return ""
    u = re.sub(r"^https?://(?:www\.)?115cdn\.com/", "https://115.com/", u, flags=re.I)
    u = re.sub(r"^https?://(?:www\.)?anxia\.com/", "https://115.com/", u, flags=re.I)
    return re.sub(r"[),.;]+$", "", u)


def extract_pan_url(raw):
    s = str(raw or "").replace("&amp;", "&").strip()
    m = re.search(r"https?://[^\s\"'<>]+", s, re.I)
    return normalize_share_url(m.group(0)) if m else ""


def is_pan_share_url(url=""):
    return bool(IS_PAN_SHARE_RE.search(str(url or "")))


def clean_content(s):
    return re.sub(r"\s+", " ", re.sub(r"收起|展开全部|内详", "", str(s or ""))).strip()


def format_movie_meta(info):
    """详情页可拿到的导演/主演/年份/备注/更新时间/简介拼接（无则空串）。"""
    if not info:
        return ""
    bits = []
    if info.get("vodContent"):
        bits.append(str(info["vodContent"]).strip())
    if info.get("vodDirector"):
        bits.append("导演：" + str(info["vodDirector"]).strip())
    if info.get("vodActor"):
        bits.append("主演：" + str(info["vodActor"]).strip())
    if info.get("vodYear"):
        bits.append("年份：" + str(info["vodYear"]).strip())
    if info.get("vodRemarks"):
        bits.append("备注：" + str(info["vodRemarks"]).strip())
    if info.get("vodPubDate"):
        bits.append("更新时间：" + str(info["vodPubDate"]).strip())
    return "\n".join(x for x in bits if x)


def apply_detail_meta(item, info, count=None):
    """把网页详情字段对齐到 CatVod 条目（导演/主演/备注/更新时间）。"""
    if not item:
        return item
    if info:
        if info.get("vodDirector"):
            item["vod_director"] = info["vodDirector"]
        if info.get("vodActor"):
            item["vod_actor"] = info["vodActor"]
        if info.get("vodYear"):
            item["vod_year"] = info["vodYear"]
        if info.get("vodPubDate"):
            item["vod_pubdate"] = info["vodPubDate"]
            item["vod_time"] = info["vodPubDate"]
        # 备注与网页 m-label=备注 对齐（如 1080P蓝光REMUX）
        if info.get("vodRemarks"):
            item["vod_remarks"] = info["vodRemarks"]
        elif count is not None and not item.get("vod_remarks"):
            item["vod_remarks"] = "%d条" % count
    if count is not None:
        # 链接数保留在简介里，避免挤掉网页备注
        content = str(item.get("vod_content") or "")
        head = "共%d条网盘链接" % count
        if head not in content:
            item["vod_content"] = (head + "\n" + content) if content else head
    return item


def build_link_content(share_url, info=None):
    """简介 = 真实分享链接；有影片元数据则接在链接后面。"""
    url = str(share_url or "").strip()
    meta = format_movie_meta(info)
    if meta:
        return url + "\n" + meta if url else meta
    return url


def pan_referer(share_url=""):
    """网盘分享页 Referer 取分享域名根，避免误用站点头。"""
    m = re.match(r"^(https?://[^/]+)", str(share_url or ""))
    if m:
        return m.group(1) + "/"
    return remove_trailing_slash(WEB_SITES[0]) + "/"


def build_category_path(category_id, page=1):
    tid = str(category_id or "").strip()
    pg = max(1, int(page) if str(page).isdigit() else 1)
    if pg <= 1:
        return "/vodtype/%s/" % tid
    return "/vodtype/%s-%d/" % (tid, pg)


def build_search_path(keyword, page=1):
    enc = quote(str(keyword or "").strip())
    pg = max(1, int(page) if str(page).isdigit() else 1)
    if pg <= 1:
        return "/vodsearch/%s-------------/" % enc
    return "/vodsearch/%s----------%d---/" % (enc, pg)


def build_detail_path(video_id):
    vid = normalize_video_id(video_id)
    if re.match(r"^https?://", str(vid), re.I):
        return str(vid)
    if str(vid).startswith("/"):
        return str(vid)
    return "/voddetail/%s/" % vid


def wrap_movie_as_group_item(movie):
    vid = normalize_video_id(movie.get("vod_id") or movie.get("vod_name") or "")
    if not vid:
        return movie
    return {
        "vod_id": encode_id("m", {"v": vid}),
        "vod_name": movie.get("vod_name") or "",
        "vod_pic": movie.get("vod_pic") or "",
        "vod_remarks": movie.get("vod_remarks") or "",
        "type_id": "pan_category",
        "type_name": "网盘",
        "vod_tag": "folder",
        "panType": "mvg",
    }


def parse_page_count(html_text, current=1):
    max_pg = max(1, int(current) if str(current).isdigit() else 1)
    for href in re.findall(r"href=\"([^\"]+)\"", html_text or ""):
        m = re.search(r"/vodtype/\d+-(\d+)/?", href, re.I)
        if m:
            max_pg = max(max_pg, int(m.group(1)))
        m = re.search(r"/vodsearch/[^/]*?----------+(\d+)---+/?", href, re.I)
        if m:
            max_pg = max(max_pg, int(m.group(1)))
    return max_pg or 1


def is_blocked_html(body=""):
    lower = str(body or "").lower()
    if not lower:
        return False
    return any(x in lower for x in ("just a moment", "cf-browser-verification", "访问验证"))


# ==================== HTML 解析 ====================
def _class_xpath(cls):
    return '//*[contains(concat(" ", normalize-space(@class), " "), " %s ")]' % cls


def _first_text(nodes):
    for n in nodes:
        t = "".join(n.itertext())
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            return t
    return ""


def parse_list_from_html(html_text, base_url=""):
    seen = set()
    result = []
    if not html_text:
        return result

    tree = None
    if lxml_html is not None:
        try:
            tree = lxml_html.fromstring(html_text)
        except Exception:
            tree = None

    if tree is not None:
        for a in tree.xpath('//a[contains(concat(" ", normalize-space(@class), " "), " video-card ")]'):
            href = a.get("href") or ""
            vid = get_id_from_href(href)
            if not vid or vid in seen:
                continue
            title = (a.get("title") or "").strip()
            if not title:
                title = _first_text(a.xpath(
                    './/*[contains(concat(" ", normalize-space(@class), " "), " video-title ")]'
                ))
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue
            seen.add(vid)
            pic = ""
            imgs = a.xpath(".//img")
            if imgs:
                img = imgs[0]
                pic = img.get("data-src") or img.get("data-original") or img.get("src") or ""
                if "loading.gif" in pic:
                    pic = img.get("data-src") or img.get("data-original") or ""
            note = _first_text(a.xpath(
                './/*[contains(concat(" ", normalize-space(@class), " "), " video-episode ")]'
            ))
            result.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": abs_url(pic, base_url),
                "type_id": "",
                "type_name": "",
                "vod_remarks": re.sub(r"\s+", " ", note).strip(),
            })

        if not result:
            for cls in ("module-item", "module-search-item"):
                for el in tree.xpath(_class_xpath(cls)):
                    anchors = el.xpath(
                        './/a[contains(@href, "/voddetail/") or contains(@href, "/vodplay/")]'
                    )
                    if not anchors:
                        continue
                    a = anchors[0]
                    vid = get_id_from_href(a.get("href") or "")
                    if not vid or vid in seen:
                        continue
                    title = (a.get("title") or "").strip()
                    if not title:
                        for sel in (
                            './/*[contains(concat(" ", normalize-space(@class), " "), " module-poster-item-title ")]',
                            './/*[contains(concat(" ", normalize-space(@class), " "), " module-item-title ")]',
                            './/*[contains(concat(" ", normalize-space(@class), " "), " video-name ")]',
                            ".//h3",
                            ".//h4",
                        ):
                            title = _first_text(el.xpath(sel))
                            if title:
                                break
                    title = re.sub(r"\s+", " ", title or "").strip()
                    title = re.sub(r"^立刻播放|^下载", "", title).strip()
                    if not title:
                        continue
                    seen.add(vid)
                    pic = ""
                    imgs = el.xpath(".//img")
                    if imgs:
                        img = imgs[0]
                        pic = img.get("data-src") or img.get("data-original") or img.get("src") or ""
                        if "loading.gif" in pic:
                            pic = img.get("data-src") or img.get("data-original") or ""
                    note = ""
                    for sel in (
                        './/*[contains(concat(" ", normalize-space(@class), " "), " module-item-note ")]',
                        './/*[contains(concat(" ", normalize-space(@class), " "), " module-poster-item-note ")]',
                        './/*[contains(concat(" ", normalize-space(@class), " "), " video-serial ")]',
                    ):
                        note = _first_text(el.xpath(sel))
                        if note:
                            break
                    result.append({
                        "vod_id": vid,
                        "vod_name": title,
                        "vod_pic": abs_url(pic, base_url),
                        "type_id": "",
                        "type_name": "",
                        "vod_remarks": re.sub(r"\s+", " ", note).strip(),
                    })

    if not result:
        for m in re.finditer(
            r'<a[^>]+href="(/voddetail/\d+/)"[^>]*>(.*?)</a>', html_text, re.S | re.I
        ):
            vid = get_id_from_href(m.group(1))
            if not vid or vid in seen:
                continue
            inner = m.group(2)
            tm = re.search(r'title="([^"]+)"', m.group(0))
            title = unescape(tm.group(1)).strip() if tm else ""
            if not title:
                tm = re.search(r'class="[^"]*video-title[^"]*"[^>]*>([^<]+)', inner)
                title = unescape(tm.group(1)).strip() if tm else ""
            if not title:
                tm = re.search(r'<img[^>]+alt="([^"]+)"', inner)
                title = unescape(tm.group(1)).strip() if tm else ""
            if not title:
                continue
            seen.add(vid)
            pm = re.search(r'<img[^>]+(?:data-src|src)="([^"]+)"', inner)
            pic = abs_url(pm.group(1), base_url) if pm else ""
            nm = re.search(r'class="[^"]*video-episode[^"]*"[^>]*>([^<]+)', inner)
            note = unescape(nm.group(1)).strip() if nm else ""
            result.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "type_id": "",
                "type_name": "",
                "vod_remarks": note,
            })

    return result


def parse_vod_base_info(html_text, base_url=""):
    info = {
        "vodName": "",
        "vodPic": "",
        "vodYear": "",
        "vodDirector": "",
        "vodActor": "",
        "vodContent": "",
        "vodRemarks": "",
        "vodPubDate": "",
    }
    if not html_text:
        return info
    if lxml_html is None:
        tm = re.search(r"<title>([^<]+)</title>", html_text, re.I)
        if tm:
            info["vodName"] = re.sub(r"\s+", " ", unescape(tm.group(1))).split(" - ")[0].strip()
        return info
    try:
        tree = lxml_html.fromstring(html_text)
    except Exception:
        return info

    for sel in (
        "//h1",
        '//*[contains(concat(" ", normalize-space(@class), " "), " page-title ")]',
        '//*[contains(concat(" ", normalize-space(@class), " "), " video-info-header ")]//h1',
        '//*[contains(concat(" ", normalize-space(@class), " "), " module-info-heading ")]//h1',
        '//*[contains(concat(" ", normalize-space(@class), " "), " mobile-detail-title ")]',
        '//*[contains(concat(" ", normalize-space(@class), " "), " premium-title ")]',
    ):
        name = _first_text(tree.xpath(sel))
        if name:
            info["vodName"] = name
            break

    for sel in (
        '//*[contains(concat(" ", normalize-space(@class), " "), " module-item-pic ")]//img',
        '//*[contains(concat(" ", normalize-space(@class), " "), " module-info-poster ")]//img',
        '//*[contains(concat(" ", normalize-space(@class), " "), " video-cover ")]//img',
        '//img[contains(@class, "lazyload") or contains(@class, "lazy")]',
        '//*[contains(concat(" ", normalize-space(@class), " "), " premium-poster ")]//img',
        "//meta[@property='og:image']",
    ):
        nodes = tree.xpath(sel)
        if not nodes:
            continue
        n = nodes[0]
        pic = n.get("data-src") or n.get("data-original") or n.get("src") or n.get("content") or ""
        if pic and "loading.gif" not in pic:
            info["vodPic"] = abs_url(pic, base_url)
            break

    for el in tree.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), " video-info-itemtitle ")]'
    ):
        key = _first_text([el])
        nxt = el.getnext()
        if nxt is None:
            continue
        if "剧情" in key or "简介" in key:
            info["vodContent"] = clean_content(_first_text(nxt.xpath(".//p")) or _first_text([nxt]))
        elif "导演" in key:
            val = ", ".join(t for t in (_first_text([a]) for a in nxt.xpath(".//a")) if t)
            if not val:
                val = _first_text([nxt])
            if val:
                info["vodDirector"] = val
        elif any(k in key for k in ("主演", "演员")):
            val = ", ".join(t for t in (_first_text([a]) for a in nxt.xpath(".//a")) if t)
            if not val:
                val = _first_text([nxt])
            if val:
                info["vodActor"] = val
        elif "备注" in key or "清晰" in key:
            val = _first_text([nxt])
            if val:
                info["vodRemarks"] = val
        elif "更新" in key:
            val = _first_text([nxt])
            if val:
                info["vodPubDate"] = val
        elif any(k in key for k in ("年代", "年份", "上映")):
            m = re.search(r"(19|20)\d{2}", _first_text([nxt]))
            if m:
                info["vodYear"] = m.group(0)

    # 网页 premium-meta-grid：导演 / 主演 / 备注 / 更新时间（多选择器用 | 并集，勿串成后代链）
    for el in tree.xpath(
        '(//*[contains(concat(" ", normalize-space(@class), " "), " premium-meta-grid ")]'
        '//*[contains(concat(" ", normalize-space(@class), " "), " meta-item ")])'
        ' | (//*[contains(concat(" ", normalize-space(@class), " "), " meta-item ")])'
        ' | (//*[contains(concat(" ", normalize-space(@class), " "), " video-info-meta ")]'
        '//*[contains(concat(" ", normalize-space(@class), " "), " meta-item ")])'
        ' | (//*[contains(concat(" ", normalize-space(@class), " "), " module-info-item ")])'
    ):
        label = _first_text(el.xpath(
            './/*[contains(concat(" ", normalize-space(@class), " "), " m-label ")]'
            ' | .//*[contains(concat(" ", normalize-space(@class), " "), " meta-label ")]'
            ' | .//*[contains(concat(" ", normalize-space(@class), " "), " info-label ")]'
            ' | .//*[contains(concat(" ", normalize-space(@class), " "), " module-info-title ")]'
        ))
        val = _first_text(el.xpath(
            './/*[contains(concat(" ", normalize-space(@class), " "), " m-val ")]'
            ' | .//*[contains(concat(" ", normalize-space(@class), " "), " meta-value ")]'
            ' | .//*[contains(concat(" ", normalize-space(@class), " "), " info-value ")]'
            ' | .//*[contains(concat(" ", normalize-space(@class), " "), " module-info-content ")]'
        ))
        if not label or not val:
            # 退化：整格文本「标签 值」
            whole = _first_text([el])
            if not whole:
                continue
            for lab in ("导演", "主演", "演员", "备注", "更新时间", "更新", "年份", "年代", "上映"):
                if whole.startswith(lab) or lab in whole[:6]:
                    label = lab
                    val = whole.replace(lab, "", 1).strip(" ：:").strip()
                    break
            if not label or not val:
                continue
        if not info["vodDirector"] and "导演" in label:
            info["vodDirector"] = val
        elif not info["vodActor"] and any(k in label for k in ("主演", "演员")):
            info["vodActor"] = val
        elif not info["vodRemarks"] and "备注" in label:
            info["vodRemarks"] = val
        elif not info["vodPubDate"] and "更新" in label:
            info["vodPubDate"] = val
        elif not info["vodYear"] and any(k in label for k in ("年代", "年份", "上映")):
            m = re.search(r"(19|20)\d{2}", val)
            if m:
                info["vodYear"] = m.group(0)

    if not info["vodYear"]:
        for el in tree.xpath(
            '//*[contains(concat(" ", normalize-space(@class), " "), " premium-tags-top ")]'
            '//*[contains(concat(" ", normalize-space(@class), " "), " p-tag ")]'
        ):
            txt = _first_text([el])
            if re.match(r"^(19|20)\d{2}$", txt):
                info["vodYear"] = txt
                break

    if not info["vodContent"]:
        for sel in (
            '//*[contains(concat(" ", normalize-space(@class), " "), " vod_content ")]',
            '//*[contains(concat(" ", normalize-space(@class), " "), " module-info-introduction ")]',
            '//*[contains(concat(" ", normalize-space(@class), " "), " video-info-content ")]',
            '//*[contains(concat(" ", normalize-space(@class), " "), " detail-desc-text ")]',
            '//*[contains(concat(" ", normalize-space(@class), " "), " premium-plot ")]',
        ):
            nodes = tree.xpath(sel)
            if nodes:
                info["vodContent"] = clean_content(_first_text(nodes[-1:]))
                if info["vodContent"]:
                    break

    return info


def _collect_candidates(el):
    out = []
    for attr in ("data-clipboard-text", "data-copy", "data-pan-item"):
        for n in el.xpath(".//*[@%s]" % attr):
            v = n.get(attr)
            if v:
                out.append(v)
    for n in el.xpath('.//a[starts-with(@href, "http")]'):
        out.append(n.get("href") or "")
    for n in el.xpath(".//p | .//span | .//i"):
        t = _first_text([n])
        if t:
            out.append(t)
    for n in el.xpath(
        './/*[contains(concat(" ", normalize-space(@class), " "), " pan-link-meta ")]'
        ' | .//*[contains(concat(" ", normalize-space(@class), " "), " pan-link-title ")]'
        ' | .//*[contains(concat(" ", normalize-space(@class), " "), " module-row-title ")]'
    ):
        t = _first_text([n])
        if t:
            out.append(t)
    return out


def extract_pan_urls(html_text):
    urls = []
    seen = set()
    if not html_text:
        return urls
    if lxml_html is not None:
        try:
            tree = lxml_html.fromstring(html_text)
        except Exception:
            tree = None
        if tree is not None:
            for sel in (
                '//*[contains(concat(" ", normalize-space(@class), " "), " module-row-info ")]',
                '//*[@data-pan-item]',
                '//*[contains(concat(" ", normalize-space(@class), " "), " pan-link-item ")]',
            ):
                for el in tree.xpath(sel):
                    for raw in _collect_candidates(el):
                        url = extract_pan_url(raw)
                        if not url or not is_pan_share_url(url) or url in seen:
                            continue
                        seen.add(url)
                        urls.append(url)
    if not urls:
        for m in PAN_URL_RE.finditer(html_text):
            url = normalize_share_url(m.group(0))
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls


def extract_pan_items(html_text):
    items = []
    seen = set()
    if not html_text:
        return items

    def push(raw, name):
        url = extract_pan_url(raw)
        if not url or not is_pan_share_url(url) or url in seen:
            return
        seen.add(url)
        clean_name = re.sub(r"https?://\S+", "", str(name or ""))
        clean_name = re.sub(r"\s+", " ", clean_name).strip()
        items.append({"url": url, "name": clean_name})

    if lxml_html is not None:
        try:
            tree = lxml_html.fromstring(html_text)
        except Exception:
            tree = None
        if tree is not None:
            for sel in (
                '//*[@data-pan-item]',
                '//*[contains(concat(" ", normalize-space(@class), " "), " pan-link-item ")]',
                '//*[contains(concat(" ", normalize-space(@class), " "), " module-row-info ")]',
            ):
                for el in tree.xpath(sel):
                    name = ""
                    for nsel in (
                        './/*[contains(concat(" ", normalize-space(@class), " "), " pan-link-title ")]',
                        './/*[contains(concat(" ", normalize-space(@class), " "), " pan-link-label ")]',
                        './/*[contains(concat(" ", normalize-space(@class), " "), " pan-link-name ")]',
                        './/*[contains(concat(" ", normalize-space(@class), " "), " link-title ")]',
                        './/*[contains(concat(" ", normalize-space(@class), " "), " module-row-title ")]',
                    ):
                        name = _first_text(el.xpath(nsel))
                        if name:
                            break
                    if not name:
                        name = _first_text(el.xpath(
                            './/*[contains(concat(" ", normalize-space(@class), " "), " pan-link-meta ")]'
                        ))
                    for raw in _collect_candidates(el):
                        push(raw, name)
    if not items:
        for m in PAN_URL_RE.finditer(html_text):
            push(m.group(0), "")
    return items


def parse_nav_classes(html_text):
    """与网页导航对齐：首页在电影等分类之前。"""
    classes = [{"type_id": "0", "type_name": "首页"}]
    if not html_text:
        return classes
    seen = {"0"}
    for m in re.finditer(
        r'<a[^>]+href="(/vodtype/(\d+)/?)"[^>]*>([^<]{1,20})</a>', html_text, re.I
    ):
        tid, name = m.group(2), unescape(m.group(3)).strip()
        name = re.sub(r"\s+", " ", name)
        if not tid or tid == "0" or not name:
            continue
        if re.search(r"首页|最近|排行|专题|求片|留言|更多", name):
            continue
        if tid in seen:
            continue
        seen.add(tid)
        classes.append({"type_id": tid, "type_name": name})
    return classes


def parse_filters_from_html(html_text):
    groups = []
    if not html_text or lxml_html is None:
        return groups
    try:
        tree = lxml_html.fromstring(html_text)
    except Exception:
        return groups
    boxes = tree.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), " library-box ")]'
    )
    for box in boxes[1:] if len(boxes) > 1 else []:
        links = box.xpath(
            './/*[contains(concat(" ", normalize-space(@class), " "), " library-list ")]//a'
        )
        if not links:
            continue
        first_href = links[0].get("href") or ""
        key = None
        for k in FILTER_KEY_NAME_MAP:
            if ("%s/" % k) in first_href or ("/%s/" % k) in first_href:
                key = k
                break
        if not key and re.search(r"/vodshow/|/vodtype/\d+|/id/\d+", first_href):
            key = "id"
        if not key:
            continue
        values = [{"name": "全部", "value": ""}]
        dedupe = {"__ALL__"}
        for a in links:
            href = a.get("href") or ""
            if not href:
                continue
            value = ""
            marker = "%s/" % key
            idx = href.find(marker)
            if idx >= 0:
                rest = href[idx + len(marker):]
                value = unescape(rest.split("/")[0].split(".")[0] or "")
            elif key == "id":
                m = re.search(r"/vodtype/(\d+)", href) or re.search(r"/id/(\d+)", href)
                value = m.group(1) if m else ""
            name = _first_text([a])
            dk = "%s::%s" % (name, value)
            if (not name and not value) or dk in dedupe:
                continue
            dedupe.add(dk)
            values.append({"name": name, "value": value})
        if len(values) > 1:
            groups.append({
                "key": key,
                "name": FILTER_KEY_NAME_MAP.get(key, key),
                "init": "",
                "value": values,
            })
    return groups


# ==================== HTTP / 登录 ====================
if requests is not None and HTTPAdapter is not object and create_urllib3_context is not None:
    class _InsecureSSLAdapter(HTTPAdapter):
        def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
            ctx = create_urllib3_context()
            ctx.check_hostname = False
            ctx.verify_mode = 0
            try:
                ctx.set_ciphers("DEFAULT@SECLEVEL=1")
            except Exception:
                pass
            kwargs["ssl_context"] = ctx
            return super().init_poolmanager(connections, maxsize, block, **kwargs)
else:
    _InsecureSSLAdapter = None


class HttpClient(object):
    def __init__(self):
        self._lock = threading.Lock()
        self._session = None
        self._logged_in = False
        self._cookie_header = WONIU4K_COOKIE
        if requests is not None:
            s = requests.Session()
            if _InsecureSSLAdapter is not None:
                try:
                    s.mount("https://", _InsecureSSLAdapter())
                except Exception:
                    pass
            s.headers.update({
                "User-Agent": SITE_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
            if self._cookie_header:
                s.headers["Cookie"] = self._cookie_header
            self._session = s

    def _headers(self, extra=None):
        h = {"User-Agent": SITE_UA}
        if self._cookie_header:
            h["Cookie"] = self._cookie_header
        if extra:
            h.update(extra)
        return h

    def get(self, path, timeout=20, referer=None):
        if requests is None:
            raise RuntimeError("requests 模块不可用")
        last_err = None
        for site in WEB_SITES:
            base = remove_trailing_slash(site)
            url = path if str(path).startswith("http") else base + path
            headers = self._headers()
            if referer:
                headers["Referer"] = referer
            elif not str(path).startswith("http"):
                headers["Referer"] = base + "/"
            try:
                resp = self._session.get(url, headers=headers, timeout=timeout, verify=False)
                if resp.status_code != 200:
                    last_err = Exception("HTTP %s" % resp.status_code)
                    continue
                body = resp.text or ""
                if not body:
                    last_err = Exception("empty body")
                    continue
                if is_blocked_html(body):
                    last_err = Exception("blocked")
                    continue
                sc = resp.headers.get("Set-Cookie")
                if sc:
                    self._merge_set_cookie(sc)
                final_base = remove_trailing_slash(str(resp.url).rsplit("/", 1)[0])
                return body, final_base
            except Exception as e:
                last_err = e
                continue
        raise last_err or Exception("所有域名请求均失败")

    def post_form(self, path, data, timeout=15, referer=None, ajax=False):
        if requests is None:
            raise RuntimeError("requests 模块不可用")
        last_err = None
        for site in WEB_SITES:
            base = remove_trailing_slash(site)
            url = path if str(path).startswith("http") else base + path
            headers = self._headers({
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": referer or (base + "/"),
            })
            if ajax:
                headers["X-Requested-With"] = "XMLHttpRequest"
            try:
                resp = self._session.post(url, data=data, headers=headers, timeout=timeout, verify=False)
                sc = resp.headers.get("Set-Cookie")
                if sc:
                    self._merge_set_cookie(sc)
                return resp
            except Exception as e:
                last_err = e
                continue
        raise last_err or Exception("登录请求失败")

    def _merge_set_cookie(self, set_cookie_text):
        pairs = re.findall(r"([^=;,]+)=([^;,]*)", set_cookie_text or "")
        if not pairs:
            return
        jar = {}
        if self._cookie_header:
            for kv in self._cookie_header.split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    jar[k.strip()] = v.strip()
        skip = {"path", "expires", "max-age", "domain", "httponly", "secure"}
        for k, v in pairs:
            k = k.strip()
            if k.lower() in skip:
                continue
            jar[k] = v.strip()
        self._cookie_header = "; ".join("%s=%s" % (k, v) for k, v in jar.items())
        if self._session is not None:
            self._session.headers["Cookie"] = self._cookie_header


_http = HttpClient()
_detail_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 43200


def _cache_get(key):
    with _cache_lock:
        hit = _detail_cache.get(key)
        if not hit:
            return None
        ts, val = hit
        if time.time() - ts > _CACHE_TTL:
            _detail_cache.pop(key, None)
            return None
        return val


def _cache_set(key, val):
    with _cache_lock:
        if len(_detail_cache) > 200:
            oldest = sorted(_detail_cache.items(), key=lambda kv: kv[1][0])
            for k, _ in oldest[:50]:
                _detail_cache.pop(k, None)
        _detail_cache[key] = (time.time(), val)


def _download_image_b64(url, timeout=10):
    if requests is None:
        return ""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": SITE_UA, "Referer": WEB_SITES[0] + "/"},
            timeout=timeout,
            verify=False,
        )
        if resp.status_code != 200 or not resp.content:
            return ""
        return base64.b64encode(resp.content).decode("ascii")
    except Exception:
        return ""


def _solve_captcha(verify_url):
    if not verify_url or not CAPTCHA_SERVICE_URL:
        return ""
    b64 = _download_image_b64(verify_url)
    if not b64:
        return ""
    try:
        resp = requests.post(
            CAPTCHA_SERVICE_URL + "/ocr/",
            json={"data": b64},
            timeout=30,
            verify=False,
        )
        data = resp.json() if resp.text else {}
        if data.get("status") == 0 and data.get("data"):
            d = data["data"]
            return str(d.get("code") or d.get("result") or d.get("text") or "").strip()
    except Exception:
        return ""
    return ""


def ensure_login():
    """登录后才能看到完整网盘链接。已登录则跳过。"""
    if _http._logged_in:
        return True
    if _http._cookie_header and _http._cookie_header != WONIU4K_COOKIE:
        try:
            body, _ = _http.get("/user/index/", timeout=12)
            if "退出登录" in body or "user-name" in body:
                _http._logged_in = True
                return True
        except Exception:
            pass
    if not LOGIN_USERNAME or not LOGIN_PASSWORD:
        return False

    for attempt in range(1, 3):
        try:
            body, _ = _http.get("/user/login/", timeout=15)
            verify_url = ""
            m = re.search(r'id="(?:verify_img|verify-img)"[^>]+src="([^"]+)"', body or "")
            if not m:
                m = re.search(r'src="([^"]+)"[^>]+id="(?:verify_img|verify-img)"', body or "")
            if m:
                verify_url = abs_url(m.group(1), WEB_SITES[0])
            code = ""
            if verify_url:
                code = _solve_captcha(verify_url)
                if not code:
                    time.sleep(0.8)
                    continue
            form = {"user_name": LOGIN_USERNAME, "user_pwd": LOGIN_PASSWORD}
            if code:
                form["verify"] = code
            resp = _http.post_form(
                "/user/login.html",
                form,
                referer=remove_trailing_slash(WEB_SITES[0]) + "/user/login/",
                ajax=True,
            )
            try:
                result = resp.json()
            except Exception:
                result = {"code": 0, "msg": "登录响应解析失败"}
            if result.get("code") == 1:
                _http._logged_in = True
                return True
            msg = str(result.get("msg") or "")
            if re.search(r"验证码|verify", msg, re.I) and attempt < 2:
                time.sleep(0.8)
                continue
            return False
        except Exception:
            if attempt < 2:
                time.sleep(1.0)
            continue
    return False


# ==================== 业务：分组 ====================
def build_movie_drive_groups(video_id, vod_name, vod_pic, pan_urls, info=None):
    by_type = {}
    unknown = 0
    for url in pan_urls or []:
        t = infer_drive_type_from_share_url(url)
        if t:
            by_type[t] = by_type.get(t, 0) + 1
        else:
            unknown += 1
    # 分组卡无分享链接：简介放影片元数据（导演/主演/备注/更新时间/剧情）
    folder_content = format_movie_meta(info)
    items = []
    for drive_type, count in by_type.items():
        item = {
            "vod_id": encode_id("g", {"v": video_id, "t": drive_type}),
            "vod_name": pan_name(drive_type),
            "vod_pic": vod_pic or pan_pic(drive_type),
            "type_id": "pan_category",
            "type_name": "网盘分类",
            "vod_remarks": "%d条" % count,
            "vod_tag": "folder",
            "panType": drive_type,
            "vod_content": folder_content,
        }
        apply_detail_meta(item, info, count=count)
        items.append(item)
    if unknown > 0:
        item = {
            "vod_id": encode_id("g", {"v": video_id, "t": "others"}),
            "vod_name": pan_name("others"),
            "vod_pic": vod_pic or pan_pic("others"),
            "type_id": "pan_category",
            "type_name": "网盘分类",
            "vod_remarks": "%d条" % unknown,
            "vod_tag": "folder",
            "panType": "others",
            "vod_content": folder_content,
        }
        apply_detail_meta(item, info, count=unknown)
        items.append(item)
    if len(items) > 1:
        items.sort(key=lambda x: x.get("vod_name") or "")
    return items


def _link_item_to_vod(share_url, name, vod_pic, drive_type, movie_title="", info=None, video_id=""):
    data = {"u": share_url, "n": name or "", "t": drive_type}
    # 带上影片 video_id：点开 R 级详情时回拉站点元数据（演员/简介/年份）
    if video_id:
        data["v"] = str(video_id)
    rid = encode_id("r", data)
    display = name or (pan_name(drive_type) if drive_type else "网盘资源")
    if movie_title and movie_title not in display:
        display = "%s · %s" % (movie_title[:20], display[:30])
    item = {
        "vod_id": rid,
        "vod_name": display,
        "vod_pic": vod_pic or pan_pic(drive_type),
        "type_id": drive_type or "others",
        "type_name": pan_name(drive_type) if drive_type else "网盘",
        "vod_remarks": movie_title or pan_name(drive_type),
        "vod_tag": "file",
        "panType": drive_type or "others",
        "panUrl": share_url,
        # 简介：真实分享链接，影片元数据接在后面（无则仅链接）
        "vod_content": build_link_content(share_url, info),
        "vod_play_from": pan_name(drive_type) if drive_type else "网盘",
        "vod_play_url": "播放$%s" % _sanitize_play_url(share_url),
    }
    # 导演/主演/备注/更新时间与网页详情对齐
    apply_detail_meta(item, info)
    if info and info.get("vodRemarks"):
        item["vod_remarks"] = info["vodRemarks"]
    return item


def _get_detail_cached(video_id):
    key = "detail:%s" % video_id
    cached = _cache_get(key)
    if cached is not None:
        return cached
    ensure_login()
    path = build_detail_path(video_id)
    body, base = _http.get(path, timeout=20)
    _cache_set(key, (body, base))
    return body, base


def _movie_drive_groups_by_vid(video_id):
    """影片详情 m → 按网盘类型拆成多张分组卡 g（trae 三级分组第一层）。"""
    vid = normalize_video_id(video_id)
    body, base = _get_detail_cached(vid)
    info = parse_vod_base_info(body, base)
    pan_urls = extract_pan_urls(body)
    groups = build_movie_drive_groups(vid, info["vodName"], info["vodPic"], pan_urls, info)
    return {
        "list": groups,
        "page": 1,
        "pagecount": 1,
        "limit": PAGE_SIZE,
        "total": len(groups),
    }


def _movie_links_by_drive(video_id, drive_type):
    """分组卡 g → 该盘下各分享链接列表，每条展开选集（三级分组第二层）。"""
    vid = normalize_video_id(video_id)
    body, base = _get_detail_cached(vid)
    info = parse_vod_base_info(body, base)
    dt = normalize_drive_type(drive_type)
    link_items = []
    seen = set()
    for url in extract_pan_urls(body):
        u = normalize_share_url(url)
        if not u or u in seen:
            continue
        inferred = infer_drive_type_from_share_url(u)
        if dt not in ("others", "all", "") and inferred != dt:
            continue
        if dt == "others" and inferred:
            continue
        seen.add(u)
        item = _link_item_to_vod(
            u, "", info["vodPic"], inferred or "others", info["vodName"], info, vid)
        _attach_episodes(item, u, inferred or "others")
        link_items.append(item)
    return {
        "list": link_items,
        "page": 1,
        "pagecount": 1,
        "limit": PAGE_SIZE,
        "total": len(link_items),
    }


def _episode_meta(name):
    """从文件名提取 (季, 集)；识别不到返回 (0, 0)。"""
    s = str(name or "")
    m = re.search(r"[Ss](\d{1,2})[ ._-]*[Ee][Pp]?(\d{1,4})", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(?:^|[^A-Za-z0-9])[Ee][Pp]?[ ._-]?(\d{1,4})(?:[^0-9]|$)", s)
    if m:
        return 1, int(m.group(1))
    m = re.search(r"第\s*(\d{1,4})\s*[集话話期]", s)
    if m:
        return 1, int(m.group(1))
    # 「剧名 - 01 [1080P]」这类：1~3 位数字，避免把年份/1080P/音轨规格当集数：
    # (?<![Hh\d]\.) 拦 H.265、7.1 小数第二位；(?!\.\d) 拦 7.1 小数第一位
    m = re.search(r"(?:^|[\s._-])(?<![Hh\d]\.)(\d{1,3})(?=[\s._\[]|$)(?!\.\d)", s)
    if m:
        return 1, int(m.group(1))
    return 0, 0


def _pick_main_group(videos):
    """多目录分享取「集数最多」的那一个目录，避免混入不同压制组的文件。"""
    if not videos:
        return []
    groups = {}
    for v in videos:
        groups.setdefault(str(v.get("dir") or ""), []).append(v)
    if len(groups) <= 1:
        return videos
    best = max(groups.values(), key=len)
    return best if len(best) > 1 else videos


def _order_episodes(videos):
    """按季/集排序并去重（同集多版本只保留一个）。"""
    def _key(v):
        season, ep = _episode_meta(v.get("name") or "")
        return (0 if ep else 1, season, ep, str(v.get("name") or ""))

    ordered = sorted(videos or [], key=_key)
    out, seen = [], set()
    for v in ordered:
        season, ep = _episode_meta(v.get("name") or "")
        k = (season, ep) if ep else str(v.get("name") or "")
        if k in seen:
            continue
        seen.add(k)
        out.append(v)
    return out


def _list_share_videos(share_url, drive_type):
    """列出分享内全部视频（带 12 小时缓存 + 主目录挑选）。"""
    key = "eps:%s" % share_url
    hit = _cache_get(key)
    if hit is not None:
        return hit
    videos = list_share_videos(share_url, drive_type) or []
    videos = _pick_main_group(videos)
    _cache_set(key, videos)
    return videos


def _build_episode_play_url(share_url, videos):
    """分享 → CatVod 选集串：[1.5G mp4] 文件名$encode_id#...（季集排序去重）。"""
    ordered = _order_episodes(videos)
    if not ordered:
        return "播放$%s" % _sanitize_play_url(share_url)
    parts = []
    for v in ordered:
        raw = str(v.get("name") or "")
        label = _ep_label(raw, v.get("size"), v.get("ext") or "")
        eid = encode_id("e", {
            "u": share_url,
            "f": str(v.get("fid") or ""),
            "n": raw,
            "h": str(v.get("sha") or ""),
        })
        parts.append("%s$%s" % (_sanitize_ep_name(label), _sanitize_play_url(eid)))
    return "#".join(parts)


def _attach_episodes(item, share_url, drive_type):
    """把分享内的视频展开成选集（单集同样带 [大小 扩展名] 文件名标签）。"""
    if not item or drive_type not in ("115", "baidu"):
        return item
    videos = _list_share_videos(share_url, drive_type)
    if videos:
        item["vod_play_from"] = pan_name(drive_type)
        item["vod_play_url"] = _build_episode_play_url(share_url, videos)
    if videos and all(
        _file_ext(v.get("name") or "", v.get("ext") or "") == "iso" for v in videos
    ):
        # 纯原盘分享：列表层明示不可在线播放，别让用户逐条点过去试
        item["vod_remarks"] = "原盘ISO·不可在线播放"
    return item


def _share_url_detail(share_url, title="", info=None, video_id=""):
    u = normalize_share_url(share_url)
    dt = infer_drive_type_from_share_url(u) or "others"
    # R 级详情：id 里带了 video_id 则回拉站点元数据（演员/导演/简介/年份）
    if not info and video_id:
        try:
            body, base = _get_detail_cached(video_id)
            info = parse_vod_base_info(body, base)
        except Exception:
            info = None
    site_name = str((info or {}).get("vodName") or "").strip()
    # 名称：站点片名 > 传入标题 > 网盘名；简介一律放真实分享链接（+元数据）
    name = site_name or title or (pan_name(dt) + "分享")
    vod = _link_item_to_vod(
        u, name, (info or {}).get("vodPic") or pan_pic(dt),
        dt, site_name or title, info, video_id or "",
    )
    vod["vod_name"] = name
    vod["vod_content"] = build_link_content(u, info)
    # 分享展开成选集（115/百度）：单集也带 [大小 扩展名] 文件名标签，失败回落「播放」
    _attach_episodes(vod, u, dt)
    return _single_vod_result(vod)


def _search_videos_by_drive(keyword, page, drive_type):
    """搜索关键词下、指定网盘类型的链接列表（探测各详情页）。"""
    ensure_login()
    path = build_search_path(keyword, page)
    body, base = _http.get(path, timeout=20)
    videos = parse_list_from_html(body, base)
    dt = normalize_drive_type(drive_type)
    link_items = []
    seen = set()
    idx = 0
    # 限制探测数量，避免过慢
    for video in videos[:12]:
        try:
            dbody, dbase = _get_detail_cached(video.get("vod_id") or "")
        except Exception:
            continue
        for item in extract_pan_items(dbody):
            u = normalize_share_url(item.get("url") or "")
            if not u or u in seen:
                continue
            inferred = infer_drive_type_from_share_url(u)
            if dt not in ("others", "all", "") and inferred != dt:
                continue
            if dt == "others" and inferred:
                continue
            seen.add(u)
            idx += 1
            # 该片详情元数据（导演/主演/剧情）接在分享链接后
            dinfo = parse_vod_base_info(dbody, dbase)
            link_items.append(
                _link_item_to_vod(u, item.get("name") or "", video.get("vod_pic") or "",
                                  inferred or "others", video.get("vod_name") or "", dinfo,
                                  video.get("vod_id") or "")
            )
    return {
        "list": link_items,
        "page": page,
        "pagecount": parse_page_count(body, page),
        "limit": PAGE_SIZE,
        "total": len(link_items),
    }


# ==================== 网盘直链解析 ====================
# playerContent 返回分享页 HTML 会导致 OK影视「container unsupported」。
# 下列 resolve_* 把分享链接解析成真视频流（m3u8/mp4），失败返回 None。

_VIDEO_EXT_RE = re.compile(
    # iso：115 蓝光原盘分享也要能列出来（在线播放层另行拦截，见 playerContent）
    r"\.(mp4|mkv|flv|ts|m3u8|avi|wmv|mov|rmvb|mpg|mpeg|m4v|webm|iso)(?:\?|$)",
    re.I,
)


def _is_video_name(name=""):
    return bool(_VIDEO_EXT_RE.search(str(name or "").strip()))


def _sanitize_play_url(url=""):
    """vod_play_url 分隔符消毒：# $ 换行会截断宿主解析。"""
    return (
        str(url or "")
        .replace("#", "%23")
        .replace("$", "%24")
        .replace("\r", "")
        .replace("\n", "")
    )


def _sanitize_ep_name(name=""):
    """选集名消毒：去掉分隔符，限长。"""
    s = re.sub(r"[$#\r\n]+", " ", str(name or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:80]


def _format_size(n):
    """字节 → 人类可读：1.5G / 500M / 100K。"""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n >= 1024 ** 3:
        v = n / float(1024 ** 3)
        return ("%.1fG" % v) if v < 100 else ("%dG" % int(v))
    if n >= 1024 ** 2:
        v = n / float(1024 ** 2)
        return ("%.1fM" % v) if v < 100 else ("%dM" % int(v))
    if n >= 1024:
        return "%dK" % int(n / 1024)
    return "%dB" % n


def _file_ext(name="", ico=""):
    """扩展名（小写、无点），优先 ico 字段。"""
    e = str(ico or "").strip().lstrip(".")
    if e:
        return e.lower()
    m = re.search(r"\.([A-Za-z0-9]{1,8})(?:\?|$)", str(name or "").strip())
    return m.group(1).lower() if m else ""


def _ep_label(name, size=None, ext=""):
    """分集显示名：[1.5G mp4] 文件名。"""
    size_s = _format_size(size)
    ext = ext or _file_ext(name)
    base = _sanitize_ep_name(name) or "播放"
    meta = " ".join(x for x in (size_s, ext) if x)
    if meta:
        return "[%s] %s" % (meta, base)
    return base


def _pack_play(lines):
    """拼 CatVod 多线路/多集。

    lines: [(线路名, [(集名, 播放id), ...]), ...]
    → (vod_play_from, vod_play_url)
    """
    froms = []
    urls = []
    for line_name, episodes in lines:
        eps = list(episodes or [])
        if not eps:
            continue
        froms.append(_sanitize_ep_name(line_name) or "线路")
        parts = []
        for i, ep in enumerate(eps):
            if isinstance(ep, dict):
                ep_name = ep.get("name") or ""
                play_id = ep.get("id") or ep.get("url") or ""
            else:
                ep_name = ep[0] if len(ep) > 0 else ""
                play_id = ep[1] if len(ep) > 1 else ""
            ep_name = _sanitize_ep_name(ep_name) or ("第%d集" % (i + 1) if len(eps) > 1 else "播放")
            play_id = _sanitize_play_url(str(play_id or ""))
            if not play_id:
                continue
            parts.append("%s$%s" % (ep_name, play_id))
        if not parts:
            continue
        urls.append("#".join(parts))
    if not froms or not urls:
        return "", ""
    return "$$$".join(froms), "$$$".join(urls)


def _single_vod_result(vod):
    if not vod:
        return {"list": [], "page": 1, "pagecount": 0, "limit": PAGE_SIZE, "total": 0}
    return {
        "list": [vod],
        "page": 1,
        "pagecount": 1,
        "limit": PAGE_SIZE,
        "total": 1,
    }


def list_share_videos(share_url="", drive_type=""):
    """列分享内全部视频文件 [{name, fid, size, ext}]，失败 []。仅 115/百度。"""
    try:
        dt = normalize_drive_type(drive_type or infer_drive_type_from_share_url(share_url))
        if dt == "115":
            return _115_list_videos(share_url)
        if dt == "baidu":
            return _baidu_list_videos(share_url)
    except Exception:
        return []
    return []


def _episodes_from_share_files(share_url, files):
    """文件列表 → 选集 [(名, share|fid)]；空则回退单条播放。"""
    u = normalize_share_url(share_url)
    eps = []
    n = len(files or [])
    for i, f in enumerate(files or []):
        if not isinstance(f, dict):
            continue
        fid = str(f.get("fid") or "").strip()
        raw = str(f.get("name") or "")
        name = _ep_label(raw, f.get("size"), f.get("ext") or "")
        if not _sanitize_ep_name(raw):
            name = "第%d集" % (i + 1) if n > 1 else "播放"
        play_id = "%s|%s" % (u, fid) if fid else u
        eps.append((name, play_id))
    if not eps:
        eps = [("播放", u)]
    return eps


class _M115Crypto:
    """115 proapi 对称+RSA 加解密（fake115upload / 115drive-webdav 同款）。"""

    G_KEY_L = bytes.fromhex("7806AD4C33865D184C013F46")
    G_KEY_S = bytes.fromhex("2923215E")
    G_KTS = bytes.fromhex(
        "F0E569AEBFDCBF8A1A45E8BE7DA673B8DE8FE7C445DA86C49B648B146AB4F1AA"
        "3801359E26692C86006B4FA5363462A62A966818F24AFDBD6B978F4D8F8913B7"
        "6C8E93ED0E0D483ED72F88D8FEFE7E8650954FD1EB832634DB667B9C7E9D7A81"
        "32EAB633DE3AA95934663BAABA816048B9D5819CF86C8477FF5478265FBEE81E"
        "369F34805C452C9B76D51B8FCCC3B8F5"
    )
    RSA_N = int(
        "8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b86021"
        "36477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad633"
        "8c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f1"
        "0a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683",
        16,
    )
    RSA_E = 0x10001

    def __init__(self):
        self.g_key_l = self.G_KEY_L
        self.g_key_s = self.G_KEY_S
        self.l_rnd_key = b""

    def _setkey(self, randkey, sk_len):
        length = sk_len * (sk_len - 1)
        index = 0
        xorkey = bytearray()
        if randkey:
            for _i in range(sk_len):
                x = (randkey[_i] + self.G_KTS[index]) & 0xFF
                xorkey.append(self.G_KTS[length] ^ x)
                length -= sk_len
                index += sk_len
        if sk_len == 4:
            self.g_key_s = bytes(xorkey)
        elif sk_len == 12:
            self.g_key_l = bytes(xorkey)

    @staticmethod
    def _xor115(src, key):
        pad = len(src) % 4
        out = bytearray(len(src))
        if pad > 0:
            for i in range(pad):
                out[i] = src[i] ^ key[i]
        lkey = len(key)
        num = 0
        for i in range(pad, len(src)):
            if num >= lkey:
                num = num % lkey
            out[i] = src[i] ^ key[num]
            num += 1
        return bytes(out)

    def encode(self, plaintext):
        """str → URL-safe base64（POST data= 后的值）。"""
        if not _HAS_CRYPTO:
            return ""
        self.g_key_l = self.G_KEY_L
        self.g_key_s = self.G_KEY_S
        self.l_rnd_key = os.urandom(16)
        self._setkey(self.l_rnd_key, 4)
        data = plaintext.encode("utf-8")
        tmp = self._xor115(data, self.g_key_s)[::-1]
        xortext = self._xor115(tmp, self.g_key_l)
        payload = self.l_rnd_key + xortext
        key = RSA.construct((self.RSA_N, self.RSA_E))
        cipher = PKCS1_v1_5.new(key)
        out = bytearray()
        block = 117
        for i in range(0, len(payload), block):
            out.extend(cipher.encrypt(payload[i : i + block]))
        return quote(base64.b64encode(bytes(out)).decode("ascii"))

    def decode(self, ciphertext_b64):
        """base64 密文 → 明文 bytes（需先 encode 同一实例）。"""
        if not _HAS_CRYPTO or not self.l_rnd_key:
            return b""
        try:
            ct = base64.b64decode(ciphertext_b64)
        except Exception:
            return b""
        plain = bytearray()
        nblocks = len(ct) // 128
        for i in range(nblocks):
            chunk = ct[i * 128 : (i + 1) * 128]
            m = long_to_bytes(pow(bytes_to_long(chunk), self.RSA_E, self.RSA_N))
            if not m:
                continue
            if m[:1] == b"\x00":
                m = m[1:]
            sep = m.find(b"\x00")
            if sep >= 0:
                plain.extend(m[sep + 1 :])
            else:
                plain.extend(m)
        if len(plain) < 16:
            return b""
        s_rnd_key = bytes(plain[:16])
        body = bytes(plain[16:])
        self._setkey(self.l_rnd_key, 4)
        self._setkey(s_rnd_key, 12)
        tmp = self._xor115(body, self.g_key_l)[::-1]
        return self._xor115(tmp, self.g_key_s)


def _115_share_downurl(session, code, pwd, fid):
    """分享文件直链：proapi.115.com/app/share/downurl（不依赖个人盘 pickcode）。"""
    if not _HAS_CRYPTO or requests is None:
        return ""
    crypto = _M115Crypto()
    payload = json.dumps(
        {
            "share_code": str(code or ""),
            "receive_code": str(pwd or ""),
            "file_id": str(fid or ""),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    enc = crypto.encode(payload)
    if not enc:
        return ""
    body = "data=" + enc
    headers = {
        "User-Agent": SITE_UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://115.com/",
        "Origin": "https://115.com",
    }
    ck = _cookie_header_for(session, "https://proapi.115.com/")
    if ck:
        headers["Cookie"] = ck
    try:
        r = session.post(
            "https://proapi.115.com/app/share/downurl",
            data=body,
            headers=headers,
            timeout=15,
            verify=False,
        )
        resp = r.json()
    except Exception:
        return ""
    if not isinstance(resp, dict):
        return ""
    if resp.get("state") is False:
        return ""
    enc_resp = resp.get("data")
    if not isinstance(enc_resp, str) or not enc_resp:
        return ""
    try:
        plain = crypto.decode(enc_resp)
        obj = json.loads(plain.decode("utf-8", "ignore"))
    except Exception:
        return ""
    if not isinstance(obj, dict):
        return ""
    u = obj.get("url")
    if isinstance(u, dict):
        return str(u.get("url") or u.get("file_url") or "")
    if isinstance(u, str) and u:
        return u
    for k in ("play_url", "download_url", "file_url"):
        if obj.get(k):
            return str(obj[k])
    return ""


def _json_get(session, url, params=None, headers=None, timeout=15):
    h = {"User-Agent": SITE_UA, "Accept": "application/json, text/plain, */*"}
    if headers:
        h.update(headers)
    r = session.get(url, params=params, headers=h, timeout=timeout, verify=False)
    try:
        return r.json()
    except Exception:
        return {}


def _json_post(session, url, data=None, headers=None, timeout=15):
    h = {"User-Agent": SITE_UA, "Accept": "application/json, text/plain, */*"}
    if headers:
        h.update(headers)
    r = session.post(url, data=data, headers=h, timeout=timeout, verify=False)
    try:
        return r.json()
    except Exception:
        return {}


def _new_pan_session(drive_type=""):
    """带网盘 Cookie 的独立 Session（与站点 HttpClient 隔离）。

    Cookie 放进 jar 而非 headers：headers 静态 Cookie 会盖住响应 Set-Cookie
    合并，且百度 streaming 对带全量配置 Cookie 的头会回 errno=71。
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": SITE_UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    ck = pan_cookie(drive_type)
    if ck:
        for part in str(ck).split(";"):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if not k:
                continue
            try:
                s.cookies.set(k, v)
            except Exception:
                pass
    return s


def _cookie_header_for(session, url=""):
    """导出将发往 url 的 Cookie 头（含 path 定向 cookie）。"""
    try:
        if url and requests is not None:
            prep = session.prepare_request(requests.Request("GET", url))
            ck = prep.headers.get("Cookie")
            if ck:
                return ck
    except Exception:
        pass
    try:
        return "; ".join("%s=%s" % (c.name, c.value) for c in session.cookies)
    except Exception:
        return ""


def _baidu_list_videos(share_url=""):
    """列百度分享内全部视频文件 [{name, fid}]，失败 []。"""
    if requests is None:
        return []
    u = str(share_url or "")
    m = re.search(r"pan\.baidu\.com/s/1([A-Za-z0-9_-]+)", u)
    if not m:
        return []
    surl = m.group(1)
    mp = re.search(r"[?&]pwd=([0-9A-Za-z]+)", u)
    pwd = mp.group(1) if mp else ""
    page_url = "https://pan.baidu.com/s/1" + surl + (("?pwd=" + pwd) if pwd else "")
    origin = "https://pan.baidu.com"
    s = requests.Session()
    s.headers.update({
        "User-Agent": SITE_UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    verify = {}
    for attempt in range(3):
        try:
            verify = _json_post(
                s,
                "https://pan.baidu.com/share/verify?surl=%s&channel=channellist&clienttype=0&app_id=250528"
                % quote(surl),
                data={"pwd": pwd, "vcode": "", "vcode_str": ""},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Referer": origin + "/",
                    "Origin": origin,
                },
            ) or {}
        except Exception:
            verify = {}
        errno = verify.get("errno")
        if str(errno) in ("0", ""):
            break
        if str(errno) in ("-12", "-9") and attempt < 2:
            time.sleep(0.8)
            continue
        break
    if verify.get("randsk") and not s.cookies.get("BDCLND"):
        try:
            s.cookies.set("BDCLND", str(verify.get("randsk")), domain="pan.baidu.com")
        except Exception:
            pass
    try:
        r = s.get(page_url, headers={"Referer": origin + "/"}, timeout=15, verify=False)
        raw = r.text or ""
    except Exception:
        return []
    seg = ""
    yi = raw.find("window.yunData=")
    if yi >= 0:
        seg = raw[yi:yi + 1200]
    else:
        ai = raw.find("share_uk")
        if ai >= 0:
            seg = raw[max(0, ai - 600):ai + 1200].replace('\\"', '"')
    mm = re.search(r'''["']?share_uk["']?\s*:\s*["']?(\d+)''', seg)
    uk = mm.group(1) if mm else ""
    mm = re.search(r'''["']?shareid["']?\s*:\s*["']?(\d+)''', seg)
    shareid = mm.group(1) if mm else ""
    if not uk or not shareid:
        return []
    sekey = unquote(s.cookies.get("BDCLND") or "")

    def _list(dir_path=""):
        params = {
            "shareid": shareid,
            "uk": uk,
            "app_id": "250528",
            "channel": "channellist",
            "clienttype": "0",
            "order": "time",
            "desc": "1",
            "showempty": "0",
            "view_mode": "1",
            "web": "1",
            "page": "1",
            "num": "100",
        }
        if sekey:
            params["is_from_web"] = "1"
            params["sekey"] = sekey
        if dir_path:
            params["dir"] = dir_path
        else:
            params["root"] = "1"
        data = _json_get(
            s,
            "https://pan.baidu.com/share/list",
            params=params,
            headers={"Referer": page_url, "Accept": "application/json, text/plain, */*"},
        )
        if not isinstance(data, dict) or str(data.get("errno", "0")) not in ("0", ""):
            return []
        lst = data.get("list")
        return lst if isinstance(lst, list) else []

    def _child_path(it):
        raw_path = str((it or {}).get("path") or "")
        if re.match(r"^/sharelink\d*-\d+(/|$)", raw_path):
            return raw_path
        name = str((it or {}).get("server_filename") or "")
        fs_id = str((it or {}).get("fs_id") or "")
        if not name or not fs_id:
            return ""
        return "/sharelink%s-%s/%s" % (uk, fs_id, name)

    out = []

    def _walk(dir_path="", depth=0):
        if depth > 4 or len(out) >= 50:
            return
        items = _list(dir_path)
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("isdir") or "0") in ("1", "true"):
                continue
            name = str(it.get("server_filename") or it.get("filename") or "")
            fid = str(it.get("fs_id") or "")
            if fid and _is_video_name(name) and len(out) < 50:
                out.append({
                    "name": name,
                    "fid": fid,
                    "size": it.get("size") or 0,
                    "ext": "",
                    "dir": dir_path,
                })
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("isdir") or "0") not in ("1", "true"):
                continue
            child = _child_path(it)
            if not child:
                continue
            _walk(child, depth + 1)
            if len(out) >= 50:
                return

    _walk()
    return out


# resolve_baidu_share 最近一次失败原因（playerContent 透给用户，见 play msg）
_LAST_RESOLVE_ERR = ""


def resolve_baidu_share(share_url="", fid=""):
    """百度分享 → 真视频流。成功返回 (url, header_dict)，失败 None。

    配方（真网已验证）：
      verify → 分享页抽 uk/shareid → list 递归找视频 fs_id
      → tplconfig 拿 sign/timestamp → streaming 出 m3u8
    streaming 必须带 Cookie + Referer(分享页) + Origin，否则 errno=31341。
    """
    global _LAST_RESOLVE_ERR
    _LAST_RESOLVE_ERR = ""
    if requests is None:
        return None
    u = str(share_url or "")
    m = re.search(r"pan\.baidu\.com/s/1([A-Za-z0-9_-]+)", u)
    if not m:
        return None
    surl = m.group(1)
    mp = re.search(r"[?&]pwd=([0-9A-Za-z]+)", u)
    pwd = mp.group(1) if mp else ""
    page_url = "https://pan.baidu.com/s/1" + surl + (("?pwd=" + pwd) if pwd else "")
    origin = "https://pan.baidu.com"
    ajax = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": origin,
        "Referer": origin + "/",
    }
    # 匿名会话（照 omnibox觅盘.js）：不预置 COOKIE_BAIDU，
    # 只靠 verify+分享页种的完整罐；预置全量 Cookie 会让 streaming 回 errno=71
    s = requests.Session()
    s.headers.update({
        "User-Agent": SITE_UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    # 1) verify → BDCLND（正确提取码偶发 -12/-9，短延迟重试；randsk 兜底进罐）
    verify = {}
    for attempt in range(3):
        try:
            verify = _json_post(
                s,
                "https://pan.baidu.com/share/verify?surl=%s&channel=channellist&clienttype=0&app_id=250528"
                % quote(surl),
                data={"pwd": pwd, "vcode": "", "vcode_str": ""},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Referer": origin + "/",
                    "Origin": origin,
                },
            ) or {}
        except Exception:
            verify = {}
        errno = verify.get("errno")
        if str(errno) in ("0", ""):
            break
        if str(errno) in ("-12", "-9") and attempt < 2:
            time.sleep(0.8)
            continue
        break
    if verify.get("randsk") and not s.cookies.get("BDCLND"):
        try:
            s.cookies.set("BDCLND", str(verify.get("randsk")), domain="pan.baidu.com")
        except Exception:
            pass

    # 2) 分享页抽 share_uk / shareid（window.yunData 窗口，缺则 share_uk 锚点反转义）
    try:
        r = s.get(page_url, headers={"Referer": origin + "/"}, timeout=15, verify=False)
        raw = r.text or ""
    except Exception:
        return None
    seg = ""
    yi = raw.find("window.yunData=")
    if yi >= 0:
        seg = raw[yi:yi + 1200]
    else:
        ai = raw.find("share_uk")
        if ai >= 0:
            seg = raw[max(0, ai - 600):ai + 1200].replace('\\"', '"')
    mm = re.search(r'''["']?share_uk["']?\s*:\s*["']?(\d+)''', seg)
    uk = mm.group(1) if mm else ""
    mm = re.search(r'''["']?shareid["']?\s*:\s*["']?(\d+)''', seg)
    shareid = mm.group(1) if mm else ""
    if not uk or not shareid:
        # 分享页拿不到 yunData：绝大多数是链接已取消/不存在（页面标题「链接不存在」）
        if "链接不存在" in raw or "share_page_type" in raw:
            _LAST_RESOLVE_ERR = "百度分享链接已失效或已取消"
        elif str(verify.get("errno", "")) == "105":
            # 正确提取码也会回 105（IP 风控/要求验证码），别误导用户去查提取码
            _LAST_RESOLVE_ERR = "百度接口风控拦截（errno 105，要求验证码），请稍后重试"
        elif str(verify.get("errno", "")) in ("-9", "-12"):
            _LAST_RESOLVE_ERR = "百度分享提取码错误"
        elif str(verify.get("errno", "")) == "-62":
            _LAST_RESOLVE_ERR = "百度接口访问过于频繁，请稍后重试"
        else:
            _LAST_RESOLVE_ERR = "百度分享页面解析失败（链接可能已失效）"
        return None

    # 3) list 递归找第一个视频 fs_id（channel=channellist；sekey 仅在有 BDCLND 时带）
    sekey = unquote(s.cookies.get("BDCLND") or "")
    list_err = ""

    def _list(dir_path=""):
        nonlocal list_err
        params = {
            "shareid": shareid,
            "uk": uk,
            "app_id": "250528",
            "channel": "channellist",
            "clienttype": "0",
            "order": "time",
            "desc": "1",
            "showempty": "0",
            "view_mode": "1",
            "web": "1",
            "page": "1",
            "num": "100",
        }
        if sekey:
            params["is_from_web"] = "1"
            params["sekey"] = sekey
        if dir_path:
            params["dir"] = dir_path
        else:
            params["root"] = "1"
        data = _json_get(
            s,
            "https://pan.baidu.com/share/list",
            params=params,
            headers={"Referer": page_url, "Accept": "application/json, text/plain, */*"},
        )
        if not isinstance(data, dict) or str(data.get("errno", "0")) not in ("0", ""):
            list_err = str((data or {}).get("errno", ""))
            return []
        lst = data.get("list")
        return lst if isinstance(lst, list) else []

    def _child_path(it):
        raw_path = str((it or {}).get("path") or "")
        if re.match(r"^/sharelink\d*-\d+(/|$)", raw_path):
            return raw_path
        name = str((it or {}).get("server_filename") or "")
        fs_id = str((it or {}).get("fs_id") or "")
        if not name or not fs_id:
            return ""
        return "/sharelink%s-%s/%s" % (uk, fs_id, name)

    def _find_video(dir_path="", depth=0):
        if depth > 4:
            return None
        items = _list(dir_path)
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("isdir") or "0") in ("1", "true"):
                continue
            name = str(it.get("server_filename") or it.get("filename") or "")
            fid = str(it.get("fs_id") or "")
            if fid and _is_video_name(name):
                return {"fid": fid, "name": name}
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("isdir") or "0") not in ("1", "true"):
                continue
            child = _child_path(it)
            if not child:
                continue
            got = _find_video(child, depth + 1)
            if got:
                return got
        return None

    target = _find_video()
    if not target:
        if list_err == "-21":
            _LAST_RESOLVE_ERR = "百度分享链接已取消或不存在"
        elif list_err in ("105", "115", "-9", "-12"):
            if str(verify.get("errno", "")) == "105":
                _LAST_RESOLVE_ERR = "百度接口风控拦截（errno 105，要求验证码），请稍后重试"
            else:
                _LAST_RESOLVE_ERR = "百度分享需要正确提取码"
        elif list_err == "-62":
            _LAST_RESOLVE_ERR = "百度接口访问过于频繁，请稍后重试"
        elif list_err:
            _LAST_RESOLVE_ERR = "百度分享列表获取失败（errno %s）" % list_err
        else:
            _LAST_RESOLVE_ERR = "百度分享内没有可播放的视频文件"
        return None
    fs_id = str(fid or "") or target["fid"]

    # 4) tplconfig → sign / timestamp
    try:
        tpl = _json_get(
            s,
            "https://pan.baidu.com/share/tplconfig",
            params={
                "surl": "1" + surl,
                "shareid": shareid,
                "uk": uk,
                "fields": "sign,timestamp",
                "view_mode": "1",
            },
            headers=ajax,
        )
    except Exception:
        return None
    sign = str((tpl or {}).get("sign") or "")
    timestamp = str((tpl or {}).get("timestamp") or "")
    if not sign:
        inner = (tpl or {}).get("data")
        if isinstance(inner, dict):
            sign = str(inner.get("sign") or "")
            timestamp = str(inner.get("timestamp") or timestamp)
    if not sign:
        _LAST_RESOLVE_ERR = "获取百度签名失败（分享可能已失效）"
        return None

    # 5) streaming → m3u8/mp4（Cookie + Referer + Origin 必带）
    stream_url = (
        "https://pan.baidu.com/share/streaming?channel=chunlei"
        "&uk=%s&fid=%s&sign=%s&timestamp=%s&shareid=%s"
        "&type=M3U8_FLV_264_480&vip=0&check_blue=1&isplayer=1"
    ) % (quote(uk), quote(fs_id), quote(sign), quote(timestamp), quote(shareid))
    cookie = _cookie_header_for(s, stream_url)
    headers = {
        "User-Agent": SITE_UA,
        "Referer": page_url,
        "Origin": origin,
    }
    if cookie:
        headers["Cookie"] = cookie
    try:
        r = s.get(stream_url, headers=headers, timeout=20, verify=False, stream=True)
        ctype = (r.headers.get("Content-Type") or "").lower()
        head = b""
        try:
            head = next(r.iter_content(64)) or b""
        except Exception:
            pass
        try:
            r.close()
        except Exception:
            pass
        if r.status_code != 200:
            _LAST_RESOLVE_ERR = "获取百度视频流失败（分享可能已失效或接口限流）"
            return None
        text_head = head.decode("utf-8", "ignore") if head else ""
        looks_m3u8 = "mpegurl" in ctype or text_head.lstrip().startswith("#EXTM3U")
        looks_mp4 = (
            "video/" in ctype
            or "mp4" in ctype
            or b"ftyp" in head[:32]
            or head[:4] in (b"\x00\x00\x00\x18", b"\x00\x00\x00\x1c", b"\x00\x00\x00\x20")
        )
        if looks_m3u8 or looks_mp4:
            return stream_url, headers
        _LAST_RESOLVE_ERR = "获取百度视频流失败（分享可能已失效或接口限流）"
        return None
    except Exception:
        _LAST_RESOLVE_ERR = "获取百度视频流失败（网络异常或分享受限）"
        return None


def _115_snap_list(session, code, pwd, cid="0", depth=0):
    """递归列 115 分享目录，返回第一个视频 {name, fid}。"""
    if depth > 3:
        return None
    data = _json_get(
        session,
        "https://webapi.115.com/share/snap",
        params={
            "share_code": code,
            "offset": "0",
            "limit": "100",
            "asc": "0",
            "o": "",
            "cid": str(cid),
            "receive_code": pwd,
            "format": "json",
        },
        headers={"Referer": "https://115.com/"},
    )
    if not isinstance(data, dict) or str(data.get("errno", "0")) not in ("0", ""):
        return None
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    lst = payload.get("list") if isinstance(payload, dict) else None
    if not isinstance(lst, list):
        return None
    # 先找视频文件（字段 fid，fc=1）；iso 原盘仅兜底，混排分享点播优先普通视频
    iso_fallback = None
    for it in lst:
        if not isinstance(it, dict):
            continue
        fid = str(it.get("fid") or it.get("file_id") or "")
        name = str(it.get("n") or it.get("name") or it.get("server_filename") or "")
        if not fid or not _is_video_name(name):
            continue
        if _file_ext(name, it.get("ico") or "") == "iso":
            if iso_fallback is None:
                iso_fallback = {"name": name, "fid": fid}
            continue
        return {"name": name, "fid": fid}
    # 再进子目录（fc=0 且有 cid、无 fid）
    for it in lst:
        if not isinstance(it, dict):
            continue
        fid = str(it.get("fid") or "")
        sub_cid = str(it.get("cid") or "")
        if fid or not sub_cid:
            continue
        if str(it.get("fc") or "0") not in ("0", "", "None"):
            continue
        got = _115_snap_list(session, code, pwd, sub_cid, depth + 1)
        if got:
            return got
    return iso_fallback


def _115_collect_videos(session, code, pwd, out, cid="0", depth=0):
    """递归收集 115 分享内全部视频到 out（[{name,fid}]），深度/数量封顶。"""
    if depth > 3 or len(out) >= 50:
        return
    data = _json_get(
        session,
        "https://webapi.115.com/share/snap",
        params={
            "share_code": code,
            "offset": "0",
            "limit": "100",
            "asc": "0",
            "o": "",
            "cid": str(cid),
            "receive_code": pwd,
            "format": "json",
        },
        headers={"Referer": "https://115.com/"},
    )
    if not isinstance(data, dict) or str(data.get("errno", "0")) not in ("0", ""):
        return
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    lst = payload.get("list") if isinstance(payload, dict) else None
    if not isinstance(lst, list):
        return
    for it in lst:
        if not isinstance(it, dict):
            continue
        fid = str(it.get("fid") or it.get("file_id") or "")
        name = str(it.get("n") or it.get("name") or it.get("server_filename") or "")
        if fid and _is_video_name(name):
            if len(out) >= 50:
                return
            out.append({
                "name": name,
                "fid": fid,
                "size": it.get("s") or 0,
                "ext": str(it.get("ico") or ""),
                "sha": str(it.get("sha") or ""),
                "dir": str(cid),
            })
    for it in lst:
        if not isinstance(it, dict):
            continue
        fid = str(it.get("fid") or "")
        sub_cid = str(it.get("cid") or "")
        if fid or not sub_cid:
            continue
        if str(it.get("fc") or "0") not in ("0", "", "None"):
            continue
        _115_collect_videos(session, code, pwd, out, sub_cid, depth + 1)
        if len(out) >= 50:
            return


def _115_list_videos(share_url=""):
    """列 115 分享内全部视频文件 [{name, fid}]，失败 []。"""
    if requests is None:
        return []
    u = normalize_share_url(share_url)
    m = re.search(r"115\.com/s/([A-Za-z0-9]+)", u or "")
    if not m:
        return []
    code = m.group(1)
    mp = re.search(r"[?&]password=([0-9A-Za-z]+)", u or "")
    pwd = mp.group(1) if mp else ""
    s = _new_pan_session("115")
    out = []
    _115_collect_videos(s, code, pwd, out)
    return out


def _115_probe_stream(session, url, referer="https://115.com/"):
    """探活直链，成功 (url, header)。"""
    h = {"User-Agent": SITE_UA, "Referer": referer or "https://115.com/"}
    cookie = _cookie_header_for(session, url)
    if cookie:
        h["Cookie"] = cookie
    try:
        r = session.get(url, headers=h, timeout=15, verify=False, stream=True)
        status = r.status_code
        head = b""
        try:
            head = next(r.iter_content(32)) or b""
        except Exception:
            pass
        try:
            r.close()
        except Exception:
            pass
        if status in (200, 206):
            return url, h
        # m3u8 文本即便非 200 探活失败也可能可播
        if head.startswith(b"#EXTM3U"):
            return url, h
        return None
    except Exception:
        # 连接都没建立（超时/拒连）→ 直链大概率对播放器同样不可用，别当成功交出去
        return None


def resolve_115_share(share_url="", fid=""):
    """115 分享 → 真视频流。成功 (url, header_dict)，失败 None。

    fid 可选：选集 share|fid 指定文件时跳过 snap 列目录。
    不依赖个人盘：
      snap(+receive_code) 列文件拿 fid
      → 优先 proapi share/downurl（RSA 加密，登录 Cookie）
      → 个人盘 search 有 pc 时再试 m3u8 / files/video
    """
    if requests is None:
        return None
    u = normalize_share_url(share_url)
    m = re.search(r"115\.com/s/([A-Za-z0-9]+)", u or "")
    if not m:
        return None
    code = m.group(1)
    mp = re.search(r"[?&]password=([0-9A-Za-z]+)", u or "")
    pwd = mp.group(1) if mp else ""

    s = _new_pan_session("115")
    fname = ""
    fid = str(fid or "").strip()
    if not fid:
        target = _115_snap_list(s, code, pwd)
        if not target:
            return None
        fname = target["name"]
        fid = target["fid"]

    # 分享直链（不需个人盘副本）
    direct = _115_share_downurl(s, code, pwd, fid)
    if direct:
        got = _115_probe_stream(s, direct, referer="https://115.com/s/%s" % code)
        if got:
            return got

    # 个人盘按文件名搜 pickcode（用户已转存/接收时可用，m3u8 更稳）；无 fname 则跳过
    pc = ""
    if fname:
        data = _json_get(
            s,
            "https://webapi.115.com/files/search",
            params={"search_value": fname, "offset": "0", "limit": "115", "aid": "1", "cid": "0", "format": "json"},
            headers={"Referer": "https://115.com/"},
        )
        if isinstance(data, dict):
            raw_list = data.get("data")
            if isinstance(raw_list, list):
                lst = raw_list
            elif isinstance(raw_list, dict):
                lst = raw_list.get("list")
                if isinstance(lst, dict):
                    lst = lst.get("list")
            else:
                lst = data.get("list")
                if isinstance(lst, dict):
                    lst = lst.get("list")
            if isinstance(lst, list):
                for it in lst:
                    if not isinstance(it, dict):
                        continue
                    n = str(it.get("n") or it.get("name") or it.get("server_filename") or "")
                    p = str(it.get("pc") or it.get("pickcode") or "")
                    if p and (n == fname or _is_video_name(n) or not n):
                        pc = p
                        break
    if not pc:
        return None

    # 优先 m3u8
    m3u8_url = "https://115.com/api/video/m3u8/%s.m3u8" % pc
    cookie = _cookie_header_for(s, m3u8_url)
    h = {"User-Agent": SITE_UA, "Referer": "https://115.com/"}
    if cookie:
        h["Cookie"] = cookie
    try:
        r = s.get(m3u8_url, headers=h, timeout=15, verify=False)
        body_head = (r.text or "")[:200]
        if r.status_code == 200 and "#EXTM3U" in body_head:
            return m3u8_url, h
    except Exception:
        pass

    # 回退 files/video → origin_file_url
    data = _json_get(
        s,
        "https://webapi.115.com/files/video",
        params={"pickcode": pc, "format": "json"},
        headers={"Referer": "https://115.com/"},
    )
    origin = ""
    if isinstance(data, dict):
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        if isinstance(payload, dict):
            origin = str(payload.get("origin_file_url") or payload.get("url") or "")
    if not origin:
        return None
    got = _115_probe_stream(s, origin)
    if got:
        return got
    return None


def resolve_share_media(share_url="", drive_type="", fid=""):
    """按网盘类型解析成真视频流。成功 (url, header)，失败 None。fid 可选指定文件。"""
    try:
        dt = normalize_drive_type(drive_type or infer_drive_type_from_share_url(share_url))
        if dt == "baidu":
            return resolve_baidu_share(share_url, fid=fid)
        if dt == "115":
            return resolve_115_share(share_url, fid=fid)
    except Exception:
        return None
    return None


# ==================== Spider ====================
class Spider(BaseSpider):
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

    def getName(self):
        return "蜗牛4K"

    def _empty(self, page=1, msg=""):
        out = {
            "list": [],
            "page": int(page) if str(page).isdigit() else 1,
            "pagecount": 0,
            "limit": PAGE_SIZE,
            "total": 0,
        }
        if msg:
            out["msg"] = msg
        return out

    def _page_list(self, videos, page=1, pagecount=1, total=None, wrap=True):
        items = [wrap_movie_as_group_item(v) for v in (videos or [])] if wrap else list(videos or [])
        return {
            "list": items,
            "page": int(page) if str(page).isdigit() else 1,
            "pagecount": max(1, int(pagecount) if str(pagecount).isdigit() else 1),
            "limit": PAGE_SIZE,
            "total": len(items) if total is None else int(total),
        }

    # ---------- 首页 ----------
    def homeContent(self, filter):
        classes = list(STATIC_CLASSES)
        try:
            body, base = _http.get("/", timeout=20)
            nav = parse_nav_classes(body)
            if nav:
                classes = nav
        except Exception:
            pass
        result = {"class": classes}
        if filter:
            filters = {}
            try:
                body, _ = _http.get("/", timeout=15)
                # 首页通常无筛选；分类页在 category 时再解析
            except Exception:
                body = ""
            if body:
                groups = parse_filters_from_html(body)
                if groups:
                    for c in classes:
                        filters[c["type_id"]] = groups
            result["filters"] = filters
        return result

    def homeVideoContent(self):
        try:
            body, base = _http.get("/", timeout=20)
            videos = parse_list_from_html(body, base)
            return self._page_list(videos, 1, 1)
        except Exception as e:
            return self._empty(1, "首页推荐加载失败：" + str(e))

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        cat_id = str(tid or "")
        try:
            ext = {}
            if isinstance(extend, dict):
                ext = extend
            elif extend:
                try:
                    ext = json.loads(extend)
                except Exception:
                    ext = {}

            # 分组跳转
            typ, data = decode_id(cat_id)
            if typ == "m":
                return _movie_drive_groups_by_vid(data.get("v") or "")
            if typ == "g":
                return _movie_links_by_drive(data.get("v") or "", data.get("t") or "")
            if typ == "k":
                return _search_videos_by_drive(data.get("k") or "", page, data.get("t") or "")
            if typ == "r":
                return _share_url_detail(data.get("u") or "", data.get("n") or "",
                                         None, data.get("v") or "")
            # 旧格式兼容
            if cat_id.startswith("mvg:"):
                return _movie_drive_groups_by_vid(cat_id[4:])
            if cat_id.startswith("mv:"):
                rest = cat_id[3:].split(":", 1)
                if len(rest) == 2:
                    return _movie_links_by_drive(rest[1], rest[0])
            if "|" in cat_id and not cat_id.startswith("mp|"):
                parts = cat_id.split("|", 1)
                if len(parts) == 2 and parts[0]:
                    return _search_videos_by_drive(parts[1], page, parts[0])

            # 首页分类（type_id=0）：与网页导航对齐，返回首页推荐
            if cat_id in ("0", "", "home", "index"):
                body, base = _http.get("/", timeout=20)
                videos = parse_list_from_html(body, base)
                for v in videos:
                    v["type_id"] = "0"
                return self._page_list(videos, page, 1, len(videos))

            # 筛选路径
            has_filter = any(
                ext.get(k) or ext.get(k + "#")
                for k in ("area", "class", "lang", "letter", "year", "sort", "by", "tid", "id")
            )
            if has_filter:
                url = "/index.php/vod/show"
                if ext.get("area"):
                    url += "/area/%s" % quote(str(ext["area"]))
                sort_value = ext.get("sort") or ext.get("by")
                if sort_value:
                    url += "/by/%s" % quote(str(sort_value))
                if ext.get("class"):
                    url += "/class/%s" % quote(str(ext["class"]))
                if ext.get("lang"):
                    url += "/lang/%s" % quote(str(ext["lang"]))
                if ext.get("letter"):
                    url += "/letter/%s" % quote(str(ext["letter"]))
                if ext.get("year"):
                    url += "/year/%s" % quote(str(ext["year"]))
                tid_value = ext.get("tid") or ext.get("id") or cat_id
                url += "/id/%s" % quote(str(tid_value))
                if page > 1:
                    url += "/page/%d" % page
                url += ".html"
            else:
                url = build_category_path(cat_id, page)

            body, base = _http.get(url, timeout=20)
            videos = parse_list_from_html(body, base)
            for v in videos:
                v["type_id"] = cat_id
            pagecount = parse_page_count(body, page)
            result = self._page_list(videos, page, pagecount, len(videos))
            if page == 1:
                groups = parse_filters_from_html(body)
                if groups:
                    result["filters"] = {cat_id: groups}
            return result
        except Exception as e:
            return self._empty(page, "分类加载失败：" + str(e))

    # ---------- 搜索 ----------
    @staticmethod
    def _is_rate_limited(body):
        if not body:
            return False
        return ("跳转提示" in body) or ("频繁操作" in body) or ("搜索时间间隔" in body)

    def _search_fetch(self, keyword, page, retries=3):
        """带限流退避的搜索抓取（站点要求搜索间隔 >=3 秒）。"""
        path = build_search_path(keyword, page)
        last = None
        for attempt in range(retries):
            body, base = _http.get(path, timeout=20)
            if not self._is_rate_limited(body):
                return body, base
            last = (body, base)
            if attempt < retries - 1:
                time.sleep(3.2)
        return last

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        keyword = str(key or "").strip()
        try:
            if not keyword:
                return self._empty(page, "搜索关键词为空")
            # 直接推送分享链接（无站点标题，名称用网盘名，简介=真实链接）
            if re.match(r"^https?://", keyword, re.I) and is_pan_share_url(keyword):
                return _share_url_detail(keyword, "")

            body, base = self._search_fetch(keyword, page)
            if self._is_rate_limited(body):
                return self._empty(page, "搜索过于频繁，请稍后再试")
            videos = parse_list_from_html(body, base)
            pagecount = parse_page_count(body, page)
            # 统一包成影片文件夹，点击后进入网盘分组
            return self._page_list(videos, page, pagecount, len(videos))
        except Exception as e:
            return self._empty(page, "搜索失败：" + str(e))

    # ---------- 详情 ----------
    def detailContent(self, ids):
        raw = ""
        if isinstance(ids, (list, tuple)):
            raw = str(ids[0] if ids else "")
        else:
            raw = str(ids or "")
        try:
            typ, data = decode_id(raw)
            if typ == "m":
                return _movie_drive_groups_by_vid(data.get("v") or "")
            if typ == "g":
                return _movie_links_by_drive(data.get("v") or "", data.get("t") or "")
            if typ == "k":
                return _search_videos_by_drive(data.get("k") or "", 1, data.get("t") or "")
            if typ == "r":
                return _share_url_detail(data.get("u") or "", data.get("n") or "",
                                         None, data.get("v") or "")

            # 旧格式
            if raw.startswith("mvg:"):
                return _movie_drive_groups_by_vid(raw[4:])
            if raw.startswith("mv:"):
                rest = raw[3:].split(":", 1)
                if len(rest) == 2:
                    return _movie_links_by_drive(rest[1], rest[0])
            if "|" in raw and not raw.startswith("mp|"):
                # 分享链接|剧名  或  网盘类型|关键词
                if is_pan_share_url(raw.split("|", 1)[0]):
                    parts = raw.split("|", 1)
                    return _share_url_detail(parts[0], parts[1] if len(parts) > 1 else "")
                parts = raw.split("|", 1)
                if len(parts) == 2 and parts[0] and not parts[0].startswith("/"):
                    # 可能是 driveType|keyword
                    if infer_drive_type_from_share_url(parts[0]) or normalize_drive_type(parts[0]) != "others":
                        return _search_videos_by_drive(parts[1], 1, parts[0])

            # 直接分享链接推送
            if re.match(r"^https?://", raw, re.I) and is_pan_share_url(raw):
                return _share_url_detail(raw, "")

            vid = normalize_video_id(raw)
            if not vid:
                return {"list": [], "page": 1, "pagecount": 0, "limit": PAGE_SIZE, "total": 0}
            return _movie_drive_groups_by_vid(vid)
        except Exception as e:
            return {"list": [], "page": 1, "pagecount": 0, "limit": PAGE_SIZE, "total": 0,
                    "msg": "详情加载失败：" + str(e)}

    # ---------- 播放 ----------
    def playerContent(self, flag, ids, vipFlags=None):
        if isinstance(ids, (list, tuple)):
            raw_id = str(ids[0]) if ids else ""
        else:
            raw_id = str(ids or "")
        play_id = raw_id.strip()
        if not play_id:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "播放地址为空"}

        share_url = play_id
        file_id = ""
        # 支持 shareURL|fileId 选集播放 id
        if "|" in play_id and not play_id.startswith("mp|"):
            parts = play_id.split("|", 1)
            share_url = parts[0]
            if len(parts) > 1 and parts[1].strip():
                file_id = parts[1].strip()
        # encodeId r（整条分享）/ e（指定集）
        typ, data = decode_id(play_id)
        if typ == "r" and data.get("u"):
            share_url = normalize_share_url(data.get("u"))
            if data.get("f"):
                file_id = str(data.get("f"))
        elif typ == "e" and data.get("u"):
            share_url = normalize_share_url(data.get("u"))
            file_id = str(data.get("f") or "")
        share_url = normalize_share_url(share_url)
        if not share_url and re.match(r"^https?://", play_id, re.I):
            share_url = play_id
        if not share_url:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "播放地址解析失败：无效链接"}

        # 按分享链接类型注入对应网盘 Cookie（115 / 百度 等，见配置区 PAN_COOKIES）
        drive_type = ""
        if typ == "r" and data.get("t"):
            drive_type = data.get("t") or ""
        if not drive_type:
            drive_type = infer_drive_type_from_share_url(share_url)
        header = {
            "User-Agent": SITE_UA,
            "Referer": pan_referer(share_url),
        }
        ck = pan_cookie(drive_type)
        if ck:
            header["Cookie"] = ck

        # 解析成真视频流（m3u8/mp4）；失败绝不回退分享页 HTML
        resolved = resolve_share_media(share_url, drive_type, fid=file_id)
        if resolved and resolved[0]:
            stream_url, stream_header = resolved
            # 蓝光原盘直链拿得到，但主流播放器（ExoPlayer/ijk）解不了 ISO：
            # 与其黑屏报 codec 错，不如直说（列表层另有「原盘ISO」备注）
            if re.search(r"\.iso(?:\?|$)", str(stream_url or ""), re.I):
                return {
                    "parse": 0,
                    "jx": 0,
                    "playUrl": "",
                    "url": "",
                    "header": {},
                    "flag": flag or "",
                    "msg": "原盘 ISO 文件不支持在线播放（需支持蓝光原盘的播放器）",
                }
            return {
                "parse": 0,
                "jx": 0,
                "playUrl": "",
                "url": stream_url,
                "header": stream_header or header,
                "flag": flag or "",
            }

        msg = "网盘分享无法解析为视频直链（需有效 Cookie 或分享可直链）"
        if drive_type == "baidu" and _LAST_RESOLVE_ERR:
            msg = _LAST_RESOLVE_ERR
        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": "",
            "header": {},
            "flag": flag or "",
            "msg": msg,
        }

    # ---------- CatVod 挂载契约（对齐 hsck） ----------
    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        u = str(url or "").lower().split("?")[0].split("#")[0]
        return u.endswith((".mp4", ".m3u8", ".flv", ".mkv", ".ts", ".avi", ".m4v", ".webm"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def localProxy(self, param):
        return [404, "text/plain", b"Not Found", {}]

    def destroy(self):
        pass
