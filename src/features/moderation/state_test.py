"""
Test for state.py
"""

import datetime
import unittest
from unittest.mock import patch

from telegram import Chat, Message, MessageOriginChat, MessageOriginHiddenUser, MessageOriginUser, User

from common import util
from common.settings import settings
from . import state, const


class TestMainLogChat(unittest.TestCase):
    @patch("common.db.sql_exec")
    def test_maybe_delete_old_messages(self, mock_sql_exec):
        state.MainChatMessage._next_cleanup_timestamp = datetime.datetime.now() - datetime.timedelta(seconds=1)

        expected_max_age = util.rounded_now() - datetime.timedelta(
            hours=settings.MODERATION_MAIN_CHAT_LOG_MAX_AGE_HOURS)
        state.MainChatMessage.maybe_delete_old_messages()

        mock_sql_exec.assert_called_once()
        max_age = datetime.datetime.fromisoformat(mock_sql_exec.call_args[0][1][0])
        self.assertTrue(abs(max_age - expected_max_age) <= datetime.timedelta(seconds=1))
        mock_sql_exec.reset_mock()

        state.MainChatMessage.maybe_delete_old_messages()
        mock_sql_exec.assert_not_called()

    @patch("common.db.sql_query")
    def test_find_original(self, mock_sql_query):
        main_chat = Chat(id=1, type=Chat.SUPERGROUP)

        original_user = User(id=1, first_name="Original", is_bot=False, username="sender")
        original_message_timestamp = util.rounded_now() - datetime.timedelta(minutes=1)
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


class TestRestriction(unittest.TestCase):
    @patch("common.db.sql_query")
    @patch("common.db.sql_exec")
    @patch("features.moderation.state.settings")
    def test_elevate(self, mock_settings, mock_sql_exec, mock_sql_query):
        mock_settings.MODERATION_RESTRICTION_LADDER = [{"action": "warn", "cooldown": 60},
                                                       {"action": "restrict", "duration": 60, "cooldown": 120},
                                                       {"action": "ban"}]

        mock_sql_query.return_value = iter(())

        restriction = state.Restriction.get_or_create(1)

        mock_sql_query.assert_called_once()

        self.assertEqual(restriction._tg_id, 1)
        self.assertEqual(restriction.level, -1)
        self.assertLessEqual(restriction._until_timestamp, util.rounded_now())

        def test_elevate_iteration(current_restriction: state.Restriction) -> state.Restriction:
            new_restriction = state.Restriction.elevate(current_restriction)
            new_level = current_restriction.level + 1

            pattern = mock_settings.MODERATION_RESTRICTION_LADDER[new_level]

            action = pattern["action"]
            if action == const.ACTION_WARN:
                duration = datetime.timedelta(minutes=pattern["cooldown"])
            elif action == const.ACTION_RESTRICT:
                duration = datetime.timedelta(minutes=(pattern["duration"] + pattern["cooldown"]))
            elif action == const.ACTION_BAN:
                duration = datetime.timedelta(days=36500)
            else:
                assert False

            self.assertEqual(new_restriction._tg_id, 1)
            self.assertEqual(new_restriction.level, new_level)
            self.assertLessEqual(new_restriction._until_timestamp, util.rounded_now() + duration)

            mock_sql_exec.assert_called()
            self.assertEqual(mock_sql_exec.call_args_list[0].args[1], (new_restriction._tg_id,))
            self.assertEqual(mock_sql_exec.call_args_list[1].args[1],
                             (new_restriction._tg_id, new_restriction.level,
                              util.db_format(new_restriction._until_timestamp)))
            mock_sql_exec.reset_mock()

            return new_restriction

        restriction = test_elevate_iteration(restriction)
        restriction = test_elevate_iteration(restriction)
        restriction = test_elevate_iteration(restriction)

        with self.assertRaises(RuntimeError):
            state.Restriction.elevate(restriction)

        mock_settings.MODERATION_RESTRICTION_LADDER.append({"action": "praise"})

        with self.assertRaises(RuntimeError):
            state.Restriction.elevate(restriction)
