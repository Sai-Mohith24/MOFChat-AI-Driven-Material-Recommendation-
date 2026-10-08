"""Offline tests for the multi-provider LLM layer (fake clients, no network calls).

    venv/bin/python -m pytest -q tests/test_llm.py
"""

import pytest

import mofchat  # noqa: F401
from mofchat import llm


class FakeReply:
    def __init__(self, content):
        self.content = content


class FakeClient:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    def invoke(self, messages):
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return FakeReply(self.behaviour)


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(llm, "_throttle", lambda spec, est=0: None)


def test_registry_is_consistent():
    ids = [m.model_id for m in llm.MODELS]
    assert len(ids) == len(set(ids))
    for m in llm.MODELS:
        assert m.provider in llm.PROVIDER_PACKAGE
        assert m.is_local or m.needs_key in ("GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY")
    assert {"gemini-3.5-flash", "gpt-oss-120b", "nemotron-super-free", "llama3-local"} <= set(ids)


def test_missing_key_is_reported_not_raised(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    ok, why = llm.availability("gpt-oss-120b")
    assert not ok and "GROQ_API_KEY" in why
    assert llm.availability("no-such-model") == (False, "unknown model 'no-such-model'")


def test_extract_json_handles_fences_and_chatter():
    assert llm.extract_json('{"intent": "search"}') == {"intent": "search"}
    assert llm.extract_json('```json\n{"intent": "count", "limit": 3}\n```') == {"intent": "count", "limit": 3}
    assert llm.extract_json('Sure! Here is the plan: {"a": {"b": [1, 2]}} Hope it helps.') == {"a": {"b": [1, 2]}}
    assert llm.extract_json("no json here") is None


def test_extract_text_handles_gemini_blocks_and_thinking():
    blocks = [{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Answer"}]
    assert llm.extract_text(FakeReply(blocks)) == "Answer"
    assert llm.extract_text(FakeReply("<think>reasoning</think>\n{\"x\": 1}")) == '{"x": 1}'


def test_chat_falls_back_after_rate_limit(monkeypatch):
    clients = {("gemini-3.5-flash", False): FakeClient(RuntimeError("429 RESOURCE_EXHAUSTED")),
               ("gpt-oss-120b", False): FakeClient("OK from Groq")}
    monkeypatch.setattr(llm, "_client", lambda mid, js: clients[(mid, js)])
    text, used = llm.chat([("human", "hi")], chain=["gemini-3.5-flash", "gpt-oss-120b"])
    assert (text, used) == ("OK from Groq", "gpt-oss-120b")


def test_chat_retries_without_json_mode(monkeypatch):
    clients = {("qwen3.8-27b", True): FakeClient(RuntimeError("400 response_format json_object not supported")),
               ("qwen3.8-27b", False): FakeClient('{"intent": "search"}')}
    monkeypatch.setattr(llm, "_client", lambda mid, js: clients[(mid, js)])
    text, used = llm.chat([("human", "plan")], json_mode=True, chain=["qwen3.8-27b"])
    assert used == "qwen3.8-27b" and llm.extract_json(text) == {"intent": "search"}


def test_chat_raises_when_every_model_fails(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda mid, js: FakeClient(RuntimeError("503 UNAVAILABLE")))
    with pytest.raises(llm.LLMError, match="all models failed"):
        llm.chat([("human", "hi")], chain=["gemini-3.8-flash", "gpt-oss-20b"])


def test_strict_mode_disables_fallback(monkeypatch):
    monkeypatch.setattr(llm, "available_ids", lambda: ["gpt-oss-120b", "gemini-3.5-flash", "llama3-local"])
    assert llm.fallback_chain("gemini-3.5-flash")[:2] == ["gemini-3.5-flash", "gpt-oss-120b"]
    monkeypatch.setattr(llm, "FALLBACK_ENABLED", False)
    assert llm.fallback_chain("gemini-3.5-flash") == ["gemini-3.5-flash"]
    assert llm.fallback_chain("qwen3.8-27b") == []          # not available -> nothing


def test_agent_records_the_model_that_answered(monkeypatch):
    from mofchat.agent import MOFChatAgent
    monkeypatch.setattr(llm, "available_ids", lambda: ["gpt-oss-120b"])
    monkeypatch.setattr(llm, "availability", lambda mid: (mid == "gpt-oss-120b", "ready"))
    plan_json = ('{"intent": "search", "constraints": [{"column": "Density", "op": "<", "value": 0.3}], '
                 '"objectives": [], "metals": [], "open_metal_site": null, "application": null, "gases": [], '
                 '"mof_ids": [], "aggregate": null, "limit": 2}')
    monkeypatch.setattr(llm, "_client", lambda mid, js: FakeClient(plan_json))
    agent = MOFChatAgent(use_llm=True, planner_mode="llm", model_id="gpt-oss-120b")
    plan, trace = agent.plan("Show 2 MOFs with density below 0.3")
    assert plan.constraints[0].column == "Density" and plan.limit == 2
    assert agent.last_models == ["gpt-oss-120b"] and "(gpt-oss-120b)" in trace[0]


def test_token_budget_falls_back_instead_of_waiting(monkeypatch):
    monkeypatch.undo()                                     # use the real throttle for this test
    monkeypatch.setattr(llm, "_windows", {})
    monkeypatch.setattr(llm, "MAX_WAIT_S", 0.5)
    spec = llm.BY_ID["gpt-oss-20b"]                        # 8,000 tokens per minute
    llm._throttle(spec, 5000)
    with pytest.raises(llm.RateLimited):
        llm._throttle(spec, 5000)                          # would exceed 8,000 within the minute
    clients = {("gpt-oss-20b", False): FakeClient("never called"), ("llama3-local", False): FakeClient("local OK")}
    monkeypatch.setattr(llm, "_client", lambda mid, js: clients[(mid, js)])
    text, used = llm.chat([("human", "x" * 20000)], chain=["gpt-oss-20b", "llama3-local"])
    assert used == "llama3-local"
