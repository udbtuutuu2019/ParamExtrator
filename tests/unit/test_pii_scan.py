"""Task 2.4 PII 扫描单元测试（RED 先行）。"""
from param_extractor.guardrail.pii_scan import apply_pii_policy, scan_pii
from tests.fixtures.transcripts import TRANSCRIPTS


def test_nric_detected():
    cats, is_pii = scan_pii("我的 NRIC 是 S9123456A")
    assert "nric" in cats and is_pii is True


def test_password_detected():
    cats, is_pii = scan_pii("我的密码是 SuperSecretPass123")
    assert "password" in cats and is_pii is True


def test_full_card_detected():
    cats, is_pii = scan_pii("卡号 4111 1111 1111 1111")
    assert "card_full" in cats and is_pii is True


def test_phone_detected():
    cats, is_pii = scan_pii("请联系我 13812345678")
    assert "phone" in cats and is_pii is True


def test_email_detected():
    cats, is_pii = scan_pii("邮箱是 user@example.com")
    assert "email" in cats and is_pii is True


def test_card_tail_only_is_not_pii():
    # Review Focus #3 / 决策 D1
    cats, is_pii = scan_pii("退回到尾号 4402 的卡")
    assert "card_tail" in cats
    assert is_pii is False


def test_tx001_card_tail_false():
    cats, is_pii = scan_pii(TRANSCRIPTS["TX-001"])
    assert is_pii is False


def test_tx002_pii_true():
    cats, is_pii = scan_pii(TRANSCRIPTS["TX-002"])
    assert is_pii is True


def test_negatives_not_flagged():
    for text in ["订单号是 20261015001", "退款日期 2026-10-15", "发票编号 #INV-4029", "被扣了 150 美元"]:
        cats, is_pii = scan_pii(text)
        assert is_pii is False, text


def test_apply_pii_policy_combines_channels():
    assert apply_pii_policy(llm_flag=True, cats=set()) is True
    assert apply_pii_policy(llm_flag=False, cats={"nric"}) is True
    assert apply_pii_policy(llm_flag=False, cats={"card_tail"}) is False
    assert apply_pii_policy(llm_flag=False, cats=set()) is False
