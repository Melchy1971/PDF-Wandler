import json
import logging
import sys


class JsonHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        msg = {
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            msg["exc_info"] = logging.Formatter().formatException(record.exc_info)
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")


def setup(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(JsonHandler())
