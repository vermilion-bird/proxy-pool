import redis
import os

_host = os.getenv("REDIS_HOST", "localhost")
_port = int(os.getenv("REDIS_PORT", "6380"))
_db = int(os.getenv("REDIS_DB", "0"))


def get_client():
    return redis.Redis(host=_host, port=_port, db=_db, decode_responses=True)