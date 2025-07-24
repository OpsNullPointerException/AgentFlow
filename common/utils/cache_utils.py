import json
import pickle
import hashlib
import time
import functools
from typing import Any, Optional, Union, Callable, Dict, List, Tuple
from django.core.cache import cache
from loguru import logger


class RedisCache:
    """
    Redis缓存工具类，提供便捷的缓存操作方法
    """
    
    @staticmethod
    def get_cache_key(prefix: str, *args, **kwargs) -> str:
        """
        生成缓存键
        
        Args:
            prefix: 键前缀
            *args, **kwargs: 用于生成唯一键的参数
            
        Returns:
            str: 缓存键名
        """
        # 将所有参数转为字符串后拼接
        key_parts = [str(arg) for arg in args]
        key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])
        
        # 生成参数的哈希值
        if key_parts:
            args_hash = hashlib.md5(":".join(key_parts).encode()).hexdigest()
            return f"{prefix}:{args_hash}"
        return prefix
    
    @staticmethod
    def set(key: str, value: Any, timeout: Optional[int] = None) -> bool:
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值，支持任何可序列化对象
            timeout: 过期时间(秒)，None表示使用默认过期时间
            
        Returns:
            bool: 是否成功设置
        """
        try:
            cache.set(key, value, timeout)
            return True
        except Exception as e:
            logger.warning(f"设置缓存失败 - 键:{key}, 错误:{str(e)}")
            return False
    
    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """
        获取缓存
        
        Args:
            key: 缓存键
            default: 默认值，当缓存不存在时返回
            
        Returns:
            缓存值或默认值
        """
        try:
            value = cache.get(key, default)
            return value
        except Exception as e:
            logger.warning(f"获取缓存失败 - 键:{key}, 错误:{str(e)}")
            return default
    
    @staticmethod
    def delete(key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否成功删除
        """
        try:
            cache.delete(key)
            return True
        except Exception as e:
            logger.warning(f"删除缓存失败 - 键:{key}, 错误:{str(e)}")
            return False
    
    @staticmethod
    def exists(key: str) -> bool:
        """
        检查缓存是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否存在
        """
        return RedisCache.get(key, None) is not None
    
    @staticmethod
    def increment(key: str, amount: int = 1) -> int:
        """
        递增缓存值
        
        Args:
            key: 缓存键
            amount: 增加量
            
        Returns:
            int: 增加后的值
        """
        try:
            return cache.incr(key, amount)
        except Exception as e:
            logger.warning(f"递增缓存失败 - 键:{key}, 错误:{str(e)}")
            return 0
    
    @staticmethod
    def decrement(key: str, amount: int = 1) -> int:
        """
        递减缓存值
        
        Args:
            key: 缓存键
            amount: 减少量
            
        Returns:
            int: 减少后的值
        """
        try:
            return cache.decr(key, amount)
        except Exception as e:
            logger.warning(f"递减缓存失败 - 键:{key}, 错误:{str(e)}")
            return 0
    
    @staticmethod
    def clear_pattern(pattern: str) -> int:
        """
        清除匹配模式的所有缓存
        
        Args:
            pattern: 键模式，例如"user:*"
            
        Returns:
            int: 清除的缓存数量
        """
        try:
            # 获取Redis连接
            client = cache.client.get_client()
            keys = client.keys(f"*{cache.key_prefix}:{pattern}*")
            if keys:
                client.delete(*keys)
                return len(keys)
            return 0
        except Exception as e:
            logger.warning(f"清除缓存模式失败 - 模式:{pattern}, 错误:{str(e)}")
            return 0
    
    @staticmethod
    def get_redis_client():
        """
        获取原始Redis客户端连接
        
        Returns:
            Redis客户端对象
        """
        try:
            return cache.client.get_client()
        except Exception as e:
            logger.error(f"获取Redis客户端失败: {str(e)}")
            raise
    
    @staticmethod
    def publish(channel: str, message: Any) -> int:
        """
        发布消息到指定频道
        
        Args:
            channel: 频道名称
            message: 要发布的消息(可以是任何可序列化对象)
            
        Returns:
            int: 接收到消息的客户端数量
        """
        try:
            client = RedisCache.get_redis_client()
            return client.publish(channel, message)
        except Exception as e:
            logger.error(f"发布消息失败 - 频道:{channel}, 错误:{str(e)}")
            return 0
    
    @staticmethod
    def get_pubsub():
        """
        获取Redis的发布订阅对象
        
        Returns:
            PubSub对象，用于订阅频道和接收消息
        """
        try:
            client = RedisCache.get_redis_client()
            return client.pubsub()
        except Exception as e:
            logger.error(f"获取PubSub对象失败: {str(e)}")
            raise


def cached(prefix: str, timeout: Optional[int] = None, key_func: Optional[Callable] = None):
    """
    函数结果缓存装饰器
    
    Args:
        prefix: 缓存键前缀
        timeout: 过期时间(秒)
        key_func: 自定义键生成函数
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(prefix, *args, **kwargs)
            else:
                cache_key = RedisCache.get_cache_key(prefix, *args, **kwargs)
            
            # 尝试从缓存获取
            result = RedisCache.get(cache_key)
            
            if result is None:
                # 缓存未命中，执行函数
                start_time = time.time()
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                # 缓存结果
                RedisCache.set(cache_key, result, timeout)
                logger.debug(f"缓存未命中 - 键:{cache_key}, 计算耗时:{duration:.4f}秒")
            else:
                logger.debug(f"缓存命中 - 键:{cache_key}")
            
            return result
        return wrapper
    return decorator


def timed_lru_cache(seconds: int = 600):
    """
    基于内存的函数结果缓存装饰器(不依赖Redis)
    
    Args:
        seconds: 过期时间(秒)
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        # 缓存存储
        cache_dict = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key_parts = [str(arg) for arg in args]
            key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])
            key = f"{func.__name__}:{':'.join(key_parts)}"
            
            # 检查缓存是否存在且未过期
            current_time = time.time()
            if key in cache_dict and current_time < cache_dict[key]["expiry"]:
                return cache_dict[key]["value"]
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache_dict[key] = {
                "value": result,
                "expiry": current_time + seconds
            }
            
            # 清理过期缓存
            expired_keys = [k for k, v in cache_dict.items() if current_time >= v["expiry"]]
            for expired_key in expired_keys:
                cache_dict.pop(expired_key, None)
                
            return result
        return wrapper
    return decorator