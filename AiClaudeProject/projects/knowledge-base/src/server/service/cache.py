"""Redis 短 TTL 缓存层

职责：对高频读低频写的查询结果做短时间缓存（5-30秒），
避免每次请求都打 DB。写操作后主动失效相关缓存键。

缓存策略：
  - 列表/统计：TTL 10s（允许短暂不一致，用户无感知）
  - Dashboard：TTL 30s（统计数字容忍延迟）
  - 搜索联想：不缓存（实时性要求高）
  - 写操作后：主动删除相关缓存键（保证写后立即读一致）

降级：Redis 不可用时自动降级为直查 DB，零风险。
"""
import json
import logging

from config import settings

_redis = None


def get_redis():
    """获取 Redis 连接（单例，首次调用时初始化）

    Redis 不可用时返回 None，调用方应降级为无缓存。
    """
    global _redis
    if _redis is None:
        try:
            import redis as _redis_lib
            _redis = _redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
            _redis.ping()  # 验证连接
        except Exception:
            _redis = None
            logging.getLogger(__name__).warning("Redis 不可用，降级为无缓存模式")
    return _redis


def cache_get(key: str):
    """读缓存，返回反序列化后的 Python 对象；未命中或 Redis 不可用返回 None"""
    r = get_redis()
    if not r:
        return None
    try:
        val = r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


def cache_set(key: str, value, ttl: int = 10):
    """写缓存（带 TTL）；Redis 不可用时静默跳过"""
    r = get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(value, ensure_ascii=False))
    except Exception:
        pass


def cache_delete(*keys):
    """删除缓存键；Redis 不可用时静默跳过"""
    r = get_redis()
    if not r:
        return
    try:
        if keys:
            r.delete(*keys)
    except Exception:
        pass


# ══════ 缓存键命名空间 ══════
KEY_DOCS_LIST = "kb:docs:list"         # 文档列表
KEY_FAQ_LIST = "kb:faq:list"           # FAQ 列表
KEY_DASHBOARD = "kb:dashboard"         # 仪表盘
KEY_STATS = "kb:stats"                 # 系统统计
KEY_RECENT = "kb:recent"               # 最近更新
KEY_COUNTS = "kb:counts"               # 各表计数

# 写操作后需失效的缓存组
DOCS_WRITE_KEYS = (KEY_DOCS_LIST, KEY_DASHBOARD, KEY_STATS, KEY_COUNTS, KEY_RECENT)
FAQ_WRITE_KEYS = (KEY_FAQ_LIST, KEY_DASHBOARD, KEY_STATS, KEY_COUNTS, KEY_RECENT)
KEYWORD_WRITE_KEYS = (KEY_DASHBOARD, KEY_STATS, KEY_COUNTS)
