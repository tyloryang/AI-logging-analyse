"""脱敏中间件单测。所有真实样本均须被替换为 <REDACTED_*> 占位符。

运行：cd backend && python -m unittest tests.test_redact
"""
import unittest

from observability.redact import redact, redact_dict


class RedactTextCase(unittest.TestCase):
    def test_bearer_token(self):
        s = "Authorization: Bearer abc1234567890XYZdefghijk"
        self.assertNotIn("abc1234567890", redact(s))
        self.assertIn("<REDACTED_TOKEN>", redact(s))

    def test_api_key_assignment(self):
        s = 'api_key="sk-abcdef1234567890ZZZ"'
        out = redact(s)
        self.assertIn("<REDACTED_KEY>", out)
        self.assertNotIn("sk-abcdef1234567890ZZZ", out)

    def test_pem_block(self):
        s = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIB...\n-----END RSA PRIVATE KEY-----"
        self.assertEqual(redact(s), "<REDACTED_PEM>")

    def test_china_phone(self):
        self.assertEqual(redact("联系 13812345678"), "联系 <REDACTED_PHONE>")
        # 不应误伤 12 位以下数字串
        self.assertEqual(redact("订单号 123456789"), "订单号 123456789")

    def test_email(self):
        self.assertIn("<REDACTED_EMAIL>", redact("发邮件到 user.name+tag@example.com"))

    def test_idcard_18(self):
        self.assertIn("<REDACTED_IDCARD>", redact("身份证 110101199003078765"))

    def test_password_field(self):
        out = redact('password: "p@ssw0rdLongEnough"')
        self.assertIn("<REDACTED_PWD>", out)
        self.assertNotIn("p@ssw0rdLongEnough", out)

    def test_secret_assignment(self):
        out = redact("export SECRET=abc12345DEFghi")
        self.assertIn("<REDACTED_SECRET>", out)

    def test_empty_and_none(self):
        self.assertEqual(redact(""), "")
        self.assertEqual(redact(None), "")
        self.assertEqual(redact(12345), "12345")

    def test_noop_on_clean_log(self):
        clean = "[2026-06-09 12:00:00][order-service] GC pause 1200ms"
        self.assertEqual(redact(clean), clean)


class RedactDictCase(unittest.TestCase):
    def test_sensitive_field_redacted(self):
        d = {"name": "alice", "api_key": "sk-xxxx-yyyy-zzzz", "extra": 1}
        out = redact_dict(d)
        self.assertEqual(out["name"], "alice")
        self.assertEqual(out["api_key"], "<REDACTED_FIELD>")
        self.assertEqual(out["extra"], 1)

    def test_nested(self):
        d = {"user": {"email": "a@b.com", "password": "secret-1234567"}}
        out = redact_dict(d)
        self.assertEqual(out["user"]["password"], "<REDACTED_FIELD>")
        self.assertIn("<REDACTED_EMAIL>", out["user"]["email"])

    def test_empty_password_not_replaced(self):
        d = {"password": ""}
        self.assertEqual(redact_dict(d)["password"], "")


if __name__ == "__main__":
    unittest.main()
