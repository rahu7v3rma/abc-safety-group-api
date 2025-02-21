import os

from src.modules.training_connect import TrainingConnect
from src.utils.log_handler import get_logger
from src.utils.redis_handler import RedisClient

log = get_logger(
    logger_name=os.getenv("LOGGER_NAME", "LMS_API"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
)
log.info("starting up app")

redis_client = RedisClient()
img_handler = RedisClient(db=1)
training_connect = TrainingConnect()
