import json
import time
import os
import re
import sys
import random

import requests
from loguru import logger
from utils.xianyu_utils import generate_sign

UPLOAD_URL = 'https://stream-upload.goofish.com/api/upload.api'
MTOP_BASE_URL = 'https://h5api.m.goofish.com/h5'


class XianyuApis:
    # ── 风控参数（可通过环境变量覆盖） ──
    # 每次 API 调用前的基础随机延迟（秒）
    API_DELAY_MIN = float(os.getenv("API_DELAY_MIN", "1.0"))
    API_DELAY_MAX = float(os.getenv("API_DELAY_MAX", "3.0"))
    # 风控触发后冷却时间（秒）
    COOLDOWN_SECONDS = int(os.getenv("RISK_COOLDOWN_SECONDS", "600"))
    # 同一 API 连续失败多少次触发冷却
    MAX_CONSECUTIVE_FAILURES = int(os.getenv("MAX_CONSECUTIVE_FAILURES", "5"))

    def __init__(self):
        self.url = 'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/'
        self.session = requests.Session()
        # 风控状态
        self._consecutive_failures: int = 0
        self._cooldown_until: float = 0.0  # 冷却结束时间戳
        self.session.headers.update({
            'accept': 'application/json',
            'accept-language': 'zh-CN,zh;q=0.9',
            'cache-control': 'no-cache',
            'origin': 'https://www.goofish.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.goofish.com/',
            'sec-ch-ua': '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        })
        
    def _call_mtop_api(
        self,
        api_name: str,
        version: str,
        data_val: str,
        retry_count: int = 0,
        max_retries: int = 3,
        extra_params: dict | None = None,
    ) -> dict:
        """通用 MTOP API 调用方法

        Args:
            api_name: API名称，如 mtop.taobao.idle.pc.detail
            version: API版本，如 1.0
            data_val: JSON字符串格式的请求数据
            retry_count: 当前重试次数
            max_retries: 最大重试次数
            extra_params: 额外的URL参数

        Returns:
            API响应的JSON字典
        """
        # ── 风控冷却检查 ──
        now = time.time()
        if self._cooldown_until > now:
            remaining = int(self._cooldown_until - now)
            logger.warning(f"⚠️ 风控冷却中，剩余 {remaining}s，跳过 API 调用: {api_name}")
            return {"error": f"风控冷却中: {remaining}s 后恢复"}

        if retry_count >= max_retries:
            logger.error(f"MTOP API 调用失败，重试次数过多: {api_name}")
            return {"error": f"MTOP API 调用失败: {api_name}"}

        # ── 请求前随机延迟，避免过于规律的调用 ──
        delay = random.uniform(self.API_DELAY_MIN, self.API_DELAY_MAX)
        if retry_count > 0:
            # 重试时使用指数退避: 2^n * 基础延迟
            delay = delay * (2 ** retry_count) + random.uniform(0, retry_count)
        time.sleep(delay)

        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': version,
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': api_name,
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
        }
        if extra_params:
            params.update(extra_params)

        data = {'data': data_val}

        token = self.session.cookies.get('_m_h5_tk', '').split('_')[0]
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign

        try:
            url = f"{MTOP_BASE_URL}/{api_name}/{version}/"
            response = self.session.post(url, params=params, data=data)
            res_json = response.json()

            if not isinstance(res_json, dict):
                logger.error(f"API返回格式异常: {res_json}")
                return self._call_mtop_api(api_name, version, data_val, retry_count + 1, max_retries, extra_params)

            ret_value = res_json.get('ret', [])
            if not any('SUCCESS' in ret for ret in ret_value):
                error_msg = str(ret_value)
                self._consecutive_failures += 1

                # 风控处理
                if 'RGV587_ERROR' in error_msg or '被挤爆啦' in error_msg:
                    logger.error(f"🚨 触发风控: {ret_value}")
                    self._consecutive_failures = self.MAX_CONSECUTIVE_FAILURES  # 直接触发冷却

                    # 自动进入冷却期
                    cooldown_mins = self.COOLDOWN_SECONDS / 60
                    logger.warning(f"⏸️ 自动进入风控冷却期 ({cooldown_mins:.0f} 分钟)")

                    # 通过 EventBus 发布风控事件（如果 bot 注入了 event_bus）
                    if hasattr(self, 'event_bus') and self.event_bus:
                        self.event_bus.publish("risk_alert", {
                            "type": "risk_control",
                            "api_name": api_name,
                            "error": error_msg[:100],
                            "cooldown_seconds": self.COOLDOWN_SECONDS,
                        })

                    print("\n" + "=" * 55)
                    print(f"🚨 闲鱼风控触发！自动冷却 {cooldown_mins:.0f} 分钟")
                    print("如需立即恢复，请输入新的 Cookie 字符串")
                    print("=" * 55)
                    new_cookie_str = input("新 Cookie (直接回车跳过): ").strip()
                    if new_cookie_str:
                        from http.cookies import SimpleCookie
                        cookie = SimpleCookie()
                        cookie.load(new_cookie_str)
                        self.session.cookies.clear()
                        for key, morsel in cookie.items():
                            self.session.cookies.set(key, morsel.value, domain='.goofish.com')
                        self.update_env_cookies()
                        self._consecutive_failures = 0
                        self._cooldown_until = 0
                        return self._call_mtop_api(api_name, version, data_val, 0, max_retries, extra_params)
                    else:
                        # 开始冷却
                        self._cooldown_until = time.time() + self.COOLDOWN_SECONDS
                        return {"error": f"风控触发: 已进入 {cooldown_mins:.0f} 分钟冷却期"}

                # 连续失败过多 → 自动冷却
                if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    logger.warning(
                        f"⚠️ 连续 {self._consecutive_failures} 次 API 失败，"
                        f"自动进入 {self.COOLDOWN_SECONDS / 60:.0f} 分钟冷却期"
                    )
                    self._cooldown_until = time.time() + self.COOLDOWN_SECONDS
                    return {"error": "连续失败过多，已进入自动冷却期"}

                logger.warning(f"API调用失败 [{api_name}]: {ret_value}")
                if 'Set-Cookie' in response.headers:
                    self.clear_duplicate_cookies()
                # 指数退避延迟已在上面处理，这里直接重试
                return self._call_mtop_api(api_name, version, data_val, retry_count + 1, max_retries, extra_params)

            # ── 成功：重置失败计数 ──
            self._consecutive_failures = 0
            return res_json

        except Exception as e:
            logger.error(f"API请求异常 [{api_name}]: {e}")
            time.sleep(0.5)
            return self._call_mtop_api(api_name, version, data_val, retry_count + 1, max_retries, extra_params)

    def clear_duplicate_cookies(self):
        """清理重复的cookies"""
        # 创建一个新的CookieJar
        new_jar = requests.cookies.RequestsCookieJar()
        
        # 记录已经添加过的cookie名称
        added_cookies = set()
        
        # 按照cookies列表的逆序遍历（最新的通常在后面）
        cookie_list = list(self.session.cookies)
        cookie_list.reverse()
        
        for cookie in cookie_list:
            # 如果这个cookie名称还没有添加过，就添加到新jar中
            if cookie.name not in added_cookies:
                new_jar.set_cookie(cookie)
                added_cookies.add(cookie.name)
                
        # 替换session的cookies
        self.session.cookies = new_jar
        
        # 更新完cookies后，更新.env文件
        self.update_env_cookies()
        
    def update_env_cookies(self):
        """更新.env文件中的COOKIES_STR"""
        try:
            # 获取当前cookies的字符串形式
            cookie_str = '; '.join([f"{cookie.name}={cookie.value}" for cookie in self.session.cookies])
            
            # 读取.env文件
            env_path = os.path.join(os.getcwd(), '.env')
            if not os.path.exists(env_path):
                logger.warning(".env文件不存在，无法更新COOKIES_STR")
                return
                
            with open(env_path, 'r', encoding='utf-8') as f:
                env_content = f.read()
                
            # 使用正则表达式替换COOKIES_STR的值
            if 'COOKIES_STR=' in env_content:
                new_env_content = re.sub(
                    r'COOKIES_STR=.*', 
                    f'COOKIES_STR={cookie_str}',
                    env_content
                )
                
                # 写回.env文件
                with open(env_path, 'w', encoding='utf-8') as f:
                    f.write(new_env_content)
                    
                logger.debug("已更新.env文件中的COOKIES_STR")
            else:
                logger.warning(".env文件中未找到COOKIES_STR配置项")
        except Exception as e:
            logger.warning(f"更新.env文件失败: {str(e)}")
        
    def hasLogin(self, retry_count=0):
        """调用hasLogin.do接口进行登录状态检查"""
        if retry_count >= 2:
            logger.error("Login检查失败，重试次数过多")
            return False
            
        try:
            url = 'https://passport.goofish.com/newlogin/hasLogin.do'
            params = {
                'appName': 'xianyu',
                'fromSite': '77'
            }
            data = {
                'hid': self.session.cookies.get('unb', ''),
                'ltl': 'true',
                'appName': 'xianyu',
                'appEntrance': 'web',
                '_csrf_token': self.session.cookies.get('XSRF-TOKEN', ''),
                'umidToken': '',
                'hsiz': self.session.cookies.get('cookie2', ''),
                'bizParams': 'taobaoBizLoginFrom=web',
                'mainPage': 'false',
                'isMobile': 'false',
                'lang': 'zh_CN',
                'returnUrl': '',
                'fromSite': '77',
                'isIframe': 'true',
                'documentReferer': 'https://www.goofish.com/',
                'defaultView': 'hasLogin',
                'umidTag': 'SERVER',
                'deviceId': self.session.cookies.get('cna', '')
            }
            
            response = self.session.post(url, params=params, data=data)
            res_json = response.json()
            
            if res_json.get('content', {}).get('success'):
                logger.debug("Login成功")
                # 清理和更新cookies
                self.clear_duplicate_cookies()
                return True
            else:
                logger.warning(f"Login失败: {res_json}")
                time.sleep(0.5)
                return self.hasLogin(retry_count + 1)
                
        except Exception as e:
            logger.error(f"Login请求异常: {str(e)}")
            time.sleep(0.5)
            return self.hasLogin(retry_count + 1)

    def get_token(self, device_id, retry_count=0):
        if retry_count >= 2:  # 最多重试3次
            logger.warning("获取token失败，尝试重新登陆")
            # 尝试通过hasLogin重新登录
            if self.hasLogin():
                logger.info("重新登录成功，重新尝试获取token")
                return self.get_token(device_id, 0)  # 重置重试次数
            else:
                logger.error("重新登录失败，Cookie已失效")
                logger.error("🔴 程序即将退出，请更新.env文件中的COOKIES_STR后重新启动")
                sys.exit(1)  # 直接退出程序

        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.taobao.idlemessage.pc.login.token',
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
            "spm_pre": "a21ybx.item.want.1.14ad3da6ALVq3n",
            "log_id": "14ad3da6ALVq3n"
        }
        data_val = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"' + device_id + '"}'
        data = {
            'data': data_val,
        }
        headers = {
            "Host": "h5api.m.goofish.com",
            "sec-ch-ua-platform": "\"Windows\"",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "accept": "application/json",
            "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Google Chrome\";v=\"146\"",
            "content-type": "application/x-www-form-urlencoded",
            "sec-ch-ua-mobile": "?0",
            "origin": "https://www.goofish.com",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://www.goofish.com/",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8,zh-TW;q=0.7,ja;q=0.6",
            "priority": "u=1, i"
        }
        # 简单获取token，信任cookies已清理干净
        token = self.session.cookies.get('_m_h5_tk', '').split('_')[0]
        
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign
        
        try:
            response = self.session.post('https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/', headers=headers, params=params, data=data)
            res_json = response.json()
            
            if isinstance(res_json, dict):
                ret_value = res_json.get('ret', [])
                # 检查ret是否包含成功信息
                if not any('SUCCESS::调用成功' in ret for ret in ret_value):
                    # 检测风控/限流错误
                    error_msg = str(ret_value)
                    if 'RGV587_ERROR' in error_msg or '被挤爆啦' in error_msg:
                        logger.error(f"❌ 触发风控: {ret_value}")
                        logger.error("🔴 系统目前无法自动解决，请进入闲鱼网页版-点击消息-过滑块-复制最新的Cookie")
                        
                        # 获取用户输入的新Cookie
                        print("\n" + "="*50)
                        new_cookie_str = input("请输入新的Cookie字符串 (复制浏览器中的完整cookie，直接回车则退出程序): ").strip()
                        print("="*50 + "\n")
                        
                        if new_cookie_str:
                            try:
                                # 解析cookie字符串并更新session
                                from http.cookies import SimpleCookie
                                cookie = SimpleCookie()
                                cookie.load(new_cookie_str)
                                
                                # 清空旧cookie并设置新cookie
                                self.session.cookies.clear()
                                for key, morsel in cookie.items():
                                    self.session.cookies.set(key, morsel.value, domain='.goofish.com')
                                
                                logger.success("✅ Cookie已更新，正在尝试重连...")
                                # 同步更新到.env文件
                                self.update_env_cookies()
                                
                                # 立即重试
                                return self.get_token(device_id, 0)
                            except Exception as e:
                                logger.error(f"Cookie解析失败: {e}")
                                sys.exit(1)
                        else:
                            logger.info("用户取消输入，程序退出")
                            sys.exit(1)

                    logger.warning(f"Token API调用失败，错误信息: {ret_value}")
                    # 处理响应中的Set-Cookie
                    if 'Set-Cookie' in response.headers:
                        logger.debug("检测到Set-Cookie，更新cookie")  # 降级为DEBUG并简化
                        self.clear_duplicate_cookies()
                    time.sleep(0.5)
                    return self.get_token(device_id, retry_count + 1)
                else:
                    logger.info("Token获取成功")
                    return res_json
            else:
                logger.error(f"Token API返回格式异常: {res_json}")
                return self.get_token(device_id, retry_count + 1)
                
        except Exception as e:
            logger.error(f"Token API请求异常: {str(e)}")
            time.sleep(0.5)
            return self.get_token(device_id, retry_count + 1)

    def get_item_info(self, item_id: str, retry_count: int = 0) -> dict:
        """获取商品信息"""
        data_val = json.dumps({"itemId": item_id})
        return self._call_mtop_api("mtop.taobao.idle.pc.detail", "1.0", data_val, retry_count=retry_count, max_retries=3)

    # ========== 商品管理 API ==========

    def list_my_items(self, page_number: int = 1, page_size: int = 20) -> dict:
        """获取我发布的商品列表

        Args:
            page_number: 页码，从1开始
            page_size: 每页数量
        """
        data_val = json.dumps({
            "needGroupInfo": False,
            "pageNumber": page_number,
            "userId": self.session.cookies.get("unb", ""),
            "pageSize": page_size,
        })
        return self._call_mtop_api(
            "mtop.idle.web.xyh.item.list", "1.0", data_val,
            extra_params={"spm_pre": "a21ybx.home.nav.1"},
        )

    def republish_item(self, item_id: str) -> dict:
        """擦亮/重新发布商品，提升曝光

        Args:
            item_id: 商品ID
        """
        data_val = json.dumps({"itemId": item_id})
        return self._call_mtop_api("mtop.taobao.idle.item.polish", "1.0", data_val)

    def search_items(self, keyword: str) -> dict:
        """搜索市场商品

        Args:
            keyword: 搜索关键词
        """
        data_val = json.dumps({
            "inputWords": keyword,
            "searchReqFromPage": "xyPcHome",
            "bucketId": 30,
            "type": 0,
        })
        return self._call_mtop_api(
            "mtop.taobao.idlemtopsearch.pc.search.suggest", "1.0", data_val,
            extra_params={"spm_pre": "a21ybx.home.searchInput.0"},
        )

    # ========== 订单管理 API ==========

    def virtual_delivery(self, biz_order_id: str) -> dict:
        """虚拟发货（无需物流）

        用于虚拟商品订单，标记为已发货/无需发货。

        Args:
            biz_order_id: 闲鱼订单ID

        Returns:
            API响应字典，成功时 ret 包含 SUCCESS
        """
        data_val = json.dumps({"bizOrderId": biz_order_id})
        return self._call_mtop_api(
            "mtop.idle.order.dummy.send", "1.0", data_val
        )

    def rate_buyer(self, biz_order_id: str, content: str = "好买家，交易愉快") -> dict:
        """卖家评价买家（好评）

        交易完成后卖家给买家好评。

        Args:
            biz_order_id: 闲鱼订单ID
            content: 评价内容

        Returns:
            API响应字典，成功时 ret 包含 SUCCESS
        """
        data_val = json.dumps({
            "bizOrderId": biz_order_id,
            "content": content,
            "score": 5,
        })
        return self._call_mtop_api(
            "mtop.idle.order.rate", "1.0", data_val
        )

    def upload_media(self, image_path: str) -> dict:
        """上传图片到闲鱼服务器，返回 {url, width, height}

        Args:
            image_path: 本地图片文件路径

        Returns:
            包含 url, width, height 的字典

        Raises:
            ValueError: 上传失败或响应格式异常时
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        params = {
            "floderId": "0",
            "appkey": "xy_chat",
            "_input_charset": "utf-8",
        }

        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/png")

        with open(image_path, 'rb') as f:
            files = {"file": (os.path.basename(image_path), f, mime_type)}
            response = self.session.post(UPLOAD_URL, params=params, files=files)

        result = response.json()

        if "object" not in result:
            error_msg = result.get("message", str(result))
            raise ValueError(f"图片上传失败: {error_msg}")

        obj = result["object"]
        url = obj["url"]
        pix = obj.get("pix", "0x0")
        parts = pix.split("x")
        width = int(parts[0]) if len(parts) >= 1 else 0
        height = int(parts[1]) if len(parts) >= 2 else 0

        logger.info(f"图片上传成功: {os.path.basename(image_path)} -> {url} ({width}x{height})")
        return {"url": url, "width": width, "height": height}
