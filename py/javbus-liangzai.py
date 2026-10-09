VERSION = "1.1.27"
# -*- coding: utf-8 -*-
import os
import re
import json
import time
import base64
import html as _html
import warnings
from concurrent.futures import ThreadPoolExecutor
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
# 配置区 —— 一般只动下面两项
# ===========================================================================
# (1) 网页代理：只管「爬虫抓网页」，图片和播放地址由 App 自己去取，不受它影响
#     ""                        = 直连
#     "7890"                    = 自动补成 http://127.0.0.1:7890
#     "http://1.2.3.4:7890"     = 指定代理（支持 http://user:pass@host:port）
#     "off" / "none" / "直连"   = 直连
PROXY = ""

# (2) 图片反代：图片显示不出来时再开（默认关闭，直连能看图就不需要）
#     实测：images.weserv.nl / wsrv.nl 已把本站域名拉黑
#           （400 "Domain or TLD blocked by policy"，开了一张图都出不来）
#           serveproxy.com 能取到，但只回 image/avif，TVBox 未必认
#     所以要走反代就填自己的，两种写法都支持：
#       "https://my-nginx/?u={url}"   ← {url} 模板（推荐）
#       "https://my-nginx/?u="        ← 前缀式，原图 URL 会自动整体编码
#     英文逗号分隔多个 → 不同图片分散到不同反代（同一张图始终走同一个，保证可缓存）
IMG_PROXY = ""

# 站点 ext（TVBox 源里 ext 字段传 JSON）可覆盖上面两项及其它开关：
#   {
#     "proxy": "7890",                        # 同 PROXY
#     "img":   "https://images.weserv.nl/?url=",  # 同 IMG_PROXY
#     "host":  "https://www.javbus.com",      # 固定域名，不再自动探测
#     "noProbe": true,                        # 不探测域名
#     "existmag": "all",                      # all=全部影片 mag=已有磁力 online=僅線上
#     "cookie": "", "lang": "zh",
#     "enableMagnet": true, "enableUncensored": true,
#     "cookie115": "",                         # 115 Cookie（可选；不填就读下面 DEFAULT_COOKIE_115）
#     "enableOffline115": true,                # 详情页多出「115离线」播放源，默认开
#     "offlineSavePath": "0",                  # 115 离线保存目录 cid，默认根目录
#     "offlineAppVer": "4.8.2",                # 115 离线接口 appVer
#     "offlineProxy": ""                       # 115 接口代理，"" = 直连（不走上面的 PROXY）
#     "offlineTestMp4": ""                     # 二分实验："noheader"/"header" 才开，正常留空
#   }
# 优先级：ext > 顶部 PROXY / IMG_PROXY
#
# 115 离线播放：详情页选「115离线」源 → 把磁力提交到 115 云端离线 → 完成后搜到文件 pickcode →
#               取播放直链返回给播放器。首次可能提示「下载中，请稍后重试」，再点一次即可。

# 候选域名：运行时自动探测，优先直连（不走代理），其次按延迟排序
HOST_CANDIDATES = [
    "https://www.javbus.com",
    "https://www.busfan.casa",
    "https://www.javbus.casa",
    "https://www.cdnbus.casa",
    "https://www.buscdn.casa",
]

HOST = HOST_CANDIDATES[0]

PAGE_SIZE = 30
SEARCH_LIMIT = 30
PROBE_TIMEOUT = 6

# 网络抖动 / 临时 5xx 的重试
HTTP_RETRY = 1
HTTP_RETRY_DELAY = 0.5
HTTP_RETRY_STATUS = (429, 500, 502, 503, 504)

# 域名探测结果缓存时长（到期自动重测，避免首次没网就永远卡住）
PROBE_TTL = 60
PROBE_CACHE_MAX = 32

WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

LIST_HEADERS = {
    "User-Agent": WEB_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
    "Referer": HOST + "/",
}

AJAX_HEADERS = {
    "Accept": "text/html, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

# 站点「已有磁力 / 全部影片」开关（cookie: existmag），默认全部影片
EXISTMAG_ALL = "all"
EXISTMAG_MAG = "mag"
EXISTMAG_ONLINE = "online"

# ============ 115 离线（复用 离线javbus.py / 离线av.py） ============
# 115 Cookie 直接写这里即可（等价于 ext.cookie115 / 环境变量 Y115_COOKIE），
# 注意本行不是注释，引号里的内容会被读取；别把带 Cookie 的文件公开分享
DEFAULT_COOKIE_115 = ("UID=7090991_R1_1785487771; CID=3c1a3ab03cfc92b0b7c80db6efa950c6; "
                      "SEID=81ec0f1ad4aa99de925b609465a91c20d8894da910834a59f27cb239ebc5eb70412b456e8e91fff5654dc089a9d0c153f5fcec844b4cf7fa1b8aac84; "
                      "KID=bc573815d056010f1b8373db03247c3b")

# 详情页播放地址里的 115 离线标记。
# 新格式 base64(json{"m":磁力,"t":片名})，旧格式 base64(磁力) 也能解
OFF_PREFIX_115 = "http://115off/"
# 播放过程留痕：写进 Python 沙箱 home 下的小文件，跨实例/跨重启都能看到。
# 用来判断「点播放后到底有没有走到我们的代码」。
OFF_TRACE_FILE = os.path.join(os.path.expanduser("~"), "javbus_off_trace.txt")


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
    """115 的 fc 字段：1=文件 0=文件夹。注意可能是 int 0，不能用 or 判空"""
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
    """播放地址解码 → (磁力, 片名, 小标题)。旧格式 base64(磁力) 也能解"""
    # 地址后面可能挂着 ?t=时间戳（防 App 按播放地址缓存旧结果），base64 里没有 ?/#
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

OFFLINE_UA = WEB_UA + " 115Browser/36.0.0"
OFFLINE_VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".ts", ".m4v",
                      ".wmv", ".rm", ".rmvb", ".iso", ".mpg", ".mpeg", ".3gp",
                      ".webm", ".m2ts", ".rmvb", ".vob", ".mp2")
OFFLINE_ADD_API = "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls"
OFFLINE_LIST_API = "https://115.com/web/lixian/?ct=lixian&ac=task_lists"
OFFLINE_POLL_TIMEOUT = 15
OFFLINE_POLL_INTERVAL = 1
# 整理+取直链一起最多花几秒；超了就不整理，直接走 v1.1.21 的老路径（先直链、取不到再搜）
OFFLINE_FINISH_BUDGET = 9
# 超过几秒还没好，就开始每一步都弹提示（卡在哪一步一看就知道）
OFFLINE_TRACE_AFTER = 4
# 二分实验用的公开测试片（免鉴权、支持 Range），只在 ext.offlineTestMp4 打开时用
OFFLINE_TEST_MP4 = ("https://commondatastorage.googleapis.com/gtv-videos-bucket/"
                    "sample/BigBuckBunny.mp4")
OFFLINE_TEST_HEADER = {
    "User-Agent": OFFLINE_UA,
    "Referer": "https://115.com/",
    "Accept": "*/*",
}

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

JAVBUS_CLASSES = [
    {"type_id": "jav_home",               "type_name": "有碼"},
    {"type_id": "jav_uncensored",          "type_name": "無碼"},
    {"type_id": "jav_genre",              "type_name": "有碼類別"},
    {"type_id": "jav_uncensored_genre",   "type_name": "無碼類別"},
    {"type_id": "jav_actress",            "type_name": "有碼女優"},
    {"type_id": "jav_uncensored_actress", "type_name": "無碼女優"},
    {"type_id": "jav_genre_hd",           "type_name": "高清"},
    {"type_id": "jav_genre_sub",          "type_name": "字幕"},
]

# 内置类别（抓取 /genre、/uncensored/genre 失败时的兜底数据）
BUILTIN_GENRE_GROUPS = {
    "genre": [
        ("主題", [
            ("62", "折磨"), ("5g", "嘔吐"), ("59", "觸手"), ("57", "蠻橫嬌羞"), ("52", "處男"), ("4y", "正太控"), ("4r", "出軌"), ("4e", "瘙癢"),
            ("4d", "運動"), ("4a", "女同接吻"), ("49", "性感的"), ("44", "美容院"), ("41", "處女"), ("40", "爛醉如泥的"), ("3x", "殘忍畫面"), ("3w", "妄想"),
            ("3v", "惡作劇"), ("3t", "學校作品"), ("3r", "粗暴"), ("3g", "通姦"), ("3e", "姐妹"), ("3d", "雙性人"), ("3c", "跳舞"), ("3b", "性奴"),
            ("37", "倒追"), ("35", "性騷擾"), ("2y", "其他"), ("2x", "戀腿癖"), ("2v", "偷窥"), ("2t", "花癡"), ("2r", "男同性恋"), ("2e", "情侶"),
            ("2d", "戀乳癖"), ("20", "亂倫"), ("1y", "其他戀物癖"), ("1u", "偶像藝人"), ("1i", "野外・露出"), ("1e", "獵豔"), ("1d", "女同性戀"), ("11", "企畫"),
            ("6h", "10枚組"), ("61", "科幻"), ("6i", "女優ベスト・総集編"), ("6j", "温泉"), ("6k", "M男"), ("6l", "原作コラボ"), ("6n", "16時間以上作品"), ("6o", "デカチン・巨根"),
            ("6p", "ファン感謝・訪問"), ("6q", "動画"), ("6r", "巨尻"), ("6s", "ハーレム"), ("6t", "日焼け"), ("6u", "早漏"), ("6v", "キス・接吻"), ("6w", "汗だく"),
            ("77", "スマホ専用縦動画"), ("7d", "Vシネマ"), ("7c", "Don Cipote's choice"), ("7f", "アニメ"), ("7g", "アクション"), ("7h", "イメージビデオ（男性）"), ("7i", "孕ませ"), ("7j", "ボーイズラブ"),
            ("7t", "ビッチ"), ("7u", "特典あり（AVベースボール）"), ("7v", "コミック雑誌"), ("7w", "時間停止"),
        ]),
        ("角色", [
            ("5w", "黑幫成員"), ("5k", "童年朋友"), ("5i", "公主"), ("5f", "亞洲女演員"), ("58", "伴侶"), ("4s", "講師"), ("4l", "婆婆"), ("4h", "格鬥家"),
            ("3o", "女檢察官"), ("39", "明星臉"), ("38", "女主人、女老板"), ("34", "模特兒"), ("32", "秘書"), ("30", "美少女"), ("2z", "新娘、年輕妻子"), ("2w", "姐姐"),
            ("2q", "格鬥家"), ("2o", "車掌小姐"), ("2f", "寡婦"), ("2b", "千金小姐"), ("2a", "白人"), ("29", "已婚婦女"), ("27", "女醫生"), ("26", "各種職業"),
            ("23", "妓女"), ("21", "賽車女郎"), ("1x", "女大學生"), ("1v", "展場女孩"), ("1n", "女教師"), ("1k", "母親"), ("1c", "家教"), ("17", "护士"),
            ("10", "蕩婦"), ("z", "黑人演員"), ("p", "女生"), ("c", "女主播"), ("b", "高中女生"), ("7", "服務生"), ("5r", "魔法少女"), ("65", "學生（其他）"),
            ("64", "動畫人物"), ("6c", "遊戲的真人版"), ("6f", "超級女英雄"),
        ]),
        ("服裝", [
            ("5h", "女戰士"), ("5c", "及膝襪"), ("5b", "娃娃"), ("56", "女忍者"), ("55", "女裝人妖"), ("50", "內衣"), ("4z", "猥褻穿著"), ("4p", "兔女郎"),
            ("4n", "貓耳女"), ("4k", "女祭司"), ("4i", "泡泡襪"), ("3i", "制服"), ("3a", "緊身衣"), ("2s", "裸體圍裙"), ("2m", "迷你裙警察"), ("2l", "空中小姐"),
            ("28", "連褲襪"), ("1w", "身體意識"), ("18", "OL"), ("12", "和服・喪服"), ("y", "體育服"), ("v", "內衣"), ("m", "水手服"), ("l", "學校泳裝"),
            ("k", "旗袍"), ("j", "女傭"), ("i", "迷你裙"), ("a", "校服"), ("9", "泳裝"), ("8", "眼鏡"), ("1", "角色扮演"), ("6b", "哥德蘿莉"),
        ]),
        ("體型", [
            ("5d", "超乳"), ("4x", "肌肉"), ("3n", "乳房"), ("3k", "嬌小的"), ("2k", "屁股"), ("2i", "高"), ("2g", "變性者"), ("22", "無毛"),
            ("1t", "胖女人"), ("1f", "苗條"), ("15", "孕婦"), ("13", "成熟的女人"), ("w", "蘿莉塔"), ("t", "貧乳・微乳"), ("e", "巨乳"),
        ]),
        ("行為", [
            ("4w", "顏面騎乘"), ("4t", "食糞"), ("4j", "足交"), ("47", "母乳"), ("46", "手指插入"), ("45", "按摩"), ("42", "女上位"), ("3q", "舔陰"),
            ("3l", "拳交"), ("3f", "深喉"), ("2h", "69"), ("24", "淫語"), ("1z", "潮吹"), ("1s", "乳交"), ("1r", "排便"), ("1p", "飲尿"),
            ("1o", "口交"), ("1j", "濫交"), ("19", "放尿"), ("x", "打手槍"), ("u", "吞精"), ("r", "肛交"), ("n", "顏射"), ("h", "自慰"),
            ("5", "顏射"), ("4", "中出"), ("6m", "肛内中出"),
        ]),
        ("玩法", [
            ("51", "立即口交"), ("4f", "女優按摩棒"), ("4c", "子宮頸"), ("4b", "催眠"), ("3z", "乳液"), ("3y", "羞恥"), ("3s", "凌辱"), ("3p", "拘束"),
            ("3m", "輪姦"), ("3h", "插入異物"), ("36", "鴨嘴"), ("2u", "灌腸"), ("25", "監禁"), ("1q", "紧缚"), ("1m", "強姦"), ("1l", "藥物"),
            ("1h", "汽車性愛"), ("1b", "SM"), ("1a", "糞便"), ("14", "玩具"), ("q", "跳蛋"), ("d", "緊縛"), ("6", "按摩棒"), ("3", "多P"),
            ("5m", "性愛"), ("5y", "假陽具"), ("63", "逆強姦"),
        ]),
        ("類別", [
            ("60", "合作作品"), ("5z", "恐怖"), ("5t", "給女性觀眾"), ("5s", "教學"), ("5q", "DMM專屬"), ("5o", "R-15"), ("5n", "R-18"), ("5e", "3D"),
            ("5a", "特效"), ("54", "故事集"), ("53", "限時降價"), ("4v", "複刻版"), ("4u", "戲劇"), ("4q", "戀愛"), ("4o", "高畫質"), ("4m", "主觀視角"),
            ("48", "介紹影片"), ("43", "4小時以上作品"), ("3u", "薄馬賽克"), ("3j", "經典"), ("33", "首次亮相"), ("31", "數位馬賽克"), ("2p", "投稿"), ("2n", "纪录片"),
            ("2c", "國外進口"), ("1g", "第一人稱攝影"), ("16", "業餘"), ("s", "局部特寫"), ("o", "獨立製作"), ("g", "DMM獨家"), ("f", "單體作品"), ("2", "合集"),
            ("hd", "高清"), ("sub", "字幕"), ("2j", "天堂TV"), ("4g", "DVD多士爐"), ("66", "AV OPEN 2014 スーパーヘビー"), ("69", "AV OPEN 2014 ヘビー級"), ("6a", "AV OPEN 2014 ミドル級"), ("70", "AV OPEN 2015 マニア/フェチ部門"),
            ("71", "AV OPEN 2015 熟女部門"), ("72", "AV OPEN 2015 企画部門"), ("73", "AV OPEN 2015 乙女部門"), ("74", "AV OPEN 2015 素人部門"), ("75", "AV OPEN 2015 SM/ハード部門"), ("76", "AV OPEN 2015 女優部門"), ("7k", "AVOPEN2016人妻・熟女部門"), ("7l", "AVOPEN2016企画部門"),
            ("7m", "AVOPEN2016ハード部門"), ("7n", "AVOPEN2016マニア・フェチ部門"), ("7o", "AVOPEN2016乙女部門"), ("7p", "AVOPEN2016女優部門"), ("7q", "AVOPEN2016ドラマ・ドキュメンタリー部門"), ("7r", "AVOPEN2016素人部門"), ("7s", "AVOPEN2016バラエティ部門"), ("7x", "VR専用"),
            ("7y", "堵嘴·喜劇"), ("7z", "幻想"), ("80", "性別轉型·女性化"), ("81", "為智能手機推薦垂直視頻"), ("82", "設置項目"), ("83", "迷你係列"), ("84", "體驗懺悔"), ("85", "黑暗系統"),
        ]),
        ("其他", [
            ("dx", "オナサポ"), ("dy", "アスリート"), ("dz", "覆面・マスク"), ("e0", "ハイクオリティVR"), ("e1", "ヘルス・ソープ"), ("e2", "ホテル"), ("e3", "アクメ・オーガズム"), ("e4", "花嫁"),
            ("e5", "デート"), ("e6", "軟体"), ("e7", "娘・養女"), ("e8", "スパンキング"), ("e9", "スワッピング・夫婦交換"), ("ea", "部下・同僚"), ("eb", "旅行"), ("ec", "胸チラ"),
            ("ed", "バック"), ("ee", "エロス"), ("ef", "男の潮吹き"), ("eg", "女上司"), ("eh", "セクシー"), ("ei", "受付嬢"), ("ej", "ノーブラ"), ("ek", "白目・失神"),
            ("el", "M女"), ("em", "女王様"), ("en", "ノーパン"), ("eo", "セレブ"), ("ep", "病院・クリニック"), ("eq", "面接"), ("er", "お風呂"), ("es", "叔母さん"),
            ("et", "罵倒"), ("eu", "お爺ちゃん"), ("ev", "逆レイプ"), ("ew", "ディルド"), ("ex", "ヨガ"), ("ey", "飲み会・合コン"), ("ez", "部活・マネージャー"), ("f0", "お婆ちゃん"),
            ("f1", "ビジネススーツ"), ("f2", "チアガール"), ("f3", "ママ友"), ("f4", "エマニエル"), ("f5", "妄想族"), ("f6", "蝋燭"), ("f7", "鼻フック"), ("f8", "放置"),
            ("f9", "サンプル動画"), ("fa", "サイコ・スリラー"), ("fb", "ラブコメ"), ("fc", "オタク"), ("fd", "4K"), ("fe", "福袋"), ("ff", "玩具責め"), ("fj", "女優"),
            ("fl", "お掃除フェラ"), ("fn", "筆おろし"), ("fq", "美脚"), ("ft", "美尻"), ("fu", "フェチ"), ("fw", "羞恥プレイ"), ("fx", "逆ナンパ"), ("fy", "着衣"),
            ("g0", "誘惑"), ("g1", "チラリズム"), ("g2", "写真集"), ("g3", "書籍版"), ("g4", "SM拘束"), ("g6", "ドキュメント"), ("g9", "グッズ"), ("ga", "Tシャツ"),
            ("gb", "失禁"), ("gc", "オナホール"), ("gd", "カップホール"), ("ge", "非貫通"), ("gf", "ローション付き"), ("gh", "配信専用"), ("gi", "官能小説"), ("gj", "CD"),
            ("gk", "生挿入"), ("gl", "風俗"), ("gm", "外国人"), ("gn", "淫語責め"), ("go", "アナルファック"), ("gp", "脚コキ"), ("gq", "オイルプレイ"), ("gr", "キャバ嬢"),
            ("gs", "調教"), ("gt", "ローション・オイル"), ("gu", "媚薬"), ("gv", "顔面騎乗位"), ("gw", "微乳"), ("gx", "デカチン"), ("gz", "野外"), ("h0", "露出"),
            ("h1", "レイプ"), ("h2", "ベスト、総集編"), ("h3", "マジックミラー号"), ("h4", "看護師"), ("h5", "アイドル"), ("h6", "妹"), ("h7", "スクール水着"), ("h8", "デリヘル"),
            ("h9", "凌辱"), ("ha", "童貞モノ"), ("hb", "ブルマ"), ("hc", "ホテヘル"), ("hd", "縛り"), ("he", "ロリータ"), ("hf", "ミニスカート"), ("hg", "尻"),
            ("hh", "奴隷"), ("hi", "芸能人"), ("hj", "下着"), ("hk", "母親"), ("hl", "湯"), ("hm", "教師"), ("hn", "ストッキング"), ("ho", "電車、バス"),
            ("hp", "健康診断"), ("hq", "野球拳"), ("hr", "浴衣"), ("hs", "爆乳"), ("ht", "ソープ"), ("hu", "スワッピング"), ("hv", "メガネ"), ("hw", "素股"),
            ("hx", "ドリンク"), ("hy", "フルハイビジョン(FHD)"), ("hz", "三十路"), ("i0", "羞恥・辱め"), ("i1", "パンチラモノ"), ("i2", "放尿・失禁"), ("i3", "五十路"), ("i4", "ショートヘアー"),
            ("i5", "着物・浴衣"), ("i6", "清楚"), ("i7", "四十路"), ("i8", "VR"), ("i9", "オモチャ"), ("ia", "エステ・マッサージ"), ("ib", "Gカップ"), ("ic", "目隠し"),
            ("id", "ドラッグ・媚薬"), ("ie", "六十路"), ("if", "淫語モノ"), ("ig", "口内発射"), ("ih", "童顔"), ("ii", "スチュワーデス・CA"), ("ij", "Dカップ"), ("ik", "美熟女"),
            ("il", "MGSだけのおまけ映像付き"), ("im", "手マン"), ("in", "パンストモノ"), ("io", "フェラモノ"), ("ip", "性教育"), ("iq", "HowTo"), ("ir", "MGS限定特典映像"), ("is", "寝取り･寝取られ"),
            ("it", "Eカップ"), ("iu", "Fカップ"), ("iv", "ロングヘアー"), ("iw", "黒髪"), ("ix", "ショートヘア"), ("iy", "金髪"), ("iz", "茶髪"), ("j0", "女子高生"),
            ("j1", "ハーフ"), ("j2", "金髪・ブロンド"), ("j3", "初撮り"), ("j4", "介護"), ("j5", "Hカップ"), ("j6", "期間限定販売"), ("j7", "多人数"), ("j8", "風俗嬢"),
            ("j9", "PICKUP素人"), ("ja", "オイル・ローション"), ("jb", "8KVR"),
        ]),
    ],
    "uncensored_genre": [
        ("主題", [
            ("hd", "高清"), ("sub", "字幕"), ("1bc", "推薦作品"), ("yz", "通姦"), ("3q", "淋浴"), ("8q", "舌頭"), ("ap", "下流"), ("8y", "敏感"),
            ("29", "變態"), ("8w", "願望"), ("au", "慾求不滿"), ("nc", "服侍"), ("ee", "外遇"), ("19o", "訪問"), ("7z", "性伴侶"), ("bk", "保守"),
            ("17g", "購物"), ("6p", "誘惑"), ("eu", "出差"), ("xx", "煩惱"), ("jm", "主動"), ("vr", "再會"), ("bd", "戀物癖"), ("vn", "問題"),
            ("164", "騙奸"), ("ui", "鬼混"), ("u4", "高手"), ("1cu", "順從"), ("v6", "密會"), ("sb", "做家務"), ("y2", "秘密"), ("pm", "送貨上門"),
            ("e5", "壓力"), ("t9", "處女作"), ("1cw", "淫語"), ("gc", "問卷"), ("wd", "住一宿"), ("12d", "眼淚"), ("7d", "跪求"), ("7g", "求職"),
            ("8i", "婚禮"), ("gre001", "第一視角"), ("gre002", "洗澡"), ("gre003", "首次"), ("gre004", "劇情"), ("gre005", "約會"), ("gre006", "實拍"), ("gre007", "同性戀"),
            ("gre008", "幻想"), ("gre009", "淫蕩"), ("gre010", "旅行"), ("gre011", "面試"), ("gre012", "喝酒"), ("gre013", "尖叫"), ("gre014", "新年"), ("gre015", "借款"),
            ("gre016", "不忠"), ("gre017", "檢查"), ("gre018", "羞恥"), ("gre019", "勾引"), ("gre020", "新人"), ("gre021", "推銷"), ("gre153", "ブルマ"),
        ]),
        ("角色", [
            ("c", "AV女優"), ("2r", "情人"), ("yg", "丈夫"), ("3", "辣妹"), ("1av", "S級女優"), ("18", "白領"), ("1y", "偶像"), ("wc", "兒子"),
            ("13", "女僕"), ("jk", "老師"), ("bm", "夫婦"), ("r5", "保健室"), ("18t", "朋友"), ("mr", "工作人員"), ("o4", "明星"), ("m8", "同事"),
            ("11x", "面具男"), ("43", "上司"), ("165", "睡眠系"), ("1a1", "奶奶"), ("12r", "播音員"), ("pk", "鄰居"), ("1co", "親人"), ("48", "店員"),
            ("9a", "魔女"), ("3r", "視訊小姐"), ("5d", "大學生"), ("ok", "寡婦"), ("ad", "小姐"), ("ct", "秘書"), ("2e", "人妖"), ("1d3", "啦啦隊"),
            ("8d", "美容師"), ("sv", "岳母"), ("1bx", "警察"), ("gre022", "熟女"), ("gre023", "素人"), ("gre024", "人妻"), ("gre025", "痴女"), ("gre026", "角色扮演"),
            ("gre027", "蘿莉"), ("gre028", "姐姐"), ("gre029", "模特"), ("gre030", "教師"), ("gre031", "學生"), ("gre032", "少女"), ("gre033", "新手"), ("gre034", "男友"),
            ("gre035", "護士"), ("gre036", "媽媽"), ("gre037", "主婦"), ("gre038", "孕婦"), ("gre039", "女教師"), ("gre040", "年輕人妻"), ("gre041", "職員"), ("gre042", "看護"),
            ("gre043", "外觀相似"), ("gre044", "色狼"), ("gre045", "醫生"), ("gre046", "新婚"), ("gre047", "黑人"), ("gre048", "空中小姐"), ("gre155", "運動系"), ("gre158", "女王"),
            ("gre159", "西裝"), ("gre160", "旗袍"), ("gre161", "兔女郎"), ("gre163", "白人"),
        ]),
        ("服裝", [
            ("2", "制服"), ("5x", "內衣"), ("19t", "休閒裝"), ("gv", "水手服"), ("mx", "全裸"), ("cd", "不穿內褲"), ("3i", "和服"), ("ce", "不戴胸罩"),
            ("16w", "連衣裙"), ("17y", "打底褲"), ("jg", "緊身衣"), ("qm", "客人"), ("f8", "晚禮服"), ("ab", "治癒系"), ("88", "大衣"), ("1di", "裸體襪子"),
            ("wz", "絲帶"), ("14", "睡衣"), ("f7", "面具"), ("17h", "牛仔褲"), ("du", "喪服"), ("hm", "極小比基尼"), ("1dp", "混血"), ("vx", "毛衣"),
            ("1bu", "頸鏈"), ("17i", "短褲"), ("gre049", "美人"), ("gre050", "連褲襪"), ("gre051", "裙子"), ("gre052", "浴衣和服"), ("gre053", "泳衣"), ("gre054", "網襪"),
            ("gre055", "眼罩"), ("gre056", "圍裙"), ("gre057", "比基尼"), ("gre058", "情趣內衣"), ("gre059", "迷你裙"), ("gre060", "套裝"), ("gre061", "眼鏡"), ("gre062", "丁字褲"),
            ("gre063", "陽具腰帶"), ("gre156", "男装"), ("gre157", "襪"),
        ]),
        ("體型", [
            ("1da", "美肌"), ("zc", "屁股"), ("bl", "美穴"), ("5g", "黑髮"), ("66", "嬌小"), ("wy", "曬痕"), ("5h", "F罩杯"), ("3z", "E罩杯"),
            ("9x", "D罩杯"), ("4s", "素顏"), ("1dd", "貓眼"), ("1b4", "捲髮"), ("17s", "虎牙"), ("199", "C罩杯"), ("mu", "I罩杯"), ("gz", "小麥色"),
            ("i0", "大陰蒂"), ("gre064", "美乳"), ("gre065", "巨乳"), ("gre066", "豐滿"), ("gre067", "苗條"), ("gre068", "美臀"), ("gre069", "美腿"), ("gre070", "無毛"),
            ("gre071", "美白"), ("gre072", "微乳"), ("gre073", "性感"), ("gre074", "高個子"), ("gre075", "爆乳"), ("gre076", "G罩杯"), ("gre077", "多毛"), ("gre078", "巨臀"),
            ("gre079", "軟體"), ("gre080", "巨大陽具"), ("gre081", "長發"), ("gre082", "H罩杯"),
        ]),
        ("行為", [
            ("i", "舔陰"), ("34", "電動陽具"), ("3x", "淫亂"), ("11a", "射在外陰"), ("c2", "猛烈"), ("v4", "後入內射"), ("5u", "足交"), ("11e", "射在胸部"),
            ("uc", "側位內射"), ("14w", "射在腹部"), ("141", "騎乘內射"), ("110", "射在頭髮"), ("kp", "母乳"), ("tc", "站立姿勢"), ("kv", "肛射"), ("10p", "陰道擴張"),
            ("12p", "內射觀察"), ("124", "射在大腿"), ("11p", "精液流出"), ("13a", "射在屁股"), ("134", "內射潮吹"), ("12x", "首次肛交"), ("128", "射在衣服上"), ("14d", "首次內射"),
            ("2c", "早洩"), ("12l", "翻白眼"), ("13r", "舔腳"), ("14v", "喝尿"), ("gre083", "口交"), ("gre084", "內射"), ("gre085", "自慰"), ("gre086", "後入"),
            ("gre087", "騎乘位"), ("gre088", "顏射"), ("gre089", "口內射精"), ("gre090", "手淫"), ("gre091", "潮吹"), ("gre092", "輪姦"), ("gre093", "亂交"), ("gre094", "乳交"),
            ("gre095", "小便"), ("gre096", "吸精"), ("gre097", "深膚色"), ("gre098", "指法"), ("gre099", "騎在臉上"), ("gre100", "連續內射"), ("gre101", "打樁機"), ("gre102", "肛交"),
            ("gre103", "吞精"), ("gre104", "鴨嘴"), ("gre105", "打飛機"), ("gre106", "剃毛"), ("gre107", "站立位"), ("gre108", "高潮"), ("gre109", "二穴同入"), ("gre110", "舔肛"),
            ("gre111", "多人口交"), ("gre112", "痙攣"), ("gre113", "玩弄肛門"), ("gre114", "立即口交"), ("gre115", "舔蛋蛋"), ("gre116", "口射"), ("gre117", "陰屁"), ("gre118", "失禁"),
            ("gre119", "大量潮吹"), ("gre154", "69"),
        ]),
        ("玩法", [
            ("6", "振動"), ("1o", "淫語"), ("w", "搭訕"), ("28", "奴役"), ("10u", "打屁股"), ("1c2", "潤滑油"), ("6w", "按摩"), ("iz", "散步"),
            ("117", "扯破連褲襪"), ("zk", "手銬"), ("22", "束縛"), ("6t", "調教"), ("62", "假陽具"), ("wo", "變態遊戲"), ("8e", "注視"), ("161", "蠟燭"),
            ("12u", "電鑽"), ("kr", "亂搞"), ("b6", "摩擦"), ("yk", "項圈"), ("sl", "繩子"), ("10w", "灌腸"), ("162", "監禁"), ("2g", "車震"),
            ("15z", "鞭打"), ("11i", "懸掛"), ("1cv", "喝口水"), ("11s", "精液塗抹"), ("12a", "舔耳朵"), ("14l", "女體盛"), ("rk", "便利店"), ("11l", "插兩根"),
            ("125", "開口器"), ("we", "暴露"), ("122", "陰道放入食物"), ("10q", "大便"), ("1b8", "經期"), ("m3", "惡作劇"), ("gre120", "電動按摩器"), ("gre121", "凌辱"),
            ("gre122", "玩具"), ("gre123", "露出"), ("gre124", "肛門"), ("gre125", "拘束"), ("gre126", "多P"), ("gre127", "潤滑劑"), ("gre128", "攝影"), ("gre129", "野外"),
            ("gre130", "陰道觀察"), ("gre131", "SM"), ("gre132", "灌入精液"), ("gre133", "受虐"), ("gre134", "綁縛"), ("gre135", "偷拍"), ("gre136", "異物插入"), ("gre137", "電話"),
            ("gre138", "公寓"), ("gre139", "遠程操作"), ("gre140", "偷窺"), ("gre141", "踩踏"), ("gre164", "無套"),
        ]),
        ("其他", [
            ("1z", "企劃物"), ("2a", "獨佔動畫"), ("1x", "10代"), ("1j", "1080p"), ("2d", "人氣系列"), ("1k", "60fps"), ("1f", "超VIP"), ("163", "投稿"),
            ("16", "VIP"), ("102", "椅子"), ("3y", "風格出眾"), ("40", "首次作品"), ("178", "更衣室"), ("io", "下午"), ("1dg", "KTV"), ("gre142", "白天"),
            ("gre143", "最佳合集"), ("gre162", "VR"), ("gre165", "動漫"),
        ]),
        ("場景", [
            ("2o", "酒店"), ("6e", "密室"), ("30", "車"), ("103", "床"), ("140", "陽台"), ("4m", "公園"), ("e7", "家中"), ("o8", "公交車"),
            ("4z", "公司"), ("po", "門口"), ("he", "附近"), ("7k", "學校"), ("59", "辦公室"), ("wj", "樓梯"), ("zu", "住宅"), ("zj", "公共廁所"),
            ("7w", "旅館"), ("7j", "教室"), ("h1", "廚房"), ("x4", "桌子"), ("hb", "大街"), ("fz", "農村"), ("6f", "和室"), ("13k", "地下室"),
            ("11w", "牢籠"), ("wh", "屋頂"), ("3a", "游泳池"), ("5e", "電梯"), ("vf", "拍攝現場"), ("9p", "別墅"), ("gre144", "房間"), ("gre145", "愛情旅館"),
            ("gre146", "車內"), ("gre147", "沙發"), ("gre148", "浴室"), ("gre149", "廁所"), ("gre150", "溫泉"), ("gre151", "醫院"), ("gre152", "榻榻米"),
        ]),
    ],
}

# 女优筛选最多显示多少个
STAR_FILTER_LIMIT = 50


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


def _extract_id(url):
    if not url:
        return ""
    m = re.search(r"/([A-Za-z0-9_\-\.]+)/?$", url)
    return m.group(1) if m else ""


def _mag_filter():
    """磁力筛选：默认全部影片"""
    return {
        "key": "existmag",
        "name": "磁力",
        "init": EXISTMAG_ALL,
        "value": [
            {"n": "全部影片", "v": EXISTMAG_ALL},
            {"n": "已有磁力", "v": EXISTMAG_MAG},
            {"n": "僅線上", "v": EXISTMAG_ONLINE},
        ],
    }


def _norm_proxy(v):
    """代理地址归一化：支持纯端口 / host:port / 完整 URL；空值表示直连"""
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


_HOST_PROBE_CACHE = {}


def _stable_bucket(s, n):
    """跨进程稳定的分桶。Python 内置 hash() 对字符串每次进程都不同，不能用于这里。"""
    if n <= 1:
        return 0
    h = 0
    for ch in _to_text(s):
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return h % n


def _sanitize_play(v):
    """TVBox 播放串用 # 分隔条目、$ 分隔「名称与地址」，值里出现这两个字符会被截断"""
    if not v:
        return v
    return (_to_text(v)
            .replace("#", "%23")
            .replace("$", "%24")
            .replace("\r", " ")
            .replace("\n", " "))


def _probe_host(base, use_env, timeout=PROBE_TIMEOUT, proxy=""):
    """探测单个域名。proxy 优先；use_env=False 表示不走系统/环境代理（直连）。"""
    if not requests:
        return None
    s = requests.Session()
    if proxy:
        s.trust_env = False
        s.proxies = {"http": proxy, "https": proxy}
    else:
        s.trust_env = bool(use_env)
    s.headers.update(LIST_HEADERS)
    s.headers["Referer"] = base + "/"
    t0 = time.time()
    try:
        r = s.get(base + "/", timeout=timeout, verify=False, allow_redirects=True)
        r.encoding = "utf-8"
        text = r.text or ""
    except Exception:
        return None
    finally:
        try:
            s.close()
        except Exception:
            pass
    cost = time.time() - t0
    if not text:
        return None
    if not any(k in text for k in ("movie-box", "ageVerify", "existmag", "JavBus")):
        return None
    return cost


def pick_host(candidates=None, proxy=""):
    """选域名：配置了代理就全走代理；否则免代理 > 最快。结果缓存 PROBE_TTL 秒。"""
    cands = [c.rstrip("/") for c in (candidates or HOST_CANDIDATES)]
    key = (tuple(cands), proxy)
    hit = _HOST_PROBE_CACHE.get(key)
    if hit:
        host, ts = hit
        if time.time() - ts < PROBE_TTL:
            return host
    if not cands or not requests:
        return None

    best = None
    if proxy:
        args = [(u, False) for u in cands]
    else:
        args = [(u, False) for u in cands] + [(u, True) for u in cands]

    def task(arg):
        base, use_env = arg
        cost = _probe_host(base, use_env, proxy=proxy)
        if cost is None:
            return None
        return (0 if not use_env else 1, cost, base)

    try:
        with ThreadPoolExecutor(max_workers=len(args)) as ex:
            for res in ex.map(task, args):
                if res and (best is None or res < best):
                    best = res
    except Exception:
        best = None

    # 失败（None）也缓存，但靠 TTL 自动重试，不会一次没网就永久卡死
    host = best[2] if best else None
    if len(_HOST_PROBE_CACHE) >= PROBE_CACHE_MAX:
        _HOST_PROBE_CACHE.clear()
    _HOST_PROBE_CACHE[key] = (host, time.time())
    return host


# ==================== 115 加密工具 ====================

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


class Spider:
    def __init__(self):
        self.s = None
        self.s115 = None
        self.host = HOST
        self.ua = WEB_UA
        self.timeout = 15
        self.page_size = PAGE_SIZE
        self.search_limit = SEARCH_LIMIT
        self.enable_magnet = True
        self.enable_uncensored = True
        # 默认全部影片；可切「已有磁力」
        self.existmag = EXISTMAG_ALL
        self.cookie = ""
        # 图片反代：默认取顶部 IMG_PROXY，也可用站点 ext 覆盖（见文件顶部注释）
        self.img_proxy = IMG_PROXY
        # 代理：默认取顶部 PROXY，也可用站点 ext 覆盖（见文件顶部注释）
        self.proxy = PROXY
        self.lang = "zh"
        self.verify = False

        # 115 离线：提交磁力到 115 云端，完成后取播放直链（见文件顶部注释）
        self.cookie_115 = DEFAULT_COOKIE_115
        self.enable_offline_115 = True
        self.offline_save_path = "0"
        self.offline_app_ver = "4.8.2"
        self.offline_timeout = 10
        self.offline_proxy = ""
        self.offline_debug = True
        # 二分实验开关（ext.offlineTestMp4）："" = 关闭
        self.offline_test_mp4 = ""
        # info_hash -> pickcode 缓存，重试时不再重新搜文件
        self._off_cache = {}
        # info_hash -> 文件名，缓存命中时给成功提示用
        self._off_name = {}
        # info_hash -> 该片原简介（详情页拿到），播放页 desc 提示时放在提示后面
        self._off_syn = {}
        # 影片 id -> 片名（女优列表入口离线整理时用）
        self._vid_title = {}

        # filters / 默认值缓存
        self._cache_filters = {}
        self._host_locked = False
        self._probed = False

        if requests:
            self.s = requests.Session()
            self.s.headers.update(LIST_HEADERS)
            # 立即应用顶部 PROXY，只填文件顶部 PROXY 即可生效
            self._apply_proxy()

    def getDependence(self):
        return []

    @staticmethod
    def _parse_extend(extend):
        """ext 兼容：JSON / URL 编码的 JSON / key=value&key2=value2（各壳传法不一）"""
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

        # 磁力筛选，默认全部影片
        if "existmag" in extend:
            self.existmag = _to_text(extend.get("existmag")) or EXISTMAG_ALL
        elif "onlyMagnet" in extend:
            self.existmag = EXISTMAG_MAG if bool(extend.get("onlyMagnet")) else EXISTMAG_ALL
        elif "hasMagnet" in extend:
            self.existmag = EXISTMAG_MAG if bool(extend.get("hasMagnet")) else EXISTMAG_ALL
        if self.existmag not in (EXISTMAG_ALL, EXISTMAG_MAG, EXISTMAG_ONLINE):
            self.existmag = EXISTMAG_ALL

        # 代理：直连不通时填端口即可（"7890" / "127.0.0.1:7890" / 完整 URL）；空值 = 直连
        if "proxy" in extend:
            self.set_proxy(extend.get("proxy"))
        elif "proxyPort" in extend or "proxy_port" in extend:
            self.set_proxy(extend.get("proxyPort") or extend.get("proxy_port"))

        # 无论 ext 是否带 proxy，都把当前代理挂到会话（顶部 PROXY 也在此生效）
        self._apply_proxy()

        # ==== 115 ====
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
            # 代理变了，重建 115 会话
        self.s115 = None
        self._off_last = ""
        if "offlineDebug" in extend:
            self.offline_debug = str(extend.get("offlineDebug")).lower() not in (
                "0", "false", "off", "no")
        # 二分实验：播放直接返回公开测试 MP4，用来判断「转圈不出画」是
        # result 结构问题 还是 115 直链/header 的问题。"" = 关闭，线上行为不变
        self.offline_test_mp4 = _to_text(extend.get("offlineTestMp4")).strip().lower()

        # 自动选域名：配置了代理全走代理，否则免代理 > 最快
        self._ensure_host()

        # 清空缓存
        self._cache_filters = {}

    def set_proxy(self, value):
        """设置/清除代理，返回归一化后的代理地址"""
        p = _norm_proxy(value)
        if p != self.proxy:
            self.proxy = p
            # 代理变了，重新探测域名
            self._probed = False
        self._apply_proxy()
        return self.proxy

    def _apply_proxy(self):
        """把代理挂到会话上（无代理则清空，保持直连/环境代理）"""
        if not self.s:
            return
        if self.proxy:
            self.s.trust_env = False
            self.s.proxies = {"http": self.proxy, "https": self.proxy}
        else:
            self.s.trust_env = True
            self.s.proxies = {}

    def _ensure_host(self):
        """探测候选域名并选一个：有代理走代理，否则免代理 > 最快"""
        if self._host_locked or self._probed:
            return
        # 只有真的选到域名才算「探测过」；失败靠 pick_host 的 TTL 缓存自愈，
        # 否则一次没网就会把这个实例永远锁死在默认域名上
        host = pick_host(proxy=self.proxy)
        if host:
            self.host = host
            self._probed = True

    # ========== 首页分类 ==========
    def homeContent(self, filter=None):
        self._ensure_host()

        classes = []
        for c in JAVBUS_CLASSES:
            if c["type_id"] in ("jav_uncensored", "jav_uncensored_genre",
                                "jav_uncensored_actress") and not self.enable_uncensored:
                continue
            classes.append(dict(c))

        filters = {}
        for c in classes:
            tid = c["type_id"]
            fs = []
            if tid == "jav_genre":
                fs = self._build_genre_filters(self.host + "/genre")
            elif tid == "jav_uncensored_genre":
                fs = self._build_genre_filters(self.host + "/uncensored/genre")
            elif tid == "jav_actress":
                fs = self._build_star_filters(self.host + "/actresses")
            elif tid == "jav_uncensored_actress":
                fs = self._build_star_filters(self.host + "/uncensored/actresses")
            fs = list(fs)
            fs.append(_mag_filter())
            filters[tid] = fs
        return {"class": classes, "filters": filters}

    # ---------- 类别筛选 ----------
    def _build_genre_filters(self, index_url):
        cache_key = "genre:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
            groups = self._parse_genre_groups(text)
        except Exception:
            groups = []
        if not groups:
            groups = self._builtin_genre_groups(index_url)

        out = []
        for gname, items in groups:
            if not items:
                continue
            values = [{"n": "全部", "v": ""}]
            for it in items:
                values.append({"n": it["name"], "v": it["gid"]})
            out.append({
                "key": "genre_" + gname,
                "name": gname,
                "init": "",
                "value": values,
            })

        self._cache_filters[cache_key] = out
        return out

    def _parse_genre_groups(self, text):
        groups = []
        h4_iter = list(re.finditer(r"<h4>([^<]+)</h4>", text))
        if not h4_iter:
            return groups

        for i, m in enumerate(h4_iter):
            gname = _clean_text(m.group(1))
            start = m.end()
            end = h4_iter[i + 1].start() if i + 1 < len(h4_iter) else len(text)
            block = text[start:end]

            items = []
            seen = set()
            for gb in re.finditer(
                r'<div[^>]+class="[^"]*genre-box[^"]*"[^>]*>(.*?)</div>',
                block, re.S
            ):
                inner = gb.group(1)
                for a in re.finditer(
                    r'<a[^>]+href="([^"]*?/genre/([^"/]+))"[^>]*>([^<]+)</a>',
                    inner
                ):
                    gid = a.group(2)
                    name = _clean_text(a.group(3))
                    if not gid or not name or gid in seen:
                        continue
                    seen.add(gid)
                    items.append({"gid": gid, "name": name})
            if items:
                groups.append((gname, items))
        return groups

    def _builtin_genre_groups(self, index_url):
        """抓取失败时使用内置类别"""
        key = "uncensored_genre" if "/uncensored/" in _to_text(index_url) else "genre"
        data = BUILTIN_GENRE_GROUPS.get(key) or []
        return [
            (gname, [{"gid": gid, "name": name} for gid, name in items])
            for gname, items in data
        ]

    # ---------- 女优筛选 ----------
    def _parse_actresses(self, text):
        """解析女优头像列表页（/actresses）：sid + 名字 + 头像"""
        out = []
        seen = set()
        for m in re.finditer(
            r'<a[^>]+class="[^"]*avatar-box[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            text, re.S
        ):
            sid = _extract_id(_fix_url(m.group(1), self.host))
            block = m.group(2)
            name = ""
            nm = re.search(r"<span>([^<]+)</span>", block)
            if nm:
                name = _clean_text(nm.group(1))
            pic = ""
            im = re.search(r'<img[^>]+src="([^"]+)"', block, re.I)
            if im:
                pic = _fix_url(im.group(1), self.host)
            if not sid or not name or sid in seen:
                continue
            seen.add(sid)
            out.append({"sid": sid, "name": name, "pic": pic})
        return out

    def _build_star_filters(self, index_url):
        cache_key = "star:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]

        try:
            text = self._get_html(index_url)
        except Exception:
            self._cache_filters[cache_key] = []
            return []

        values = [{"n": "全部", "v": ""}]
        for it in self._parse_actresses(text):
            values.append({"n": it["name"], "v": it["sid"]})
            if len(values) > STAR_FILTER_LIMIT:
                break

        if len(values) <= 1:
            self._cache_filters[cache_key] = []
            return []

        out = [{
            "key": "star",
            "name": "女優",
            "init": "",
            "value": values,
        }]
        self._cache_filters[cache_key] = out
        return out

    # ---------- 默认值（点分类未选筛选时用） ----------
    @staticmethod
    def _first_filter_value(filters):
        """从已构建的筛选里取第一个非空 value（复用缓存，不再重复请求）"""
        for f in filters or []:
            for v in f.get("value") or []:
                val = _to_text(v.get("v")) if isinstance(v, dict) else ""
                if val:
                    return val
        return ""

    def _get_default_genre(self, index_url):
        """取类别页第一个类别作为默认（复用 _build_genre_filters 的结果）"""
        cache_key = "default_genre:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]
        gid = self._first_filter_value(self._build_genre_filters(index_url))
        self._cache_filters[cache_key] = gid
        return gid

    def homeVideoContent(self):
        # 首页直接展示有碼最新影片（App 调到才发请求）
        self._ensure_host()
        return self._list_page(self.host + "/", 1, None)

    # ========== 分类内容 ==========
    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        t = _to_text(tid)
        page = _safe_int(pg, 1)

        # 解析筛选
        genre_sel = {}
        star_sel = {}
        mag = ""
        for src in (filter, extend):
            if isinstance(src, dict):
                for k, v in src.items():
                    k = _to_text(k)
                    v = _to_text(v)
                    if not v:
                        continue
                    if k.startswith("genre_"):
                        genre_sel[v] = True
                    elif k == "star":
                        star_sel[v] = True
                    elif k == "existmag":
                        mag = v
        hdr = self._mag_headers(mag)

        # 有码首页
        if t == "jav_home":
            if page <= 1:
                return self._list_page(self.host + "/", page, hdr)
            return self._list_page(self.host + "/page/%d" % page, page, hdr)

        # 无码首页
        if t == "jav_uncensored":
            if page <= 1:
                return self._list_page(self.host + "/uncensored", page, hdr)
            return self._list_page(self.host + "/uncensored/page/%d" % page, page, hdr)

        # 有码类别：选筛选 → 对应类别（支持多选 a-b-c）；否则 → 第一个默认类别
        if t == "jav_genre":
            if genre_sel:
                return self._category_list(
                    self.host + "/genre", "-".join(genre_sel.keys()), page, hdr)
            default_gid = self._get_default_genre(self.host + "/genre")
            if default_gid:
                return self._category_list(self.host + "/genre", default_gid, page, hdr)
            if page <= 1:
                return self._list_page(self.host + "/", page, hdr)
            return self._list_page(self.host + "/page/%d" % page, page, hdr)

        # 无码类别：选筛选 → 对应类别（支持多选 a-b-c）；否则 → 第一个默认类别
        if t == "jav_uncensored_genre":
            if genre_sel:
                return self._category_list(
                    self.host + "/uncensored/genre", "-".join(genre_sel.keys()), page, hdr)
            default_gid = self._get_default_genre(self.host + "/uncensored/genre")
            if default_gid:
                return self._category_list(
                    self.host + "/uncensored/genre", default_gid, page, hdr)
            if page <= 1:
                return self._list_page(self.host + "/uncensored", page, hdr)
            return self._list_page(self.host + "/uncensored/page/%d" % page, page, hdr)

        # 有码女优：选了女优 → 该女优影片；否则 → 头像列表（点头像进她影片）
        if t == "jav_actress":
            if star_sel:
                return self._star_list(
                    self.host + "/star", next(iter(star_sel)), page, hdr)
            return self._actress_list(
                self.host + "/actresses", "jav_star_", page, hdr)

        # 无码女优：选了女优 → 该女优影片；否则 → 头像列表（点头像进她影片）
        if t == "jav_uncensored_actress":
            if star_sel:
                return self._star_list(
                    self.host + "/uncensored/star", next(iter(star_sel)), page, hdr)
            return self._actress_list(
                self.host + "/uncensored/actresses", "jav_uc_star_", page, hdr)

        # 具体类别页
        if t.startswith("jav_genre_"):
            gid = t[len("jav_genre_"):]
            return self._category_list(self.host + "/genre", gid, page, hdr)

        if t.startswith("jav_uc_genre_"):
            gid = t[len("jav_uc_genre_"):]
            return self._category_list(self.host + "/uncensored/genre", gid, page, hdr)

        # 具体女优页
        if t.startswith("jav_star_"):
            sid = t[len("jav_star_"):]
            return self._star_list(self.host + "/star", sid, page, hdr)

        if t.startswith("jav_uc_star_"):
            sid = t[len("jav_uc_star_"):]
            return self._star_list(self.host + "/uncensored/star", sid, page, hdr)

        return {"list": [], "page": page, "pagecount": 1,
                "limit": self.page_size, "total": 0}

    def _mag_headers(self, mag):
        """按筛选覆盖 existmag cookie；与全局一致时不覆盖"""
        mag = _to_text(mag)
        if not mag or mag == self.existmag:
            return None
        parts = ["existmag=" + mag]
        if self.cookie:
            parts.append(self.cookie)
        return {"Cookie": "; ".join(parts)}

    def _category_list(self, base, gid, page, hdr=None):
        """类别列表页：/genre/xxx 或 /genre/xxx/2"""
        if page <= 1:
            url = "%s/%s" % (base.rstrip("/"), gid)
        else:
            url = "%s/%s/%d" % (base.rstrip("/"), gid, page)
        return self._list_page(url, page, hdr)

    def _star_list(self, base, sid, page, hdr=None):
        """女优列表页：/star/xxx 或 /star/xxx/2"""
        if page <= 1:
            url = "%s/%s" % (base.rstrip("/"), sid)
        else:
            url = "%s/%s/%d" % (base.rstrip("/"), sid, page)
        return self._list_page(url, page, hdr)

    def _actress_list(self, index_url, id_prefix, page, hdr=None):
        """女优头像列表：vod_tag=folder，点击后 vod_id 变成新的分类 ID 进下一层"""
        url = index_url if page <= 1 else "%s/%d" % (index_url.rstrip("/"), page)
        try:
            text = self._get_html(url, headers=hdr)
        except Exception:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.page_size, "total": 0}

        out = []
        for it in self._parse_actresses(text):
            out.append({
                "vod_id": id_prefix + it["sid"],
                "vod_name": it["name"],
                "vod_pic": self._proxy_pic(it["pic"]),
                "vod_remarks": "",
                "vod_tag": "folder",
            })

        has_next = self._has_next_page(text, page)
        return {
            "list": out,
            "page": page,
            "pagecount": page + 1 if has_next else page,
            "limit": len(out) or self.page_size,
            "total": len(out),
        }

    # ========== 列表页解析 ==========
    @staticmethod
    def _parse_tags(block):
        """取 item-tag 里的标记（高清 / 前日新種 …，即磁力可用性提示）"""
        tags = []
        m = re.search(
            r'<div[^>]+class="[^"]*item-tag[^"]*"[^>]*>(.*?)</div>', block, re.S
        )
        if not m:
            return tags
        for t in re.findall(r"<button[^>]*>([^<]+)</button>", m.group(1)):
            t = _clean_text(t)
            if t and t not in tags:
                tags.append(t)
        return tags

    @staticmethod
    def _has_next_page(text, page):
        if re.search(r'<a[^>]+id="next"[^>]+href="[^"]+"', text):
            return True
        pag = re.search(
            r'<ul[^>]+class="[^"]*pagination[^"]*"[^>]*>(.*?)</ul>', text, re.S
        )
        if not pag:
            return False
        nums = [_safe_int(x) for x in re.findall(r'href="[^"]*?/(\d+)"', pag.group(1))]
        nums = [n for n in nums if n > 0]
        return bool(nums) and max(nums) > page

    def _parse_movie_boxes(self, text):
        """解析所有 movie-box 条目（列表页 / 搜索页共用）"""
        out = []
        seen = set()
        for m in re.finditer(
            r'<a[^>]+class="[^"]*movie-box[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            text, re.S
        ):
            try:
                href = _fix_url(m.group(1), self.host)
                block = m.group(2)

                img = re.search(
                    r'<img[^>]*(?:src|data-src|data-original)=["\']([^"\']+)',
                    block, re.I
                )
                pic = _fix_url(img.group(1), self.host) if img else ""

                title = ""
                tm = re.search(r'<img[^>]+title="([^"]+)"', block, re.I)
                if tm:
                    title = _clean_text(tm.group(1))
                if not title:
                    tm = re.search(r"<span>([^<]+)", block)
                    if tm:
                        title = _clean_text(tm.group(1))

                num = ""
                dates = re.findall(r"<date>([^<]+)</date>", block)
                if dates:
                    num = _clean_text(dates[0])

                vid = _extract_id(href)
                if not vid or vid in seen:
                    continue
                seen.add(vid)

                remarks = " ".join([x for x in [num] + self._parse_tags(block) if x])
                out.append({
                    "vod_id": vid,
                    "vod_name": title or num or vid,
                    "vod_pic": self._proxy_pic(pic),
                    "vod_remarks": remarks,
                })
            except Exception:
                continue
        return out

    def _list_page(self, url, page, hdr=None):
        try:
            text = self._get_html(url, headers=hdr)
        except Exception:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.page_size, "total": 0}

        out = self._parse_movie_boxes(text)
        has_next = self._has_next_page(text, page)

        return {
            "list": out,
            "page": page,
            "pagecount": page + 1 if has_next else page,
            "limit": self.page_size,
            "total": len(out),
        }

    # ========== 详情 ==========
    def detailContent(self, ids):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")
        if not vid:
            return {"list": []}

        # 兼容：如果框架把类别 ID 传到 detailContent，直接返回空
        if vid.startswith(("jav_genre_", "jav_uc_genre_")):
            return {"list": []}

        # 兼容：框架不支持 vod_tag=folder 时，点头像会进这里。
        # 返回她的影片作为播放列表，点影片时再去取磁力播放。
        if vid.startswith(("jav_star_", "jav_uc_star_")):
            return self._actress_detail(vid)

        url = _fix_url("/" + vid, self.host)
        try:
            text = self._get_html(url)
        except Exception:
            return {"list": []}

        title = ""
        tm = re.search(r"<title>([^<]+)</title>", text)
        if tm:
            title = _clean_text(tm.group(1)).replace(" - JavBus", "").strip()

        pic = ""
        pm = re.search(r'<a[^>]+class="bigImage"[^>]+href="([^"]+)"', text)
        if pm:
            pic = _fix_url(pm.group(1), self.host)
        if not pic:
            pm = re.search(r'<img[^>]+src="(/imgs/cover/[^"]+)"', text)
            if pm:
                pic = _fix_url(pm.group(1), self.host)
        if not pic:
            pm = re.search(r'<img[^>]+src="(/imgs/[^"]+\.jpg)"', text)
            if pm:
                pic = _fix_url(pm.group(1), self.host)
        pic = self._proxy_pic(pic)

        num = ""
        for pat in (
            r'識別碼:</span>\s*<span[^>]*>([^<]+)',
            r'識別碼[:：]\s*</span>\s*<span[^>]*>([^<]+)',
            r'<span[^>]*class="header"[^>]*>識別碼[:：]</span>\s*<span[^>]*>([^<]+)',
        ):
            nm = re.search(pat, text)
            if nm:
                num = _clean_text(nm.group(1))
                if num:
                    break

        date = ""
        for pat in (
            r'發行日期:</span>\s*([^<]+)',
            r'發行日期[:：]\s*</span>\s*([^<]+)',
            r'<span[^>]*class="header"[^>]*>發行日期[:：]</span>\s*([^<]+)',
        ):
            dm = re.search(pat, text)
            if dm:
                date = _clean_text(dm.group(1))
                if date:
                    break

        actors = re.findall(
            r'class="avatar-box"[^>]+href="[^"]+"[^>]*>\s*<div[^>]*>\s*<img[^>]+title="([^"]+)"',
            text
        )
        if not actors:
            actors = re.findall(
                r'<a[^>]+href="[^"]*star/[^"]+"[^>]*title="([^"]+)"',
                text
            )
        actors = [_clean_text(a) for a in actors if a]

        # 类别：优先取勾选框 gr_sel（唯一代表本片类别），避免命中导航里的 genre/hd
        genres = []
        seen_g = set()
        for gm in re.finditer(
            r'name="gr_sel"[^>]*value="([^"]*)"[^>]*>\s*'
            r'<a href="[^"]*?/genre/([^"]+)">([^<]+)</a>',
            text
        ):
            gname = _clean_text(gm.group(3))
            gid = gm.group(2)
            if not gname or gid in seen_g:
                continue
            seen_g.add(gid)
            genres.append(gname)
        if not genres:
            # 兜底：只在正文区（</nav> 之后、抽屉菜单之前）找类别链接，排除导航
            body = text
            n0 = body.find("</nav>")
            if n0 > 0:
                body = body[n0 + 6:]
            n1 = body.find('class="overlay')
            if n1 > 0:
                body = body[:n1]
            for g in re.findall(r'<a href="[^"]*?/genre/[^"]+">([^<]+)</a>', body):
                g = _clean_text(g)
                if g and g not in seen_g:
                    seen_g.add(g)
                    genres.append(g)

        info_lines = []
        if num:
            info_lines.append("番号: %s" % num)
        if date:
            info_lines.append("发行: %s" % date)
        if actors:
            info_lines.append("演员: %s" % "、".join(actors))
        if genres:
            info_lines.append("类别: %s" % "、".join(genres))
        if self.enable_offline_115:
            info_lines.append("115离线：提交到115云端，完成后自动直连播放；"
                              "网盘里只留视频文件，命名为「片名_小标题 大小」(v%s)"
                              % VERSION)

        magnets = []
        if self.enable_magnet or self.enable_offline_115:
            try:
                magnets = self._fetch_magnets(text, vid)
            except Exception:
                magnets = []

        # 按 info_hash 去重：115 离线按 hash 提交，重复条目没意义
        magnet_items = []
        seen_h = set()
        for g in magnets:
            raw = _sanitize_play(_to_text(g.get("magnet") or ""))
            h = self._magnet_hash(raw)
            if not raw or not h or h in seen_h:
                continue
            seen_h.add(h)
            # 115 只认干净的 btih 磁力（去掉 dn / tr 参数）
            magnet_items.append((g, raw, _normalize_magnet(raw), h))

        # 标题去重：页面 <title> 本身通常已带番号
        vod_name = _to_text(title)
        if num and vod_name:
            if not vod_name.startswith(num):
                vod_name = (num + " " + vod_name).strip()
        elif num:
            vod_name = num

        froms, urls = [], []

        # 磁力源（交给播放器，能不能播看内核；保留原始磁力，带 tracker）
        if self.enable_magnet and magnet_items:
            eps = []
            for i, (g, raw, clean, h) in enumerate(magnet_items):
                label = self._magnet_label(g, i, num)
                eps.append("%s$%s" % (label, raw))
            if eps:
                froms.append("磁力")
                urls.append("#".join(eps))

        # 115 离线源（提交到 115 云端，完成后取播放直链）。
        # 把片名和这条磁力的小标题（含大小）一起带过去，整理文件时命名：
        # 片名_小标题 1.35GB.mp4
        if self.enable_offline_115 and magnet_items:
            eps = []
            for i, (g, raw, clean, h) in enumerate(magnet_items):
                label = self._magnet_label(g, i, num)
                b64 = _off_id_encode(clean, vod_name, label)
                # ?t= 时间戳：App 若按播放地址缓存了旧结果（旧直链改名后就失效），
                # 每次进详情都换个地址，强制重新走 playerContent 拿新直链
                eps.append("%s$%s%s?t=%d" % (label, OFF_PREFIX_115, b64,
                                             int(time.time())))
            if eps:
                froms.append("115离线")
                urls.append("#".join(eps))

        # 记下原简介：播放页 desc 提示时把提示放在原简介前面，不把原简介顶掉
        base_content = "\n".join(info_lines)
        if self.enable_offline_115:
            for (_g, _raw, _clean, h) in magnet_items:
                if h not in self._off_syn:
                    self._off_syn[h] = base_content

        # 已经离线完成的片子：简介第一行给提示，进详情页就弹一次 toast。
        # FongMi 对 detailContent 的 msg 是 Notify.show（list 非空不会被打断），
        # 而 playerContent 的 msg 会被当播放错误，两边不能混用。
        done_note = ""
        for (_g, _raw, _clean, h) in magnet_items:
            if h in self._off_name:
                done_note = self._offline_note("115离线完成", self._off_name.get(h, ""))
                break
        if done_note:
            info_lines.insert(0, done_note)
        # 上次点播放走到哪一步/什么结果：直接写进简介首行（一定看得见，不依赖 toast）
        last = _to_text(self._off_last) or _trace_read()
        if self.enable_offline_115 and last:
            info_lines.insert(0, "[上次播放] " + last)

        item = {
            "vod_id": vid,
            "vod_name": vod_name or vid,
            "vod_pic": pic,
            "vod_year": (date or "")[:4],
            "vod_actor": "、".join(actors),
            "vod_content": "\n".join(info_lines),
        }
        if froms:
            item["vod_play_from"] = "$$$".join(froms)
            item["vod_play_url"] = "$$$".join(urls)

        res = {"list": [item]}
        if done_note:
            res["msg"] = done_note
        elif self.enable_offline_115 and last:
            # 兜底诊断：上次点播放卡在哪一步/结果如何，进详情页弹一次
            res["msg"] = last
        return res

    def _actress_detail(self, vid):
        """女优详情（vod_tag=folder 不被支持时的兜底）：把她的影片做成播放列表"""
        if vid.startswith("jav_uc_star_"):
            sid = vid[len("jav_uc_star_"):]
            base = self.host + "/uncensored/star"
        else:
            sid = vid[len("jav_star_"):]
            base = self.host + "/star"
        if not sid:
            return {"list": []}
        try:
            text = self._get_html("%s/%s" % (base.rstrip("/"), sid))
        except Exception:
            return {"list": []}

        title = ""
        tm = re.search(r"<title>([^<]+)</title>", text)
        if tm:
            title = _clean_text(tm.group(1))
            title = title.replace(" - JavBus", "").strip()
            title = re.sub(r"\s*-\s*(影片|有碼|無碼)\s*$", "", title).strip()

        pic = ""
        pm = re.search(r'(?:src|href)="([^"]*pics/actress/[^"]+)"', text, re.I)
        if pm:
            pic = self._proxy_pic(_fix_url(pm.group(1), self.host))

        eps, eps115 = [], []
        for m in self._parse_movie_boxes(text):
            name = _to_text(m.get("vod_name"))
            label = re.sub(r"[$#&\n\r\t]", " ", name).strip()[:40]
            mid = _to_text(m.get("vod_id"))
            if not mid:
                continue
            eps.append("%s$%s" % (label or sid, "jav_movie_" + mid))
            if self.enable_offline_115:
                eps115.append("%s$jav_movie115_%s?t=%d"
                              % (label or sid, mid, int(time.time())))

        item = {
            "vod_id": vid,
            "vod_name": title or sid,
            "vod_pic": pic,
            "vod_content": "",
        }
        froms, urls = [], []
        if eps:
            froms.append("她的影片")
            urls.append("#".join(eps))
        if eps115:
            froms.append("115离线")
            urls.append("#".join(eps115))
        if froms:
            item["vod_play_from"] = "$$$".join(froms)
            item["vod_play_url"] = "$$$".join(urls)
        return {"list": [item]}

    def _magnets_of(self, vid):
        """按影片 ID 取磁力列表（兜底播放用）"""
        try:
            text = self._get_html(_fix_url("/" + _to_text(vid), self.host))
        except Exception:
            return []
        # 顺手记下片名，115 离线整理文件时要用
        try:
            m = re.search(r"<title>([^<]+)</title>", text or "", re.I)
            if m:
                name = _clean_text(m.group(1))
                name = re.sub(r"\s*-\s*JavBus\s*$", "", name, flags=re.I).strip()
                if name:
                    self._vid_title[_to_text(vid)] = name
        except Exception:
            pass
        try:
            return self._fetch_magnets(text, vid)
        except Exception:
            return []

    def _title_of(self, vid):
        return _to_text(self._vid_title.get(_to_text(vid), ""))

    def _fetch_magnets(self, detail_html, vid):
        gid = ""
        for pat in (
            r"var\s+gid\s*=\s*(\d+)",
            r"gid\s*=\s*(\d+)",
            r'data-gid\s*=\s*"(\d+)"',
        ):
            gm = re.search(pat, detail_html)
            if gm:
                gid = gm.group(1)
                if gid:
                    break
        if not gid:
            return []

        img = ""
        im = re.search(r"var\s+img\s*=\s*'([^']+)'", detail_html)
        if im:
            img = im.group(1)

        uc = "1" if re.search(r"var\s+uc\s*=\s*1", detail_html) else "0"

        ajax_url = (
            "%s/ajax/uncledatoolsbyajax.php?gid=%s&lang=%s&img=%s&uc=%s&floor=%d"
            % (self.host, gid, self.lang, quote(img, safe=""), uc,
               int(time.time() * 1000) % 1000 + 1)
        )
        try:
            text = self._get_html(ajax_url, headers=AJAX_HEADERS)
        except Exception:
            return []
        if not text:
            return []

        out = []
        seen_hash = set()
        for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", text, re.S):
            block = m.group(1)
            am = re.search(r'href="(magnet:[^"]+)"', block)
            if not am:
                continue
            magnet = _sanitize_play(am.group(1).replace("&amp;", "&"))

            hm = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet)
            if not hm:
                continue
            h = hm.group(1).lower()
            if h in seen_hash:
                continue
            seen_hash.add(h)

            name = ""
            nm = re.search(r"<a[^>]*>([^<]+)</a>", block)
            if nm:
                name = _clean_text(nm.group(1))

            # 体积在第 2 列，形如「2.62GB」（数字和单位之间没空格），外面还包着 <a>
            size = ""
            sm = re.search(
                r"<td[^>]*>\s*<a[^>]*>\s*([\d]+(?:\.\d+)?)\s*(TB|GB|MB|KB)\s*</a>",
                block, re.I
            )
            if not sm:
                sm = re.search(r"([\d]+(?:\.\d+)?)\s*(TB|GB|MB|KB)\b", block, re.I)
            if sm:
                size = "%s %s" % (sm.group(1), sm.group(2).upper())

            out.append({
                "name": name,
                "size": size,
                "magnet": magnet,
            })

        # 保持站点原始顺序（体积只是显示在标签里，用户自己挑）
        return out

    @staticmethod
    def _magnet_label(g, i, num):
        raw = _to_text(g.get("name")) or num or ("资源%d" % (i + 1))
        safe = re.sub(r"[$#&\n\r\t]", " ", raw).strip()[:40]
        parts = [safe]
        size = g.get("size")
        if size:
            parts.append(_sanitize_play(size))
        return " ".join(parts) or ("资源%d" % (i + 1))

    def _proxy_pic(self, url):
        """图片反代：支持前缀式 和 {url} 模板式，多个用逗号分隔时按图片稳定分散"""
        if not url:
            return ""
        raw = (self.img_proxy or "").strip()
        if not raw:
            return url
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            return url
        try:
            enc = quote(url, safe="")
        except Exception:
            return url
        p = parts[0] if len(parts) == 1 else parts[_stable_bucket(url, len(parts))]
        if "{url}" in p:
            return p.replace("{url}", enc)
        return p + enc

    # ========== 115 离线 ==========
    def _offline_session(self):
        """115 接口专用会话：默认直连（不走爬虫代理、不读系统代理）"""
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

    @staticmethod
    def _magnet_hash(magnet):
        m = re.search(r"btih:([0-9a-fA-F]{40}|[0-9a-zA-Z]{32})", magnet or "")
        return m.group(1).lower() if m else ""

    @staticmethod
    def _magnet_dn(magnet):
        """磁力链接里的 dn 参数（原始文件名）→ 用来提交前先搜一遍网盘"""
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
        """115 离线任务对象里直接带 pick_code，能拿到就不用再按文件名搜"""
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
        base = os.path.splitext(name)[0]
        ext = os.path.splitext(name)[1].lower()
        # 带视频后缀的完整文件名：直接按文件名搜（115 是子串匹配，最准）
        if ext in (".mp4", ".mkv", ".avi", ".mov", ".flv", ".ts", ".m4v", ".wmv",
                   ".rm", ".rmvb", ".iso", ".mpg", ".mpeg", ".3gp", ".webm"):
            return (base.replace("_", " ").strip() or name)[:60]
        base = base.replace("_", " ").replace(".", " ").strip()
        m = re.search(r"(FC2)[- ]?(PPV)?[- ]?(\d{5,8})", base, re.I)
        if m:
            return "FC2-PPV-%s" % m.group(3)
        m = re.search(r"([A-Za-z]{2,6})[- ]?(\d{2,5})", base)
        if m:
            return "%s-%s" % (m.group(1).upper(), m.group(2))
        return base[:40]

    def _find_pickcode_by_name(self, name, retries=3, interval=1, exact=""):
        keyword = self._guess_keyword_from_name(name)
        if not keyword:
            return ""
        sess = self._offline_session()
        if sess is None:
            return ""
        headers = {
            "User-Agent": WEB_UA,
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
            "Accept": "application/json, text/plain, */*",
            "Cookie": self.cookie_115,
        }
        exact = _to_text(exact)
        for _ in range(max(1, retries)):
            fallback = ""
            # type=4 视频优先，找不到再搜全部（兜底）
            for stype in (4, 0):
                try:
                    r = sess.get("https://webapi.115.com/files/search", params={
                        "search_value": keyword, "type": stype, "offset": 0,
                        "limit": 50, "aid": 1, "cid": 0, "format": "json",
                    }, headers=headers, timeout=10, verify=False)
                    data = _safe_json(r.text, {})
                    rows = data.get("data")
                    if not isinstance(rows, list):
                        rows = []
                    for it in rows:
                        if int(it.get("fc") or 0) != 1:
                            continue
                        pc = it.get("pc") or it.get("pick_code") or it.get("pickcode")
                        if not pc:
                            continue
                        if exact and _to_text(it.get("n") or it.get("name")) == exact:
                            return pc
                        if not fallback:
                            fallback = pc
                except Exception:
                    pass
            if fallback:
                return fallback
            if interval:
                time.sleep(interval)
        return ""

    def _resolve_pickcode(self, pickcode):
        if not self.cookie_115:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "未配置115 Cookie（文件 DEFAULT_COOKIE_115 / ext.cookie115 / Y115_COOKIE）"}
        sess = self._offline_session()
        if not requests or sess is None:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "requests 模块不可用"}

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
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "115 取直链失败: %s" % e}

        try:
            decoded = _decode_downurl_response(r.text)
        except Exception as e:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "115 解密失败: %s" % e}

        real_url = _find_url_deep(decoded)
        if not real_url:
            msg = _find_msg_deep(decoded) or "未发现下载链接"
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "115 限制: %s" % msg}

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
        return result

    @staticmethod
    def _offline_note(prefix, name=""):
        """成功提示文案。

        不能用 msg：FongMi/OK影视 的 PlaybackActivity.getPlaybackError() 里
        `if (result.hasMsg()) return result.getMsg()`，playerContent 的 msg 一律当
        播放错误处理（成功也会打断播放），msg 只留给真正的错误。
        播放页没有可用的 toast 入口，成功提示走三个非阻塞通道：
        desc（播放页描述面板，提示放原简介前面）+ detailContent 的 msg（打开详情页时
        Notify.show 一次）+ subs（画面下方 8 秒字幕）。
        """
        name = _to_text(name).strip()
        return "%s：%s" % (prefix, name) if name else prefix

    def _set_off_last(self, text):
        """记下上次播放走到哪一步：内存 + 文件（跨实例/重启也能看）"""
        self._off_last = _to_text(text)
        _trace_write(self._off_last)

    def _off_trace(self, phase, t0, force=False):
        """离线播放过程提示（ext.offlineDebug 控制，默认开）。

        文本总是记到 self._off_last——播放页看不到时，进详情页会用 msg 弹一次兜底。
        每一步都 toast 一次，一直转圈时就知道卡在哪一步。
        """
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
        """本地代理地址前缀：App 内能拿到 Proxy 端口就用 http，拿不到退回 proxy://。"""
        try:
            from com.github.catvod import Proxy
            port = int(Proxy.getPort() or 0)
        except Exception:
            port = 0
        return "http://127.0.0.1:%d/proxy?" % port if port > 0 else "proxy://"

    @staticmethod
    def _offline_srt(text):
        """提示做成 8 秒字幕：播放开始时显示在画面下方，不打断播放。"""
        text = _to_text(text).strip() or "115离线完成"
        return "1\n00:00:00,000 --> 00:00:08,000\n%s\n\n" % text

    def _offline_hint(self, res, note, info_hash=""):
        """成功结果挂提示：绝不写 msg（会变成播放错误），用 desc + subs。

        desc 落在播放页的描述面板（renderDescription → mBinding.content），
        把提示放在原简介前面，原简介仍然保留。
        """
        syn = _to_text(self._off_syn.get(info_hash, "")) if info_hash else ""
        res["desc"] = (note + "\n\n" + syn) if syn else note
        try:
            # siteKey 由 App 在 init 前注入（chaquo 里 obj.put("siteKey", ...)），
            # 带上它，本地 /proxy 才能路由回本爬虫
            key = _to_text(getattr(self, "siteKey", ""))
            q = "do=py" + ("&siteKey=%s" % quote(key) if key else "")
            url = self._offline_proxy_base() + q + "&k=offnote&v=%s" % quote(note)
            res["subs"] = [{"name": "115离线", "url": url, "lang": "zh",
                            "format": "application/x-subrip", "flag": 0}]
        except Exception:
            pass
        return res

    # ========== 115 网盘整理：一个种子只留一个视频，改名 片名_小标题 大小 ==========

    def _offline_webapi(self, path, params=None, data=None, timeout=8):
        """webapi.115.com 通用请求 → dict"""
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
        """pick_code → 文件/文件夹信息 dict（fc: 1=文件 0=文件夹）"""
        if not pickcode:
            return {}
        data = self._offline_webapi("/files/get_info",
                                    params={"pick_code": pickcode, "format": "json"})
        row = data.get("data")
        if isinstance(row, list):
            row = row[0] if row else {}
        return row if isinstance(row, dict) else {}

    def _offline_dir(self, cid, limit=1000, deadline=0):
        """列目录（aid=1）→ 子项列表，自动翻页"""
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
        """目录子项 → 要播的那个视频文件；不是视频就返回 None（别乱删）"""
        videos = [r for r in rows if _fc(r) == "1"
                  and cls._is_video_name(r.get("n") or r.get("name") or "")]
        return max(videos, key=lambda r: _safe_int(r.get("s") or r.get("size") or 0, 0),
                   default=None)

    def _offline_find_video(self, cid, depth=1, deadline=0):
        """找体积最大的视频 → (子项, 它所在的目录 cid)；找不到返回 (None, "")"""
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
        """片名_小标题 1.35GB.mp4（用户指定下划线分隔）

        带来小标题就用「片名_小标题 大小.后缀」；带不过来退回「片名_原文件名」。
        """
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
            # 115 文件名别超长（截片名，小标题和后缀保留）
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
        """丢回收站（可恢复），顺带删掉里面的其它文件"""
        if not fid:
            return False
        data = self._offline_webapi("/rb/delete", data={"fid[0]": fid})
        return bool(data.get("state"))

    def _offline_parent(self, info, deadline=0):
        """文件夹所在的父目录 cid；拿不到就返回 ""（宁可不移动）"""
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

    def _tidy_file(self, info, name, title, label=""):
        """单文件种子：只改名"""
        pc = info.get("pc") or info.get("pick_code") or ""
        orig = _to_text(info.get("n") or info.get("name") or name)
        new = self._offline_new_name(title, orig, label)
        if new and new != orig and self._offline_rename(info.get("fid"), new):
            orig = new
        return pc, orig or _to_text(name)

    def _tidy_folder(self, info, name, title, label="", deadline=0):
        """文件夹种子：挑体积最大的视频 → 改名 → 移出文件夹 → 删掉文件夹（回收站）"""
        cid = _to_text(info.get("cid") or info.get("fid") or "")
        if deadline and time.time() >= deadline:
            return "", _to_text(name)
        video, src = self._offline_find_video(cid, deadline=deadline) if cid else (None, "")
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
            left = self._offline_dir(src or cid, limit=200, deadline=deadline)
            if any(_to_text(r.get("fid") or "") == fid for r in left):
                pass                        # 其实没移动成功，文件夹不能删
            else:
                self._offline_trash(cid)     # 连子目录和其它文件一起进回收站
        return vpc or _to_text(info.get("pc") or ""), orig or _to_text(name)

    def _offline_tidy(self, pc, name, title="", label="", deadline=0):
        """整理离线产物；返回 (播放用 pickcode, 展示名)。任何失败都不影响播放。"""
        try:
            info = self._offline_info(pc) or {}
        except Exception:
            info = {}
        if not info:
            return pc, _to_text(name)
        # fc 可能是 int 0（文件夹），拿不到 fc 时用有没有 fid 兜底判断
        fc = _fc(info)
        is_dir = (fc == "0") if fc else (not bool(info.get("fid")))
        try:
            if is_dir:
                return self._tidy_folder(info, name, title, label, deadline=deadline)
            return self._tidy_file(info, name, title, label)
        except Exception:
            return pc, _to_text(name)

    def _offline_real_name(self, pickcode):
        """拿文件现在在网盘里的名字（整理过就是 片名_小标题 大小.mp4）"""
        try:
            info = self._offline_info(pickcode) or {}
        except Exception:
            return ""
        return _to_text(info.get("n") or info.get("name") or "")

    def _offline_finish(self, info_hash, pc, name, title="", label="",
                        allow_search=True, t0=None):
        """pickcode → 播放直链。

        任务 pick_code 常指向「离线任务文件夹」（多文件），downurl 返回 url:false。
        整理：挑体积最大的视频、改名成 片名_小标题 1.35GB.mp4、移到原位置、
        文件夹和里面其它文件丢回收站；整理后再取直链。

        整理只在预算（OFFLINE_FINISH_BUDGET）内做：超预算就完全不整理，直接按
        v1.1.21 的老路子取直链（取不到再按文件名搜），保证能及时返回不卡播放页。
        """
        name = _to_text(name).strip()
        title = _to_text(title).strip()
        label = _to_text(label).strip()
        t0 = t0 or time.time()
        deadline = t0 + OFFLINE_FINISH_BUDGET
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

        self._off_trace("取直链", t0)
        res = None
        if play_pc:
            res = self._resolve_pickcode(play_pc)
            if res.get("url"):
                # 整理过就用整理时算好的名字；没整理成才去网盘查一次实际文件名
                if not tidied:
                    display = self._offline_real_name(play_pc) or display
                self._off_cache[info_hash] = play_pc
                if display:
                    self._off_name[info_hash] = display
                return self._offline_hint(res,
                                          self._offline_note("115离线完成", display),
                                          info_hash)
        # 兜底：文件夹被整理掉、pickcode 失效时按片名/小标题/任务名搜出那个视频
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
                    self._off_cache[info_hash] = alt
                    self._off_name[info_hash] = shown
                    return self._offline_hint(res2,
                                              self._offline_note("115离线完成", shown),
                                              info_hash)
                res = res2
        return res or {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                       "msg": "取直链失败（%.0fs），可重试" % (time.time() - t0)}

    def _play_offline_safe(self, magnet, title="", label=""):
        """离线播放入口兜底：任何异常都要落到 msg，绝不允许静默转圈。

        OK影视/影视仓 只看 playerContent 的返回；抛异常时 App 端既无 msg 也无 url，
        播放页就一直转圈没提示。
        """
        t0 = time.time()
        try:
            res = self._submit_offline_115(magnet, title, label)
        except Exception as e:
            res = {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                   "msg": "115离线出错：%s" % e}
        if not isinstance(res, dict):
            res = {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                   "msg": "115离线返回异常"}
        if res.get("url"):
            self._set_off_last("115离线：成功（%.0fs）" % (time.time() - t0))
            return res
        if not res.get("msg"):
            res["msg"] = "115离线取直链失败，请重试"
        self._set_off_last("115离线：失败 %s" % res.get("msg"))
        return res

    def _submit_offline_115(self, magnet, title="", label=""):
        if not self.enable_offline_115:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "115离线已关闭（ext.enableOffline115）"}
        # dn 必须在 normalize 之前取：_normalize_magnet 只留 btih，会把 dn 丢掉
        dn_hint = self._magnet_dn(magnet)
        magnet = _normalize_magnet(magnet)
        if not self.cookie_115:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "未配置115 Cookie（文件 DEFAULT_COOKIE_115 / ext.cookie115 / Y115_COOKIE），无法离线"}
        if not requests or self._offline_session() is None:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "requests 模块不可用"}

        t0 = time.time()
        self._off_trace("开始处理", t0, force=True)

        info_hash = self._magnet_hash(magnet)
        if not info_hash:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "无法从磁力中解析 info_hash"}

        # 已经离线过：直接拿缓存的 pickcode 取直链，不再提交
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

        # ---- 冷启动重播：先搜网盘、再看已有任务，能不提交就不提交 ----
        # （借鉴 良最新 的顺序：缓存 → 按名搜网盘 → 查任务 → 才提交，
        #   上次下完但 App 重启丢了缓存时，省掉 task_lists + add_task_urls 两次请求）
        name_hint = dn_hint
        early_fail = None

        # 1) 网盘里可能已经有文件（dn 是磁力自带的原始文件名）
        if name_hint:
            self._off_trace("先搜网盘", t0)
            pc1 = self._find_pickcode_by_name(name_hint, retries=1, interval=0)
            if pc1:
                self._off_cache[info_hash] = pc1
                res1 = self._offline_finish(info_hash, pc1, name_hint, title=title,
                                            label=label, allow_search=True, t0=t0)
                if res1.get("url"):
                    return res1
                if res1.get("msg"):
                    early_fail = res1

        # 2) 离线任务可能早就在（上次提交过）
        task = None
        try:
            task = self._offline_find_task(info_hash)
        except Exception:
            task = None
        task_name = _to_text(task.get("name") or task.get("file_name") or "") if task else ""
        if not name_hint:
            name_hint = task_name

        if task:
            done0, failed0, msg0 = self._offline_task_state(task)
            pc0 = self._task_pickcode(task)
            if done0 and pc0:
                self._off_trace("任务已完成，整理并取直链", t0)
                res0 = self._offline_finish(info_hash, pc0, task_name,
                                            title=title, label=label, allow_search=True, t0=t0)
                if res0.get("url"):
                    return res0
                early_fail = res0
            elif failed0:
                # 上次任务失败：重新提交一次再看结果（保持老流程的重试语义）
                task = None

        if not task:
            self._off_trace("提交离线任务", t0)
            try:
                add = self._offline_add(magnet)
            except Exception as e:
                return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                        "msg": "提交离线失败：%s" % e}

            # 115 把重复提交算失败（error_msg=任务已存在…），只要任务还在就继续走
            add_msg = _to_text(add.get("message") or add.get("error_msg")
                               or add.get("error"))
            existed = any(k in add_msg for k in ("已存在", "重复"))

            try:
                task = self._offline_find_task(info_hash)
            except Exception:
                task = None

            if not task and not add.get("state") and not existed:
                return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                        "msg": "115离线提交失败：%s" % (add_msg or "提交失败")}

            task_name = _to_text(task.get("name") or task.get("file_name") or "") if task else ""
            if not name_hint:
                name_hint = task_name

            # 秒传 / 已下完：任务对象里直接带 pick_code，直接取直链
            if task:
                done0, failed0, msg0 = self._offline_task_state(task)
                if failed0:
                    return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                            "msg": "115离线失败：%s" % msg0}
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
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "已提交115离线，下载中（%s），请稍后重试"
                           % (name_or_msg or "等待完成")}

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
            return early_fail or {
                "parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                "msg": "离线已完成，但115网盘里还没搜到文件，请稍后重试"}

        res = self._offline_finish(info_hash, pickcode, name,
                                   title=title, label=label, allow_search=False, t0=t0)
        if res.get("url") or not early_fail:
            return res
        return early_fail

    # ========== 搜索 ==========
    def searchContent(self, key, quick=False, pg="1"):
        page = _safe_int(pg, 1)
        keyword = _to_text(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self.search_limit, "total": 0}

        seen = set()
        out = []
        has_next = False
        # 分页格式：/search/KEY/2（Wayback 存档已确认）；页码拼在整条路径后面
        bases = [
            "%s/search/%s&type=&parent=ce" % (self.host, quote(keyword, safe="")),
        ]
        if self.enable_uncensored:
            bases.append(
                "%s/uncensored/search/%s&type=0&parent=uc"
                % (self.host, quote(keyword, safe=""))
            )

        for base in bases:
            u = base if page <= 1 else "%s/%d" % (base, page)
            try:
                text = self._get_html(u)
            except Exception:
                continue
            has_next = has_next or self._has_next_page(text, page)
            for it in self._parse_movie_boxes(text):
                vid = _to_text(it.get("vod_id"))
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                out.append(it)

        return {
            "list": out,
            "page": page,
            "pagecount": page + 1 if has_next else page,
            "limit": len(out) or self.search_limit,
            "total": len(out),
        }

    # ========== 播放 ==========
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
        # 留痕：只要 App 调过 playerContent 就一定有这行（详情页简介首行能看到）
        self._set_off_last("收到播放请求：%s" % _to_text(vid)[:50])

        # 二分实验：只劫持 115 离线入口，其它播放源一律不碰
        if self.offline_test_mp4 and (vid.startswith(OFF_PREFIX_115)
                                      or vid.startswith("115off:")
                                      or vid.startswith("jav_movie115_")):
            return self._offline_test_result()

        # 115 离线：http://115off/<base64(磁力|json)> → 提交离线 → 取播放直链
        if vid.startswith(OFF_PREFIX_115):
            magnet, title, label = _off_id_decode(vid[len(OFF_PREFIX_115):])
            if not magnet:
                return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                        "msg": "磁力解码失败"}
            return self._play_offline_safe(magnet, title, label)

        if vid.startswith("115off:"):
            return self._play_offline_safe(vid[len("115off:"):].strip())

        # 女优列表的「115离线」源：先取该片磁力，再提交到 115
        if vid.startswith("jav_movie115_"):
            mid = vid[len("jav_movie115_"):].split("?")[0].split("#")[0]
            try:
                magnets = self._magnets_of(mid)
            except Exception:
                magnets = []
            for i, g in enumerate(magnets):
                m = _normalize_magnet(g.get("magnet"))
                if m:
                    return self._play_offline_safe(m, self._title_of(mid),
                                                   self._magnet_label(g, i, ""))
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {},
                    "msg": "该片没有可用磁力，无法115离线"}

        if vid.startswith("magnet:"):
            m = _normalize_magnet(vid)
            return {
                "parse": 0,
                "jx": 0,
                "playUrl": "",
                "url": m or vid,
                "header": {"User-Agent": self.ua, "Accept": "*/*"},
            }

        # 兜底：女优头像 → 详情播放列表里的“影片”，取该片磁力播放
        if vid.startswith("jav_movie_"):
            for g in self._magnets_of(vid[len("jav_movie_"):]):
                m = _normalize_magnet(g.get("magnet"))
                if m:
                    return {
                        "parse": 0,
                        "jx": 0,
                        "playUrl": "",
                        "url": m,
                        "header": {"User-Agent": self.ua, "Accept": "*/*"},
                    }

        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": "",
            "header": {},
        }

    def localProxy(self, param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        if not isinstance(param, dict):
            param = {}
        # 播放页的成功提示字幕（playerContent 的 subs 指到这里）
        if _to_text(param.get("k")) == "offnote":
            body = self._offline_srt(param.get("v") or "")
            return [200, "application/x-subrip", body.encode("utf-8"), {}]
        return [404, "text/plain", b"Not Found", {}]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = _to_text(url).lower()
        if u.startswith("magnet:"):
            return True
        # 115 离线占位地址：交 playerContent 换成真实直链，别当网页去嗅探
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
        return None

    def _headers(self, extra=None):
        h = dict(LIST_HEADERS)
        h["Referer"] = self.host + "/"
        if self.cookie:
            h["Cookie"] = self.cookie
        # 站点「已有磁力 / 全部影片」开关，默认全部影片
        if self.existmag and "existmag=" not in (h.get("Cookie") or ""):
            prefix = (h["Cookie"] + "; ") if h.get("Cookie") else ""
            h["Cookie"] = prefix + "existmag=" + self.existmag
        if extra:
            h.update(extra)
        return h

    @staticmethod
    def _is_age_gate(text):
        if not text:
            return False
        # 任一标识命中即视为年龄墙（站点改文案/改属性顺序时仍能识别）
        if "我已經成年" not in text and "ageVerify" not in text:
            return False
        # 年龄墙是整页弹窗；正常页面即使残留同名节点也必带影片内容
        return "movie-box" not in text

    def _pass_age_verify(self, resp, url, headers=None):
        """年龄验证是一个 POST 表单（name=Submit value=確認），自动提交通过"""
        if not requests or self.s is None:
            return False
        targets = []
        final = _to_text(getattr(resp, "url", ""))
        if final:
            targets.append(final)
        if url and url not in targets:
            targets.append(url)
        base = self._headers(headers)
        for t in targets:
            try:
                r = self.s.post(t, data={"Submit": "確認"}, headers=base,
                                timeout=self.timeout, verify=self.verify,
                                allow_redirects=True)
                r.encoding = "utf-8"
                body = r.text or ""
                if body and not self._is_age_gate(body):
                    return True
            except Exception:
                continue
        return False

    def _get_html(self, url, headers=None, _age=True):
        if not requests or self.s is None:
            raise RuntimeError("requests 不可用")
        last_err = None
        for attempt in range(HTTP_RETRY + 1):
            if attempt:
                time.sleep(HTTP_RETRY_DELAY * attempt)
            try:
                r = self.s.get(url, headers=self._headers(headers),
                               timeout=self.timeout, verify=self.verify)
            except Exception as e:
                last_err = e
                continue
            # 临时性错误码重试；重试用尽后仍返回正文，交给上层解析
            if r.status_code in HTTP_RETRY_STATUS and attempt < HTTP_RETRY:
                continue
            r.encoding = "utf-8"
            text = r.text or ""
            if _age and self._is_age_gate(text) and self._pass_age_verify(r, url, headers):
                return self._get_html(url, headers=headers, _age=False)
            return text
        if last_err is not None:
            raise last_err
        return ""