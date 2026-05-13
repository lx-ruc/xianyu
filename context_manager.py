import sqlite3
import os
import json
from datetime import datetime
from loguru import logger


class ChatContextManager:
    """
    聊天上下文管理器
    
    负责存储和检索用户与商品之间的对话历史，使用SQLite数据库进行持久化存储。
    支持按会话ID检索对话历史，以及议价次数统计。
    """
    
    def __init__(self, max_history=100, db_path="data/chat_history.db"):
        """
        初始化聊天上下文管理器
        
        Args:
            max_history: 每个对话保留的最大消息数
            db_path: SQLite数据库文件路径
        """
        self.max_history = max_history
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """初始化数据库表结构"""
        # 确保数据库目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建消息表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            chat_id TEXT
        )
        ''')
        
        # 检查是否需要添加chat_id字段（兼容旧数据库）
        cursor.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'chat_id' not in columns:
            cursor.execute('ALTER TABLE messages ADD COLUMN chat_id TEXT')
            logger.info("已为messages表添加chat_id字段")
        
        # 创建索引以加速查询
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_user_item ON messages (user_id, item_id)
        ''')
        
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_chat_id ON messages (chat_id)
        ''')
        
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_timestamp ON messages (timestamp)
        ''')
        
        # 创建基于会话ID的议价次数表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_bargain_counts (
            chat_id TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 创建商品信息表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            price REAL,
            description TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 创建订单表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            biz_order_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            item_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            delivery_result TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            delivered_at DATETIME
        )
        ''')

        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status)
        ''')

        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_orders_created ON orders (created_at)
        ''')

        conn.commit()
        conn.close()
        logger.info(f"聊天历史数据库初始化完成: {self.db_path}")

    def _ensure_analytics_tables(self, conn):
        """确保分析和日志表存在"""
        cursor = conn.cursor()

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            inquiries INTEGER DEFAULT 0,
            favorites INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            snapshot_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_analytics_item_time
        ON item_analytics (item_id, snapshot_time)
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS command_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT NOT NULL,
            args TEXT,
            result TEXT,
            success INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        conn.commit()
        

            
    def save_item_info(self, item_id, item_data):
        """
        保存商品信息到数据库
        
        Args:
            item_id: 商品ID
            item_data: 商品信息字典
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 从商品数据中提取有用信息
            price = float(item_data.get('soldPrice', 0))
            description = item_data.get('desc', '')
            
            # 将整个商品数据转换为JSON字符串
            data_json = json.dumps(item_data, ensure_ascii=False)
            
            cursor.execute(
                """
                INSERT INTO items (item_id, data, price, description, last_updated) 
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(item_id) 
                DO UPDATE SET data = ?, price = ?, description = ?, last_updated = ?
                """,
                (
                    item_id, data_json, price, description, datetime.now().isoformat(),
                    data_json, price, description, datetime.now().isoformat()
                )
            )
            
            conn.commit()
            logger.debug(f"商品信息已保存: {item_id}")
        except Exception as e:
            logger.error(f"保存商品信息时出错: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def get_item_info(self, item_id):
        """
        从数据库获取商品信息
        
        Args:
            item_id: 商品ID
            
        Returns:
            dict: 商品信息字典，如果不存在返回None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT data FROM items WHERE item_id = ?",
                (item_id,)
            )
            
            result = cursor.fetchone()
            if result:
                return json.loads(result[0])
            return None
        except Exception as e:
            logger.error(f"获取商品信息时出错: {e}")
            return None
        finally:
            conn.close()

    def add_message_by_chat(self, chat_id, user_id, item_id, role, content):
        """
        基于会话ID添加新消息到对话历史
        
        Args:
            chat_id: 会话ID
            user_id: 用户ID (用户消息存真实user_id，助手消息存卖家ID)
            item_id: 商品ID
            role: 消息角色 (user/assistant)
            content: 消息内容
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 插入新消息，使用chat_id作为额外标识
            cursor.execute(
                "INSERT INTO messages (user_id, item_id, role, content, timestamp, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, item_id, role, content, datetime.now().isoformat(), chat_id)
            )
            
            # 检查是否需要清理旧消息（基于chat_id）
            cursor.execute(
                """
                SELECT id FROM messages 
                WHERE chat_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?, 1
                """, 
                (chat_id, self.max_history)
            )
            
            oldest_to_keep = cursor.fetchone()
            if oldest_to_keep:
                cursor.execute(
                    "DELETE FROM messages WHERE chat_id = ? AND id < ?",
                    (chat_id, oldest_to_keep[0])
                )
            
            conn.commit()
        except Exception as e:
            logger.error(f"添加消息到数据库时出错: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_context_by_chat(self, chat_id):
        """
        基于会话ID获取对话历史
        
        Args:
            chat_id: 会话ID
            
        Returns:
            list: 包含对话历史的列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                SELECT role, content FROM messages 
                WHERE chat_id = ? 
                ORDER BY timestamp ASC
                LIMIT ?
                """, 
                (chat_id, self.max_history)
            )
            
            messages = [{"role": role, "content": content} for role, content in cursor.fetchall()]
            
            # 获取议价次数并添加到上下文中
            bargain_count = self.get_bargain_count_by_chat(chat_id)
            if bargain_count > 0:
                messages.append({
                    "role": "system", 
                    "content": f"议价次数: {bargain_count}"
                })
            
        except Exception as e:
            logger.error(f"获取对话历史时出错: {e}")
            messages = []
        finally:
            conn.close()
        
        return messages

    def increment_bargain_count_by_chat(self, chat_id):
        """
        基于会话ID增加议价次数
        
        Args:
            chat_id: 会话ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 使用UPSERT语法直接基于chat_id增加议价次数
            cursor.execute(
                """
                INSERT INTO chat_bargain_counts (chat_id, count, last_updated)
                VALUES (?, 1, ?)
                ON CONFLICT(chat_id) 
                DO UPDATE SET count = count + 1, last_updated = ?
                """,
                (chat_id, datetime.now().isoformat(), datetime.now().isoformat())
            )
            
            conn.commit()
            logger.debug(f"会话 {chat_id} 议价次数已增加")
        except Exception as e:
            logger.error(f"增加议价次数时出错: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_bargain_count_by_chat(self, chat_id):
        """
        基于会话ID获取议价次数
        
        Args:
            chat_id: 会话ID
            
        Returns:
            int: 议价次数
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT count FROM chat_bargain_counts WHERE chat_id = ?",
                (chat_id,)
            )
            
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"获取议价次数时出错: {e}")
            return 0
        finally:
            conn.close()

    # ========== 数据分析与指令日志 ==========

    def save_analytics_snapshot(self, item_id: str, views: int = 0,
                                inquiries: int = 0, favorites: int = 0,
                                shares: int = 0) -> None:
        """保存商品数据快照，用于趋势分析"""
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_analytics_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO item_analytics (item_id, views, inquiries, favorites, shares, snapshot_time) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (item_id, views, inquiries, favorites, shares, datetime.now().isoformat()),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"保存数据快照出错: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_analytics_trend(self, item_id: str, hours: int = 24) -> list:
        """查询商品数据趋势

        Returns:
            list of dict: [{snapshot_time, views, inquiries, favorites, shares}, ...]
        """
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_analytics_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT views, inquiries, favorites, shares, snapshot_time "
                "FROM item_analytics WHERE item_id = ? "
                "AND snapshot_time >= datetime('now', ?) "
                "ORDER BY snapshot_time ASC",
                (item_id, f"-{hours} hours"),
            )
            rows = cursor.fetchall()
            return [
                {
                    "views": r[0], "inquiries": r[1],
                    "favorites": r[2], "shares": r[3],
                    "snapshot_time": r[4],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"查询数据趋势出错: {e}")
            return []
        finally:
            conn.close()

    def log_command(self, command: str, args: str, result: str, success: bool) -> None:
        """记录指令执行日志"""
        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_analytics_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO command_log (command, args, result, success, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (command, args, result, int(success), datetime.now().isoformat()),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"记录指令日志出错: {e}")
            conn.rollback()
        finally:
            conn.close()

    # ========== 订单管理 ==========

    def save_order(
        self,
        biz_order_id: str,
        user_id: str,
        item_id: str | None = None,
        status: str = "pending",
        delivery_result: str | None = None,
    ) -> None:
        """保存或更新订单记录

        Args:
            biz_order_id: 闲鱼订单ID
            user_id: 买家用户ID
            item_id: 商品ID
            status: 订单状态 (pending/delivered/failed)
            delivery_result: 发货API返回结果
        """
        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.now().isoformat()
            delivered_at = now if status == "delivered" else None
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO orders (biz_order_id, user_id, item_id, status, delivery_result, created_at, delivered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(biz_order_id)
                DO UPDATE SET status = ?, delivery_result = ?, delivered_at = ?
                """,
                (
                    biz_order_id, user_id, item_id, status, delivery_result, now, delivered_at,
                    status, delivery_result, delivered_at,
                ),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"保存订单记录出错: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_recent_orders(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """查询最近的订单记录

        Args:
            limit: 返回数量
            offset: 偏移量

        Returns:
            订单字典列表
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT biz_order_id, user_id, item_id, status, delivery_result, created_at, delivered_at "
                "FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()
            return [
                {
                    "biz_order_id": r[0],
                    "user_id": r[1],
                    "item_id": r[2],
                    "status": r[3],
                    "delivery_result": r[4],
                    "created_at": r[5],
                    "delivered_at": r[6],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"查询订单记录出错: {e}")
            return []
        finally:
            conn.close()

    def get_order_stats(self) -> dict:
        """获取订单统计信息"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            today = datetime.now().strftime("%Y-%m-%d")

            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT status, COUNT(*) FROM orders GROUP BY status",
            )
            by_status = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT COUNT(*) FROM orders WHERE date(created_at) = ?",
                (today,),
            )
            today_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM orders WHERE status = 'delivered' AND date(delivered_at) = ?",
                (today,),
            )
            today_delivered = cursor.fetchone()[0]

            return {
                "total": total,
                "pending": by_status.get("pending", 0),
                "delivered": by_status.get("delivered", 0),
                "failed": by_status.get("failed", 0),
                "rated": by_status.get("rated", 0),
                "rate_failed": by_status.get("rate_failed", 0),
                "today_count": today_count,
                "today_delivered": today_delivered,
            }
        except Exception as e:
            logger.error(f"获取订单统计出错: {e}")
            return {
                "total": 0, "pending": 0, "delivered": 0,
                "failed": 0, "rated": 0, "rate_failed": 0,
                "today_count": 0, "today_delivered": 0,
            }
        finally:
            conn.close() 