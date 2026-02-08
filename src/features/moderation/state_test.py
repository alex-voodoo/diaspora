"""
Test for state.py
"""

import datetime
import unittest
from unittest.mock import patch

from telegram import Chat, Message, MessageOriginChat, MessageOriginHiddenUser, MessageOriginUser, User

from . import state


class TestMainLogChat(unittest.TestCase):
    @patch("common.db.sql_query")
    def test_find_original(self, mock_sql_query):
        main_chat = Chat(id=1, type=Chat.SUPERGROUP)

        original_user = User(id=1, first_name="Original", is_bot=False, username="sender")
        original_message_timestamp = datetime.datetime.now().replace(microsecond=0) - datetime.timedelta(minutes=1)
        original_message_timestamp_str = original_message_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        original_message = Message(message_id=1, date=original_message_timestamp, chat=main_chat,
                                   from_user=original_user, text="Original message")

        forwarder_chat = Chat(id=2, type=Chat.PRIVATE)
        forwarder_user = User(id=2, first_name="Forwarder", is_bot=False)
        supported_cases = ({"origin": MessageOriginUser(date=original_message_timestamp, sender_user=original_user),
                            "where_clause": "sender_tg_id=?",
                            "parameters": (original_message_timestamp_str, original_message.text, original_user.id)}, {
                               "origin": MessageOriginHiddenUser(date=original_message_timestamp,
                                                                 sender_user_name=original_user.name),
                               "where_clause": "sender_name=?", "parameters": (
                original_message_timestamp_str, original_message.text, original_user.name)})
        for case in supported_cases:
            forwarded_message = Message(message_id=2, date=datetime.datetime.now(), chat=forwarder_chat,
                                        forward_origin=case["origin"], from_user=forwarder_user,
                                        text="Original message")

            mock_sql_query.return_value = iter(())

            self.assertIsNone(state.MainChatMessage.find_original(forwarded_message))

            mock_sql_query.assert_called_once()
            call_args = mock_sql_query.call_args[0]
            self.assertIn(case["where_clause"], call_args[0])
            self.assertEqual(call_args[1], case["parameters"])

            mock_sql_query.return_value = iter((
                {"tg_id": original_user.id, "timestamp": original_message_timestamp_str, "text": original_message.text,
                 "sender_tg_id": original_user.id, "sender_name": original_user.name,
                 "sender_username": original_user.username},))

            found_message = state.MainChatMessage.find_original(forwarded_message)

            self.assertIsInstance(found_message, state.MainChatMessage)
            self.assertIsInstance(found_message._timestamp, datetime.datetime)
            self.assertEqual(found_message.tg_id, original_message.id)
            self.assertEqual(found_message._timestamp, original_message.date)
            self.assertEqual(found_message._text, original_message.text)
            self.assertEqual(found_message._sender_tg_id, original_message.from_user.id)
            self.assertEqual(found_message._sender_name, original_message.from_user.name)
            self.assertEqual(found_message._sender_username, original_message.from_user.username)

            mock_sql_query.reset_mock()

        forwarded_message = Message(message_id=3, date=datetime.datetime.now(), chat=forwarder_chat,
                                    forward_origin=MessageOriginChat(date=original_message_timestamp,
                                                                     sender_chat=main_chat), from_user=forwarder_user,
                                    text="Original message")

        with self.assertRaises(RuntimeError):
            state.MainChatMessage.find_original(forwarded_message)
