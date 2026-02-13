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
    def test__construct_from_row(self):
        until_timestamp_str = util.db_format(util.rounded_now() - datetime.timedelta(seconds=33))
        cooldown_until_timestamp_str = util.db_format(util.rounded_now() + datetime.timedelta(seconds=44))
        data = {"user_tg_id": 11, "level": 22, "until_timestamp": until_timestamp_str,
                "cooldown_until_timestamp": cooldown_until_timestamp_str}

        restriction = state.Restriction._construct_from_row(data)

        self.assertEqual(restriction._user_tg_id, data["user_tg_id"])
        self.assertEqual(restriction.level, data["level"])
        self.assertEqual(restriction.until_timestamp, datetime.datetime.fromisoformat(until_timestamp_str))
        self.assertEqual(restriction.cooldown_until_timestamp,
                         datetime.datetime.fromisoformat(cooldown_until_timestamp_str))

    @patch("common.db.sql_query")
    def test_get_current_or_create(self, mock_sql_query):
        now = datetime.datetime.now()
        user_tg_id = 12345

        # When nothing is returned by a DB query, a new restriction should be returned (at level -1 and eligible for
        # immediate elevation).
        restriction = state.Restriction.get_current_or_create(user_tg_id)

        self.assertEqual(restriction._user_tg_id, user_tg_id)
        self.assertEqual(restriction.level, -1)
        self.assertLess(restriction.until_timestamp, now)
        self.assertGreater(restriction.cooldown_until_timestamp, now)

        # When there is a record in the database, it should be returned.
        level = 22
        until_timestamp = util.rounded_now() - datetime.timedelta(seconds=33)
        cooldown_until_timestamp = util.rounded_now() + datetime.timedelta(seconds=44)
        mock_sql_query.return_value = iter(
            ({"user_tg_id": user_tg_id, "level": level, "until_timestamp": util.db_format(until_timestamp),
              "cooldown_until_timestamp": util.db_format(cooldown_until_timestamp)},))

        restriction = state.Restriction.get_current_or_create(user_tg_id)

        self.assertEqual(restriction._user_tg_id, user_tg_id)
        self.assertEqual(restriction.level, level)
        self.assertEqual(restriction.until_timestamp, until_timestamp)
        self.assertEqual(restriction.cooldown_until_timestamp, cooldown_until_timestamp)

    @patch("common.db.sql_query")
    def test_get_most_recent(self, mock_sql_query):
        user_tg_id = 12345

        # When nothing is returned by a DB query, None should be returned.
        self.assertIsNone(state.Restriction.get_most_recent(user_tg_id))

        # When there are records in the database, the latest one should be returned.  ("The latest" is effectively the
        # first one in the set returned by the DB, which is simulated here by the mock function returning several rows.)
        level = 22
        until_timestamp = util.rounded_now() - datetime.timedelta(seconds=33)
        cooldown_until_timestamp = util.rounded_now() + datetime.timedelta(seconds=44)
        mock_sql_query.return_value = iter(
            ({"user_tg_id": user_tg_id, "level": level, "until_timestamp": util.db_format(until_timestamp),
              "cooldown_until_timestamp": util.db_format(cooldown_until_timestamp)},
             {"user_tg_id": user_tg_id, "level": level + 1, "until_timestamp": util.db_format(until_timestamp),
              "cooldown_until_timestamp": util.db_format(cooldown_until_timestamp)},))

        restriction = state.Restriction.get_current_or_create(user_tg_id)

        self.assertEqual(restriction._user_tg_id, user_tg_id)
        self.assertEqual(restriction.level, level)
        self.assertEqual(restriction.until_timestamp, until_timestamp)
        self.assertEqual(restriction.cooldown_until_timestamp, cooldown_until_timestamp)

    @patch("common.db.sql_query")
    @patch("common.db.sql_exec")
    @patch("features.moderation.state.settings")
    def test_elevate_or_prolong(self, mock_settings, mock_sql_exec, mock_sql_query):
        mock_settings.MODERATION_RESTRICTION_LADDER = [{"action": "warn", "cooldown": 60},
                                                       {"action": "restrict", "duration": 60, "cooldown": 120},
                                                       {"action": "ban"}]
        user_tg_id = 12345

        # Create a new restriction
        mock_sql_query.return_value = iter(())

        restriction = state.Restriction.get_current_or_create(user_tg_id)

        mock_sql_query.assert_called_once()

        self.assertEqual(restriction._user_tg_id, user_tg_id)
        self.assertEqual(restriction.level, -1)
        self.assertLess(restriction.until_timestamp, util.rounded_now())
        self.assertGreater(restriction.cooldown_until_timestamp, util.rounded_now())

        def test_elevate_iteration(current_restriction: state.Restriction) -> state.Restriction:
            new_restriction = state.Restriction.elevate_or_prolong(current_restriction)
            new_level = new_restriction.level

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

            self.assertEqual(new_restriction._user_tg_id, user_tg_id)
            self.assertEqual(new_restriction.level, new_level)
            self.assertLessEqual(new_restriction._until_timestamp, util.rounded_now() + duration)

            mock_sql_exec.assert_called()
            self.assertEqual(mock_sql_exec.call_args_list[0].args[1],
                             (new_restriction._user_tg_id, util.db_format(util.rounded_now())))
            self.assertEqual(mock_sql_exec.call_args_list[1].args[1],
                             (new_restriction._user_tg_id, new_restriction.level,
                              util.db_format(new_restriction._until_timestamp),
                              util.db_format(new_restriction._cooldown_until_timestamp)))
            mock_sql_exec.reset_mock()

            return new_restriction

        # The new restriction should elevate without problems.
        restriction = test_elevate_iteration(restriction)

        # The level 0 restriction does not have an active period, so it is on cooldown already.
        restriction = test_elevate_iteration(restriction)

        # Level 1 has a duration, so it cannot be elevated right away.
        with self.assertRaises(RuntimeError):
            restriction = test_elevate_iteration(restriction)
        # However, with the duration passed over, there should not be a problem anymore.
        restriction._until_timestamp = util.rounded_now() - datetime.timedelta(seconds=1)
        restriction = test_elevate_iteration(restriction)

        # We are now at level 2 that is the maximum, and should stay at this level.
        restriction._until_timestamp = util.rounded_now() - datetime.timedelta(seconds=1)
        prolonged_restriction = test_elevate_iteration(restriction)
        self.assertEqual(prolonged_restriction.level, restriction.level)

        # A restriction that has already cooled down cannot be elevated.
        restriction._cooldown_until_timestamp = util.rounded_now() - datetime.timedelta(seconds=1)
        with self.assertRaises(RuntimeError):
            restriction = test_elevate_iteration(restriction)

        # Finally, test an unsupported action in the config.
        mock_settings.MODERATION_RESTRICTION_LADDER.append({"action": "praise"})

        with self.assertRaises(RuntimeError):
            state.Restriction.elevate_or_prolong(restriction)
