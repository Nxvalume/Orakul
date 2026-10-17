import unittest
from unittest.mock import patch
import bot

class Tests(unittest.TestCase):
    def test_html_escape(self):
        r = bot.lead_text({"from":{"id":7,"first_name":"<X>"},"text":"<script>&"})
        self.assertIn("&lt;X&gt;",r)
        self.assertIn("&lt;script&gt;&amp;",r)
        self.assertNotIn("<script>",r)

    @patch("bot.reply")
    def test_start(self, send):
        bot.process({"message":{"chat":{"id":8,"type":"private"},"from":{"id":8},"text":"/start"}})
        send.assert_called_once()

    @patch("bot.reply")
    def test_group_ignored(self, send):
        bot.process({"message":{"chat":{"id":-1,"type":"group"},"text":"hi"}})
        send.assert_not_called()

    @patch("bot.reply")
    @patch("bot.api")
    def test_forward(self, tg, send):
        with patch.object(bot,"OWNER_ID",200):
            bot.process({"message":{"chat":{"id":8,"type":"private"},"from":{"id":8},"text":"Need a bot"}})
        self.assertEqual(tg.call_args.args[1]["chat_id"],200)
        send.assert_called_once()

    @patch("bot.reply")
    @patch("bot.api")
    def test_owner_no_self_forward(self, tg, send):
        with patch.object(bot,"OWNER_ID",8):
            bot.process({"message":{"chat":{"id":8,"type":"private"},"from":{"id":8},"text":"test"}})
        tg.assert_not_called()
        send.assert_called_once()

    @patch("bot.reply")
    def test_admin_denied(self, send):
        with patch.object(bot,"OWNER_ID",9):
            bot.process({"message":{"chat":{"id":8,"type":"private"},"from":{"id":8},"text":"/admin"}})
        self.assertEqual(send.call_args.args[1], "Нет доступа.")

if __name__=="__main__":
    unittest.main()
