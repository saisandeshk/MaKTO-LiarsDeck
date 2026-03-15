from typing import Any, Dict, Optional, Tuple

from liarsdeck.agents import GPTAgent, HumanAgent, MaKTOAgent, SFTAgent

try:
	import openai
except Exception:  # pragma: no cover
	openai = None


class Registry:
	def __init__(self, name: str):
		self.name = name
		self.entries: Dict[str, Any] = {}

	def register(self, keys):
		def decorator(cls):
			for key in keys:
				if key in self.entries:
					raise ValueError(f"{key} already registered in {self.name}")
				self.entries[key] = cls
			return cls

		return decorator

	def build_client(self, model_type: str, model_params: Dict[str, Any]):
		if openai is None:
			return None

		lower = model_type.lower()
		if "gpt" in lower or "o1" in lower:
			api_key = model_params.get("api_key")
			base_url = model_params.get("base_url")
			if api_key and base_url:
				return openai.OpenAI(api_key=api_key, base_url=base_url)
			return None

		if "sft" in lower or "makto" in lower:
			port = model_params.get("port", 8000)
			ip = model_params.get("ip", "localhost")
			return openai.OpenAI(api_key="EMPTY", base_url=f"http://{ip}:{port}/v1")

		return None

	def build_agent(
		self,
		model_type: str,
		model_params: Dict[str, Any],
		log_file: Optional[str] = None,
	):
		if model_type not in self.entries:
			raise ValueError(f"{model_type} not registered in {self.name}")

		cls = self.entries[model_type]
		if cls is HumanAgent:
			return cls()

		client = self.build_client(model_type=model_type, model_params=model_params)
		return cls(
			client=client,
			tokenizer=model_params.get("tokenizer"),
			llm=model_params.get("llm", model_type),
			temperature=model_params.get("temperature", 0.7),
			log_file=log_file,
			seed=model_params.get("seed"),
		)


AGENT_REGISTRY = Registry(name="liarsdeck_agent")
AGENT_REGISTRY.entries = {
	"gpt": GPTAgent,
	"human": HumanAgent,
	"sft_agent": SFTAgent,
	"makto_agent": MaKTOAgent,
}
