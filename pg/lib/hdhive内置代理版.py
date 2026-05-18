# -*- coding: utf-8 -*-
import sys
import json
import time
import re
import requests
from urllib.parse import quote, unquote

sys.path.append('..')

try:
    from base.spider import Spider
except Exception:
    class Spider:
        pass


class Spider(Spider):

    def getName(self):
        return "HDHive+TMDB"

    def init(self, extend=""):
        """
        HDHive + TMDB for OK影视PG

        ext 推荐 JSON：

        {
          "api_key": "HDHive API Key 或 App Secret",
          "access_token": "HDHive User Access Token，可选",
          "api_base": "https://hdhive.com/api/open",

          "tmdb_api_key": "你的 TMDB API Key",
          "tmdb_api_base": "https://api.themoviedb.org/3",
          "tmdb_language": "zh-CN",
          "tmdb_region": "CN",
          "tmdb_image_base": "https://image.tmdb.org/t/p/w500",

          "default_type": "movie"
        }

        HDHive:
        - GET  /api/open/resources/:type/:tmdb_id
        - GET  /api/open/shares/:slug
        - POST /api/open/resources/unlock

        TMDB:
        - GET /discover/movie
        - GET /discover/tv
        - GET /movie/popular
        - GET /tv/popular
        - GET /search/multi
        - GET /movie/{id}
        - GET /tv/{id}
        """

        self.timeout = 15

        # HDHive
        self.api_base = "https://hdhive.com/api/open"
        self.api_key = ""
        self.access_token = ""

        # TMDB
        self.tmdb_api_key = ""
        self.tmdb_api_base = "https://api.themoviedb.org/3"
        self.tmdb_language = "zh-CN"
        self.tmdb_region = "CN"
        self.tmdb_image_base = "https://image.tmdb.org/t/p/w500"
        self.tmdb_include_adult = False

        # 搜索纯数字时默认类型
        self.default_type = "movie"

        # 关键词映射，可选
        self.keyword_map = {}

        # 冷却控制
        self.cooldown_until = 0
        self.last_error = ""

        if extend:
            extend = extend.strip()

            if extend.startswith("{"):
                try:
                    ext = json.loads(extend)

                    self.api_key = str(ext.get("api_key", "")).strip()
                    self.access_token = str(ext.get("access_token", "")).strip()
                    self.api_base = str(ext.get("api_base", self.api_base)).strip().rstrip("/")

                    self.tmdb_api_key = str(ext.get("tmdb_api_key", "")).strip()
                    self.tmdb_api_base = str(ext.get("tmdb_api_base", self.tmdb_api_base)).strip().rstrip("/")
                    self.tmdb_language = str(ext.get("tmdb_language", self.tmdb_language)).strip() or "zh-CN"
                    self.tmdb_region = str(ext.get("tmdb_region", self.tmdb_region)).strip() or "CN"
                    self.tmdb_image_base = str(ext.get("tmdb_image_base", self.tmdb_image_base)).strip().rstrip("/")
                    self.tmdb_include_adult = bool(ext.get("tmdb_include_adult", False))

                    self.default_type = str(ext.get("default_type", self.default_type)).strip() or "movie"

                    km = ext.get("keyword_map", {})
                    if isinstance(km, dict):
                        self.keyword_map = km

                except Exception as e:
                    print("HDHive init json ext error:", e)
                    self.api_key = extend

            elif "|" in extend:
                parts = extend.split("|")
                self.api_key = parts[0].strip()
                if len(parts) > 1:
                    self.access_token = parts[1].strip()

            else:
                self.api_key = extend.strip()

        self.headers = self.build_hdhive_headers()

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ==================================================
    # 基础工具
    # ==================================================

    def safe_str(self, value):
        if value is None:
            return ""
        return str(value)

    def now(self):
        return int(time.time())

    def pick(self, data, keys, default=""):
        if not isinstance(data, dict):
            return default

        for key in keys:
            value = data.get(key)
            if value is not None and value != "":
                return value

        return default

    def make_error_video(self, title, desc=""):
        return {
            "vod_id": "error",
            "vod_name": title,
            "vod_pic": "",
            "vod_remarks": desc
        }

    def build_hdhive_headers(self):
        headers = {
            "User-Agent": "Mozilla/5.0 OKPG-HDHive-TMDB-Spider/1.0",
            "Accept": "application/json,text/plain,*/*",
            "Content-Type": "application/json;charset=utf-8",
            "X-API-Key": self.api_key
        }

        if self.access_token:
            headers["Authorization"] = "Bearer " + self.access_token

        return headers

    def format_api_error(self, result):
        if not isinstance(result, dict):
            return "unknown error"

        code = result.get("code", "")
        message = result.get("message", "")
        desc = result.get("description", "")
        retry = result.get("retry_after_seconds", "")
        scope = result.get("limit_scope_label", result.get("limit_scope", ""))

        text = ""

        if code:
            text += "[" + str(code) + "] "

        if message:
            text += str(message)

        if desc:
            text += " " + str(desc)

        if scope:
            text += " 限制对象:" + str(scope)

        if retry:
            text += " 等待:" + str(retry) + "秒"

        return text.strip()

    # ==================================================
    # HDHive 请求
    # ==================================================

    def hdhive_fetch(self, path_or_url, params=None, method="GET", data=None):
        """
        HDHive OpenAPI 通用请求。
        处理：
        - X-API-Key
        - Authorization Bearer
        - 429 Retry-After
        """

        current = self.now()

        if self.cooldown_until > current:
            wait_seconds = self.cooldown_until - current
            return {
                "success": False,
                "code": "LOCAL_COOLDOWN",
                "message": "本地冷却中",
                "description": "HDHive API 当前处于冷却期，请稍后再试",
                "retry_after_seconds": wait_seconds
            }

        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            if not path_or_url.startswith("/"):
                path_or_url = "/" + path_or_url
            url = self.api_base + path_or_url

        try:
            headers = self.build_hdhive_headers()

            if method.upper() == "POST":
                resp = requests.post(url, headers=headers, params=params, json=data, timeout=self.timeout)
            elif method.upper() == "PATCH":
                resp = requests.patch(url, headers=headers, params=params, json=data, timeout=self.timeout)
            elif method.upper() == "DELETE":
                resp = requests.delete(url, headers=headers, params=params, json=data, timeout=self.timeout)
            else:
                resp = requests.get(url, headers=headers, params=params, timeout=self.timeout)

            try:
                result = resp.json()
            except Exception:
                result = {
                    "success": False,
                    "code": str(resp.status_code),
                    "message": "non-json response",
                    "raw": resp.text
                }

            result["_http_status"] = resp.status_code
            result["_headers"] = {
                "Retry-After": resp.headers.get("Retry-After", ""),
                "X-OpenAPI-User-Daily-Limit": resp.headers.get("X-OpenAPI-User-Daily-Limit", ""),
                "X-OpenAPI-User-Daily-Remaining": resp.headers.get("X-OpenAPI-User-Daily-Remaining", ""),
                "X-OpenAPI-App-Daily-Limit": resp.headers.get("X-OpenAPI-App-Daily-Limit", ""),
                "X-OpenAPI-App-Daily-Remaining": resp.headers.get("X-OpenAPI-App-Daily-Remaining", "")
            }

            if resp.status_code == 429:
                retry_after = 0

                try:
                    retry_after = int(resp.headers.get("Retry-After", "0"))
                except Exception:
                    retry_after = 0

                if not retry_after:
                    try:
                        retry_after = int(result.get("retry_after_seconds", 0))
                    except Exception:
                        retry_after = 0

                if retry_after > 0:
                    self.cooldown_until = self.now() + retry_after

            if resp.status_code >= 400:
                self.last_error = self.format_api_error(result)
                print("HDHive API Error:", self.last_error)

            return result

        except Exception as e:
            print("HDHive request error:", e)
            return {
                "success": False,
                "code": "REQUEST_EXCEPTION",
                "message": str(e)
            }

    def hdhive_data(self, result):
        if isinstance(result, dict):
            return result.get("data")
        return None

    def hdhive_list(self, result):
        if isinstance(result, list):
            return result

        if not isinstance(result, dict):
            return []

        data = result.get("data")

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ["list", "items", "results", "records", "shares", "resources"]:
                if isinstance(data.get(key), list):
                    return data.get(key, [])

        for key in ["list", "items", "results", "records", "shares", "resources"]:
            if isinstance(result.get(key), list):
                return result.get(key, [])

        return []

    def api_ping(self):
        return self.hdhive_fetch("/ping")

    def api_resources(self, media_type, tmdb_id):
        """
        GET /api/open/resources/:type/:tmdb_id
        """
        return self.hdhive_fetch("/resources/%s/%s" % (media_type, tmdb_id))

    def api_share_detail(self, slug):
        """
        GET /api/open/shares/:slug
        """
        return self.hdhive_fetch("/shares/%s" % slug)

    def api_unlock(self, slug):
        """
        POST /api/open/resources/unlock
        """
        return self.hdhive_fetch(
            "/resources/unlock",
            method="POST",
            data={
                "slug": slug
            }
        )

    # ==================================================
    # TMDB 请求
    # ==================================================

    def tmdb_fetch(self, path, params=None):
        if not self.tmdb_api_key:
            return {}

        if params is None:
            params = {}

        params["api_key"] = self.tmdb_api_key

        if "language" not in params:
            params["language"] = self.tmdb_language

        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = self.tmdb_api_base + path

        try:
            resp = requests.get(
                url,
                params=params,
                headers={
                    "User-Agent": "Mozilla/5.0 OKPG-HDHive-TMDB-Spider/1.0",
                    "Accept": "application/json,text/plain,*/*"
                },
                timeout=self.timeout
            )

            try:
                return resp.json()
            except Exception:
                return {}

        except Exception as e:
            print("TMDB request error:", e)
            return {}

    def tmdb_img(self, poster_path):
        if not poster_path:
            return ""
        if str(poster_path).startswith("http"):
            return str(poster_path)
        return self.tmdb_image_base + str(poster_path)

    def tmdb_format_item(self, item, media_type):
        """
        把 TMDB 的 movie/tv 条目格式化为 OK影视卡片。
        vod_id 设计为：
        tmdb|movie|550
        tmdb|tv|1399
        """

        tmdb_id = self.pick(item, ["id"], "")

        if media_type == "movie":
            title = self.pick(item, ["title", "name", "original_title"], "")
            date = self.pick(item, ["release_date"], "")
        else:
            title = self.pick(item, ["name", "title", "original_name"], "")
            date = self.pick(item, ["first_air_date"], "")

        year = ""
        if isinstance(date, str) and len(date) >= 4:
            year = date[:4]

        poster = self.tmdb_img(self.pick(item, ["poster_path"], ""))

        vote = self.pick(item, ["vote_average"], "")
        remarks = []

        if year:
            remarks.append(year)

        if vote not in ["", None]:
            remarks.append("TMDB %.1f" % float(vote))

        return {
            "vod_id": "tmdb|%s|%s" % (media_type, tmdb_id),
            "vod_name": self.safe_str(title),
            "vod_pic": poster,
            "vod_remarks": " · ".join(remarks)
        }

    def tmdb_detail(self, media_type, tmdb_id):
        """
        TMDB 详情，用于补充海报、简介、演员等。
        """

        append = "credits,videos,external_ids"

        if media_type == "movie":
            path = "/movie/%s" % tmdb_id
        else:
            path = "/tv/%s" % tmdb_id

        return self.tmdb_fetch(
            path,
            params={
                "append_to_response": append,
                "language": self.tmdb_language
            }
        )

    def tmdb_search_keyword(self, keyword):
        """
        使用 TMDB search/multi 搜索普通片名。
        返回候选列表。
        """

        keyword = str(keyword).strip()
        if not keyword or not self.tmdb_api_key:
            return []

        data = self.tmdb_fetch(
            "/search/multi",
            params={
                "query": keyword,
                "page": 1,
                "include_adult": "true" if self.tmdb_include_adult else "false",
                "language": self.tmdb_language
            }
        )

        results = data.get("results", []) if isinstance(data, dict) else []
        videos = []

        for item in results:
            media_type = item.get("media_type", "")

            if media_type not in ["movie", "tv"]:
                continue

            videos.append(self.tmdb_format_item(item, media_type))

        return videos

    def tmdb_discover(self, tid, page, extend=None):
        """
        根据 OK影视分类 tid 获取 TMDB 列表。
        """

        if extend is None:
            extend = {}

        params = {
            "page": page,
            "language": self.tmdb_language,
            "region": self.tmdb_region,
            "include_adult": "true" if self.tmdb_include_adult else "false"
        }

        # 基础筛选
        if isinstance(extend, dict):
            year = str(extend.get("year", "")).strip()
            genre = str(extend.get("genre", "")).strip()
            sort_by = str(extend.get("sort_by", "")).strip()

            if genre:
                params["with_genres"] = genre

            if sort_by:
                params["sort_by"] = sort_by

            if year:
                # movie 用 primary_release_year，tv 用 first_air_date_year
                if tid.startswith("tv") or tid in ["popular_tv", "top_tv", "anime_tv"]:
                    params["first_air_date_year"] = year
                else:
                    params["primary_release_year"] = year

        media_type = "movie"
        path = "/discover/movie"

        if tid == "movie":
            media_type = "movie"
            path = "/discover/movie"
            params.setdefault("sort_by", "popularity.desc")

        elif tid == "tv":
            media_type = "tv"
            path = "/discover/tv"
            params.setdefault("sort_by", "popularity.desc")

        elif tid == "popular_movie":
            media_type = "movie"
            path = "/movie/popular"

        elif tid == "popular_tv":
            media_type = "tv"
            path = "/tv/popular"

        elif tid == "now_playing":
            media_type = "movie"
            path = "/movie/now_playing"

        elif tid == "top_movie":
            media_type = "movie"
            path = "/movie/top_rated"

        elif tid == "top_tv":
            media_type = "tv"
            path = "/tv/top_rated"

        elif tid == "anime_movie":
            media_type = "movie"
            path = "/discover/movie"
            params["with_genres"] = "16"
            params.setdefault("sort_by", "popularity.desc")

        elif tid == "anime_tv":
            media_type = "tv"
            path = "/discover/tv"
            params["with_genres"] = "16"
            params.setdefault("sort_by", "popularity.desc")

        elif tid == "documentary_movie":
            media_type = "movie"
            path = "/discover/movie"
            params["with_genres"] = "99"
            params.setdefault("sort_by", "popularity.desc")

        else:
            media_type = "movie"
            path = "/discover/movie"
            params.setdefault("sort_by", "popularity.desc")

        data = self.tmdb_fetch(path, params=params)

        results = data.get("results", []) if isinstance(data, dict) else []
        total_pages = data.get("total_pages", 1) if isinstance(data, dict) else 1
        total_results = data.get("total_results", len(results)) if isinstance(data, dict) else len(results)

        videos = []

        for item in results:
            videos.append(self.tmdb_format_item(item, media_type))

        return {
            "page": page,
            "pagecount": int(total_pages) if total_pages else 1,
            "limit": 20,
            "total": int(total_results) if total_results else len(videos),
            "list": videos
        }

    # ==================================================
    # HDHive 资源格式化
    # ==================================================

    def format_hdhive_resource_as_play(self, item, index=1):
        """
        HDHive 资源转成 OK影视播放项：
        资源标题$share|slug
        """

        slug = self.pick(item, ["slug", "id", "uuid"], "")
        title = self.pick(item, ["title", "name"], "")

        if not title:
            title = "资源%s" % index

        pan_type = self.pick(item, ["pan_type"], "")
        share_size = self.pick(item, ["share_size"], "")
        unlock_points = self.pick(item, ["unlock_points"], "")
        is_unlocked = item.get("is_unlocked", None)

        parts = [str(title)]

        if pan_type:
            parts.append(str(pan_type))

        if share_size:
            parts.append(str(share_size))

        if unlock_points not in ["", None]:
            parts.append("积分%s" % str(unlock_points))

        if is_unlocked is True:
            parts.append("已解锁")
        elif is_unlocked is False:
            parts.append("未解锁")

        name = " · ".join(parts)

        return "%s$share|%s" % (name, slug)

    def format_hdhive_resource_card(self, item, tmdb_info=None):
        """
        HDHive 资源转成搜索结果卡片。
        """

        slug = self.pick(item, ["slug", "id", "uuid"], "")
        title = self.pick(item, ["title", "name"], "")

        if not title:
            title = "HDHive资源"

        pan_type = self.pick(item, ["pan_type"], "")
        share_size = self.pick(item, ["share_size"], "")
        unlock_points = self.pick(item, ["unlock_points"], "")
        is_unlocked = item.get("is_unlocked", None)

        video_resolution = item.get("video_resolution", [])
        source = item.get("source", [])
        subtitle_language = item.get("subtitle_language", [])

        remarks = []

        if pan_type:
            remarks.append(str(pan_type))

        if share_size:
            remarks.append(str(share_size))

        if isinstance(video_resolution, list) and video_resolution:
            remarks.append("/".join([str(x) for x in video_resolution]))

        if isinstance(source, list) and source:
            remarks.append("/".join([str(x) for x in source]))

        if isinstance(subtitle_language, list) and subtitle_language:
            remarks.append("字幕:" + "/".join([str(x) for x in subtitle_language]))

        if unlock_points not in ["", None]:
            remarks.append("积分:" + str(unlock_points))

        if is_unlocked is True:
            remarks.append("已解锁")
        elif is_unlocked is False:
            remarks.append("未解锁")

        pic = ""
        prefix = ""

        if isinstance(tmdb_info, dict):
            pic = tmdb_info.get("poster", "")
            prefix = tmdb_info.get("title", "")

        name = title
        if prefix:
            name = prefix + " - " + title

        return {
            "vod_id": "share|" + str(slug),
            "vod_name": self.safe_str(name),
            "vod_pic": pic,
            "vod_remarks": " · ".join(remarks)
        }

    def build_tmdb_detail_with_hdhive_resources(self, media_type, tmdb_id):
        """
        点击 TMDB 条目后：
        1. 获取 TMDB 详情
        2. 查询 HDHive resources/:type/:tmdb_id
        3. 按网盘类型拆成不同线路
        4. 线路排序：夸克、115、其他
        5. 每条线路内积分0资源排前面
        """
        tmdb = self.tmdb_detail(media_type, tmdb_id)

        if not isinstance(tmdb, dict):
            tmdb = {}

        if media_type == "movie":
            title = self.pick(tmdb, ["title", "name", "original_title"], "TMDB电影")
            date = self.pick(tmdb, ["release_date"], "")
        else:
            title = self.pick(tmdb, ["name", "title", "original_name"], "TMDB剧集")
            date = self.pick(tmdb, ["first_air_date"], "")

        year = ""
        if isinstance(date, str) and len(date) >= 4:
            year = date[:4]

        poster = self.tmdb_img(self.pick(tmdb, ["poster_path"], ""))
        overview = self.pick(tmdb, ["overview"], "")

        genres = tmdb.get("genres", [])
        genre_text = ""
        if isinstance(genres, list):
            genre_text = " / ".join([
                str(x.get("name", ""))
                for x in genres
                if isinstance(x, dict) and x.get("name")
            ])

        countries = tmdb.get("production_countries", [])
        area_text = ""
        if isinstance(countries, list):
            area_text = " / ".join([
                str(x.get("name", ""))
                for x in countries
                if isinstance(x, dict) and x.get("name")
            ])

        vote = self.pick(tmdb, ["vote_average"], "")
        runtime = self.pick(tmdb, ["runtime", "episode_run_time"], "")

        actor_text = ""
        director_text = ""

        credits = tmdb.get("credits", {})
        if isinstance(credits, dict):
            cast = credits.get("cast", [])
            if isinstance(cast, list):
                actor_text = " / ".join([
                    str(x.get("name", ""))
                    for x in cast[:8]
                    if isinstance(x, dict) and x.get("name")
                ])

            crew = credits.get("crew", [])
            directors = []
            if isinstance(crew, list):
                for x in crew:
                    if isinstance(x, dict) and x.get("job") in ["Director", "Creator"]:
                        if x.get("name"):
                            directors.append(x.get("name"))
            director_text = " / ".join(directors[:5])

        content_parts = []

        if overview:
            content_parts.append(overview)

        if vote not in ["", None]:
            try:
                content_parts.append("TMDB评分：%.1f" % float(vote))
            except Exception:
                content_parts.append("TMDB评分：" + str(vote))

        if genre_text:
            content_parts.append("类型：" + genre_text)

        if runtime:
            content_parts.append("片长：" + str(runtime))

        content_parts.append("TMDB ID：%s" % str(tmdb_id))

        # 查询 HDHive 资源
        hdhive_result = self.api_resources(media_type, tmdb_id)

        resource_count = 0
        play_from = "HDHive"
        play_url = "暂无HDHive资源$noop"

        if isinstance(hdhive_result, dict) and hdhive_result.get("success") is False:
            err = self.format_api_error(hdhive_result)
            play_from = "HDHive"
            play_url = "HDHive接口错误：%s$noop" % self.safe_play_text(err)
        else:
            resources = self.hdhive_list(hdhive_result)
            resource_count = len(resources)

            if resources:
                play_from, play_url = self.build_grouped_play_list(resources)
            else:
                play_from = "HDHive"
                play_url = "暂无HDHive资源$noop"

        try:
            vod_id = self.make_tmdb_id(media_type, tmdb_id)
        except Exception:
            vod_id = "tmdb|%s|%s" % (media_type, tmdb_id)

        vod = {
            "vod_id": vod_id,
            "vod_name": self.safe_str(title),
            "vod_pic": poster,
            "type_name": genre_text,
            "vod_year": year,
            "vod_area": area_text,
            "vod_remarks": "HDHive资源数：%s" % str(resource_count) if resource_count > 0 else "暂无HDHive资源",
            "vod_actor": actor_text,
            "vod_director": director_text,
            "vod_content": "\n".join(content_parts),
            "vod_play_from": play_from,
            "vod_play_url": play_url
        }

        return vod
    def build_share_detail(self, slug):
        """
        直接打开 HDHive 分享详情。
        """

        result = self.api_share_detail(slug)

        if isinstance(result, dict) and result.get("success") is False:
            vod = {
                "vod_id": "share|" + str(slug),
                "vod_name": "HDHive接口错误",
                "vod_pic": "",
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": self.format_api_error(result),
                "vod_play_from": "HDHive",
                "vod_play_url": "接口错误$noop"
            }
            return vod

        data = self.hdhive_data(result)
        if not isinstance(data, dict):
            data = {}

        title = self.pick(data, ["title", "name", "share_name"], "HDHive资源")
        pan_type = self.pick(data, ["pan_type"], "")
        share_size = self.pick(data, ["share_size"], "")
        unlock_points = self.pick(data, ["unlock_points"], "")
        desc = self.pick(data, ["description", "desc", "content", "remark", "remarks"], "")

        content_parts = []

        if desc:
            content_parts.append(str(desc))

        if pan_type:
            content_parts.append("网盘类型：" + str(pan_type))

        if share_size:
            content_parts.append("资源大小：" + str(share_size))

        if unlock_points not in ["", None]:
            content_parts.append("解锁积分：" + str(unlock_points))

        vod = {
            "vod_id": "share|" + str(slug),
            "vod_name": self.safe_str(title),
            "vod_pic": "",
            "type_name": self.safe_str(pan_type),
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": self.safe_str(share_size),
            "vod_actor": "",
            "vod_director": "",
            "vod_content": "\n".join(content_parts),
            "vod_play_from": "HDHive",
            "vod_play_url": "解锁资源$share|" + str(slug)
        }

        return vod

    # ==================================================
    # 网盘线路分组 / 排序 / Push 推送辅助
    # ==================================================

    def safe_play_text(self, text):
        """
        OK影视播放列表中需要避免特殊分隔符：
        #   分集分隔符
        $   名称和播放ID分隔符
        $$$ 线路分隔符
        """
        text = self.safe_str(text)
        text = text.replace("#", " ")
        text = text.replace("$", " ")
        text = text.replace("\n", " ")
        text = text.replace("\r", " ")
        return text.strip()

    def make_share_id(self, slug):
        """
        安全 HDHive share 播放ID。
        使用 share_ + URL编码，避免 slug 特殊字符导致播放异常。
        """
        try:
            return "share_" + quote(str(slug), safe="")
        except Exception:
            return "share|" + str(slug)

    def parse_share_id(self, vod_id):
        """
        兼容：
        share_xxx
        share|xxx
        xxx
        """
        vod_id = str(vod_id).strip()

        if vod_id.startswith("share_"):
            try:
                return unquote(vod_id[6:])
            except Exception:
                return vod_id[6:]

        if vod_id.startswith("share|"):
            return vod_id.split("|", 1)[1]

        return vod_id

    def get_unlock_points(self, item):
        """
        获取资源所需积分。
        积分0资源需要排在最前。
        """
        if not isinstance(item, dict):
            return 999999

        value = item.get("unlock_points", 999999)

        try:
            if value is None or value == "":
                return 999999
            return int(float(str(value)))
        except Exception:
            return 999999

    def normalize_pan_name(self, pan_type):
        """
        统一 HDHive 返回的 pan_type 名称。
        常见值可能有：
        quark / 夸克 / 115 / baiDu / baidu / 189 / ali / aliyun 等。
        """
        raw = self.safe_str(pan_type).strip()
        low = raw.lower()

        if not raw:
            return "其他"

        if "quark" in low or "夸克" in raw:
            return "夸克"

        if low == "115" or "115" in low:
            return "115"

        if "baidu" in low or "百度" in raw:
            return "百度"

        if "aliyun" in low or low == "ali" or "阿里" in raw:
            return "阿里"

        if "189" in low or "天翼" in raw:
            return "189"

        if "xunlei" in low or "迅雷" in raw:
            return "迅雷"

        if low == "uc" or "uc网盘" in low or "uc" in low:
            return "UC"

        if "pikpak" in low:
            return "PikPak"

        return raw

    def pan_line_sort_key(self, pan_name):
        """
        播放线路排序：
        1. 夸克
        2. 115
        3. 其他
        """
        name = self.safe_str(pan_name)

        if name == "夸克":
            return (0, name)

        if name == "115":
            return (1, name)

        return (10, name)

    def resource_sort_key(self, item):
        """
        每个线路内部资源排序：
        1. 积分0
        2. 已解锁
        3. 积分低
        4. 积分高
        """
        points = self.get_unlock_points(item)

        is_unlocked = item.get("is_unlocked", None) if isinstance(item, dict) else None

        if points == 0:
            point_rank = 0
        else:
            point_rank = 1

        if is_unlocked is True:
            unlock_rank = 0
        else:
            unlock_rank = 1

        return (point_rank, unlock_rank, points)

    def format_resource_play_name(self, item, index=1):
        """
        格式化每条资源在选集里的显示名称。
        """
        title = self.pick(item, ["title", "name"], "")
        pan_type = self.normalize_pan_name(self.pick(item, ["pan_type"], ""))
        share_size = self.pick(item, ["share_size"], "")
        unlock_points = self.get_unlock_points(item)
        is_unlocked = item.get("is_unlocked", None)

        video_resolution = item.get("video_resolution", [])
        source = item.get("source", [])
        subtitle_language = item.get("subtitle_language", [])

        parts = []

        if title:
            parts.append(str(title))
        else:
            parts.append("资源%s" % index)

        if pan_type:
            parts.append(str(pan_type))

        if share_size:
            parts.append(str(share_size))

        if isinstance(video_resolution, list) and video_resolution:
            parts.append("/".join([str(x) for x in video_resolution]))

        if isinstance(source, list) and source:
            parts.append("/".join([str(x) for x in source]))

        if isinstance(subtitle_language, list) and subtitle_language:
            parts.append("字幕:" + "/".join([str(x) for x in subtitle_language]))

        if unlock_points != 999999:
            parts.append("积分%s" % str(unlock_points))

        if is_unlocked is True:
            parts.append("已解锁")
        elif is_unlocked is False:
            parts.append("未解锁")

        return self.safe_play_text(" · ".join(parts))

    def build_grouped_play_list(self, resources):
        """
        将 HDHive 资源按网盘类型拆分成不同线路。

        返回：
        vod_play_from = 夸克$$$115$$$百度$$$189
        vod_play_url  = 资源1$share_xxx#资源2$share_xxx$$$资源1$share_xxx
        """
        if not isinstance(resources, list) or not resources:
            return "HDHive", "暂无HDHive资源$noop"

        groups = {}

        for item in resources:
            if not isinstance(item, dict):
                continue

            pan_name = self.normalize_pan_name(self.pick(item, ["pan_type"], "其他"))

            if pan_name not in groups:
                groups[pan_name] = []

            groups[pan_name].append(item)

        pan_names = sorted(groups.keys(), key=lambda x: self.pan_line_sort_key(x))

        play_from_list = []
        play_url_group_list = []

        for pan_name in pan_names:
            items = groups.get(pan_name, [])

            # 线路内排序：积分0优先，已解锁优先，积分低优先
            items = sorted(items, key=lambda x: self.resource_sort_key(x))

            episode_list = []

            for idx, item in enumerate(items):
                slug = self.pick(item, ["slug", "id", "uuid"], "")

                if not slug:
                    continue

                name = self.format_resource_play_name(item, idx + 1)
                play_id = self.make_share_id(slug)

                episode_list.append("%s$%s" % (name, play_id))

            if episode_list:
                play_from_list.append(self.safe_play_text(pan_name))
                play_url_group_list.append("#".join(episode_list))

        if not play_from_list:
            return "HDHive", "暂无HDHive资源$noop"

        return "$$$".join(play_from_list), "$$$".join(play_url_group_list)

    def make_push_url(self, final_url):
        """
        把最终网盘链接转换成 OK影视 push 链接。

        例如：
        https://pan.quark.cn/s/xxx
        转为：
        push://https://pan.quark.cn/s/xxx
        """
        final_url = self.safe_str(final_url).strip()

        if not final_url:
            return ""

        if final_url.startswith("push://"):
            return final_url

        return "push://" + final_url

    # ==================================================
    # OK影视：首页分类
    # ==================================================

    def homeContent(self, filter):
        classes = [
            {"type_name": "热门电影", "type_id": "popular_movie"},
            {"type_name": "热门剧集", "type_id": "popular_tv"},
            {"type_name": "正在上映", "type_id": "now_playing"},
            {"type_name": "高分电影", "type_id": "top_movie"},
            {"type_name": "高分剧集", "type_id": "top_tv"},
            {"type_name": "动漫电影", "type_id": "anime_movie"},
            {"type_name": "动漫剧集", "type_id": "anime_tv"},
            {"type_name": "纪录片", "type_id": "documentary_movie"},
            {"type_name": "电影库", "type_id": "movie"},
            {"type_name": "剧集库", "type_id": "tv"}
        ]

        years = [
            {"n": "全部", "v": ""},
            {"n": "2026", "v": "2026"},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
            {"n": "2023", "v": "2023"},
            {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"},
            {"n": "2020", "v": "2020"},
            {"n": "2019", "v": "2019"},
            {"n": "2018", "v": "2018"},
            {"n": "2017", "v": "2017"},
            {"n": "2016", "v": "2016"},
            {"n": "2015", "v": "2015"}
        ]

        movie_genres = [
            {"n": "全部", "v": ""},
            {"n": "动作", "v": "28"},
            {"n": "冒险", "v": "12"},
            {"n": "动画", "v": "16"},
            {"n": "喜剧", "v": "35"},
            {"n": "犯罪", "v": "80"},
            {"n": "纪录", "v": "99"},
            {"n": "剧情", "v": "18"},
            {"n": "家庭", "v": "10751"},
            {"n": "奇幻", "v": "14"},
            {"n": "历史", "v": "36"},
            {"n": "恐怖", "v": "27"},
            {"n": "音乐", "v": "10402"},
            {"n": "悬疑", "v": "9648"},
            {"n": "爱情", "v": "10749"},
            {"n": "科幻", "v": "878"},
            {"n": "战争", "v": "10752"}
        ]

        tv_genres = [
            {"n": "全部", "v": ""},
            {"n": "动作冒险", "v": "10759"},
            {"n": "动画", "v": "16"},
            {"n": "喜剧", "v": "35"},
            {"n": "犯罪", "v": "80"},
            {"n": "纪录", "v": "99"},
            {"n": "剧情", "v": "18"},
            {"n": "家庭", "v": "10751"},
            {"n": "儿童", "v": "10762"},
            {"n": "悬疑", "v": "9648"},
            {"n": "新闻", "v": "10763"},
            {"n": "真人秀", "v": "10764"},
            {"n": "科幻奇幻", "v": "10765"},
            {"n": "肥皂剧", "v": "10766"},
            {"n": "脱口秀", "v": "10767"},
            {"n": "战争政治", "v": "10768"},
            {"n": "西部", "v": "37"}
        ]

        sort_values = [
            {"n": "热门降序", "v": "popularity.desc"},
            {"n": "评分降序", "v": "vote_average.desc"},
            {"n": "日期降序", "v": "primary_release_date.desc"},
            {"n": "日期升序", "v": "primary_release_date.asc"}
        ]

        tv_sort_values = [
            {"n": "热门降序", "v": "popularity.desc"},
            {"n": "评分降序", "v": "vote_average.desc"},
            {"n": "日期降序", "v": "first_air_date.desc"},
            {"n": "日期升序", "v": "first_air_date.asc"}
        ]

        filters = {}

        movie_filter = [
            {"key": "year", "name": "年份", "value": years},
            {"key": "genre", "name": "类型", "value": movie_genres},
            {"key": "sort_by", "name": "排序", "value": sort_values}
        ]

        tv_filter = [
            {"key": "year", "name": "年份", "value": years},
            {"key": "genre", "name": "类型", "value": tv_genres},
            {"key": "sort_by", "name": "排序", "value": tv_sort_values}
        ]

        for tid in ["movie", "popular_movie", "now_playing", "top_movie", "anime_movie", "documentary_movie"]:
            filters[tid] = movie_filter

        for tid in ["tv", "popular_tv", "top_tv", "anime_tv"]:
            filters[tid] = tv_filter

        return {
            "class": classes,
            "filters": filters
        }

    # ==================================================
    # OK影视：首页推荐
    # ==================================================

    def homeVideoContent(self):
        """
        首页推荐使用 TMDB 热门电影。
        """

        videos = []

        if not self.tmdb_api_key:
            videos.append({
                "vod_id": "help",
                "vod_name": "请配置 TMDB API Key",
                "vod_pic": "",
                "vod_remarks": "ext.tmdb_api_key"
            })
            return {"list": videos}

        result = self.tmdb_discover("popular_movie", 1, {})
        videos = result.get("list", [])

        if not videos:
            videos.append({
                "vod_id": "help",
                "vod_name": "TMDB 暂无数据或配置错误",
                "vod_pic": "",
                "vod_remarks": "检查 tmdb_api_key"
            })

        return {
            "list": videos
        }

    # ==================================================
    # OK影视：分类列表
    # ==================================================

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)

            if not self.tmdb_api_key:
                return {
                    "page": page,
                    "pagecount": 1,
                    "limit": 20,
                    "total": 1,
                    "list": [
                        self.make_error_video("请配置 TMDB API Key", "ext.tmdb_api_key 不能为空")
                    ]
                }

            return self.tmdb_discover(tid, page, extend if isinstance(extend, dict) else {})

        except Exception as e:
            print("categoryContent error:", e)
            return {
                "page": int(pg),
                "pagecount": 1,
                "limit": 20,
                "total": 0,
                "list": [
                    self.make_error_video("分类加载异常", str(e))
                ]
            }

    # ==================================================
    # 搜索关键词解析
    # ==================================================

    def parse_search_key(self, key):
        """
        支持：
        movie:550
        tv:1399
        movie/550
        tv/1399
        550

        普通片名交给 TMDB search/multi。
        """

        raw = str(key).strip()

        if not raw:
            return None, None

        if raw in self.keyword_map:
            value = self.keyword_map.get(raw)
            if isinstance(value, dict):
                media_type = str(value.get("type", value.get("media_type", self.default_type))).strip()
                tmdb_id = str(value.get("tmdb_id", value.get("id", ""))).strip()
                if media_type in ["movie", "tv"] and tmdb_id:
                    return media_type, tmdb_id
            elif isinstance(value, str):
                return self.parse_search_key(value)

        m = re.match(r"^(movie|tv)\s*[:/|,， ]\s*(\d+)$", raw, re.I)
        if m:
            return m.group(1).lower(), m.group(2)

        m = re.match(r"^tmdb\s*[:/|,， ]\s*(movie|tv)\s*[:/|,， ]\s*(\d+)$", raw, re.I)
        if m:
            return m.group(1).lower(), m.group(2)

        if re.match(r"^\d+$", raw):
            media_type = self.default_type
            if media_type not in ["movie", "tv"]:
                media_type = "movie"
            return media_type, raw

        return None, None

    # ==================================================
    # OK影视：搜索
    # ==================================================

    def searchContent(self, key, quick, pg="1"):
        """
        搜索逻辑：
        1. movie:550 / tv:1399 / 纯数字：直接查 HDHive
        2. 普通片名：TMDB 搜索，展示 TMDB 卡片
        3. 点击 TMDB 卡片进入详情后自动查询 HDHive 资源
        """

        videos = []

        try:
            media_type, tmdb_id = self.parse_search_key(key)

            # 直接 TMDB ID 查询：展示 HDHive 资源卡片
            if media_type and tmdb_id:
                tmdb = self.tmdb_detail(media_type, tmdb_id)

                tmdb_info = {}

                if isinstance(tmdb, dict):
                    if media_type == "movie":
                        title = self.pick(tmdb, ["title", "name", "original_title"], "")
                    else:
                        title = self.pick(tmdb, ["name", "title", "original_name"], "")

                    tmdb_info = {
                        "title": title,
                        "poster": self.tmdb_img(self.pick(tmdb, ["poster_path"], ""))
                    }

                result = self.api_resources(media_type, tmdb_id)

                if isinstance(result, dict) and result.get("success") is False:
                    videos.append(self.make_error_video("HDHive接口错误", self.format_api_error(result)))
                    return {"list": videos}

                resources = self.hdhive_list(result)

                for item in resources:
                    videos.append(self.format_hdhive_resource_card(item, tmdb_info))

                if not videos:
                    videos.append({
                        "vod_id": "tmdb|%s|%s" % (media_type, tmdb_id),
                        "vod_name": tmdb_info.get("title", "TMDB %s:%s" % (media_type, tmdb_id)),
                        "vod_pic": tmdb_info.get("poster", ""),
                        "vod_remarks": "暂无HDHive资源，点击查看详情"
                    })

                return {
                    "list": videos
                }

            # 普通片名：用 TMDB 搜索，展示电影/剧集卡片
            if not self.tmdb_api_key:
                videos.append({
                    "vod_id": "help",
                    "vod_name": "请配置 TMDB API Key 后搜索片名",
                    "vod_pic": "",
                    "vod_remarks": "或直接搜 movie:550 / tv:1399"
                })
                return {"list": videos}

            videos = self.tmdb_search_keyword(key)

            if not videos:
                videos.append({
                    "vod_id": "empty",
                    "vod_name": "TMDB未找到：" + str(key),
                    "vod_pic": "",
                    "vod_remarks": "换个关键词试试"
                })

            return {
                "list": videos
            }

        except Exception as e:
            print("searchContent error:", e)
            return {
                "list": [
                    self.make_error_video("搜索异常", str(e))
                ]
            }

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ==================================================
    # OK影视：详情页
    # ==================================================

    def detailContent(self, ids):
        """
        支持：
        tmdb|movie|550
        tmdb|tv|1399
        share|slug

        点击 TMDB 条目时自动查 HDHive 资源。
        """

        try:
            vod_id = ids[0]

            if vod_id in ["help", "empty", "error"]:
                vod = {
                    "vod_id": vod_id,
                    "vod_name": "HDHive+TMDB提示",
                    "vod_pic": "",
                    "type_name": "",
                    "vod_year": "",
                    "vod_area": "",
                    "vod_remarks": "",
                    "vod_actor": "",
                    "vod_director": "",
                    "vod_content": "请配置 TMDB API Key 和 HDHive API Key。搜索片名会先查询 TMDB，点击条目后自动查询 HDHive 资源。",
                    "vod_play_from": "HDHive",
                    "vod_play_url": "无可播放资源$noop"
                }
                return {"list": [vod]}

            if vod_id.startswith("tmdb|"):
                parts = vod_id.split("|")
                if len(parts) >= 3:
                    media_type = parts[1]
                    tmdb_id = parts[2]
                    vod = self.build_tmdb_detail_with_hdhive_resources(media_type, tmdb_id)
                    return {"list": [vod]}

            if vod_id.startswith("share|"):
                slug = vod_id.split("|", 1)[1]
                vod = self.build_share_detail(slug)
                return {"list": [vod]}

            # 兼容直接传 slug
            vod = self.build_share_detail(vod_id)
            return {"list": [vod]}

        except Exception as e:
            print("detailContent error:", e)
            vod = {
                "vod_id": "error",
                "vod_name": "详情异常",
                "vod_pic": "",
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": str(e),
                "vod_play_from": "HDHive",
                "vod_play_url": "异常$noop"
            }
            return {"list": [vod]}

    # ==================================================
    # OK影视：播放 / 解锁
    # ==================================================

    def playerContent(self, flag, id, vipFlags):
        """
        点击线路下任意 HDHive 资源时：

        1. 自动调用 /resources/unlock
        2. 获取网盘链接 full_url / url / access_code
        3. 自动在前面加 push://
        4. 返回给 OK影视，实现网盘链接推送

        注意：
        如果资源显示积分大于0且未解锁，点击后会按 HDHive 规则自动解锁，可能消耗积分。
        """
        try:
            play_id = str(id).strip()

            if play_id == "noop" or not play_id:
                return {
                    "parse": 1,
                    "jx": 0,
                    "playUrl": "",
                    "url": "",
                    "danmaku": ""
                }

            # 如果已经是 push 链接，直接返回
            if play_id.startswith("push://"):
                return {
                    "parse": 0,
                    "jx": 0,
                    "playUrl": "",
                    "url": play_id,
                    "danmaku": "",
                    "header": {
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://hdhive.com/"
                    }
                }

            # 如果本身已经是普通链接，也转成 push://
            if play_id.startswith("http://") or play_id.startswith("https://"):
                return {
                    "parse": 0,
                    "jx": 0,
                    "playUrl": "",
                    "url": self.make_push_url(play_id),
                    "danmaku": "",
                    "header": {
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://hdhive.com/"
                    }
                }

            # 兼容 share_xxx / share|xxx / xxx
            slug = self.parse_share_id(play_id)

            # 自动 unlock
            result = self.api_unlock(slug)

            if isinstance(result, dict) and result.get("success") is False:
                err = self.format_api_error(result)

                return {
                    "parse": 1,
                    "jx": 0,
                    "playUrl": "",
                    "url": err,
                    "danmaku": ""
                }

            data = self.hdhive_data(result)

            if not isinstance(data, dict):
                data = {}

            full_url = self.pick(data, ["full_url"], "")
            url = self.pick(data, ["url"], "")
            access_code = self.pick(data, ["access_code", "pwd", "password"], "")

            final_url = full_url or url

            # 没有 full_url 但有 access_code 时，把访问码拼到后面
            if final_url and access_code and str(access_code) not in final_url:
                if "pwd=" not in final_url and "password=" not in final_url:
                    final_url = final_url + " 访问码:" + str(access_code)

            if final_url:
                push_url = self.make_push_url(final_url)

                return {
                    "parse": 0,
                    "jx": 0,
                    "playUrl": "",
                    "url": push_url,
                    "danmaku": "",
                    "header": {
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://hdhive.com/"
                    }
                }

            return {
                "parse": 1,
                "jx": 0,
                "playUrl": "",
                "url": "HDHive解锁成功，但未返回网盘链接",
                "danmaku": ""
            }

        except Exception as e:
            print("playerContent error:", e)

            return {
                "parse": 1,
                "jx": 0,
                "playUrl": "",
                "url": str(e),
                "danmaku": ""
            }
    # ==================================================
    # 本地代理
    # ==================================================

    def localProxy(self, param):
        return None


# ===== HDHIVE_TMDB_PROXY_PATCH_BEGIN =====
# -*- coding: utf-8 -*-
# ============================================================
# HDHive + TMDB 代理补丁
#
# 代理规则：
#   1. HDHive API 请求走代理
#   2. TMDB API 请求走代理
#   3. TMDB 图片 / 封面走本地图片代理，本地代理内部再走代理
#   4. 首页 / 分类 / 搜索 / 详情返回的 vod_pic 自动套图片代理
#
# 不走代理：
#   1. 网盘 push:// 播放链接
#   2. playerContent 最终返回的网盘推送播放
#
# 默认代理：
#   http://127.0.0.1:10172
#
# extend 可选：
# {
#   "proxy_url": "http://127.0.0.1:10172",
#   "site_proxy": "http://127.0.0.1:10172",
#   "image_proxy": true
# }
# ============================================================

import json as _hpx_json
import requests as _hpx_requests
from urllib.parse import quote as _hpx_quote
from urllib.parse import unquote as _hpx_unquote
from urllib.parse import urlparse as _hpx_urlparse
from urllib.parse import parse_qs as _hpx_parse_qs

try:
    Spider._hpx_old_init = Spider.init
except Exception:
    Spider._hpx_old_init = None

try:
    Spider._hpx_old_hdhive_fetch = Spider.hdhive_fetch
except Exception:
    Spider._hpx_old_hdhive_fetch = None

try:
    Spider._hpx_old_tmdb_fetch = Spider.tmdb_fetch
except Exception:
    Spider._hpx_old_tmdb_fetch = None

try:
    Spider._hpx_old_tmdb_img = Spider.tmdb_img
except Exception:
    Spider._hpx_old_tmdb_img = None

try:
    Spider._hpx_old_homeVideoContent = Spider.homeVideoContent
except Exception:
    Spider._hpx_old_homeVideoContent = None

try:
    Spider._hpx_old_categoryContent = Spider.categoryContent
except Exception:
    Spider._hpx_old_categoryContent = None

try:
    Spider._hpx_old_searchContent = Spider.searchContent
except Exception:
    Spider._hpx_old_searchContent = None

try:
    Spider._hpx_old_detailContent = Spider.detailContent
except Exception:
    Spider._hpx_old_detailContent = None

try:
    Spider._hpx_old_playerContent = Spider.playerContent
except Exception:
    Spider._hpx_old_playerContent = None

try:
    Spider._hpx_old_localProxy = Spider.localProxy
except Exception:
    Spider._hpx_old_localProxy = None


def _hpx_default_proxy():
    return "http://127.0.0.1:10172"


def _hpx_get_proxy(self):
    try:
        p = (
            getattr(self, "site_proxy", "")
            or getattr(self, "proxy_url", "")
            or getattr(self, "hdhive_proxy", "")
            or getattr(self, "tmdb_proxy", "")
            or ""
        )
        p = str(p or "").strip()
        if p:
            return p
    except Exception:
        pass
    return _hpx_default_proxy()


def _hpx_proxies(self):
    p = _hpx_get_proxy(self)
    if not p:
        return None
    return {
        "http": p,
        "https": p
    }


def _hpx_get_param(params, key):
    try:
        if not isinstance(params, dict):
            return ""
        v = params.get(key, "")
        if isinstance(v, list):
            return v[0] if v else ""
        return v
    except Exception:
        return ""


def _hpx_is_local_proxy_url(url):
    try:
        u = str(url or "")
        return (
            "/proxy?" in u
            and "url=" in u
            and (
                "127.0.0.1" in u
                or "localhost" in u
                or ":9978" in u
            )
        )
    except Exception:
        return False


def _hpx_unwrap_proxy_url(url):
    try:
        url = str(url or "").strip()
        if not url:
            return ""
        for _ in range(10):
            url = _hpx_unquote(url)
            if not _hpx_is_local_proxy_url(url):
                break

            up = _hpx_urlparse(url)
            qs = _hpx_parse_qs(up.query)
            inner = ""

            if "url" in qs and qs["url"]:
                inner = qs["url"][0]

            if not inner:
                break

            inner = _hpx_unquote(inner)

            if inner == url:
                break

            url = inner

        return url
    except Exception:
        return str(url or "")


def _hpx_is_img(url):
    try:
        u = str(url or "").lower()
        return (
            u.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"))
            or "image.tmdb.org" in u
            or "/t/p/" in u
        )
    except Exception:
        return False


def _hpx_headers(self, image=False):
    try:
        ua = "Mozilla/5.0 OKPG-HDHive-TMDB-Spider/1.0"

        if image:
            accept = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        else:
            accept = "application/json,text/plain,*/*"

        return {
            "User-Agent": ua,
            "Accept": accept,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Referer": "https://www.themoviedb.org/"
        }
    except Exception:
        return {
            "User-Agent": "Mozilla/5.0"
        }


def _hpx_guess_ctype(url, content=None, rsp=None):
    try:
        if rsp is not None:
            ctype = rsp.headers.get("Content-Type") or ""
            if ctype:
                return ctype

        if content:
            if content[:3] == b"\xff\xd8\xff":
                return "image/jpeg"
            if content[:8] == b"\x89PNG\r\n\x1a\n":
                return "image/png"
            if content[:4] == b"RIFF" and b"WEBP" in content[:20]:
                return "image/webp"
            if content[:6] in [b"GIF87a", b"GIF89a"]:
                return "image/gif"

        low = str(url or "").lower()

        if ".png" in low:
            return "image/png"
        if ".webp" in low:
            return "image/webp"
        if ".gif" in low:
            return "image/gif"
        if ".avif" in low:
            return "image/avif"

        return "image/jpeg"
    except Exception:
        return "application/octet-stream"


def _hpx_get_proxy_url(self):
    try:
        if hasattr(self, "getProxyUrl"):
            proxy = self.getProxyUrl()
            if proxy:
                return proxy
    except Exception:
        pass
    return ""


def _hpx_to_img_proxy(self, url):
    try:
        url = _hpx_unwrap_proxy_url(url)
        url = str(url or "").strip()

        if not url:
            return ""

        if not _hpx_is_img(url):
            return url

        if not getattr(self, "use_img_proxy", True):
            return url

        proxy = _hpx_get_proxy_url(self)

        if not proxy:
            return url

        sep = "&" if "?" in proxy else "?"
        return proxy + sep + "type=img&url=" + _hpx_quote(url, safe="")
    except Exception:
        return str(url or "")


def _hpx_fix_vod_pics(self, ret):
    try:
        if not isinstance(ret, dict):
            return ret

        lst = ret.get("list", [])

        if not isinstance(lst, list):
            return ret

        for v in lst:
            try:
                if not isinstance(v, dict):
                    continue

                pic = v.get("vod_pic", "")

                if pic:
                    v["vod_pic"] = _hpx_to_img_proxy(self, pic)
            except Exception:
                pass

        return ret
    except Exception:
        return ret


def _hpx_init(self, extend=""):
    if getattr(Spider, "_hpx_old_init", None):
        Spider._hpx_old_init(self, extend)

    self.proxy_url = getattr(self, "proxy_url", "") or _hpx_default_proxy()
    self.site_proxy = getattr(self, "site_proxy", "") or self.proxy_url
    self.hdhive_proxy = getattr(self, "hdhive_proxy", "") or self.site_proxy
    self.tmdb_proxy = getattr(self, "tmdb_proxy", "") or self.site_proxy
    self.use_img_proxy = True

    try:
        if extend:
            ext = _hpx_json.loads(extend) if str(extend).strip().startswith("{") else {}

            if isinstance(ext, dict):
                p = str(
                    ext.get("site_proxy", "")
                    or ext.get("proxy_url", "")
                    or ext.get("hdhive_proxy", "")
                    or ext.get("tmdb_proxy", "")
                    or ""
                ).strip()

                if p:
                    self.proxy_url = p
                    self.site_proxy = p
                    self.hdhive_proxy = p
                    self.tmdb_proxy = p

                if str(ext.get("image_proxy", "true")).lower() in ["0", "false", "no"]:
                    self.use_img_proxy = False
                else:
                    self.use_img_proxy = True

    except Exception as e:
        print("[HDHive Proxy init ext error]", e)

    try:
        sess = _hpx_requests.Session()
        sess.trust_env = False
        sess.verify = False
        sess.proxies.update(_hpx_proxies(self) or {})
        self.hpx_session = sess
    except Exception as e:
        print("[HDHive Proxy session error]", e)

    print("[HDHive+TMDB Proxy] proxy=%s image_proxy=%s" % (
        _hpx_get_proxy(self),
        bool(getattr(self, "use_img_proxy", True))
    ))
    print("[HDHive+TMDB Proxy] push:// netdisk playback keep direct")


def _hpx_request(self, method, url, headers=None, params=None, json_data=None, timeout=None):
    sess = getattr(self, "hpx_session", None)

    if sess is None:
        sess = _hpx_requests.Session()
        sess.trust_env = False
        sess.verify = False
        sess.proxies.update(_hpx_proxies(self) or {})
        self.hpx_session = sess

    method = str(method or "GET").upper()

    kwargs = {
        "headers": headers,
        "params": params,
        "timeout": timeout or getattr(self, "timeout", 15),
        "verify": False,
        "proxies": _hpx_proxies(self),
    }

    if json_data is not None:
        kwargs["json"] = json_data

    if method == "POST":
        return sess.post(url, **kwargs)

    if method == "PATCH":
        return sess.patch(url, **kwargs)

    if method == "DELETE":
        return sess.delete(url, **kwargs)

    return sess.get(url, **kwargs)


def _hpx_hdhive_fetch(self, path_or_url, params=None, method="GET", data=None):
    """
    HDHive OpenAPI 请求：走代理。
    """
    try:
        current = self.now()

        if self.cooldown_until > current:
            wait_seconds = self.cooldown_until - current
            return {
                "success": False,
                "code": "LOCAL_COOLDOWN",
                "message": "本地冷却中",
                "description": "HDHive API 当前处于冷却期，请稍后再试",
                "retry_after_seconds": wait_seconds
            }

        if str(path_or_url).startswith("http://") or str(path_or_url).startswith("https://"):
            url = str(path_or_url)
        else:
            if not str(path_or_url).startswith("/"):
                path_or_url = "/" + str(path_or_url)
            url = self.api_base + str(path_or_url)

        headers = self.build_hdhive_headers()

        resp = _hpx_request(
            self,
            method,
            url,
            headers=headers,
            params=params,
            json_data=data,
            timeout=getattr(self, "timeout", 15)
        )

        try:
            result = resp.json()
        except Exception:
            result = {
                "success": False,
                "code": str(resp.status_code),
                "message": "non-json response",
                "raw": resp.text
            }

        result["_http_status"] = resp.status_code
        result["_headers"] = {
            "Retry-After": resp.headers.get("Retry-After", ""),
            "X-OpenAPI-User-Daily-Limit": resp.headers.get("X-OpenAPI-User-Daily-Limit", ""),
            "X-OpenAPI-User-Daily-Remaining": resp.headers.get("X-OpenAPI-User-Daily-Remaining", ""),
            "X-OpenAPI-App-Daily-Limit": resp.headers.get("X-OpenAPI-App-Daily-Limit", ""),
            "X-OpenAPI-App-Daily-Remaining": resp.headers.get("X-OpenAPI-App-Daily-Remaining", "")
        }

        if resp.status_code == 429:
            retry_after = 0

            try:
                retry_after = int(resp.headers.get("Retry-After", "0"))
            except Exception:
                retry_after = 0

            if not retry_after:
                try:
                    retry_after = int(result.get("retry_after_seconds", 0))
                except Exception:
                    retry_after = 0

            if retry_after > 0:
                self.cooldown_until = self.now() + retry_after

        if resp.status_code >= 400:
            self.last_error = self.format_api_error(result)
            print("HDHive API Error:", self.last_error)

        print("[HDHive Proxy API] %s %s => %s proxy=%s" % (
            str(method).upper(),
            url,
            resp.status_code,
            _hpx_get_proxy(self)
        ))

        return result

    except Exception as e:
        print("HDHive request error:", e)
        return {
            "success": False,
            "code": "REQUEST_EXCEPTION",
            "message": str(e)
        }


def _hpx_tmdb_fetch(self, path, params=None):
    """
    TMDB API 请求：走代理。
    """
    try:
        if not self.tmdb_api_key:
            return {}

        if params is None:
            params = {}

        params["api_key"] = self.tmdb_api_key

        if "language" not in params:
            params["language"] = self.tmdb_language

        if str(path).startswith("http://") or str(path).startswith("https://"):
            url = str(path)
        else:
            if not str(path).startswith("/"):
                path = "/" + str(path)
            url = self.tmdb_api_base + str(path)

        headers = {
            "User-Agent": "Mozilla/5.0 OKPG-HDHive-TMDB-Spider/1.0",
            "Accept": "application/json,text/plain,*/*"
        }

        resp = _hpx_request(
            self,
            "GET",
            url,
            headers=headers,
            params=params,
            timeout=getattr(self, "timeout", 15)
        )

        print("[TMDB Proxy API] GET %s => %s proxy=%s" % (
            url,
            resp.status_code,
            _hpx_get_proxy(self)
        ))

        try:
            return resp.json()
        except Exception:
            return {}

    except Exception as e:
        print("TMDB request error:", e)
        return {}


def _hpx_tmdb_img(self, poster_path):
    """
    TMDB 图片地址：返回本地图片代理地址。
    """
    try:
        if not poster_path:
            return ""

        if str(poster_path).startswith("http"):
            raw = str(poster_path)
        else:
            raw = self.tmdb_image_base + str(poster_path)

        return _hpx_to_img_proxy(self, raw)
    except Exception:
        return ""


def _hpx_homeVideoContent(self):
    old = getattr(Spider, "_hpx_old_homeVideoContent", None)

    if old:
        ret = old(self)
    else:
        ret = {"list": []}

    return _hpx_fix_vod_pics(self, ret)


def _hpx_categoryContent(self, tid, pg, filter, extend):
    old = getattr(Spider, "_hpx_old_categoryContent", None)

    if old:
        ret = old(self, tid, pg, filter, extend)
    else:
        ret = {
            "list": [],
            "page": pg,
            "pagecount": 1,
            "limit": 20,
            "total": 0
        }

    return _hpx_fix_vod_pics(self, ret)


def _hpx_searchContent(self, key, quick, pg="1"):
    old = getattr(Spider, "_hpx_old_searchContent", None)

    if old:
        ret = old(self, key, quick, pg)
    else:
        ret = {"list": []}

    return _hpx_fix_vod_pics(self, ret)


def _hpx_detailContent(self, ids):
    old = getattr(Spider, "_hpx_old_detailContent", None)

    if old:
        ret = old(self, ids)
    else:
        ret = {"list": []}

    return _hpx_fix_vod_pics(self, ret)


def _hpx_playerContent(self, flag, id, vipFlags):
    """
    播放逻辑保持原样。
    网盘 push:// 不加代理。
    """
    old = getattr(Spider, "_hpx_old_playerContent", None)

    if old:
        return old(self, flag, id, vipFlags)

    return {
        "parse": 1,
        "jx": 0,
        "playUrl": "",
        "url": str(id or ""),
        "danmaku": ""
    }


def _hpx_localProxy(self, param):
    """
    图片本地代理：
    客户端请求本地 /proxy?type=img&url=xxx
    Python 内部再通过 http://127.0.0.1:10172 去请求真实图片。
    """
    try:
        ptype = str(_hpx_get_param(param, "type") or "").strip()
        action = str(_hpx_get_param(param, "action") or "").strip()
        do_val = str(_hpx_get_param(param, "do") or "").strip()

        is_img = ptype == "img" or action == "img" or do_val == "img"

        if not is_img:
            old = getattr(Spider, "_hpx_old_localProxy", None)

            if old:
                return old(self, param)

            return [404, "text/plain", "Not Found"]

        raw_url = str(_hpx_get_param(param, "url") or "").strip()

        if not raw_url:
            return [404, "text/plain", "No Url"]

        fixed = _hpx_unwrap_proxy_url(_hpx_unquote(raw_url))

        if not fixed:
            return [404, "text/plain", "Bad Url"]

        sess = getattr(self, "hpx_img_session", None)

        if sess is None:
            sess = _hpx_requests.Session()
            sess.trust_env = False
            sess.verify = False
            sess.proxies.update(_hpx_proxies(self) or {})
            self.hpx_img_session = sess

        rsp = sess.get(
            fixed,
            headers=_hpx_headers(self, image=True),
            timeout=30,
            allow_redirects=True,
            verify=False,
            proxies=_hpx_proxies(self)
        )

        content = rsp.content or b""
        ctype = rsp.headers.get("Content-Type") or ""

        print("[HDHive Proxy IMG] status=%s ctype=%s len=%s url=%s proxy=%s" % (
            rsp.status_code,
            ctype,
            len(content),
            fixed,
            _hpx_get_proxy(self)
        ))

        if rsp.status_code != 200 or not content:
            return [404, "text/plain", "Proxy Image Failed"]

        return [200, _hpx_guess_ctype(fixed, content, rsp), content]

    except Exception as e:
        print("[HDHive Proxy localProxy error]", e)
        return [404, "text/plain", "Proxy Error"]


# 绑定覆盖
Spider.init = _hpx_init
Spider.hdhive_fetch = _hpx_hdhive_fetch
Spider.tmdb_fetch = _hpx_tmdb_fetch
Spider.tmdb_img = _hpx_tmdb_img
Spider.homeVideoContent = _hpx_homeVideoContent
Spider.categoryContent = _hpx_categoryContent
Spider.searchContent = _hpx_searchContent
Spider.detailContent = _hpx_detailContent
Spider.playerContent = _hpx_playerContent
Spider.localProxy = _hpx_localProxy

print("[HDHIVE TMDB PROXY PATCH] loaded")
# ===== HDHIVE_TMDB_PROXY_PATCH_END =====

