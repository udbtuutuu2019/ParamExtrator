"""Task 3.1 LLMClient / provider 单元测试（RED 先行）。"""
from param_extractor.extraction.client import LLMClient, LLMResponse
from param_extractor.extraction.provider import InstructorClient


class _FakeMsg:
    content = '{"ok": true}'


class _FakeChoice:
    message = _FakeMsg()
    finish_reason = "stop"


class _FakeRaw:
    choices = [_FakeChoice()]


class _FakeParsed:
    def model_dump_json(self):
        return '{"parsed": true}'


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    def create_with_completion(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeParsed(), _FakeRaw()


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeInstructor:
    def __init__(self):
        self.chat = _FakeChat()


def test_extract_passes_max_retries_zero():
    fake = _FakeInstructor()
    InstructorClient(fake, model="deepseek-chat").extract(
        [{"role": "user", "content": "hi"}], temperature=0.0)
    call = fake.chat.completions.calls[0]
    assert call["max_retries"] == 0
    assert call["model"] == "deepseek-chat"
    assert call["temperature"] == 0.0


def test_extract_returns_raw_content_and_finish_reason():
    fake = _FakeInstructor()
    resp = InstructorClient(fake, model="deepseek-chat").extract(
        [{"role": "user", "content": "hi"}])
    assert isinstance(resp, LLMResponse)
    assert resp.content == '{"ok": true}'
    assert resp.finish_reason == "stop"


def test_instructor_client_satisfies_protocol():
    assert isinstance(InstructorClient(_FakeInstructor(), model="m"), LLMClient)


def test_llm_response_defaults():
    assert LLMResponse(content="x").finish_reason is None


class _FakeFunction:
    arguments = '{"from": "tool_call"}'


class _FakeToolCall:
    function = _FakeFunction()


class _FakeMsgTool:
    content = None
    tool_calls = [_FakeToolCall()]


class _FakeChoiceTool:
    message = _FakeMsgTool()
    finish_reason = "tool_calls"


class _FakeRawTool:
    choices = [_FakeChoiceTool()]


class _FakeCompletionsTool:
    def create_with_completion(self, **kwargs):
        return _FakeParsed(), _FakeRawTool()


class _FakeChatTool:
    completions = _FakeCompletionsTool()


class _FakeInstructorTool:
    chat = _FakeChatTool()


def test_extract_reads_tool_call_arguments_when_content_empty():
    # function-calling 模式下 content 为空，结构化数据在 tool_calls.arguments
    resp = InstructorClient(_FakeInstructorTool(), model="m").extract(
        [{"role": "user", "content": "x"}])
    assert resp.content == '{"from": "tool_call"}'
    assert resp.finish_reason == "tool_calls"

