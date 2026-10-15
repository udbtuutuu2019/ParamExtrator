"""护栏子包。"""
from .injection import detect_injection
from .sanitizer import wrap_untrusted

__all__ = ["detect_injection", "wrap_untrusted"]
