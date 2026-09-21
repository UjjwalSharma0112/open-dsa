import sys
import types as _pytypes

import pytest

from opendsa.adapters import gemini

RESPONSE_TEXT = "resp-text"


def install_fake_sdk(monkeypatch, chunks: list[str] | None = None):
    """Inject fake google.genai modules and reset adapter-level caches."""
    google_mod = _pytypes.ModuleType("google")
    genai_mod = _pytypes.ModuleType("google.genai")
    types_mod = _pytypes.ModuleType("google.genai.types")
    google_mod.genai = genai_mod

    calls: dict = {"clients": [], "generations": [], "streams": []}

    class Part:
        def __init__(self, text=None):
            self.text = text

    class Content:
        def __init__(self, role=None, parts=None):
            self.role = role
            self.parts = parts or []

    class Response:
        def __init__(self, text):
            self.text = text

    class Models:
        def generate_content(self, **kw):
            calls["generations"].append(kw)
            return Response(text=RESPONSE_TEXT)

        def generate_content_stream(self, **kw):
            calls["streams"].append(kw)
            for c in chunks or ["chunk-a", "chunk-b"]:
                yield Response(text=c)

    class FakeClient:
        def __init__(self, **kw):
            self.api_key = kw.get("api_key")
            self.models = Models()
            calls["clients"].append((self.api_key, self.models))

    genai_mod.Client = FakeClient
    types_mod.Part = Part
    types_mod.Content = Content
    types_mod.GenerateContentConfig = object

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_mod)
    monkeypatch.setattr(gemini, "_genai", None)
    monkeypatch.setattr(gemini, "_types", None)
    monkeypatch.setattr(gemini, "_clients", {})
    return calls


@pytest.fixture
def fake_sdk(monkeypatch):
    return install_fake_sdk(monkeypatch)


def test_generate_wire_format(fake_sdk) -> None:
    adapter = gemini.GeminiAdapter(model="m1", api_key="k1")
    out = adapter.generate(
        system="SYSTEM",
        history=[
            {"role": "assistant", "content": "question"},
            {"role": "user", "content": "answer"},
        ],
    )
    assert out == RESPONSE_TEXT
    api_key, models = fake_sdk["clients"][0]
    assert api_key == "k1"
    call = fake_sdk["generations"][0]
    assert call["model"] == "m1"
    assert call["config"] == {"system_instruction": "SYSTEM"}
    roles = [c.role for c in call["contents"]]
    assert roles == ["model", "user"]
    assert call["contents"][0].parts[0].text == "question"


def test_model_from_env_precedence(monkeypatch, fake_sdk) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    adapter = gemini.GeminiAdapter(model="ignored", api_key="k")
    assert adapter.model == "gemini-2.5-pro"


def test_model_falls_back_to_arg(monkeypatch, fake_sdk) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    adapter = gemini.GeminiAdapter(model="gemini-x", api_key="k")
    assert adapter.model == "gemini-x"


def test_model_default_when_nothing_set(monkeypatch, fake_sdk) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    adapter = gemini.GeminiAdapter(api_key="k")
    assert adapter.model == gemini.DEFAULT_MODEL


def test_key_from_env(monkeypatch, fake_sdk) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "x")
    monkeypatch.setenv("GOOGLE_API_KEY", "env-key")
    adapter = gemini.GeminiAdapter()
    assert adapter._api_key == "env-key"


def test_missing_api_key_raises(monkeypatch, fake_sdk) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    adapter = gemini.GeminiAdapter(api_key=None)
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        adapter.generate("s", [{"role": "user", "content": "c"}])


def test_stream_yields_chunks(fake_sdk) -> None:
    adapter = gemini.GeminiAdapter(model="m", api_key="k")
    chunks: list[str] = list(
        adapter.stream("s", [{"role": "user", "content": "c"}])
    )
    assert chunks == ["chunk-a", "chunk-b"]
    assert fake_sdk["streams"][0]["model"] == "m"


def test_client_cached_by_api_key(fake_sdk) -> None:
    a1 = gemini.GeminiAdapter(model="m", api_key="same")
    a2 = gemini.GeminiAdapter(model="m", api_key="same")
    a1.generate("s", [])
    a2.generate("s", [])
    assert len(fake_sdk["clients"]) == 1


def test_empty_response_raises(monkeypatch) -> None:
    install_fake_sdk(monkeypatch)
    genai_mod = sys.modules["google.genai"]

    class EmptyModels:
        def generate_content(self, **kw):
            class R:
                text = None

            return R()

    class EmptyClient:
        def __init__(self, **kw):
            self.models = EmptyModels()

    genai_mod.Client = EmptyClient
    monkeypatch.setattr(gemini, "_clients", {})

    adapter = gemini.GeminiAdapter(model="m", api_key="k")
    with pytest.raises(RuntimeError, match="empty response"):
        adapter.generate("s", [{"role": "user", "content": "c"}])