import json
import logging
import re
import time
from typing import Any, Dict

from liarsdeck.agents.base_agent import Agent, RandomAgent
from liarsdeck.agents.prompt_template_v0 import GAME_RULES, PLAY_PROMPT, SPEECH_REWRITE_PROMPT
from liarsdeck.helper.log_utils import CustomLoggerAdapter, JsonFormatter


class LLMAgent(Agent):
  def __init__(self, client=None, tokenizer=None, llm=None, temperature=0.7, log_file=None, seed=None):
    self.client = client
    self.tokenizer = tokenizer
    self.llm = llm
    self.temperature = temperature
    self.fallback_agent = RandomAgent(seed=seed)
    self.has_log = log_file is not None
    if self.has_log:
      handler = logging.FileHandler(log_file)
      handler.setLevel(logging.INFO)
      handler.setFormatter(JsonFormatter())
      logger = logging.getLogger(log_file.split("/")[-1].replace(".jsonl", ""))
      logger.setLevel(logging.INFO)
      logger.addHandler(handler)
      self.logger = CustomLoggerAdapter(logger, extra={})
    self.last_prompt = ""
    self.last_response_text = ""
    self.last_latency_ms = 0

  def format_observation(self, observation: Dict[str, Any]) -> str:
    public_state = observation.get("public_state", {})
    private_state = observation.get("private_state", {})
    valid_actions = observation.get("valid_action", [])
    return PLAY_PROMPT.format(
      phase=observation.get("phase"),
      table_rank=public_state.get("table_rank"),
      pile_size=public_state.get("pile_size"),
      self_hand=private_state.get("self_hand", []),
      last_play=public_state.get("last_play"),
      valid_actions=valid_actions,
    )

  def _call_model(self, prompt: str) -> str:
    if self.client is None:
      return ""
    if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
      response = self.client.chat.completions.create(
        model=self.llm,
        temperature=self.temperature,
        messages=[
          {"role": "system", "content": GAME_RULES},
          {"role": "user", "content": prompt},
        ],
      )
      return response.choices[0].message.content or ""
    return ""

  def _parse_action(self, text: str, observation: Dict[str, Any]) -> Dict[str, Any]:
    if not text:
      return self.fallback_agent.act(observation)

    try:
      parsed = json.loads(text)
      if isinstance(parsed, dict) and "type" in parsed:
        return parsed
    except Exception:
      pass

    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
      try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict) and "type" in parsed:
          return parsed
      except Exception:
        pass

    return self.fallback_agent.act(observation)

  def act(self, observation: Dict[str, Any]):
    prompt = self.format_observation(observation)
    start = time.time()
    response_text = self._call_model(prompt)
    latency_ms = int((time.time() - start) * 1000)
    self.last_prompt = prompt
    self.last_response_text = response_text
    self.last_latency_ms = latency_ms
    selected_action = self._parse_action(response_text, observation)

    if self.has_log:
      self.logger.info(
        "llm_action",
        extra={
          "phase": observation.get("phase"),
          "prompt": prompt,
          "response": response_text,
          "selected_action": selected_action,
          "latency_ms": latency_ms,
          "gen_times": 1,
          "obs_message": observation.get("phase"),
        },
      )
    return selected_action

  def generate_speech(
    self,
    observation: Dict[str, Any],
    planned_action: Dict[str, Any],
    reasoning_trace: str = "",
    max_chars: int = 180,
  ) -> str:
    public_state = observation.get("public_state", {})
    private_state = observation.get("private_state", {})
    prompt = SPEECH_REWRITE_PROMPT.format(
      phase=observation.get("phase"),
      table_rank=public_state.get("table_rank"),
      pile_size=public_state.get("pile_size"),
      last_play=public_state.get("last_play"),
      planned_action=planned_action,
      self_hand=private_state.get("self_hand", []),
      reasoning_trace=reasoning_trace or self.last_response_text or "",
      max_chars=max_chars,
    )
    speech = self._call_model(prompt).strip()
    if not speech:
      action_type = planned_action.get("type", "play")
      if action_type == "call_liar":
        speech = "I am challenging this claim."
      else:
        speech = "I make a steady play this turn."
    if len(speech) > max_chars:
      speech = speech[:max_chars].rstrip()
    return speech
