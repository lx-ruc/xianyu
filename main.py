import base64
import json
import asyncio
import time
import os
import websockets
from loguru import logger
from dotenv import load_dotenv, set_key
from XianyuApis import XianyuApis
import sys
import random
from datetime import datetime, timedelta


from utils.xianyu_utils import generate_mid, generate_uuid, trans_cookies, generate_device_id, decrypt
from XianyuAgent import XianyuReplyBot
from context_manager import ChatContextManager
from command_parser import CommandParser, HELP_TEXT


class XianyuLive:
    def __init__(self, cookies_str):
        self.xianyu = XianyuApis()
        self.base_url = 'wss://wss-goofish.dingtalk.com/'
        self.cookies_str = cookies_str
        self.cookies = trans_cookies(cookies_str)
        self.xianyu.session.cookies.update(self.cookies)  # 直接使用 session.cookies.update
        self.myid = self.cookies['unb']
        self.device_id = generate_device_id(self.myid)
        self.context_manager = ChatContextManager()
        
        # 心跳相关配置
        self.heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL", "15"))  # 心跳间隔，默认15秒
        self.heartbeat_timeout = int(os.getenv("HEARTBEAT_TIMEOUT", "5"))     # 心跳超时，默认5秒
        self.last_heartbeat_time = 0
        self.last_heartbeat_response = 0
        self.heartbeat_task = None
        self.ws = None
        
        # Token刷新相关配置
        self.token_refresh_interval = int(os.getenv("TOKEN_REFRESH_INTERVAL", "3600"))  # Token刷新间隔，默认1小时
        self.token_retry_interval = int(os.getenv("TOKEN_RETRY_INTERVAL", "300"))       # Token重试间隔，默认5分钟
        self.last_token_refresh_time = 0
        self.current_token = None
        self.token_refresh_task = None
        self.bump_task = None
        self.connection_restart_flag = False  # 连接重启标志

        # 人工接管相关配置
        self.manual_mode_conversations = set()  # 存储处于人工接管模式的会话ID
        self.manual_mode_timeout = int(os.getenv("MANUAL_MODE_TIMEOUT", "3600"))  # 人工接管超时时间，默认1小时
        self.manual_mode_timestamps = {}  # 记录进入人工模式的时间
        
        # 消息过期时间配置
        self.message_expire_time = int(os.getenv("MESSAGE_EXPIRE_TIME", "300000"))  # 消息过期时间，默认5分钟
        
        # 人工接管关键词，从环境变量读取
        self.toggle_keywords = os.getenv("TOGGLE_KEYWORDS", "。")
        
        # 模拟人工输入配置
        self.simulate_human_typing = os.getenv("SIMULATE_HUMAN_TYPING", "False").lower() == "true"

        # 指令解析器和管理员配置
        self.command_parser = CommandParser()
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        self.admin_user_ids = set(admin_ids_str.split(",")) if admin_ids_str else set()

    async def refresh_token(self):
        """刷新token"""
        try:
            logger.info("开始刷新token...")
            
            # 获取新token（如果Cookie失效，get_token会直接退出程序）
            token_result = self.xianyu.get_token(self.device_id)
            if 'data' in token_result and 'accessToken' in token_result['data']:
                new_token = token_result['data']['accessToken']
                self.current_token = new_token
                self.last_token_refresh_time = time.time()
                logger.info("Token刷新成功")
                return new_token
            else:
                logger.error(f"Token刷新失败: {token_result}")
                return None
                
        except Exception as e:
            logger.error(f"Token刷新异常: {str(e)}")
            return None

    async def token_refresh_loop(self):
        """Token刷新循环"""
        while True:
            try:
                current_time = time.time()
                
                # 检查是否需要刷新token
                if current_time - self.last_token_refresh_time >= self.token_refresh_interval:
                    logger.info("Token即将过期，准备刷新...")
                    
                    new_token = await self.refresh_token()
                    if new_token:
                        logger.info("Token刷新成功，准备重新建立连接...")
                        # 设置连接重启标志
                        self.connection_restart_flag = True
                        # 关闭当前WebSocket连接，触发重连
                        if self.ws:
                            await self.ws.close()
                        break
                    else:
                        logger.error("Token刷新失败，将在{}分钟后重试".format(self.token_retry_interval // 60))
                        await asyncio.sleep(self.token_retry_interval)  # 使用配置的重试间隔
                        continue
                
                # 每分钟检查一次
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Token刷新循环出错: {e}")
                await asyncio.sleep(60)

    async def bump_all_loop(self):
        """每天随机时间（7:30~8:00）擦亮全部商品"""
        while True:
            try:
                now = datetime.now()
                # 计算今天7:30~8:00之间的随机时间
                target_hour = 7
                target_minute = random.randint(30, 59)
                target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

                # 如果今天的随机时间已过，安排到明天
                if now >= target_time:
                    target_time = target_time + timedelta(days=1)

                wait_seconds = (target_time - now).total_seconds()
                logger.info(f"下次擦亮时间: {target_time.strftime('%Y-%m-%d %H:%M')}, 等待 {wait_seconds/60:.0f} 分钟")

                await asyncio.sleep(wait_seconds)

                # 执行擦亮
                logger.info("开始执行每日擦亮任务...")

                # 分页获取所有商品
                all_items = []
                page = 1
                while True:
                    result = self.xianyu.list_my_items(page_number=page, page_size=20)
                    card_list = result.get("data", {}).get("cardList", [])
                    if not card_list:
                        break
                    all_items.extend(card_list)
                    if len(card_list) < 20:
                        break
                    page += 1
                    await asyncio.sleep(0.5)

                if not all_items:
                    logger.info("无在售商品，跳过擦亮")
                    continue

                success_count = 0
                already_count = 0
                fail_count = 0
                for card in all_items:
                    item_id = card.get("cardData", {}).get("id", "")
                    if not item_id:
                        continue
                    bump_result = self.xianyu.republish_item(item_id)
                    ret = str(bump_result.get("ret", []))
                    if "SUCCESS" in ret:
                        success_count += 1
                    elif "POLISH_AGAIN" in ret:
                        already_count += 1
                    else:
                        fail_count += 1
                    await asyncio.sleep(random.uniform(1.5, 3.0))

                logger.info(f"每日擦亮完成: 成功{success_count}, 已擦亮{already_count}, 失败{fail_count}")

                # 等到明天再计算新的随机时间（避免重复执行）
                await asyncio.sleep(3600)

            except Exception as e:
                logger.error(f"擦亮任务出错: {e}")
                await asyncio.sleep(3600)

    async def send_msg(self, ws, cid, toid, text):
        text = {
            "contentType": 1,
            "text": {
                "text": text
            }
        }
        text_base64 = str(base64.b64encode(json.dumps(text).encode('utf-8')), 'utf-8')
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{cid}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {
                            "type": 1,
                            "data": text_base64
                        }
                    },
                    "redPointPolicy": 0,
                    "extension": {
                        "extJson": "{}"
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    },
                    "mtags": {},
                    "msgReadStatusSetting": 1
                },
                {
                    "actualReceivers": [
                        f"{toid}@goofish",
                        f"{self.myid}@goofish"
                    ]
                }
            ]
        }
        await ws.send(json.dumps(msg))

    async def send_image_msg(self, ws, cid, toid, image_info: dict):
        """发送图片消息

        Args:
            ws: WebSocket连接
            cid: 会话ID
            toid: 接收者ID
            image_info: 包含 url, width, height 的字典
        """
        image_payload = {
            "contentType": 2,
            "image": {
                "pics": [{
                    "type": 0,
                    "url": image_info["url"],
                    "width": image_info["width"],
                    "height": image_info["height"]
                }]
            }
        }
        payload_base64 = str(base64.b64encode(json.dumps(image_payload).encode('utf-8')), 'utf-8')
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{cid}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {
                            "type": 2,
                            "data": payload_base64
                        }
                    },
                    "redPointPolicy": 0,
                    "extension": {
                        "extJson": "{}"
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    },
                    "mtags": {},
                    "msgReadStatusSetting": 1
                },
                {
                    "actualReceivers": [
                        f"{toid}@goofish",
                        f"{self.myid}@goofish"
                    ]
                }
            ]
        }
        await ws.send(json.dumps(msg))
        logger.info(f"图片消息已发送: {image_info['url'][:80]}...")

    async def _send_images(self, ws, cid: str, toid: str, image_ids: list):
        """上传并发送图片，每次最多1张，避免触发风控

        Args:
            ws: WebSocket连接
            cid: 会话ID
            toid: 接收者ID
            image_ids: 要发送的图片ID列表
        """
        # 只发第一张，避免短时间内发多张图片触发风控
        image_id = image_ids[0] if image_ids else None
        if not image_id:
            return

        image_info = bot.image_config.get(image_id)
        if not image_info:
            logger.warning(f"未找到图片配置: {image_id}")
            return

        file_path = image_info.get("file", "")
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"图片文件不存在: {file_path}")
            return

        try:
            # 文本消息后等待3-5秒再发图片，模拟人工找图
            await asyncio.sleep(random.uniform(3.0, 5.0))

            # 检查缓存
            if image_id in bot._image_cache:
                upload_result = bot._image_cache[image_id]
                logger.info(f"使用缓存的图片: {image_id}")
            else:
                # 上传图片
                upload_result = self.xianyu.upload_media(file_path)
                bot._image_cache[image_id] = upload_result

            await self.send_image_msg(ws, cid, toid, upload_result)
        except Exception as e:
            logger.error(f"发送图片 {image_id} 失败: {e}")

    async def init(self, ws):
        # 如果没有token或者token过期，获取新token
        if not self.current_token or (time.time() - self.last_token_refresh_time) >= self.token_refresh_interval:
            logger.info("获取初始token...")
            await self.refresh_token()
        
        if not self.current_token:
            logger.error("无法获取有效token，初始化失败")
            raise Exception("Token获取失败")
            
        msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": self.current_token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 DingTalk(2.1.5) OS(Windows/10) Browser(Chrome/133.0.0.0) DingWeb/2.1.5 IMPaaS DingWeb/2.1.5",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": generate_mid()
            }
        }
        await ws.send(json.dumps(msg))
        # 等待一段时间，确保连接注册完成
        await asyncio.sleep(1)
        msg = {"lwp": "/r/SyncStatus/ackDiff", "headers": {"mid": "5701741704675979 0"}, "body": [
            {"pipeline": "sync", "tooLong2Tag": "PNM,1", "channel": "sync", "topic": "sync", "highPts": 0,
             "pts": int(time.time() * 1000) * 1000, "seq": 0, "timestamp": int(time.time() * 1000)}]}
        await ws.send(json.dumps(msg))
        logger.info('连接注册完成')

    def is_chat_message(self, message):
        """判断是否为用户聊天消息"""
        try:
            return (
                isinstance(message, dict) 
                and "1" in message 
                and isinstance(message["1"], dict)  # 确保是字典类型
                and "10" in message["1"]
                and isinstance(message["1"]["10"], dict)  # 确保是字典类型
                and "reminderContent" in message["1"]["10"]
            )
        except Exception:
            return False

    def is_sync_package(self, message_data):
        """判断是否为同步包消息"""
        try:
            return (
                isinstance(message_data, dict)
                and "body" in message_data
                and "syncPushPackage" in message_data["body"]
                and "data" in message_data["body"]["syncPushPackage"]
                and len(message_data["body"]["syncPushPackage"]["data"]) > 0
            )
        except Exception:
            return False

    def is_typing_status(self, message):
        """判断是否为用户正在输入状态消息"""
        try:
            return (
                isinstance(message, dict)
                and "1" in message
                and isinstance(message["1"], list)
                and len(message["1"]) > 0
                and isinstance(message["1"][0], dict)
                and "1" in message["1"][0]
                and isinstance(message["1"][0]["1"], str)
                and "@goofish" in message["1"][0]["1"]
            )
        except Exception:
            return False

    def is_system_message(self, message):
        """判断是否为系统消息"""
        try:
            return (
                isinstance(message, dict)
                and "3" in message
                and isinstance(message["3"], dict)
                and "needPush" in message["3"]
                and message["3"]["needPush"] == "false"
            )
        except Exception:
            return False
    
    def is_bracket_system_message(self, message):
        """检查是否为带中括号的系统消息"""
        try:
            if not message or not isinstance(message, str):
                return False
            
            clean_message = message.strip()
            # 检查是否以 [ 开头，以 ] 结尾
            if clean_message.startswith('[') and clean_message.endswith(']'):
                logger.debug(f"检测到系统消息: {clean_message}")
                return True
            return False
        except Exception as e:
            logger.error(f"检查系统消息失败: {e}")
            return False

    def check_toggle_keywords(self, message):
        """检查消息是否包含切换关键词"""
        message_stripped = message.strip()
        return message_stripped in self.toggle_keywords

    def is_manual_mode(self, chat_id):
        """检查特定会话是否处于人工接管模式"""
        if chat_id not in self.manual_mode_conversations:
            return False
        
        # 检查是否超时
        current_time = time.time()
        if chat_id in self.manual_mode_timestamps:
            if current_time - self.manual_mode_timestamps[chat_id] > self.manual_mode_timeout:
                # 超时，自动退出人工模式
                self.exit_manual_mode(chat_id)
                return False
        
        return True

    def enter_manual_mode(self, chat_id):
        """进入人工接管模式"""
        self.manual_mode_conversations.add(chat_id)
        self.manual_mode_timestamps[chat_id] = time.time()

    def exit_manual_mode(self, chat_id):
        """退出人工接管模式"""
        self.manual_mode_conversations.discard(chat_id)
        if chat_id in self.manual_mode_timestamps:
            del self.manual_mode_timestamps[chat_id]

    def toggle_manual_mode(self, chat_id):
        """切换人工接管模式"""
        if self.is_manual_mode(chat_id):
            self.exit_manual_mode(chat_id)
            return "auto"
        else:
            self.enter_manual_mode(chat_id)
            return "manual"
    
    def format_price(self, price):
        """
        处理逻辑：标准化价格（分转元）
        """
        try:
            return round(float(price) / 100, 2)
        except (ValueError, TypeError):
            # 遇到 None 或脏数据，默认返回 0
            return 0.0
    
    def build_item_description(self, item_info):
        """构建商品描述"""
        
        # 处理 SKU 列表
        clean_skus = []
        raw_sku_list = item_info.get('skuList', [])
        
        for sku in raw_sku_list:
            # 提取规格文本
            specs = [p['valueText'] for p in sku.get('propertyList', []) if p.get('valueText')]
            spec_text = " ".join(specs) if specs else "默认规格"
            
            clean_skus.append({
                "spec": spec_text,
                "price": self.format_price(sku.get('price', 0)),
                "stock": sku.get('quantity', 0)
            })

        # 获取价格
        valid_prices = [s['price'] for s in clean_skus if s['price'] > 0]
        
        if valid_prices:
            min_price = min(valid_prices)
            max_price = max(valid_prices)
            if min_price == max_price:
                price_display = f"¥{min_price}"
            else:
                price_display = f"¥{min_price} - ¥{max_price}" # 价格区间
        else:
            # 如果没有SKU价格，回退使用商品主价格
            main_price = round(float(item_info.get('soldPrice', 0)), 2)
            price_display = f"¥{main_price}"

        summary = {
            "title": item_info.get('title', ''),
            "desc": item_info.get('desc', ''),
            "price_range": price_display,
            "total_stock": item_info.get('quantity', 0),
            "sku_details": clean_skus
        }

        return json.dumps(summary, ensure_ascii=False)

    async def handle_message(self, message_data, websocket):
        """处理所有类型的消息"""
        try:

            try:
                message = message_data
                ack = {
                    "code": 200,
                    "headers": {
                        "mid": message["headers"]["mid"] if "mid" in message["headers"] else generate_mid(),
                        "sid": message["headers"]["sid"] if "sid" in message["headers"] else '',
                    }
                }
                if 'app-key' in message["headers"]:
                    ack["headers"]["app-key"] = message["headers"]["app-key"]
                if 'ua' in message["headers"]:
                    ack["headers"]["ua"] = message["headers"]["ua"]
                if 'dt' in message["headers"]:
                    ack["headers"]["dt"] = message["headers"]["dt"]
                await websocket.send(json.dumps(ack))
            except Exception as e:
                pass

            # 如果不是同步包消息，直接返回
            if not self.is_sync_package(message_data):
                return

            # 获取并解密数据
            sync_data = message_data["body"]["syncPushPackage"]["data"][0]
            
            # 检查是否有必要的字段
            if "data" not in sync_data:
                logger.debug("同步包中无data字段")
                return

            # 解密数据
            try:
                data = sync_data["data"]
                try:
                    data = base64.b64decode(data).decode("utf-8")
                    data = json.loads(data)
                    # logger.info(f"无需解密 message: {data}")
                    return
                except Exception as e:
                    # logger.info(f'加密数据: {data}')
                    decrypted_data = decrypt(data)
                    message = json.loads(decrypted_data)
            except Exception as e:
                logger.error(f"消息解密失败: {e}")
                return

            try:
                # 判断是否为订单消息,需要自行编写付款后的逻辑
                if message['3']['redReminder'] == '等待买家付款':
                    user_id = message['1'].split('@')[0]
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'等待买家 {user_url} 付款')
                    return
                elif message['3']['redReminder'] == '交易关闭':
                    user_id = message['1'].split('@')[0]
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'买家 {user_url} 交易关闭')
                    return
                elif message['3']['redReminder'] == '等待卖家发货':
                    user_id = message['1'].split('@')[0]
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'交易成功 {user_url} 等待卖家发货')
                    return

            except:
                pass

            # 判断消息类型
            if self.is_typing_status(message):
                logger.debug("用户正在输入")
                return
            elif not self.is_chat_message(message):
                logger.debug("其他非聊天消息")
                logger.debug(f"原始消息: {message}")
                return

            # 处理聊天消息
            create_time = int(message["1"]["5"])
            send_user_name = message["1"]["10"]["reminderTitle"]
            send_user_id = message["1"]["10"]["senderUserId"]
            send_message = message["1"]["10"]["reminderContent"]
            
            # 时效性验证（过滤5分钟前消息）
            if (time.time() * 1000 - create_time) > self.message_expire_time:
                logger.debug("过期消息丢弃")
                return
                
            # 获取商品ID和会话ID
            url_info = message["1"]["10"]["reminderUrl"]
            item_id = url_info.split("itemId=")[1].split("&")[0] if "itemId=" in url_info else None
            chat_id = message["1"]["2"].split('@')[0]
            
            if not item_id:
                logger.warning("无法获取商品ID")
                return

            # 检查是否为卖家或管理员发送的管理指令
            is_admin = send_user_id in self.admin_user_ids
            is_seller = send_user_id == self.myid

            if is_seller or is_admin:
                logger.debug(f"检测到{'管理员' if is_admin and not is_seller else '卖家'}消息，检查是否为控制命令")
                logger.info(f"消息内容: {send_message}")

                # 优先检查管理指令
                parsed = self.command_parser.parse(send_message)
                logger.info(f"指令解析结果: {parsed}")
                if parsed:
                    await self.handle_seller_command(parsed, websocket, chat_id)
                    return

                # 管理员发的非指令消息，走正常的AI回复流程（不拦截）
                if is_admin and not is_seller:
                    pass  # 继续往下走到AI回复
                else:
                    # 卖家的非指令消息处理
                    # 检查切换命令
                    if self.check_toggle_keywords(send_message):
                        mode = self.toggle_manual_mode(chat_id)
                        if mode == "manual":
                            logger.info(f"🔴 已接管会话 {chat_id} (商品: {item_id})")
                        else:
                            logger.info(f"🟢 已恢复会话 {chat_id} 的自动回复 (商品: {item_id})")
                        return

                    # 记录卖家人工回复
                    self.context_manager.add_message_by_chat(chat_id, self.myid, item_id, "assistant", send_message)
                    logger.info(f"卖家人工回复 (会话: {chat_id}, 商品: {item_id}): {send_message}")
                    return
            
            logger.info(f"用户: {send_user_name} (ID: {send_user_id}), 商品: {item_id}, 会话: {chat_id}, 消息: {send_message}")
            
            
            # 如果当前会话处于人工接管模式，不进行自动回复
            if self.is_manual_mode(chat_id):
                logger.info(f"🔴 会话 {chat_id} 处于人工接管模式，跳过自动回复")
                # 添加用户消息到上下文
                self.context_manager.add_message_by_chat(chat_id, send_user_id, item_id, "user", send_message)
                return
            # 检查是否为带中括号的系统消息
            if self.is_bracket_system_message(send_message):
                logger.info(f"检测到系统消息：'{send_message}'，跳过自动回复")
                return
            if self.is_system_message(message):
                logger.debug("系统消息，跳过处理")
                return
            # 从数据库中获取商品信息，如果不存在则从API获取并保存
            item_info = self.context_manager.get_item_info(item_id)
            if not item_info:
                logger.info(f"从API获取商品信息: {item_id}")
                api_result = self.xianyu.get_item_info(item_id)
                if 'data' in api_result and 'itemDO' in api_result['data']:
                    item_info = api_result['data']['itemDO']
                    # 保存商品信息到数据库
                    self.context_manager.save_item_info(item_id, item_info)
                else:
                    logger.warning(f"获取商品信息失败: {api_result}")
                    return
            else:
                logger.info(f"从数据库获取商品信息: {item_id}")
                
            item_description=f"当前商品的信息如下：{self.build_item_description(item_info)}"
            
            # 获取完整的对话上下文
            context = self.context_manager.get_context_by_chat(chat_id)
            # 生成回复
            reply_result = bot.generate_reply(
                send_message,
                item_description,
                context=context
            )

            bot_reply = reply_result["text"]
            image_ids = reply_result.get("images", [])

            # 检查是否需要回复
            if bot_reply == "-":
                logger.info(f"[无需回复] 用户 {send_user_name} 的消息被识别为无需回复类型")
                return

            # 添加用户消息到上下文
            self.context_manager.add_message_by_chat(chat_id, send_user_id, item_id, "user", send_message)

            # 检查是否为价格意图，如果是则增加议价次数
            if bot.last_intent == "price":
                self.context_manager.increment_bargain_count_by_chat(chat_id)
                bargain_count = self.context_manager.get_bargain_count_by_chat(chat_id)
                logger.info(f"用户 {send_user_name} 对商品 {item_id} 的议价次数: {bargain_count}")

            # 添加机器人回复到上下文
            self.context_manager.add_message_by_chat(chat_id, self.myid, item_id, "assistant", bot_reply)

            logger.info(f"机器人回复: {bot_reply}")

            # 模拟人工输入延迟
            if self.simulate_human_typing:
                # 基础延迟 0-1秒 + 每字 0.1-0.3秒
                base_delay = random.uniform(0, 1)
                typing_delay = len(bot_reply) * random.uniform(0.1, 0.3)
                total_delay = base_delay + typing_delay
                # 设置最大延迟上限，防止过长回复等待太久
                total_delay = min(total_delay, 10.0)

                logger.info(f"模拟人工输入，延迟发送 {total_delay:.2f} 秒...")
                await asyncio.sleep(total_delay)

            await self.send_msg(websocket, chat_id, send_user_id, bot_reply)

            # 发送图片消息
            if image_ids:
                await self._send_images(websocket, chat_id, send_user_id, image_ids)
            
        except Exception as e:
            logger.error(f"处理消息时发生错误: {str(e)}")
            logger.debug(f"原始消息: {message_data}")

    async def handle_seller_command(self, command, ws, chat_id: str):
        """执行卖家管理指令并回复结果

        Args:
            command: 解析后的 Command 对象
            ws: WebSocket连接
            chat_id: 会话ID
        """
        name = command.name
        args = command.args

        try:
            logger.info(f"执行指令: /{name}, 参数: {args}")

            if name == "help":
                reply = HELP_TEXT

            elif name == "items":
                reply = await self._cmd_items(args)

            elif name == "bump":
                reply = await self._cmd_bump(args)

            elif name == "bumpall":
                reply = await self._cmd_bumpall()

            elif name == "search":
                reply = await self._cmd_search(args)

            else:
                reply = f"未知指令: /{name}\n发送 /help 查看可用指令"

            await self.send_msg(ws, chat_id, self.myid, reply)
            logger.info(f"指令 /{name} 回复已发送")

        except Exception as e:
            logger.error(f"执行指令 /{name} 失败: {e}")
            await self.send_msg(ws, chat_id, self.myid, f"指令执行失败: {e}")

    # ========== 指令处理方法 ==========

    async def _cmd_items(self, args: dict) -> str:
        """处理 /items 指令"""
        page = args.get("page", 1)
        result = self.xianyu.list_my_items(page_number=page)

        if "error" in result:
            return f"获取商品列表失败: {result.get('error', '未知错误')}"

        data = result.get("data", {})
        card_list = data.get("cardList", [])
        if not card_list:
            return "暂无在售商品" if page == 1 else f"第{page}页没有商品"

        lines = [f"商品列表 (第{page}页):"]
        for i, card in enumerate(card_list, 1):
            cd = card.get("cardData", {})
            dp = cd.get("detailParams", {})
            title = dp.get("title", "未知商品")
            item_id = cd.get("id", "")
            price = dp.get("soldPrice", "?")
            lines.append(f"{i}. [{item_id}] {title} - ¥{price}")

        total = data.get("totalCount", len(card_list))
        lines.append(f"\n共 {total} 件商品，发送 /items {page + 1} 查看下一页")
        return "\n".join(lines)

    async def _cmd_bump(self, args: dict) -> str:
        """处理 /bump 指令"""
        item_id = args.get("item_id", "")
        if not item_id:
            return "用法: /bump <商品ID>"

        result = self.xianyu.republish_item(item_id)
        if "error" in result:
            return f"擦亮失败: {result.get('error', '未知错误')}"

        ret = result.get("ret", [])
        if any("SUCCESS" in r for r in ret):
            return f"擦亮成功: {item_id}"
        return f"擦亮失败: {ret}"

    async def _cmd_bumpall(self) -> str:
        """处理 /bumpall 指令"""
        result = self.xianyu.list_my_items(page_number=1, page_size=50)
        if "error" in result:
            return f"获取商品列表失败: {result.get('error', '未知错误')}"

        items = result.get("data", {}).get("resultList", [])
        if not items:
            return "暂无在售商品"

        success_count = 0
        fail_count = 0
        for item in items:
            item_id = item.get("itemId", "")
            if not item_id:
                continue
            try:
                bump_result = self.xianyu.republish_item(item_id)
                ret = bump_result.get("ret", [])
                if any("SUCCESS" in r for r in ret):
                    success_count += 1
                else:
                    fail_count += 1
                # 间隔1-2秒避免风控
                await asyncio.sleep(random.uniform(1.0, 2.0))
            except Exception:
                fail_count += 1

        return f"擦亮完成: 成功{success_count}件, 失败{fail_count}件"

    async def send_heartbeat(self, ws):
        """发送心跳包并等待响应"""
        try:
            heartbeat_mid = generate_mid()
            heartbeat_msg = {
                "lwp": "/!",
                "headers": {
                    "mid": heartbeat_mid
                }
            }
            await ws.send(json.dumps(heartbeat_msg))
            self.last_heartbeat_time = time.time()
            logger.debug("心跳包已发送")
            return heartbeat_mid
        except Exception as e:
            logger.error(f"发送心跳包失败: {e}")
            raise

    async def heartbeat_loop(self, ws):
        """心跳维护循环"""
        while True:
            try:
                current_time = time.time()
                
                # 检查是否需要发送心跳
                if current_time - self.last_heartbeat_time >= self.heartbeat_interval:
                    await self.send_heartbeat(ws)
                
                # 检查上次心跳响应时间，如果超时则认为连接已断开
                if (current_time - self.last_heartbeat_response) > (self.heartbeat_interval + self.heartbeat_timeout):
                    logger.warning("心跳响应超时，可能连接已断开")
                    break
                
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"心跳循环出错: {e}")
                break

    async def handle_heartbeat_response(self, message_data):
        """处理心跳响应"""
        try:
            if (
                isinstance(message_data, dict)
                and "headers" in message_data
                and "mid" in message_data["headers"]
                and "code" in message_data
                and message_data["code"] == 200
            ):
                self.last_heartbeat_response = time.time()
                logger.debug("收到心跳响应")
                return True
        except Exception as e:
            logger.error(f"处理心跳响应出错: {e}")
        return False

    async def main(self):
        while True:
            try:
                # 重置连接重启标志
                self.connection_restart_flag = False
                
                headers = {
                    "Cookie": self.cookies_str,
                    "Host": "wss-goofish.dingtalk.com",
                    "Connection": "Upgrade",
                    "Pragma": "no-cache",
                    "Cache-Control": "no-cache",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                    "Origin": "https://www.goofish.com",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                }

                async with websockets.connect(self.base_url, extra_headers=headers) as websocket:
                    self.ws = websocket
                    await self.init(websocket)
                    
                    # 初始化心跳时间
                    self.last_heartbeat_time = time.time()
                    self.last_heartbeat_response = time.time()
                    
                    # 启动心跳任务
                    self.heartbeat_task = asyncio.create_task(self.heartbeat_loop(websocket))
                    
                    # 启动token刷新任务
                    self.token_refresh_task = asyncio.create_task(self.token_refresh_loop())

                    # 启动每日擦亮任务
                    self.bump_task = asyncio.create_task(self.bump_all_loop())
                    
                    async for message in websocket:
                        try:
                            # 检查是否需要重启连接
                            if self.connection_restart_flag:
                                logger.info("检测到连接重启标志，准备重新建立连接...")
                                break
                                
                            message_data = json.loads(message)
                            
                            # 处理心跳响应
                            if await self.handle_heartbeat_response(message_data):
                                continue
                            
                            # 发送通用ACK响应
                            if "headers" in message_data and "mid" in message_data["headers"]:
                                ack = {
                                    "code": 200,
                                    "headers": {
                                        "mid": message_data["headers"]["mid"],
                                        "sid": message_data["headers"].get("sid", "")
                                    }
                                }
                                # 复制其他可能的header字段
                                for key in ["app-key", "ua", "dt"]:
                                    if key in message_data["headers"]:
                                        ack["headers"][key] = message_data["headers"][key]
                                await websocket.send(json.dumps(ack))
                            
                            # 处理其他消息
                            await self.handle_message(message_data, websocket)
                                
                        except json.JSONDecodeError:
                            logger.error("消息解析失败")
                        except Exception as e:
                            logger.error(f"处理消息时发生错误: {str(e)}")
                            logger.debug(f"原始消息: {message}")

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket连接已关闭")
                
            except Exception as e:
                logger.error(f"连接发生错误: {e}")
                
            finally:
                # 清理任务
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                    try:
                        await self.heartbeat_task
                    except asyncio.CancelledError:
                        pass
                        
                if self.token_refresh_task:
                    self.token_refresh_task.cancel()
                    try:
                        await self.token_refresh_task
                    except asyncio.CancelledError:
                        pass
                
                # 如果是主动重启，立即重连；否则等待5秒
                if self.connection_restart_flag:
                    logger.info("主动重启连接，立即重连...")
                else:
                    logger.info("等待5秒后重连...")
                    await asyncio.sleep(5)



def check_and_complete_env():
    """检查并补全关键环境变量"""
    # 定义关键变量及其默认无效值（占位符）
    critical_vars = {
        "API_KEY": "默认使用通义千问,apikey通过百炼模型平台获取",
        "COOKIES_STR": "your_cookies_here"
    }
    
    env_path = ".env"
    updated = False
    
    for key, placeholder in critical_vars.items():
        curr_val = os.getenv(key)
        
        # 如果变量未设置，或者值等于占位符
        if not curr_val or curr_val == placeholder:
            logger.warning(f"配置项 [{key}] 未设置或为默认值，请输入")
            while True:
                val = input(f"请输入 {key}: ").strip()
                if val:
                    # 更新当前环境
                    os.environ[key] = val
                    
                    # 尝试持久化到 .env
                    try:
                        # 如果没有.env文件，先创建
                        if not os.path.exists(env_path):
                            with open(env_path, 'w', encoding='utf-8') as f:
                                pass # Create empty file
                        
                        set_key(env_path, key, val)
                        updated = True
                    except Exception as e:
                        logger.warning(f"无法自动写入.env文件，请手动保存: {e}")
                    break
                else:
                    print(f"{key} 不能为空，请重新输入")
    
    if updated:
        logger.info("新的配置已保存/更新至 .env 文件中")


if __name__ == '__main__':
    # 加载环境变量
    if os.path.exists(".env"):
        load_dotenv()
        logger.info("已加载 .env 配置")
    
    if os.path.exists(".env.example"):
        load_dotenv(".env.example")  # 不会覆盖已存在的变量
        logger.info("已加载 .env.example 默认配置")
    
    # 配置日志级别
    log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    logger.remove()  # 移除默认handler
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    logger.info(f"日志级别设置为: {log_level}")
    
    # 交互式检查并补全配置
    check_and_complete_env()
    
    cookies_str = os.getenv("COOKIES_STR")
    bot = XianyuReplyBot()
    xianyuLive = XianyuLive(cookies_str)
    # 常驻进程
    asyncio.run(xianyuLive.main())
