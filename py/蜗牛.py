# -*- coding: utf-8 -*-
"""蜗牛 - wn4k.com 通用 CatVod Python 蜘蛛

业务参照: omn蜗牛.js (MacCMS panlian_dark/mxone, 网盘资源分组)
分组参照: omnibox觅盘.js (encodeId: mp|type|base64url(JSON))

分组 ID:
  mp|m|...  影片 -> 网盘分组卡
  mp|g|...  影片+网盘类型 -> 分享链接列表
  mp|r|...  分享链接资源详情
  mp|k|...  搜索关键词+网盘类型 -> 链接列表
  纯数字    站点影片 ID

播放: 115/百度 分享会先解析成 m3u8/mp4 直链再交给播放器（115 需有效 Cookie），
      解析失败才回退分享页，避免播放器把网页当视频报 container unsupported。
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


# 源配置 extend 里可覆盖的 Cookie 键（OK影视/TVBox 挂载时填写）
COOKIE_EXTEND_KEYS = {
    "115": ("cookie115", "cookie_115", "pan115", "115cookie", "115_cookie", "115"),
    "baidu": ("cookiebaidu", "cookie_baidu", "panbaidu", "baiducookie", "baidu_cookie", "baidu"),
}


def apply_extend_options(ext):
    """从 init(extend) 读取网盘 Cookie，覆盖内置/环境变量配置。"""
    if not isinstance(ext, dict):
        return
    for drive, keys in COOKIE_EXTEND_KEYS.items():
        for k in keys:
            v = ext.get(k)
            if isinstance(v, str) and v.strip():
                PAN_COOKIES[drive] = v.strip()
                break


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
        "vod_play_url": "播放$%s" % share_url,
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
    # 「剧名 - 01 [1080P]」这类：1~3 位数字，避免把年份/1080P 当集数
    m = re.search(r"(?:^|[\s._-])(\d{1,3})(?=[\s._\[]|$)", s)
    if m:
        return 1, int(m.group(1))
    return 0, 0


def _episode_label(name, index):
    season, ep = _episode_meta(name)
    if ep:
        if season > 1:
            return "第%d季第%d集" % (season, ep)
        return "第%d集" % ep
    stem = re.sub(r"\.[^.]+$", "", str(name or "")).strip()
    return stem[:20] if stem else ("第%d集" % (index + 1))


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
    """列出分享内全部视频（带 12 小时缓存）。"""
    key = "eps:%s" % share_url
    hit = _cache_get(key)
    if hit is not None:
        return hit
    videos = []
    try:
        if drive_type == "115":
            code, pwd = _115_share_parts(share_url)
            if code:
                videos = _115_snap_videos(_new_pan_session("115"), code, pwd)
        elif drive_type == "baidu":
            ctx = _baidu_context(share_url)
            if ctx:
                videos = _baidu_list_videos(ctx)
    except Exception:
        videos = []
    videos = _pick_main_group(videos)
    _cache_set(key, videos)
    return videos


def _build_episode_play_url(share_url, videos):
    """分享 → CatVod 选集串：第N集$encode_id#..."""
    ordered = _order_episodes(videos)
    if not ordered:
        return "播放$%s" % share_url
    if len(ordered) == 1:
        return "播放$%s" % share_url
    parts = []
    for idx, v in enumerate(ordered):
        label = _episode_label(v.get("name") or "", idx)
        eid = encode_id("e", {
            "u": share_url,
            "f": str(v.get("fid") or ""),
            "n": str(v.get("name") or ""),
            "h": str(v.get("sha") or ""),
        })
        parts.append("%s$%s" % (label, eid))
    return "#".join(parts)


def _attach_episodes(item, share_url, drive_type):
    """把分享内的多集展开到列表项，播放器可直接选集。"""
    if not item or drive_type not in ("115", "baidu"):
        return item
    videos = _list_share_videos(share_url, drive_type)
    if len(videos) > 1:
        item["vod_play_from"] = pan_name(drive_type)
        item["vod_play_url"] = _build_episode_play_url(share_url, videos)
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
    # 多集分享展开选集（115/百度），单集保持原样
    _attach_episodes(vod, u, dt)
    return {
        "list": [vod],
        "page": 1,
        "pagecount": 1,
        "limit": PAGE_SIZE,
        "total": 1,
    }


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
# 下列 resolve_* 把分享链接解析成真视频流（m3u8/mp4），失败返回 None 回退分享页。

_VIDEO_EXT_RE = re.compile(
    r"\.(mp4|mkv|flv|ts|m3u8|avi|wmv|mov|rmvb|mpg|mpeg|m4v|webm)(?:\?|$)",
    re.I,
)


def _is_video_name(name=""):
    return bool(_VIDEO_EXT_RE.search(str(name or "").strip()))


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


def _cookie_get(session, name):
    """安全取单个 Cookie（同名多域时返回第一个）。"""
    try:
        for c in session.cookies:
            if c.name == name:
                return c.value
    except Exception:
        pass
    return ""


def _baidu_context(share_url=""):
    """百度分享 → 会话上下文（分享页 + verify）。失败 None。

    配方（真网已验证）：
      分享页抽 share_uk/shareid → 旧版 verify(shareid+uk) 拿 randsk（不触发图形验证码）
    新版 verify(surl) 会被要求图形验证码；旧版 shareid+uk 接口仍可用。
    """
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

    # 匿名会话：只需 verify 种下的 BDCLND，预置全量 Cookie 会触发 errno=71
    s = requests.Session()
    s.headers.update({
        "User-Agent": SITE_UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    # 1) 分享页抽 share_uk / shareid
    try:
        raw = s.get(page_url, headers={"Referer": origin + "/"}, timeout=15, verify=False).text or ""
    except Exception:
        return None
    mm = re.search(r'''["']?share_uk["']?\s*:\s*["']?(\d+)''', raw)
    uk = mm.group(1) if mm else ""
    mm = re.search(r'''["']?shareid["']?\s*:\s*["']?(\d+)''', raw)
    shareid = mm.group(1) if mm else ""
    if not uk or not shareid:
        return None

    # 2) 旧版 verify（shareid+uk，不触发验证码）→ randsk/BDCLND
    randsk = ""
    if pwd:
        verify = {}
        try:
            verify = _json_post(
                s,
                "https://pan.baidu.com/share/verify?shareid=%s&uk=%s&app_id=250528"
                % (quote(shareid), quote(uk)),
                data={"pwd": pwd},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Referer": page_url,
                    "Origin": origin,
                    "X-Requested-With": "XMLHttpRequest",
                },
            ) or {}
            randsk = str(verify.get("randsk") or "")
        except Exception:
            randsk = ""
        if randsk and not _cookie_get(s, "BDCLND"):
            try:
                s.cookies.set("BDCLND", randsk, domain="pan.baidu.com")
            except Exception:
                pass
        if str(verify.get("errno") or "0") not in ("0", ""):
            return None

    return {
        "s": s,
        "surl": surl,
        "page_url": page_url,
        "origin": origin,
        "uk": uk,
        "shareid": shareid,
        "randsk": randsk,
        "sekey": unquote(randsk or _cookie_get(s, "BDCLND") or ""),
        "ajax": {
            "X-Requested-With": "XMLHttpRequest",
            "Origin": origin,
            "Referer": page_url,
            "Accept": "application/json, text/plain, */*",
        },
    }


def _baidu_list_videos(ctx):
    """递归列出百度分享中的全部视频，返回 [{name, fid}]。"""
    videos = []
    s = ctx["s"]
    ajax = ctx["ajax"]
    sekey = ctx["sekey"]

    def walk(dir_path="", depth=0):
        if depth > 4 or len(videos) >= 500:
            return
        params = {
            "shareid": ctx["shareid"],
            "uk": ctx["uk"],
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
        data = _json_get(s, "https://pan.baidu.com/share/list", params=params, headers=ajax)
        if not isinstance(data, dict) or str(data.get("errno", "0")) not in ("0", ""):
            return
        items = data.get("list") if isinstance(data.get("list"), list) else []
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("isdir") or "0") in ("1", "true"):
                continue
            name = str(it.get("server_filename") or it.get("filename") or "")
            fid = str(it.get("fs_id") or "")
            if fid and _is_video_name(name):
                videos.append({"name": name, "fid": fid, "dir": dir_path})
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("isdir") or "0") not in ("1", "true"):
                continue
            child = str(it.get("path") or "")
            if child:
                walk(child, depth + 1)

    walk()
    return videos


def _baidu_stream(ctx, fs_id):
    """百度分享文件 → m3u8 流。成功 (url, header)，失败 None。"""
    s = ctx["s"]
    ajax = ctx["ajax"]
    try:
        tpl = _json_get(
            s,
            "https://pan.baidu.com/share/tplconfig",
            params={
                "surl": "1" + ctx["surl"],
                "shareid": ctx["shareid"],
                "uk": ctx["uk"],
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
        return None

    # streaming → m3u8（非会员一般只有 480P 转码；分片直链本身带签名）
    headers = {
        "User-Agent": SITE_UA,
        "Referer": ctx["page_url"],
        "Origin": ctx["origin"],
    }
    bdclnd = _cookie_get(s, "BDCLND") or ctx["randsk"]
    if bdclnd:
        headers["Cookie"] = "BDCLND=" + bdclnd
    for typ in ("M3U8_FLV_264_480", "M3U8_AUTO_480", "M3U8_MP4_264_480"):
        stream_url = (
            "https://pan.baidu.com/share/streaming?channel=chunlei"
            "&uk=%s&fid=%s&sign=%s&timestamp=%s&shareid=%s"
            "&type=%s&vip=0&check_blue=1&isplayer=1"
        ) % (quote(ctx["uk"]), quote(str(fs_id)), quote(sign), quote(timestamp),
             quote(ctx["shareid"]), typ)
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
                continue
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
        except Exception:
            continue
    return None


def resolve_baidu_file(share_url="", file_id=""):
    """百度分享中的指定文件 → 真视频流（选集播放用）。"""
    ctx = _baidu_context(share_url)
    if not ctx or not file_id:
        return None
    return _baidu_stream(ctx, file_id)


def resolve_baidu_share(share_url=""):
    """百度分享 → 真视频流（默认取分享内第一个视频）。"""
    ctx = _baidu_context(share_url)
    if not ctx:
        return None
    videos = _baidu_list_videos(ctx)
    if not videos:
        return None
    return _baidu_stream(ctx, videos[0]["fid"])


def _115_share_parts(share_url=""):
    """分享链接 → (share_code, password)。"""
    u = normalize_share_url(share_url)
    m = re.search(r"115\.com/s/([A-Za-z0-9]+)", u or "")
    if not m:
        return "", ""
    mp = re.search(r"[?&]password=([0-9A-Za-z]+)", u or "")
    return m.group(1), (mp.group(1) if mp else "")


def _115_snap_videos(session, code, pwd, cid="0", depth=0, out=None):
    """递归列出 115 分享中的全部视频（含 fid/sha/size），返回列表。"""
    if out is None:
        out = []
    if depth > 3 or len(out) >= 500:
        return out
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
        return out
    payload = data.get("data") if isinstance(data.get("data"), dict) else {}
    if not isinstance(payload, dict):
        return out
    lst = payload.get("list")
    if not isinstance(lst, list):
        return out
    for it in lst:
        if not isinstance(it, dict):
            continue
        fid = str(it.get("fid") or it.get("file_id") or "")
        name = str(it.get("n") or it.get("name") or it.get("server_filename") or "")
        if fid and _is_video_name(name):
            out.append({
                "name": name,
                "fid": fid,
                "sha": str(it.get("sha") or ""),
                "cid": str(it.get("cid") or ""),
                "dir": str(cid),
                "size": it.get("s") or 0,
            })
    # 再进子目录（fc=0 且有 cid、无 fid）
    for it in lst:
        if not isinstance(it, dict):
            continue
        if str(it.get("fid") or ""):
            continue
        sub_cid = str(it.get("cid") or "")
        if not sub_cid:
            continue
        if str(it.get("fc") or "0") not in ("0", "", "None"):
            continue
        _115_snap_videos(session, code, pwd, sub_cid, depth + 1, out)
    return out


def _probe_stream(session, url, headers=None, timeout=15):
    """探测 url 是否返回可播放流（排除 HTML/JSON 页面）。"""
    if not url:
        return False
    try:
        r = session.get(url, headers=headers or {}, timeout=timeout, verify=False, stream=True)
        status = r.status_code
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
        if status not in (200, 206):
            return False
        if "html" in ctype or "json" in ctype:
            return False
        if "mpegurl" in ctype or head.lstrip().lower().startswith(b"#extm3u"):
            return True
        if "video/" in ctype or "octet-stream" in ctype:
            return True
        if head[:4] == b"\x1a\x45\xdf\xa3":  # mkv
            return True
        if len(head) >= 12 and head[4:8] == b"ftyp":  # mp4/mov
            return True
        if head[:1] in (b"\x47", b"\x00"):  # ts / 裸流
            return True
        return False
    except Exception:
        return False


def _115_name_key(name):
    """同名文件去重键：去掉「(1)」这类重复后缀。"""
    s = str(name or "").strip()
    return re.sub(r"\(\d+\)(?=\.[^.]*$)", "", s)


def _115_find_pickcode(session, fname, sha=""):
    """个人盘按文件名/哈希搜 pickcode（已转存/接收时可用）。"""
    if not fname and not sha:
        return ""
    data = _json_get(
        session,
        "https://webapi.115.com/files/search",
        params={"search_value": fname, "offset": "0", "limit": "115", "aid": "1", "cid": "0", "format": "json"},
        headers={"Referer": "https://115.com/"},
    )
    if not isinstance(data, dict):
        return ""
    # files/search：data 可能是列表（顶层 data:[...]），也可能是 {list:[...]}
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
    if not isinstance(lst, list):
        return ""
    want = _115_name_key(fname)
    fuzzy = ""
    for it in lst:
        if not isinstance(it, dict):
            continue
        n = str(it.get("n") or it.get("name") or it.get("server_filename") or "")
        p = str(it.get("pc") or it.get("pickcode") or "")
        if not p:
            continue
        if sha and str(it.get("sha") or "").upper() == sha.upper():
            return p
        if n == fname:
            return p
        if not fuzzy and _115_name_key(n) == want:
            fuzzy = p
    return fuzzy


def _115_play_by_pickcode(session, pc):
    """个人盘文件 → 官方 m3u8 转码流。"""
    if not pc:
        return None
    url = "https://115.com/api/video/m3u8/%s.m3u8" % pc
    h = {"User-Agent": SITE_UA, "Referer": "https://115.com/"}
    cookie = _cookie_header_for(session, url)
    if cookie:
        h["Cookie"] = cookie
    try:
        r = session.get(url, headers=h, timeout=15, verify=False)
        if r.status_code == 200 and "#EXTM3U" in (r.text or "")[:200]:
            return url, h
    except Exception:
        pass
    return None


def _115_receive(session, code, pwd, fid=""):
    """把分享文件转存到个人盘；已转存过也视为成功（不重复转存）。"""
    try:
        form = {"share_code": code, "receive_code": pwd}
        if fid:
            form["file_id"] = fid
        r = session.post(
            "https://webapi.115.com/share/receive",
            data=form,
            headers={
                "User-Agent": SITE_UA,
                "Referer": "https://115.com/s/%s" % code,
                "Origin": "https://115.com",
            },
            timeout=15,
            verify=False,
        )
        data = r.json() if r.text else {}
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    # 4200045 文件已接收 / 4100024 已经转存过该文件
    if str(data.get("errno") or "") in ("4200045", "4100024"):
        return True
    return bool(data.get("state"))


def _115_skip_login_url(session, code, pwd, fid):
    """分享者开启「免登录下载」时可直接取直链。"""
    try:
        r = session.post(
            "https://webapi.115.com/share/skip_login_downurl",
            data={"share_code": code, "receive_code": pwd, "file_id": fid},
            headers={
                "User-Agent": SITE_UA,
                "Referer": "https://115.com/s/%s" % code,
                "Origin": "https://115.com",
            },
            timeout=15,
            verify=False,
        )
        data = r.json() if r.text else {}
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("state"):
        return None
    payload = data.get("data") if isinstance(data.get("data"), dict) else {}
    url = ""
    for key in ("url", "file_url", "downurl"):
        val = payload.get(key)
        if isinstance(val, dict):
            url = str(val.get("url") or "")
        elif isinstance(val, str):
            url = val
        if url:
            break
    if not url:
        return None
    h = {"User-Agent": SITE_UA, "Referer": "https://115.com/"}
    if _probe_stream(session, url, h):
        return url, h
    return None


def resolve_115_file(share_url="", file_id="", name="", sha=""):
    """115 分享中的指定文件 → 真视频流（选集播放用）。"""
    if requests is None:
        return None
    code, pwd = _115_share_parts(share_url)
    if not code or not file_id:
        return None
    s = _new_pan_session("115")
    cookie = pan_cookie("115")
    if cookie:
        # 1) 个人盘已有该文件（按 sha/文件名匹配）
        got = _115_play_by_pickcode(s, _115_find_pickcode(s, name, sha))
        if got:
            return got
        # 2) 转存该集后再取 m3u8
        if _115_receive(s, code, pwd, file_id):
            for _attempt in range(4):
                time.sleep(1.2)
                got = _115_play_by_pickcode(s, _115_find_pickcode(s, name, sha))
                if got:
                    return got
    # 3) 免登录下载直链
    return _115_skip_login_url(s, code, pwd, file_id)


def resolve_115_share(share_url=""):
    """115 分享 → 真视频流。成功 (url, header_dict)，失败 None。

    顺序：
      1) 个人盘已有同名文件 → 官方 m3u8（最稳定，无副作用）
      2) 转存到个人盘 → 轮询 pickcode → 官方 m3u8
      3) /share/skip_login_downurl（分享者开启免登录下载）
    无有效 115 Cookie 时只有第 3 步可能成功。
    """
    if requests is None:
        return None
    code, pwd = _115_share_parts(share_url)
    if not code:
        return None
    videos = _115_snap_videos(_new_pan_session("115"), code, pwd)
    if not videos:
        return None
    first = videos[0]
    return resolve_115_file(share_url, first["fid"], first.get("name") or "", first.get("sha") or "")


def resolve_share_media_file(share_url="", drive_type="", file_id="", name="", sha=""):
    """选集：按网盘类型解析分享中的指定文件。失败回退整条分享解析。"""
    try:
        dt = normalize_drive_type(drive_type or infer_drive_type_from_share_url(share_url))
        if dt == "115" and file_id:
            got = resolve_115_file(share_url, file_id, name, sha)
            if got:
                return got
        if dt == "baidu" and file_id:
            got = resolve_baidu_file(share_url, file_id)
            if got:
                return got
    except Exception:
        pass
    return resolve_share_media(share_url, drive_type)


def resolve_share_media(share_url="", drive_type=""):
    """按网盘类型解析成真视频流。成功 (url, header)，失败 None。"""
    try:
        dt = normalize_drive_type(drive_type or infer_drive_type_from_share_url(share_url))
        if dt == "baidu":
            return resolve_baidu_share(share_url)
        if dt == "115":
            return resolve_115_share(share_url)
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
        if not isinstance(self.options, dict):
            self.options = {}
        # 允许在源配置里直接填网盘 Cookie（如 {"cookie115": "..."}）
        apply_extend_options(self.options)

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

            body, base = _get_detail_cached(vid)
            info = parse_vod_base_info(body, base)
            pan_urls = extract_pan_urls(body)
            groups = build_movie_drive_groups(vid, info["vodName"], info["vodPic"], pan_urls, info)
            if groups:
                return {
                    "list": groups,
                    "page": 1,
                    "pagecount": 1,
                    "limit": PAGE_SIZE,
                    "total": len(groups),
                }
            return {"list": [], "page": 1, "pagecount": 0, "limit": PAGE_SIZE, "total": 0}
        except Exception as e:
            return {"list": [], "page": 1, "pagecount": 0, "limit": PAGE_SIZE, "total": 0,
                    "msg": "详情加载失败：" + str(e)}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        play_id = str(id or "").strip()
        if not play_id:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "播放地址为空"}

        share_url = play_id
        # 支持 shareURL|fileId|... 取首段
        if "|" in play_id:
            share_url = play_id.split("|", 1)[0]
        # encodeId r（整条分享）/ e（指定集）
        typ, data = decode_id(play_id)
        file_id = ""
        file_name = ""
        file_sha = ""
        if typ == "r" and data.get("u"):
            share_url = normalize_share_url(data.get("u"))
        elif typ == "e" and data.get("u"):
            share_url = normalize_share_url(data.get("u"))
            file_id = str(data.get("f") or "")
            file_name = str(data.get("n") or "")
            file_sha = str(data.get("h") or "")
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

        # 先解析成真视频流（m3u8/mp4），避免分享页 HTML 触发 container unsupported
        resolved = resolve_share_media_file(share_url, drive_type, file_id, file_name, file_sha)
        if resolved and resolved[0]:
            stream_url, stream_header = resolved
            return {
                "parse": 0,
                "jx": 0,
                "playUrl": "",
                "url": stream_url,
                "header": stream_header or header,
                "flag": flag or "",
            }

        # 回退：分享页直链（parse=0 交宿主网盘插件；parse=1 会嗅探失败）
        hint = ""
        if drive_type == "115":
            hint = "115 解析失败：请确认源配置 cookie115 有效、115 账号有网盘空间"
        elif drive_type == "baidu":
            hint = "百度分享解析失败：请确认分享链接与提取码有效"
        result = {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": share_url,
            "header": header,
            "flag": flag or "",
        }
        if hint:
            result["msg"] = hint
        return result

    def destroy(self):
        pass
