import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class Log:
	viewer: list
	source: int
	target: Any
	content: Dict[str, Any]
	day: int
	time: str
	event: str


class JsonFormatter(logging.Formatter):
	def format(self, record: logging.LogRecord) -> str:
		log_record = record.__dict__.copy()
		non_custom_fields = [
			"name",
			"msg",
			"args",
			"levelname",
			"levelno",
			"pathname",
			"filename",
			"module",
			"exc_info",
			"exc_text",
			"stack_info",
			"lineno",
			"funcName",
			"created",
			"msecs",
			"relativeCreated",
			"thread",
			"threadName",
			"processName",
			"process",
			"message",
		]
		for field in non_custom_fields:
			log_record.pop(field, None)

		log_record["message"] = record.getMessage()
		return json.dumps(log_record, ensure_ascii=False)


class CustomLoggerAdapter(logging.LoggerAdapter):
	def process(self, msg, kwargs):
		if "extra" not in kwargs:
			kwargs["extra"] = {}
		kwargs["extra"].update(self.extra)
		return msg, kwargs


def ensure_parent(path: Path) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: str, payload: Dict[str, Any]) -> None:
	path_obj = Path(path)
	ensure_parent(path_obj)
	with path_obj.open("w", encoding="utf-8") as file:
		json.dump(payload, file, ensure_ascii=False, indent=2)


def append_jsonl(path: str, payload: Dict[str, Any]) -> None:
	path_obj = Path(path)
	ensure_parent(path_obj)
	with path_obj.open("a", encoding="utf-8") as file:
		file.write(json.dumps(payload, ensure_ascii=False) + "\n")
