"""Task 2.5 脱敏单元测试（RED 先行）。"""
from param_extractor.observability.redaction import redact


def test_password_masked():
    out = redact("我的密码是 SuperSecretPass123")
    assert "SuperSecretPass123" not in out
    assert "***" in out


def test_card_masked_keeps_last4():
    out = redact("card 4111111111111111")
    assert "4111111111111111" not in out
    assert "1111" in out


def test_nric_masked():
    out = redact("NRIC S9123456A")
    assert "S9123456A" not in out


def test_truncation_to_max_len():
    out = redact("x" * 1000, max_len=256)
    assert len(out) <= 256


def test_non_pii_preserved():
    assert redact("hello world") == "hello world"


def test_non_string_input_safe():
    assert redact(None) == ""


def test_email_masked():
    # C2：邮箱必须掩码（§8.4 必做）
    out = redact("请联系我 user@example.com")
    assert "user@example.com" not in out


def test_phone_masked():
    # C2：手机号必须掩码（§8.4 必做）
    out = redact("电话是 13812345678")
    assert "13812345678" not in out
