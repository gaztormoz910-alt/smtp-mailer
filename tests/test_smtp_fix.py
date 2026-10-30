# -*- coding: utf-8 -*-
"""Verification tests for SMTP Account Validation Enhancements."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from core.smtp_manager import (
    SmtpAccount,
    SmtpManager,
    SmtpStatus,
    parse_smtp_line,
    _make_smart_ehlo,
)


class TestSmtpFix(unittest.TestCase):

    def test_account_parsing_and_username(self):
        """Gate 7: SmtpAccount supports 4-part and 5-part lines with optional username."""
        # 4-part standard: host:port:email:password
        a1 = parse_smtp_line("smtp.gmail.com:587:user@gmail.com:secret123")
        self.assertIsNotNone(a1)
        self.assertEqual(a1.host, "smtp.gmail.com")
        self.assertEqual(a1.port, 587)
        self.assertEqual(a1.email, "user@gmail.com")
        self.assertEqual(a1.password, "secret123")
        self.assertEqual(a1.username, "user@gmail.com")

        # 5-part relay format: host:port:username:email:password
        a2 = parse_smtp_line("smtp.sendgrid.net:587:apikey:sender@domain.com:SG.abc123xyz")
        self.assertIsNotNone(a2)
        self.assertEqual(a2.host, "smtp.sendgrid.net")
        self.assertEqual(a2.port, 587)
        self.assertEqual(a2.username, "apikey")
        self.assertEqual(a2.email, "sender@domain.com")
        self.assertEqual(a2.password, "SG.abc123xyz")

        print("test_account_parsing_and_username passed")

    def test_smart_ehlo_realism(self):
        """Gate 8: EHLO generation for Office 365 and Exchange generates authentic client hostnames."""
        # For Office 365 or onmicrosoft domains, must NOT generate non-existent mail.domain.com
        for _ in range(20):
            ehlo = _make_smart_ehlo("user@company.onmicrosoft.com", target_host="smtp.office365.com")
            self.assertTrue(
                ehlo.startswith("DESKTOP-") or ehlo.startswith("LAPTOP-") or ehlo.startswith("PC-") or ".outlook.com" in ehlo,
                f"Expected realistic client EHLO, got: {ehlo}"
            )

        print("test_smart_ehlo_realism passed")

    def test_host_concurrency_throttling(self):
        """Gate 9: _HOST_MAX_CONCURRENT is set to polite value <= 4 to prevent password spraying bans."""
        mgr = SmtpManager()
        self.assertLessEqual(mgr._HOST_MAX_CONCURRENT, 4, "Host concurrency must be <= 4 to prevent bans")
        print("test_host_concurrency_throttling passed")

    def test_error_categorization_accuracy(self):
        """Gate 11: Error messages for 5.7.3 and basic auth are technically truthful without misleading '(не пароль)'."""
        import smtplib
        mgr = SmtpManager()
        acc = SmtpAccount(host="smtp.office365.com", port=587, email="test@wroc.pl", password="pass")

        # Simulate 5.7.3 Authentication unsuccessful error
        err = smtplib.SMTPAuthenticationError(535, b"5.7.3 Authentication unsuccessful [PROD.OUTLOOK.COM]")
        with patch("core.smtp_manager.connect_smtp", side_effect=err):
            ok = mgr.check_single(acc)
            self.assertFalse(ok)
            self.assertEqual(acc.status, SmtpStatus.UNTESTED)
            self.assertNotIn("(не пароль)", acc.last_error, "Should not claim '(не пароль)' for 5.7.3")
            self.assertIn("5.7.3", acc.last_error)

        print("test_error_categorization_accuracy passed")


if __name__ == "__main__":
    unittest.main()
