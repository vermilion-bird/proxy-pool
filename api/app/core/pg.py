"""PostgreSQL 连接管理（审计历史存储）。

配置（环境变量）：
  PG_ENABLED    是否启用审计落库（默认 0；启用后历史写入 PostgreSQL）
  PG_HOST       数据库主机（默认 localhost）
  PG_PORT       数据库端口（默认 5432）
  PG_DB         数据库名（默认 proxy_pool）
  PG_USER       用户名（默认 proxy_pool）
  PG_PASSWORD   密码（默认空）
"""

import logging
import os

logger = logging.getLogger("proxy-pool")


def pg_enabled() -> bool:
    return os.getenv("PG_ENABLED", "0") == "1"


def pg_config() -> dict:
    return {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "dbname": os.getenv("PG_DB", "proxy_pool"),
        "user": os.getenv("PG_USER", "proxy_pool"),
        "password": os.getenv("PG_PASSWORD", ""),
    }


def get_connection():
    """创建 psycopg2 连接；失败时抛异常由调用方捕获。"""
    import psycopg2

    return psycopg2.connect(**pg_config())
