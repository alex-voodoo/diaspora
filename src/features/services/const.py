"""
Constants used in commands and conversation graphs
"""

COMMAND_WHO, COMMAND_ENROLL, COMMAND_UPDATE, COMMAND_RETIRE, COMMAND_INFO = (
"who", "update", "enroll", "retire", "service_info")
SELECTING_CATEGORY, TYPING_OCCUPATION, TYPING_DESCRIPTION, TYPING_LOCATION, CONFIRMING_LEGALITY = range(5)
RESPONSE_YES, RESPONSE_NO = ("yes", "no")
MODERATOR_APPROVE, MODERATOR_DECLINE = ("approve", "decline")
PING_CONFIRM_ALL, PING_CONFIRM_EDIT, PING_DELETE_ALL = ("ping_confirm_all", "ping_confirm_edit", "ping_delete_all")
PING_DELETE_ALL_YES, PING_DELETE_ALL_NO = ("ping_delete_all_yes", "ping_delete_all_no")
