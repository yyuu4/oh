# -*- coding: utf-8 -*-
import re
import json
import time
import html as _html
import warnings
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urljoin

try:
    import requests
except ImportError:
    requests = None

try:
    from urllib3.exceptions import InsecureRequestWarning
    warnings.simplefilter("ignore", InsecureRequestWarning)
except Exception:
    pass


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


_HOST_PROBE_CACHE = {}


def _probe_host(base, use_env, timeout=PROBE_TIMEOUT):
    """探测单个域名。use_env=False 表示不走系统/环境代理（直连）。"""
    if not requests:
        return None
    s = requests.Session()
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


def pick_host(candidates=None):
    """选域名：优先不需要代理的直连，其次按响应时间排序。"""
    cands = [c.rstrip("/") for c in (candidates or HOST_CANDIDATES)]
    key = tuple(cands)
    if key in _HOST_PROBE_CACHE:
        return _HOST_PROBE_CACHE[key]
    if not cands or not requests:
        return None

    best = None
    args = [(u, False) for u in cands] + [(u, True) for u in cands]

    def task(arg):
        base, use_env = arg
        cost = _probe_host(base, use_env)
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

    host = best[2] if best else None
    _HOST_PROBE_CACHE[key] = host
    return host


class Spider:
    def __init__(self):
        self.s = None
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
        self.img_proxy = ""
        self.lang = "zh"
        self.verify = False

        # filters / 默认值缓存
        self._cache_filters = {}
        self._host_locked = False
        self._probed = False

        if requests:
            self.s = requests.Session()
            self.s.headers.update(LIST_HEADERS)

    def getDependence(self):
        return []

    def init(self, extend=""):
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}

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

        # 自动选域名：直连（不走代理）优先，其次按响应时间
        self._ensure_host()

        # 清空缓存
        self._cache_filters = {}

    def _ensure_host(self):
        """探测候选域名并选一个：免代理 > 最快"""
        if self._host_locked or self._probed:
            return
        self._probed = True
        host = pick_host()
        if host:
            self.host = host

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
        seen = set()
        for m in re.finditer(
            r'<a[^>]+class="[^"]*avatar-box[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            text, re.S
        ):
            href = _fix_url(m.group(1), self.host)
            block = m.group(2)
            sid = _extract_id(href)
            name = ""
            nm = re.search(r"<span>([^<]+)</span>", block)
            if nm:
                name = _clean_text(nm.group(1))
            if not sid or not name or sid in seen:
                continue
            seen.add(sid)
            values.append({"n": name, "v": sid})
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

    def _get_default_star(self, index_url):
        """取女优页第一个女优作为默认（复用 _build_star_filters 的结果）"""
        cache_key = "default_star:" + index_url
        if cache_key in self._cache_filters:
            return self._cache_filters[cache_key]
        sid = self._first_filter_value(self._build_star_filters(index_url))
        self._cache_filters[cache_key] = sid
        return sid

    def homeVideoContent(self):
        return {"list": []}

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

        # 有码女优：选女优 → 该女优影片；否则 → 第一个默认女优
        if t == "jav_actress":
            if star_sel:
                return self._star_list(
                    self.host + "/star", next(iter(star_sel)), page, hdr)
            default_sid = self._get_default_star(self.host + "/actresses")
            if default_sid:
                return self._star_list(self.host + "/star", default_sid, page, hdr)
            if page <= 1:
                return self._list_page(self.host + "/", page, hdr)
            return self._list_page(self.host + "/page/%d" % page, page, hdr)

        # 无码女优：选女优 → 该女优影片；否则 → 第一个默认女优
        if t == "jav_uncensored_actress":
            if star_sel:
                return self._star_list(
                    self.host + "/uncensored/star", next(iter(star_sel)), page, hdr)
            default_sid = self._get_default_star(self.host + "/uncensored/actresses")
            if default_sid:
                return self._star_list(
                    self.host + "/uncensored/star", default_sid, page, hdr)
            if page <= 1:
                return self._list_page(self.host + "/uncensored", page, hdr)
            return self._list_page(
                self.host + "/uncensored/page/%d" % page, page, hdr)

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

        # 兼容：如果框架把类别/女优 ID 传到 detailContent，直接返回空
        if vid.startswith(("jav_genre_", "jav_uc_genre_",
                           "jav_star_", "jav_uc_star_")):
            return {"list": []}

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

        magnets = []
        if self.enable_magnet:
            try:
                magnets = self._fetch_magnets(text, vid)
            except Exception:
                magnets = []

        froms, urls = [], []
        if magnets:
            eps = []
            for i, g in enumerate(magnets):
                label = self._magnet_label(g, i, num)
                magnet = g.get("magnet") or ""
                if not magnet:
                    continue
                eps.append("%s$%s" % (label, magnet))
            if eps:
                froms.append("磁力")
                urls.append("#".join(eps))

        # 标题去重：页面 <title> 本身通常已带番号
        vod_name = _to_text(title)
        if num and vod_name:
            if not vod_name.startswith(num):
                vod_name = (num + " " + vod_name).strip()
        elif num:
            vod_name = num

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
        return {"list": [item]}

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
            magnet = am.group(1).replace("&amp;", "&")

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

            size = ""
            sm = re.search(
                r"<td[^>]*>([^<]*?(?:GB|MB|TB|KB)[^<]*?)</td>",
                block, re.I
            )
            if sm:
                size = _clean_text(sm.group(1))

            out.append({
                "name": name,
                "size": size,
                "magnet": magnet,
            })

        def _size_key(g):
            s = g.get("size") or ""
            mm = re.search(r"([\d.]+)\s*(GB|MB|TB|KB)", s, re.I)
            if not mm:
                return 0
            try:
                n = float(mm.group(1))
            except Exception:
                return 0
            unit = mm.group(2).upper()
            mult = {"KB": 1.0 / 1024, "MB": 1.0, "GB": 1024.0, "TB": 1024.0 * 1024}.get(unit, 1.0)
            return n * mult

        out.sort(key=_size_key, reverse=True)
        return out

    @staticmethod
    def _magnet_label(g, i, num):
        raw = _to_text(g.get("name")) or num or ("资源%d" % (i + 1))
        safe = re.sub(r"[$#&\n\r\t]", " ", raw).strip()[:40]
        parts = [safe]
        if g.get("size"):
            parts.append(g["size"])
        return " ".join(parts) or ("资源%d" % (i + 1))

    def _proxy_pic(self, url):
        if not url:
            return ""
        p = (self.img_proxy or "").strip()
        if not p:
            return url
        try:
            return p + quote(url, safe="")
        except Exception:
            return url

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
        urls = [
            "%s/search/%s&type=&parent=ce" % (self.host, quote(keyword)),
        ]
        if self.enable_uncensored:
            urls.append(
                "%s/uncensored/search/%s&type=0&parent=uc" % (self.host, quote(keyword))
            )

        for u in urls:
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
            "limit": self.search_limit,
            "total": len(out),
        }

    # ========== 播放 ==========
    def playerContent(self, flag, ids, vipFlags=None):
        vid = str(ids[0]) if isinstance(ids, (list, tuple)) and ids else str(ids or "")

        if vid.startswith("magnet:"):
            m = _normalize_magnet(vid)
            return {
                "parse": 0,
                "jx": 0,
                "playUrl": "",
                "url": m or vid,
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
        return [404, "text/plain", b"Not Found", {}]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = _to_text(url).lower()
        if u.startswith("magnet:"):
            return True
        u = u.split("?")[0]
        return u.endswith((".mp4", ".m3u8", ".flv", ".mkv", ".ts", ".avi"))

    def action(self, action):
        return {}

    def destroy(self):
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
        return bool(text) and "我已經成年" in text and 'id="ageVerify"' in text

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
        r = self.s.get(url, headers=self._headers(headers),
                       timeout=self.timeout, verify=self.verify)
        r.encoding = "utf-8"
        text = r.text or ""
        if _age and self._is_age_gate(text) and self._pass_age_verify(r, url, headers):
            return self._get_html(url, headers=headers, _age=False)
        return text