#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# 版本: 1.0.4  (2026-11-10)
# 更新简介:
#   v1.0.4 (2026-11-10)
#     - 直连域名: 写入 missav.fans / missav.media (抓取/详情/播放均无需代理)
#     - 代理优先: 有代理先走 missav.ws; 代理不可用或 ws 失败时自动切换直连域名
#     - 详情播放: 兼容 surrit.mrstcdn.store 与 packer 页, 播放地址优先 mrstcdn (直连可播)
#     - 播放头 Referer/Origin 跟随当前活动域名, 不再写死 missav.ws
#   v1.0.3 (2026-11-10)
#     - 分类末尾新增: 韩国直播 (klive → /cn/klive)、中国直播 (clive → /cn/clive)
#     - banned_slugs 加入 klive/clive 与页脚工具页 (contact/ads/terms/...),
#       防止导航/页尾链接被解析成伪影片条目
#     - 视频编号须含数字: 筛选空结果时回退正则不再误抓 contact/ads 等页脚链接
#   v1.0.2 (2026-11-10)
#     - 缓存上限: _cat_cache/_vid_cache 超过 512 条按最旧淘汰, 防长期运行内存增长
#     - 线程隔离: 服务模式 get_spider 改为线程本地实例, 避免多线程共用 opener/cookiejar
#     - 安全提示: 启动横幅与首页注明监听 0.0.0.0 (局域网可达)
#     - 非法筛选值统一: height/cup/age/debut/sort/filters 不在合法集合时按 all 忽略
#       (原 age=abc 返回默认、height=999 返回空, 现统一为忽略)
#   v1.0.1 (2026-11-10)
#     - 女优筛选与网页对齐: sort 增加 debut(出道)
#     - 女优 age 取值改为网页真实值: <20→0-20, >60→60-99 (原值为无效参数)
#     - 女优 debut 年份下限 2008→2000, 与网页 27 档一致
#   v1.0.0 (2026-11-10)
#     - 首个版本化发布; 文件由 MissAV.py 更名为 MissAV1.py
#     - 代理: 支持 ext 配置 {"proxy": "..."}; 自动探测列表含 127.0.0.1 与 192.168.1.8:7144
#     - resolve_play_url: 解析失败不再写入缓存, 避免瞬时错误导致 120 秒持续 503/黑屏
#     - serve 横幅: 缓存时长与聚合页数改为动态输出, 与 --cache-mins / --pages 实际值一致
#     - 服务器模式 (ysp-live 式 M3U): /all.m3u /cat/ /v/ /health, 静态导出 --static
#
# 约定: 以后每次更新递增版本号并在此追加一条更新简介 (最新在最上)

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

class Spider(SpiderBase):
    # 直连域名: 抓取/详情/播放全直连, 无需代理
    DIRECT_HOSTS = ["https://missav.fans", "https://missav.media"]
    # 代理优先时使用的主站 (本网络常需代理; 失败自动切 DIRECT_HOSTS)
    PROXY_HOST = "https://missav.ws"

    def __init__(self):
        super(Spider, self).__init__()
        self.primaryHost = self.PROXY_HOST
        self.fallbackHost = self.DIRECT_HOSTS[0]
        self.baseHost = self.primaryHost
        self._proxy_ok = False
        self._prefer_direct = False

        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "TG群: @tvshare23"
        self.brandDirector = "蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.categoryRoutes = {
            "chinese_subtitle": "/dm278/cn/chinese-subtitle",
            "new": "/dm539/cn/new",
            "release": "/dm635/cn/release",
            "uncensored_leak": "/dm817/cn/uncensored-leak",
            "today_hot": "/dm301/cn/today-hot",
            "weekly_hot": "/dm170/cn/weekly-hot",
            "monthly_hot": "/dm273/cn/monthly-hot",
            "actresses": "/cn/actresses",
            "actresses_ranking": "/cn/actresses/ranking",
            "genres": "/cn/genres",
            "makers": "/cn/makers",
            "vr": "/cn/genres/VR",
            "fc2": "/dm597/cn/fc2",
            "heyzo": "/dm2208642/cn/heyzo",
            "tokyohot": "/dm42/cn/tokyohot",
            "1pondo": "/dm5199603/cn/1pondo",
            "caribbeancom": "/dm7704788/cn/caribbeancom",
            "caribbeancompr": "/dm91887/cn/caribbeancompr",
            "10musume": "/dm7208981/cn/10musume",
            "pacopacomama": "/dm3600557/cn/pacopacomama",
            "gachinco": "/dm150/cn/gachinco",
            "siro": "/dm36/cn/siro",
            "luxu": "/dm34/cn/luxu",
            "gana": "/dm34/cn/gana",
            "scute": "/dm38/cn/scute",
            "maan": "/dm1004/cn/maan",
            "ara": "/dm34/cn/ara",
            "naughty4610": "/dm33/cn/naughty4610",
            "naughty0930": "/dm37/cn/naughty0930",
            "madou": "/dm63/cn/madou",
            "twav": "/dm31/cn/twav",
            "furuke": "/dm15/cn/furuke",
            "marriedslash": "/dm37/cn/marriedslash",
            "xxxav": "/dm42/cn/xxxav",
            "klive": "/cn/klive",
            "clive": "/cn/clive"
        }

        self.color_palette = [
            ("1e3a8a", "60a5fa"), ("14532d", "4ade80"), ("701a75", "f472b6"),
            ("7c2d12", "fb923c"), ("1f2937", "38bdf8"), ("312e81", "818cf8"),
            ("831843", "fb7185"), ("064e3b", "34d399"), ("3b0764", "c084fc")
        ]

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self._build_opener()

    # 局域网/本机常见代理端口, 依次探测, 通了就用 (抓取 missav.ws 需要; surrit CDN 播放不需要)
    PROXY_PROBE = [
        ("127.0.0.1", 7890), ("127.0.0.1", 7897),
        ("127.0.0.1", 10808), ("127.0.0.1", 10809),
        ("192.168.1.8", 7144),
    ]

    def _build_opener(self):
        # 直连 opener (fans/media 不需要代理)
        direct_handlers = [
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        ]
        self._opener_direct = urllib.request.build_opener(*direct_handlers)

        # 代理优先: ext 配置 {"proxy": "..."} > 探测列表
        cfg_proxy = ""
        try:
            if isinstance(self.options, dict):
                cfg_proxy = str(self.options.get("proxy") or "").strip()
        except Exception:
            pass
        proxy_url = cfg_proxy
        if not proxy_url:
            import socket
            for host, port in self.PROXY_PROBE:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.3)
                    if s.connect_ex((host, port)) == 0:
                        proxy_url = "http://%s:%d" % (host, port)
                        s.close()
                        break
                    s.close()
                except Exception:
                    pass

        if proxy_url:
            self._proxy_ok = True
            proxy_handlers = [
                urllib.request.HTTPCookieProcessor(self.cj),
                urllib.request.HTTPSHandler(context=self.ctx),
                urllib.request.ProxyHandler({
                    'http': proxy_url, 'https': proxy_url
                })
            ]
            self._opener_proxy = urllib.request.build_opener(*proxy_handlers)
            self.opener = self._opener_proxy
            if not self._prefer_direct:
                self.primaryHost = self.PROXY_HOST
                self.baseHost = self.primaryHost
        else:
            self._proxy_ok = False
            self._opener_proxy = None
            self.opener = self._opener_direct
            self.primaryHost = self.DIRECT_HOSTS[0]
            self.baseHost = self.primaryHost
            self._prefer_direct = True

    def _opener_for(self, host):
        if (not self._prefer_direct) and self._proxy_ok and host == self.PROXY_HOST:
            return getattr(self, "_opener_proxy", None) or self.opener
        return getattr(self, "_opener_direct", None) or self.opener

    def _host_candidates(self):
        """候选主机: 代理优先 → 直连域名; 已切直连后不再回头试 ws。"""
        if self._prefer_direct or not self._proxy_ok:
            hosts = list(self.DIRECT_HOSTS)
            cur = self.baseHost
            if cur in hosts:
                hosts.remove(cur)
                hosts.insert(0, cur)
            elif cur:
                hosts.insert(0, cur)
            # 去重保序
            seen = set()
            out = []
            for h in hosts:
                if h and h not in seen:
                    seen.add(h)
                    out.append(h)
            return out
        return [self.PROXY_HOST] + [h for h in self.DIRECT_HOSTS if h != self.PROXY_HOST]

    @staticmethod
    def _swap_host(url, new_host):
        p = urllib.parse.urlparse(url)
        np = urllib.parse.urlparse(new_host)
        return urllib.parse.urlunparse(
            (np.scheme or "https", np.netloc, p.path, p.params, p.query, p.fragment)
        )

    def _switch_host(self, host):
        self.primaryHost = host
        self.baseHost = host
        if host in self.DIRECT_HOSTS:
            # 直连已通, 不再回头试 missav.ws (省一次必败请求)
            self._prefer_direct = True

    @staticmethod
    def _fetch_ok(res):
        text = res.get("text") or ""
        return (res.get("code") == 200 and len(text) >= 2000
                and "Just a moment" not in text)

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        # ext 里带了代理配置则重建 opener 使其生效 (并恢复代理优先)
        try:
            if isinstance(self.options, dict) and self.options.get("proxy"):
                self._prefer_direct = False
                self._build_opener()
        except Exception:
            pass
        return True

    def getName(self):
        return "蝴蝶影视·MissAV"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def _clean_pic_url(self, raw_pic, fallback_id=""):
        p = str(raw_pic or "").strip()
        if p.startswith("//"):
            p = "https:" + p
        elif p.startswith("/"):
            p = urllib.parse.urljoin(self.baseHost, p)
        
        if not p and fallback_id:
            p = "https://fourhoi.com/%s/cover-t.jpg" % fallback_id
            
        if not p:
            return "https://dummyimage.com/640x360/1e293b/ffffff.png&text=NO_COVER"
            
        # 彻底移除 @Referer= 与 @User-Agent= 等 iOS 无法识别的语法糖后缀
        if "@Referer=" in p:
            p = p.split("@Referer=")[0]
        return p

    def _raw_fetch(self, target_url, host_ctx=""):
        cur_host = host_ctx if host_ctx else self.baseHost
        headers = {
            "User-Agent": self._ua,
            "Referer": cur_host + "/",
            "Origin": cur_host,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        opener = self._opener_for(cur_host)
        try:
            req = urllib.request.Request(target_url, headers=headers)
            with opener.open(req, timeout=8) as resp:
                raw = resp.read()
                enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                text = raw.decode("utf-8", errors="ignore")
                return {"code": resp.getcode(), "text": text, "final_url": resp.geturl()}
        except urllib.error.HTTPError as e:
            return {"code": e.code, "text": ""}
        except Exception:
            return {"code": -1, "text": ""}

    def _fetch(self, target_url):
        real_url = target_url
        if real_url.startswith("//"):
            real_url = "https:" + real_url
        elif real_url.startswith("/"):
            real_url = self.baseHost + real_url

        res = {"code": -1, "text": ""}
        for host in self._host_candidates():
            url = self._swap_host(real_url, host)
            res = self._raw_fetch(url, host)
            if self._fetch_ok(res):
                if host != self.baseHost:
                    self._switch_host(host)
                return res
        return res

    def homeContent(self, filter):
        classes = [
            {"type_name": "中文字幕", "type_id": "chinese_subtitle"},
            {"type_name": "最近更新", "type_id": "new"},
            {"type_name": "新作上市", "type_id": "release"},
            {"type_name": "无码流出", "type_id": "uncensored_leak"},
            {"type_name": "女优一览", "type_id": "actresses"},
            {"type_name": "女优排行", "type_id": "actresses_ranking"},
            {"type_name": "全部类型", "type_id": "genres"},
            {"type_name": "全部发行商", "type_id": "makers"},
            {"type_name": "VR 专区", "type_id": "vr"},
            {"type_name": "今日热门", "type_id": "today_hot"},
            {"type_name": "本周热门", "type_id": "weekly_hot"},
            {"type_name": "本月热门", "type_id": "monthly_hot"},
            {"type_name": "FC2", "type_id": "fc2"},
            {"type_name": "HEYZO", "type_id": "heyzo"},
            {"type_name": "东京热", "type_id": "tokyohot"},
            {"type_name": "一本道", "type_id": "1pondo"},
            {"type_name": "加勒比", "type_id": "caribbeancom"},
            {"type_name": "加勒比PR", "type_id": "caribbeancompr"},
            {"type_name": "天然素人", "type_id": "10musume"},
            {"type_name": "熟女俱乐部", "type_id": "pacopacomama"},
            {"type_name": "Gachinco", "type_id": "gachinco"},
            {"type_name": "SIRO", "type_id": "siro"},
            {"type_name": "LUXU", "type_id": "luxu"},
            {"type_name": "GANA", "type_id": "gana"},
            {"type_name": "S-CUTE", "type_id": "scute"},
            {"type_name": "PRESTIGE", "type_id": "maan"},
            {"type_name": "ARA", "type_id": "ara"},
            {"type_name": "顽皮4610", "type_id": "naughty4610"},
            {"type_name": "顽皮0930", "type_id": "naughty0930"},
            {"type_name": "麻豆传媒", "type_id": "madou"},
            {"type_name": "TWAV", "type_id": "twav"},
            {"type_name": "Furuke", "type_id": "furuke"},
            {"type_name": "人妻斩", "type_id": "marriedslash"},
            {"type_name": "XXX-AV", "type_id": "xxxav"},
            {"type_name": "韩国直播", "type_id": "klive"},
            {"type_name": "中国直播", "type_id": "clive"}
        ]

        result = {"class": classes}

        if filter:
            filter_sort = {
                "key": "sort",
                "name": "排序",
                "init": "default",
                "value": [
                    {"n": "默认排序", "v": "default"},
                    {"n": "发行日期", "v": "released_at"},
                    {"n": "最近更新", "v": "published_at"},
                    {"n": "收藏最多", "v": "saved"},
                    {"n": "今日浏览", "v": "today_views"},
                    {"n": "本周浏览", "v": "weekly_views"},
                    {"n": "本月浏览", "v": "monthly_views"},
                    {"n": "总浏览数", "v": "views"}
                ]
            }
            filter_type = {
                "key": "filters",
                "name": "过滤",
                "init": "all",
                "value": [
                    {"n": "所有", "v": "all"},
                    {"n": "单人作品", "v": "individual"},
                    {"n": "多人作品", "v": "multiple"},
                    {"n": "中文字幕", "v": "chinese-subtitle"}
                ]
            }

            height_ranges = [
                "131-135", "136-140", "141-145", "146-150", "151-155",
                "156-160", "161-165", "166-170", "171-175", "176-180",
                "181-185", "186-190"
            ]
            filter_actress_height = {
                "key": "height",
                "name": "身高",
                "init": "all",
                "value": [{"n": "选择身高", "v": "all"}] + [{"n": "%scm" % r, "v": r} for r in height_ranges]
            }

            cups = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q"]
            filter_actress_cup = {
                "key": "cup",
                "name": "罩杯",
                "init": "all",
                "value": [{"n": "选择罩杯", "v": "all"}] + [{"n": "%s 罩杯" % c, "v": c} for c in cups]
            }

            filter_actress_age = {
                "key": "age",
                "name": "年龄",
                "init": "all",
                "value": [
                    {"n": "选择年龄", "v": "all"},
                    {"n": "< 20", "v": "0-20"},
                    {"n": "20 - 30", "v": "20-30"},
                    {"n": "30 - 40", "v": "30-40"},
                    {"n": "40 - 50", "v": "40-50"},
                    {"n": "50 - 60", "v": "50-60"},
                    {"n": "> 60", "v": "60-99"}
                ]
            }

            years = [str(y) for y in range(2026, 1999, -1)]
            filter_actress_debut = {
                "key": "debut",
                "name": "出道年份",
                "init": "all",
                "value": [{"n": "选择出道年份", "v": "all"}] + [{"n": "%s 以前" % y, "v": y} for y in years]
            }

            filter_actress_sort = {
                "key": "sort",
                "name": "排序",
                "init": "default",
                "value": [
                    {"n": "默认排序", "v": "default"},
                    {"n": "影片最多", "v": "videos"},
                    {"n": "出道", "v": "debut"}
                ]
            }

            filters_dict = {}
            for item in classes:
                cid = item["type_id"]
                if cid == "actresses":
                    filters_dict[cid] = [
                        filter_actress_sort,
                        filter_actress_height,
                        filter_actress_cup,
                        filter_actress_age,
                        filter_actress_debut
                    ]
                elif cid not in ("actresses_ranking", "genres", "makers"):
                    filters_dict[cid] = [filter_sort, filter_type]

            result["filters"] = filters_dict

        return result

    def homeVideoContent(self):
        res = self._fetch(self.primaryHost + "/dm247/cn")
        vod_list = self._parse_cards(res.get("text", ""), "video")
        return {"list": vod_list[:16]}

    def _parse_cards(self, html, mode="video"):
        if not html:
            return []

        body = html
        if "</nav>" in body:
            body = body.split("</nav>", 1)[1]
        elif "</header>" in body:
            body = body.split("</header>", 1)[1]

        vod_list = []
        seen_ids = set()

        if mode in ("actress", "actress_ranking"):
            is_ranking = (mode == "actress_ranking")

            chunks = re.findall(r'(<div[^>]*>\s*<a[^>]+href=["\'][^"\']*/actresses/[^"\']+["\'][^>]*>[\s\S]*?</div>\s*</div>)', body)
            if not chunks:
                chunks = re.findall(r'(<a[^>]+href=["\'][^"\']*/actresses/[^"\']+["\'][^>]*>[\s\S]*?</a>\s*<div[\s\S]*?</div>)', body)

            for block in chunks:
                href_m = re.search(r'href=["\']([^"\']*/actresses/[^"\']+)["\']', block)
                if not href_m:
                    continue
                href = href_m.group(1).strip()
                if href.endswith("/actresses/ranking") or "actresses/ranking" in href:
                    continue
                if href in seen_ids:
                    continue
                seen_ids.add(href)

                pic_m = re.search(r'(?:data-src|data-original|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', block, re.I)
                raw_pic = pic_m.group(1).strip() if pic_m else ""
                clean_pic = self._clean_pic_url(raw_pic)

                alt_m = re.search(r'alt=["\']([^"\']+)["\']', block)
                title = alt_m.group(1).strip() if alt_m else ""

                if not title:
                    txt_cands = re.findall(r'>([^<]+)<', block)
                    for tc in txt_cands:
                        t = tc.strip()
                        if t and not any(k in t for k in ("影片", "条", "條", "部", "出道", "年", "第", "名", "Ranking")):
                            if len(t) >= 2 and not t.isdigit():
                                title = t
                                break
                if not title:
                    title = "女优"

                title = html_lib.unescape(title)

                if is_ranking:
                    rank_m = re.search(r'(第\s*\d+\s*名)', block)
                    sub_desc = rank_m.group(1).replace(" ", "") if rank_m else ""
                    remarks_text = ("蝴蝶影视 · %s" % sub_desc) if sub_desc else "蝴蝶影视"
                else:
                    count_m = re.search(r'(\d+)\s*(?:条影片|條影片|部影片|部)', block)
                    debut_m = re.search(r'(\d{4})\s*(?:出道|年出道)', block)
                    meta_arr = []
                    if count_m:
                        meta_arr.append("%s部" % count_m.group(1))
                    if debut_m:
                        meta_arr.append("%s出道" % debut_m.group(1))
                    sub_desc = " · ".join(meta_arr) if meta_arr else ""
                    remarks_text = ("蝴蝶影视 · %s" % sub_desc) if sub_desc else "蝴蝶影视"

                display_name = ("%s\n%s" % (title, sub_desc)) if sub_desc else title

                vod_list.append({
                    "vod_id": "folder@" + (href if href.startswith("http") else urllib.parse.urljoin(self.baseHost, href)),
                    "vod_name": display_name,
                    "vod_pic": clean_pic,
                    "vod_remarks": remarks_text,
                    "vod_tag": "folder",
                    "style": {"type": "oval", "ratio": 1.0}
                })
            return vod_list

        if mode in ("genres", "makers"):
            target_key = "genres" if mode == "genres" else "makers"
            cell_pattern = r'(<div>\s*<a[^>]+href=["\'][^"\']*/' + target_key + r'/[^"\']+["\'][^>]*>[\s\S]*?</div>)'
            cells = re.findall(cell_pattern, body)

            for idx, cell in enumerate(cells):
                href_m = re.search(r'href=["\']([^"\']*/' + target_key + r'/[^"\']+)["\']', cell)
                if not href_m:
                    continue
                clean_href = href_m.group(1).strip()
                if clean_href in seen_ids or clean_href.endswith(("/" + target_key, "/" + target_key + "/")):
                    continue
                seen_ids.add(clean_href)

                title_m = re.search(r'<a[^>]+class=["\'][^"\']*text-nord13[^"\']*["\'][^>]*>([\s\S]*?)</a>', cell)
                if not title_m:
                    title_m = re.search(r'<a[^>]+href=["\'][^"\']*/' + target_key + r'/[^"\']+["\'][^>]*>([\s\S]*?)</a>', cell)
                raw_title = title_m.group(1).strip() if title_m else ""
                title = html_lib.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()

                if not title:
                    continue

                count_m = re.search(r'(\d+)\s*(?:条影片|條影片|部影片|部)', cell)
                remarks = ("蝴蝶影视 · %s部" % count_m.group(1)) if count_m else "蝴蝶影视"

                first_char = title[0].strip().upper()
                bg_color, fg_color = self.color_palette[idx % len(self.color_palette)]
                card_pic = "https://dummyimage.com/640x360/%s/%s.png&text=%s" % (
                    bg_color, fg_color, quote(first_char)
                )

                vod_list.append({
                    "vod_id": "folder@" + (clean_href if clean_href.startswith("http") else urllib.parse.urljoin(self.baseHost, clean_href)),
                    "vod_name": title,
                    "vod_pic": card_pic,
                    "vod_remarks": remarks,
                    "vod_tag": "folder",
                    "style": {"type": "rect", "ratio": 1.78}
                })
            return vod_list

        card_chunks = []
        if 'class="relative group' in body:
            card_chunks = body.split('class="relative group')[1:]
        elif 'class="thumbnail' in body:
            card_chunks = body.split('class="thumbnail')[1:]
        else:
            card_chunks = re.findall(r'(<a[^>]+href=["\'][^"\']*(?:missav\.[^"\']+|/[^"\']+)["\'][^>]*>[\s\S]*?</a>)', body)

        banned_slugs = {
            "chinese-subtitle", "new", "release", "uncensored-leak", "today-hot",
            "weekly-hot", "monthly-hot", "genres", "actresses", "makers", "series", "tags",
            "vip", "saved", "playlists", "history", "login", "register", "siro", "luxu", "gana",
            "klive", "clive",
            # 页脚/工具页: 筛选空结果时回退正则易误抓
            "contact", "ads", "terms", "upload", "articles", "about", "privacy",
            "dmca", "disclaimer", "cookie", "sitemap", "search", "faq", "help",
            "password", "forget", "profile", "settings",
        }

        for ch in card_chunks:
            href_m = re.search(r'href=["\']([^"\']*/(?:cn|dm\d+/cn)/([A-Za-z0-9_-]+))["\']', ch)
            if not href_m:
                continue
            full_href, dvd_id = href_m.groups()
            dvd_low = dvd_id.lower()

            if dvd_low in banned_slugs or dvd_low in seen_ids or len(dvd_id) < 3:
                continue
            # 影片编号几乎必含数字; 页脚链接 (contact/ads/terms/...) 无数字
            if not any(c.isdigit() for c in dvd_id):
                continue
            seen_ids.add(dvd_low)

            title = ""
            name_div_m = re.search(r'<div[^>]*class=["\'][^"\']*(?:title|my-2|font-semibold)[^"\']*["\'][^>]*>([\s\S]*?)</div>', ch)
            if name_div_m:
                cand_title = re.sub(r'<[^>]+>', '', name_div_m.group(1)).strip()
                if cand_title and cand_title.lower() != dvd_low and len(cand_title) >= len(dvd_id):
                    title = cand_title

            if not title:
                alt_m = re.search(r'alt=["\']([^"\']+)["\']', ch)
                if alt_m:
                    cand_alt = alt_m.group(1).strip()
                    if cand_alt and cand_alt.lower() != dvd_low and len(cand_alt) >= len(dvd_id):
                        title = cand_alt

            if not title:
                txt_cands = re.findall(r'>([^<]{4,120})<', ch)
                for tc in txt_cands:
                    t_str = tc.strip()
                    if t_str and t_str.lower() != dvd_low and len(t_str) > len(dvd_id):
                        if not any(k in t_str for k in ("item.", "HD", "FHD", "4K", ":", "条影片")):
                            title = t_str
                            break

            if not title:
                title = dvd_id.upper()

            title = html_lib.unescape(title)

            pic_m = re.search(r'(?:data-src|data-original|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', ch, re.I)
            raw_pic = ""
            if pic_m and "item.dvd_id" not in pic_m.group(1):
                raw_pic = pic_m.group(1).strip()

            clean_pic = self._clean_pic_url(raw_pic, dvd_id)

            dur_m = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', ch)
            dur = ("蝴蝶影视 · %s" % dur_m.group(1)) if dur_m else "蝴蝶影视"

            pack_id = "%s@@%s" % (dvd_id, full_href)

            vod_list.append({
                "vod_id": pack_id,
                "vod_name": title,
                "vod_pic": clean_pic,
                "vod_remarks": dur,
                "style": {"type": "rect", "ratio": 1.78}
            })

        return vod_list

    def categoryContent(self, tid, pg, filter, extend):
        slug = str(tid).strip()
        page = int(pg) if str(pg).isdigit() else 1

        if slug.startswith("folder@"):
            target_url = slug.replace("folder@", "")
            parse_mode = "video"
        else:
            route_path = self.categoryRoutes.get(slug, self.categoryRoutes["chinese_subtitle"])
            target_url = "%s%s" % (self.primaryHost, route_path)
            if slug == "actresses":
                parse_mode = "actress"
            elif slug == "actresses_ranking":
                parse_mode = "actress_ranking"
            elif slug in ("genres", "makers"):
                parse_mode = slug
            else:
                parse_mode = "video"

        query_parts = []
        if page > 1:
            query_parts.append("page=%d" % page)

        if isinstance(extend, dict):
            if parse_mode == "actress":
                for param_k, allowed in (
                    ("height", _ACTRESS_HEIGHTS),
                    ("cup", _ACTRESS_CUPS),
                    ("age", _ACTRESS_AGES),
                    ("debut", _ACTRESS_DEBUTS),
                ):
                    val = extend.get(param_k)
                    # 非法值按 all 忽略, 与 age/height 站点行为差异解耦
                    if val and val != "all" and val in allowed:
                        query_parts.append("%s=%s" % (param_k, quote(val)))

                sort_val = extend.get("sort")
                if sort_val and sort_val != "default" and sort_val in _ACTRESS_SORTS:
                    query_parts.append("sort=%s" % sort_val)

            elif parse_mode == "video":
                active_sort = extend.get("sort", "default")
                if active_sort and active_sort != "default" and active_sort in _VIDEO_SORTS:
                    query_parts.append("sort=%s" % active_sort)

                active_filters = extend.get("filters", "all")
                if active_filters and active_filters != "all" and active_filters in _VIDEO_FILTERS:
                    query_parts.append("filters=%s" % active_filters)

        if query_parts:
            sep = "&" if "?" in target_url else "?"
            target_url = "%s%s%s" % (target_url, sep, "&".join(query_parts))

        res = self._fetch(target_url)
        vod_list = self._parse_cards(res.get("text", ""), parse_mode)

        return {
            "page": page,
            "pagecount": (page + 1) if len(vod_list) >= 12 else page,
            "limit": len(vod_list),
            "total": 999,
            "list": vod_list
        }

    def _extract_surrit_uuid(self, html):
        if not html:
            return ""

        uuid_pat = r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'

        def _clean(u, pos):
            ctx = html[max(0, pos - 40):min(len(html), pos + 80)].lower()
            if any(bad in ctx for bad in ("user_uuid", "sample", "preview", "recombee", "thumbnail")):
                return ""
            return u

        # 直连域名详情页: surrit.mrstcdn.store (含 JS 转义 \/ 与 packer 拼接)
        for pat in (
            r'surrit\.mrstcdn\.store(?:\\/|/)' + uuid_pat,
            r'surrit\\+\.mrstcdn\\+\.store(?:\\/|/)' + uuid_pat,
        ):
            m = re.search(pat, html, re.I)
            if m:
                u = _clean(m.group(1), m.start(1))
                if u:
                    return u

        # packer keys 含完整 uuid 分段时直接拼
        pk = re.search(r"\}\('([\s\S]*?)',\s*16,\s*16,\s*'([^']+)'\.split\('\|'\)", html)
        if pk and "mrstcdn" in pk.group(2):
            keys = pk.group(2).split("|")
            joined = "|".join(keys)
            # 顺序: 0c1dcef7|e14b|4176|aacb|6a0a57dacff5 形态
            m = re.search(
                r'([a-f0-9]{8})\|([a-f0-9]{4})\|([a-f0-9]{4})\|([a-f0-9]{4})\|([a-f0-9]{12})',
                joined, re.I
            )
            if m:
                u = "%s-%s-%s-%s-%s" % m.groups()
                if "sample" not in pk.group(1).lower():
                    return u

        hls_match = re.search(
            r'hls\.loadSource\(["\']https?://[^/]+/' + uuid_pat + r'/playlist\.m3u8["\']\)', html)
        if hls_match:
            u = _clean(hls_match.group(1), hls_match.start(1))
            if u:
                return u

        urls_block = re.search(r'urls:\s*\[\s*["\']([^"\']+)["\']', html)
        if urls_block:
            target_link = urls_block.group(1)
            if "sample" not in target_link and "preview" not in target_link:
                u_m = re.search(uuid_pat, target_link)
                if u_m:
                    return u_m.group(1)

        scripts = re.findall(r'<script[^>]*>([\s\S]*?)</script>', html)
        for sc in scripts:
            if any(k in sc for k in ("surrit.com", "sixyik.com", "mrstcdn.store")) and "sample" not in sc:
                uuids = re.findall(uuid_pat, sc)
                for u in uuids:
                    u_pos = sc.find(u)
                    surround = sc[max(0, u_pos - 40):min(len(sc), u_pos + 60)]
                    if not any(bad in surround for bad in ("user_uuid", "sample", "preview", "thumbnail", "recombee")):
                        return u

        cands = re.findall(
            r'https?://(?:surrit\.com|sixyik\.com|surrit\.mrstcdn\.store)/' + uuid_pat + r'/(?:playlist\.m3u8)?',
            html)
        for c in cands:
            c_pos = html.find(c)
            if "sample" not in html[max(0, c_pos - 30):min(len(html), c_pos + 60)]:
                return c

        return ""

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)

        if "@@" in raw_id:
            vid, origin_href = raw_id.split("@@", 1)
        else:
            vid = raw_id.replace("vod@", "").strip("/")
            origin_href = "%s/dm247/cn/%s" % (self.primaryHost, vid)

        cand_urls = []
        if origin_href.startswith("http"):
            cand_urls.append(origin_href)
        seen_u = set(cand_urls)
        for h in self._host_candidates():
            for path in ("/dm247/cn/%s" % vid, "/cn/%s" % vid):
                u = h + path
                if u not in seen_u:
                    seen_u.add(u)
                    cand_urls.append(u)

        html = ""
        for u in cand_urls:
            res = self._fetch(u)
            if res.get("code") == 200 and len(res.get("text", "")) > 3000:
                html = res.get("text", "")
                # 记录实际打开的站点, 供播放头 Referer 使用
                try:
                    final = res.get("final_url") or u
                    fh = urllib.parse.urlparse(final)
                    if fh.netloc:
                        self._switch_host("%s://%s" % (fh.scheme or "https", fh.netloc))
                except Exception:
                    pass
                break

        title_m = re.search(r'<title>(.*?)</title>', html, re.I)
        vod_name = vid.upper()
        if title_m:
            t_raw = title_m.group(1).split(" | ")[0].split(" - ")[0].strip()
            if t_raw:
                vod_name = t_raw

        actress_matches = re.findall(r'<a[^>]+href=["\'][^"\']*/actresses/[^"\']+["\'][^>]*>([\s\S]*?)</a>', html)
        clean_actresses = []
        for a in actress_matches:
            name = re.sub(r'<[^>]+>', '', a).strip()
            if name and not any(k in name for k in ("排行", "Ranking", "一览", "SEP", "OCT", "NOV", "202")):
                if name not in clean_actresses:
                    clean_actresses.append(name)

        actor_text = ", ".join(clean_actresses) if clean_actresses else self.brandActor

        desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', html)
        desc = desc_m.group(1).strip() if desc_m else "蝴蝶影视高清聚合，全网同步更新。"
        vod_content = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.tgGroup, desc)
        escaped_desc = vod_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        surrit_uuid = self._extract_surrit_uuid(html)

        play_froms = []
        play_urls = []

        if surrit_uuid:
            # mrstcdn 直连可播; surrit.com 在部分网络直连 403, 作备线
            real_m3u8 = "https://surrit.mrstcdn.store/%s/playlist.m3u8" % surrit_uuid
            play_froms.append("蝴蝶正片专线")
            play_urls.append("超清原画正片$%s" % real_m3u8)
            play_froms.append("蝴蝶备线")
            play_urls.append("原画备线$https://surrit.com/%s/playlist.m3u8" % surrit_uuid)

        pic = "https://fourhoi.com/%s/cover-n.jpg" % vid

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": html_lib.unescape(vod_name),
                "vod_pic": pic,
                "vod_actor": actor_text,
                "vod_director": self.brandDirector,
                "vod_remarks": "蝴蝶影视",
                "vod_content": escaped_desc,
                "vod_play_from": "$$$".join(play_froms) if play_froms else "蝴蝶专线",
                "vod_play_url": "$$$".join(play_urls) if play_urls else ("超清原画正片$" + cand_urls[0])
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id).strip()
        base = self.baseHost or self.primaryHost or self.PROXY_HOST
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": {
                "User-Agent": self._ua,
                "Referer": base + "/",
                "Origin": base,
                "Accept": "*/*",
                "Connection": "keep-alive"
            }
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        search_url = "%s/search/%s" % (self.primaryHost + "/dm247/cn", quote(key))
        if page > 1:
            search_url = "%s?page=%d" % (search_url, page)

        res = self._fetch(search_url)
        vod_list = self._parse_cards(res.get("text", ""), "video")

        return {
            "page": page,
            "pagecount": (page + 1) if len(vod_list) >= 12 else page,
            "limit": len(vod_list),
            "total": 999,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Disabled"]

    def destroy(self):
        self.options = {}

# ================================================================ 服务器模式 (ysp-live 式)
#   python3 MissAV.py [port]            # 默认 19530, 起 HTTP 服务
#   python3 MissAV.py --static -o missav.m3u [--pages 5]
#
#   /all.m3u              聚合订阅: 第 1 块 (1--pages 页), 条目 -> 本机 /v/<id>.m3u8
#   /all-2.m3u            第 2 块 (6-10 页); 也支持 ?chunk=2 (参数优先)
#   /cat/<type_id>.m3u    单个分类, 同样支持 -N / ?chunk=
#   /v/<id>.m3u8          实时解析详情页拿 surrit m3u8, 服务端跟 variant 并转绝对地址
#   /health               健康检查
#
# 说明: Spider 类原封不动, TVBox 照常用; 直接运行时才起服务。

import time as _time
import threading as _threading
import argparse as _argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin as _urljoin

SRV_PAGES = 5        # 每块抓几页 (--pages), /all.m3u 用
SRV_CAT_PAGES = 10     # /cat/ 单分类默认页数
SRV_CACHE_MINS = 30  # 分类列表缓存分钟数
SRV_TIMEOUT = 15     # m3u8 下发超时秒数
SRV_VID_CACHE_SECS = 120  # 解析出的播放地址缓存秒数
SRV_CACHE_MAX = 512  # _cat_cache/_vid_cache 最大条数, 超出按最旧淘汰

# 合法筛选值 (与网页 option 对齐); 非法值在 categoryContent 中按 all 忽略
_VIDEO_SORTS = frozenset((
    "default", "released_at", "published_at", "saved",
    "today_views", "weekly_views", "monthly_views", "views",
))
_VIDEO_FILTERS = frozenset(("all", "individual", "multiple", "chinese-subtitle"))
_ACTRESS_SORTS = frozenset(("default", "videos", "debut"))
_ACTRESS_HEIGHTS = frozenset(
    ["all"] + ["%d-%d" % (a, a + 4) for a in range(131, 191, 5)]
)  # 131-135 .. 186-190
_ACTRESS_CUPS = frozenset(["all"] + list("ABCDEFGHIJKLMNOPQ"))
_ACTRESS_AGES = frozenset((
    "all", "0-20", "20-30", "30-40", "40-50", "50-60", "60-99",
))
_ACTRESS_DEBUTS = frozenset(["all"] + [str(y) for y in range(2000, 2027)])

# 播放请求头: 写入 M3U 条目属性, 供支持该写法的播放器在直连 CDN 分片时携带
# (surrit CDN 验 Referer/Origin/UA; 服务端抓取 m3u8 时同样携带这些头)
# 默认值仅作兜底; 运行时用 _site_ref_origin() 跟随当前活动域名 (fans/media/ws)。
M3U_REFERER = "https://missav.fans/"
M3U_ORIGIN = "https://missav.fans"

_spider_local = _threading.local()  # 每线程独立 Spider, 避免共享 opener/cookiejar 竞态
_cat_cache = {}   # (tid, chunk) -> (ts, [(vod_id, vod_name, vod_pic)])
_vid_cache = {}   # raw_id -> (ts, play_url)
_cache_lock = _threading.Lock()


def _log(msg):
    print(msg, flush=True)


def get_spider():
    """线程本地 Spider: 网络句柄不跨线程共享; 列表/播放缓存仍是全局+锁。"""
    sp = getattr(_spider_local, "spider", None)
    if sp is None:
        sp = Spider()
        sp.init("")
        _spider_local.spider = sp
    return sp


def _cache_put_locked(cache, key, item):
    """写入缓存并限制最大条数 (调用方需已持有 _cache_lock)。item=(ts, value)。"""
    cache[key] = item
    if len(cache) > SRV_CACHE_MAX:
        # 按时间戳淘汰最旧, 且不淘汰刚写入的 key
        drop_n = len(cache) - SRV_CACHE_MAX
        for k in sorted(cache.keys(), key=lambda k: cache[k][0]):
            if k == key:
                continue
            del cache[k]
            drop_n -= 1
            if drop_n <= 0:
                break


def srv_cats():
    return get_spider().homeContent(False).get("class", [])


def _m3u_title(name):
    return re.sub(r"\s+", " ", str(name or "")).strip().replace(",", "，")


def _site_ref_origin():
    """当前活动站点的 Referer / Origin, 播放头与 M3U 属性共用。"""
    sp = get_spider()
    base = sp.baseHost or sp.primaryHost or M3U_ORIGIN
    if not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/") + "/", base.rstrip("/")


def _m3u_header_attrs():
    sp = get_spider()
    ref, origin = _site_ref_origin()
    return ('http-user-agent="%s" http-referer="%s" http-header="Origin=%s"'
            % (sp._ua, ref, origin))


def cached_category(tid, chunk=1, pages=None):
    sp = get_spider()
    pages = SRV_PAGES if pages is None else pages
    chunk = max(1, int(chunk))
    start = (chunk - 1) * pages + 1   # 第 chunk 块: start..end 页, 块之间不重叠
    end = chunk * pages
    now = _time.time()
    key = (tid, chunk, pages)
    with _cache_lock:
        hit = _cat_cache.get(key)
        if hit and now - hit[0] < SRV_CACHE_MINS * 60:
            return hit[1]
    videos = []
    _log("[%s] 开始抓取 chunk%d (%d页)..." % (tid, chunk, pages))
    for pg in range(start, end + 1):
        try:
            data = sp.categoryContent(tid, pg, {}, {})
        except Exception as e:
            _log("  [%s] 第%d页 列表抓取失败: %s" % (tid, pg, e))
            break
        vids = data.get("list", []) if isinstance(data, dict) else []
        if not vids:
            break
        for v in vids:
            vid = str(v.get("vod_id", "") or "")
            if not vid or vid.startswith("folder@"):
                continue  # 女优/类型/发行商等文件夹条目不可直接播放, 跳过
            videos.append((vid, v.get("vod_name", ""), v.get("vod_pic", "")))
    _log("[%s] 抓取完成, 共 %d 条" % (tid, len(videos)))
    with _cache_lock:
        _cache_put_locked(_cat_cache, key, (now, videos))
    return videos


def resolve_play_url(raw_id):
    """详情页 -> 可播放地址。拿不到(或不是媒体地址)返回 ''。"""
    sp = get_spider()
    now = _time.time()
    with _cache_lock:
        hit = _vid_cache.get(raw_id)
        if hit and now - hit[0] < SRV_VID_CACHE_SECS:
            return hit[1]
    url = ""
    try:
        d = sp.detailContent(raw_id)
        lst = d.get("list", []) if isinstance(d, dict) else []
        if lst:
            play = str(lst[0].get("vod_play_url", "") or "")
            url = (play.split("$", 1)[1] if "$" in play else play).strip()
            if not sp.isVideoFormat(url):
                url = ""
    except Exception:
        url = ""
    if url:
        # 只缓存成功结果; 失败不缓存, 避免瞬时网络错误导致后续 2 分钟持续 503/黑屏
        with _cache_lock:
            _cache_put_locked(_vid_cache, raw_id, (now, url))
    return url


def _parse_hls_attr_list(raw):
    """解析 HLS #EXT-X-STREAM-INF / #EXT-X-I-FRAME-STREAM-INF 属性。"""
    attrs = {}
    for m in re.finditer(r'([A-Z0-9-]+)=((?:"[^"]*")|(?:[^,]*))', raw or ''):
        key = m.group(1)
        value = m.group(2).strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        attrs[key] = value
    return attrs


def _hls_variant_score(attrs):
    """清晰度选择规则：优先 1080P；若无 1080P，则优先最高分辨率，再以最高码率决胜。"""
    resolution = str(attrs.get('RESOLUTION', '') or '')
    width = height = 0
    m = re.match(r'^(\d+)x(\d+)$', resolution)
    if m:
        width, height = int(m.group(1)), int(m.group(2))

    try:
        bandwidth = int(float(str(attrs.get('BANDWIDTH', '0')).strip() or 0))
    except Exception:
        bandwidth = 0
    try:
        average_bandwidth = int(float(str(attrs.get('AVERAGE-BANDWIDTH', '0')).strip() or 0))
    except Exception:
        average_bandwidth = 0

    # 1080P（高度在 1000~1199）优先；同为 1080P 时选择最高码率。
    is_1080 = 1 if 1000 <= height < 1200 else 0
    pixels = width * height
    effective_bw = max(bandwidth, average_bandwidth)

    # 规则：
    # 1. 有 1080P 时优先 1080P；
    # 2. 没有 1080P 时选择最高分辨率；
    # 3. 同分辨率下选择最高码率。
    return (is_1080, pixels, effective_bw, height, width)


def _select_hls_variant(text, final_url):
    """从 Master M3U8 中选择最佳视频 Variant，并返回绝对 URL。"""
    lines = text.splitlines()
    variants = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.upper().startswith('#EXT-X-STREAM-INF:'):
            continue

        attrs = _parse_hls_attr_list(stripped.split(':', 1)[1])
        uri = ''

        # EXT-X-STREAM-INF 的 URI 按 HLS 规范通常位于下一条非注释行。
        for j in range(i + 1, len(lines)):
            candidate = lines[j].strip()
            if not candidate:
                continue
            if candidate.startswith('#'):
                continue
            uri = candidate
            break

        if not uri:
            continue

        variants.append({
            'attrs': attrs,
            'url': _urljoin(final_url, uri),
        })

    if not variants:
        return None

    variants.sort(key=lambda x: _hls_variant_score(x['attrs']), reverse=True)
    best = variants[0]
    attrs = best['attrs']
    resolution = attrs.get('RESOLUTION', 'unknown')
    bandwidth = attrs.get('BANDWIDTH') or attrs.get('AVERAGE-BANDWIDTH') or '0'
    _log('[HLS] 选择 Variant: %s, BANDWIDTH=%s, URL=%s' % (
        resolution, bandwidth, best['url']))
    return best['url']


def _rewrite_hls_media_playlist(text, final_url):
    """把 Media Playlist 中的分片、KEY、MAP、SESSION-KEY 等 URI 全部转成绝对地址。"""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue

        if stripped.startswith('#'):
            # HLS 标签中的 URI="..."，例如 EXT-X-KEY / EXT-X-MAP / EXT-X-MEDIA。
            line = re.sub(
                r'URI="([^"]+)"',
                lambda m: 'URI="%s"' % _urljoin(final_url, m.group(1)),
                line
            )
            out.append(line)
        else:
            out.append(_urljoin(final_url, stripped))
    return '\n'.join(out) + '\n'


def fetch_abs_playlist(url, depth=0):
    """
    抓远程 HLS M3U8，并兼容 APTV：

    1. 如果是 Master M3U8：优先选择 1080P；没有 1080P 时选择最高分辨率，
       同分辨率选择最高 BANDWIDTH / AVERAGE-BANDWIDTH。
    2. 如果是 Media Playlist：原样保留 HLS 标签，并把 TS/fMP4/KEY/MAP 等 URI
       转成绝对地址，避免 APTV 因相对路径导致黑屏或只有部分分片。
    3. 最多跟随 3 层 Variant，兼容某些 CDN 的多级 Master M3U8。
    """
    sp = get_spider()
    ref, origin = _site_ref_origin()
    req = urllib.request.Request(url, headers={
        'User-Agent': sp._ua,
        'Referer': ref,
        'Origin': origin,
        'Accept': 'application/vnd.apple.mpegurl,application/x-mpegURL,*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
    })

    with sp.opener.open(req, timeout=SRV_TIMEOUT) as r:
        raw = r.read()
        enc = getattr(r, 'headers', {}).get('Content-Encoding', '')
        if raw.startswith(b'\x1f\x8b') or enc == 'gzip':
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        elif enc == 'deflate':
            try:
                raw = zlib.decompress(raw)
            except Exception:
                try:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                except Exception:
                    pass
        text = raw.decode('utf-8', 'replace')
        final = r.geturl()

    # Master Playlist：主动选择最佳清晰度。
    if depth < 3 and '#EXT-X-STREAM-INF' in text.upper():
        selected = _select_hls_variant(text, final)
        if selected:
            return fetch_abs_playlist(selected, depth + 1)

    # 已经是 Media Playlist：所有分片/KEY/MAP 地址绝对化。
    return _rewrite_hls_media_playlist(text, final)


def _v_url(host, vod_id):
    return "http://%s/v/%s.m3u8" % (host, quote(vod_id, safe=""))


def build_cat_m3u(tid, host, chunk=1, pages=None):
    cats = {c["type_id"]: c["type_name"] for c in srv_cats()}
    if tid not in cats:
        return None
    videos = cached_category(tid, chunk=chunk, pages=pages)
    cname = cats[tid]
    hattrs = _m3u_header_attrs()
    lines = ["#EXTM3U",
             "#EXT-X-APTV-PREVIEW: FALSE",
             "#EXT-X-APTV-LATENCY: FALSE",
             "#EXT-X-APTV-LOGO: FALSE"]
    for vid, name, pic in videos:
        logo = ' tvg-logo="%s"' % pic if pic else ""
        lines.append('#EXTINF:-1 group-title="%s"%s %s,%s' % (cname, logo, hattrs, _m3u_title(name)))
        lines.append(_v_url(host, vid))
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    server_version = "missav-m3u/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _redirect(self, url):
        try:
            self.send_response(302)
            self.send_header("Location", url)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _chunk_of(self, path_num, qs):
        """取块号: ?chunk=N 参数优先, 其次路径里的 -N 后缀, 都没有则为 1。"""
        try:
            q = int(qs.get("chunk", [""])[0])
            if q >= 1:
                return q
        except (ValueError, TypeError):
            pass
        if path_num:
            return max(1, int(path_num))
        return 1

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path, qs = u.path, urllib.parse.parse_qs(u.query)
        host = self.headers.get("Host", "localhost:19530")
        if path in ("/", "/index.html"):
            self._send(200, _index_page(), "text/html; charset=utf-8")
            return
        if path == "/health":
            self._send(200, "ok")
            return
        m = re.match(r"^/all(?:-(\d+))?\.m3u$", path)
        if m:
            chunk = self._chunk_of(m.group(1), qs)
            cats = srv_cats()
            # 并发预热分类缓存
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda c: cached_category(c["type_id"], chunk=chunk), cats))
            names = {c["type_id"]: c["type_name"] for c in cats}
            hattrs = _m3u_header_attrs()
            lines = ["#EXTM3U",
                     "#EXT-X-APTV-PREVIEW: FALSE",
                     "#EXT-X-APTV-LATENCY: FALSE",
                     "#EXT-X-APTV-LOGO: FALSE"]
            for c in cats:
                for vid, name, pic in cached_category(c["type_id"], chunk=chunk):
                    logo = ' tvg-logo="%s"' % pic if pic else ""
                    lines.append('#EXTINF:-1 group-title="%s"%s %s,%s'
                                 % (names[c["type_id"]], logo, hattrs, _m3u_title(name)))
                    lines.append(_v_url(host, vid))
            self._send(200, "\n".join(lines) + "\n", "application/vnd.apple.mpegurl")
            return
        m = re.match(r"^/cat/([A-Za-z0-9_]+)(?:-(\d+))?\.m3u$", path)
        if m:
            body = build_cat_m3u(m.group(1), host, chunk=self._chunk_of(m.group(2), qs),
                                 pages=SRV_CAT_PAGES)
            if body is None:
                self._send(404, "未知分类\n")
            else:
                self._send(200, body, "application/vnd.apple.mpegurl")
            return
        m = re.match(r"^/v/(.+)\.m3u8$", path)
        if m:
            raw_id = unquote(m.group(1))
            url = resolve_play_url(raw_id)
            if not url:
                self._send(503, "视频暂无可播放地址, 请稍后重试\n")
                return
            if ".m3u8" in url.lower():
                try:
                    self._send(200, fetch_abs_playlist(url), "application/vnd.apple.mpegurl")
                except Exception:
                    self._redirect(url)  # 服务端下发失败则 302 让播放器直连
            else:
                self._redirect(url)
            return
        self._send(404, "not found\n")


def _index_page():
    items = []
    for c in srv_cats():
        items.append('<li><a href="/cat/%s.m3u">%s</a> <span>/cat/%s.m3u</span></li>'
                     % (c["type_id"], c["type_name"], c["type_id"]))
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>MissAV M3U 服务</title>"
            "<style>body{font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:720px;"
            "margin:0 auto;padding:20px;}li{margin:6px 0;}span{color:#888;font-size:12px;"
            "margin-left:8px;}code{background:#f4f4f4;padding:1px 5px;border-radius:3px;}</style></head><body>"
            "<h2>MissAV M3U 服务 (%d 个分类)</h2>"
            "<p>聚合订阅: <a href='/all.m3u'>/all.m3u</a> (第 1 块, 1–%d 页) · "
            "<a href='/all-2.m3u'>/all-2.m3u</a> (第 2 块, %d–%d 页) · "
            "也支持 <code>?chunk=N</code> 参数 (参数优先)。块之间不重叠, "
            "超出范围的块返回空列表。</p>"
            "<p>条目指向本机 <code>/v/&lt;id&gt;.m3u8</code>, 服务端实时解析详情页拿 surrit 播放地址并转绝对地址, "
            "播放器直连 CDN 拉分片。女优 / 类型 / 发行商为文件夹导航, 在 M3U 中无可播放条目。</p>"
            "<p>服务监听 <code>0.0.0.0</code>, 局域网内设备可直接订阅; 仅在可信网络下运行。</p>"
            "<p>分类列表缓存 %d 分钟 (按块缓存)。</p>"
            "<ul>%s</ul></body></html>"
            % (len(items), SRV_PAGES, SRV_PAGES + 1, SRV_PAGES * 2,
               SRV_CACHE_MINS, "".join(items)))


def _prewarm():
    """启动后后台预热 chunk1, 首个 /all.m3u 直接命中缓存, 不用现抓等超时。"""
    try:
        cats = srv_cats()
        _log("后台预热开始, %d 个分类..." % len(cats))
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda c: cached_category(c["type_id"], chunk=1), cats))
        _log("后台预热完成")
    except Exception as e:
        _log("后台预热失败: %s" % e)


def serve(port):
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    ncats = len(srv_cats())
    print("=" * 64, flush=True)
    print("MissAV M3U 服务启动: %d 个分类, 端口 %d" % (ncats, port), flush=True)
    print("  监听: 0.0.0.0:%d （局域网内可访问, 仅限可信网络）" % port, flush=True)
    print("  聚合订阅: http://127.0.0.1:%d/all.m3u （默认前 %d 页）" % (port, SRV_PAGES), flush=True)
    print("  分页: http://127.0.0.1:%d/all.m3u?chunk=2 （chunk=2=%d-%d页, 以此类推）"
          % (port, SRV_PAGES + 1, SRV_PAGES * 2), flush=True)
    print("  分类: http://127.0.0.1:%d/cat/<分类ID>.m3u （默认10页）  健康检查: /health" % port, flush=True)
    print("  缓存: 分类列表%d分钟, 播放地址%d秒" % (SRV_CACHE_MINS, SRV_VID_CACHE_SECS), flush=True)
    print("  分类列表:")
    for c in srv_cats():
        print("    %s = %s" % (c["type_id"], c["type_name"]), flush=True)
    print("=" * 64, flush=True)
    import threading
    threading.Thread(target=_prewarm, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def build_m3u_static(cats=None, pages=5, threads=8, max_videos=0):
    """静态模式: 一次性生成 M3U, 条目为直连 surrit 地址。"""
    sp = get_spider()
    allcats = srv_cats()
    if cats:
        want = {c.strip() for c in cats if c.strip()}
        sel = [c for c in allcats if c["type_id"] in want or c["type_name"] in want]
    else:
        sel = allcats
    if not sel:
        raise ValueError("没有匹配的分类")
    videos = []  # (cat_name, vod_id, name, pic)
    for c in sel:
        for pg in range(1, pages + 1):
            try:
                data = sp.categoryContent(c["type_id"], pg, {}, {})
            except Exception as e:
                _log("  [%s] 第%d页 列表抓取失败: %s" % (c["type_name"], pg, e))
                break
            vids = data.get("list", []) if isinstance(data, dict) else []
            if not vids:
                break
            for v in vids:
                vid = str(v.get("vod_id", "") or "")
                if vid and not vid.startswith("folder@"):
                    videos.append((c["type_name"], vid, v.get("vod_name", ""), v.get("vod_pic", "")))
            _log("  [%s] 第%d页 %d 条" % (c["type_name"], pg, len(vids)))
            if max_videos and len(videos) >= max_videos:
                break
        if max_videos and len(videos) >= max_videos:
            break
    videos = videos[:max_videos] if max_videos else videos
    _log("共 %d 条视频, 开始解析播放地址 (线程=%d)..." % (len(videos), threads))

    results = [None] * len(videos)
    lock = _threading.Lock()
    done = [0]

    def _worker(idx):
        cat_name, vid, name, pic = videos[idx]
        url = resolve_play_url(vid)
        if url:
            results[idx] = (cat_name, name, pic, url)
        with lock:
            done[0] += 1
            if done[0] % 20 == 0 or done[0] == len(videos):
                _log("  解析进度 %d/%d" % (done[0], len(videos)))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(_worker, range(len(videos))))

    lines = ["#EXTM3U",
             "#EXT-X-APTV-PREVIEW: FALSE",
             "#EXT-X-APTV-LATENCY: FALSE",
             "#EXT-X-APTV-LOGO: FALSE"]
    ok = 0
    hattrs = _m3u_header_attrs()
    for r in results:
        if not r:
            continue
        cat_name, name, pic, url = r
        ok += 1
        logo = ' tvg-logo="%s"' % pic if pic else ""
        lines.append('#EXTINF:-1 group-title="%s"%s %s,%s' % (cat_name, logo, hattrs, _m3u_title(name)))
        lines.append(url)
    return "\n".join(lines) + "\n", ok, len(videos) - ok


def main(argv=None):
    ap = _argparse.ArgumentParser(description="MissAV -> M3U 服务 (ysp-live 式)")
    ap.add_argument("port", nargs="?", type=int, default=19530, help="监听端口 (默认 19530)")
    ap.add_argument("--static", action="store_true", help="静态模式: 一次性生成 M3U 文件, 不起服务")
    ap.add_argument("-o", "--output", default="missav.m3u", help="静态模式输出文件 (默认 missav.m3u)")
    ap.add_argument("--cats", default="", help="只包含这些分类, 逗号分隔 (type_id 或分类名, 默认全部)")
    ap.add_argument("--pages", type=int, default=5, help="每个分类抓几页 (默认5; 服务模式下为每块页数)")
    ap.add_argument("--threads", type=int, default=8, help="静态模式详情页并发数 (默认8)")
    ap.add_argument("--max", type=int, default=0, help="静态模式最多抓多少条视频 (默认0=不限)")
    ap.add_argument("--cache-mins", type=int, default=10, help="服务模式分类列表缓存分钟数 (默认10)")
    args = ap.parse_args(argv)

    global SRV_PAGES, SRV_CACHE_MINS
    SRV_PAGES = args.pages
    SRV_CACHE_MINS = args.cache_mins

    if args.static:
        _log("MissAV -> 静态 M3U 开始")
        m3u, ok, fail = build_m3u_static(
            cats=[c for c in args.cats.split(",") if c.strip()] or None,
            pages=args.pages, threads=args.threads, max_videos=args.max)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(m3u)
        _log("完成: 成功 %d 条, 失败 %d 条 -> %s" % (ok, fail, args.output))
        return

    serve(args.port)


if __name__ == "__main__":
    main()
