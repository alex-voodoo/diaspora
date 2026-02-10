# Public moderation

This feature implements user-driven public moderation.

**Alpha status.**  This is still work in progress, not fully implemented, and not well tested.

## Problem

The standard approach to moderation in Telegram is insufficient (if not saying "flawed in many ways").  Here are some disadvantages:
- Administrators may have conflict of interests: they may want to participate in discussions, but at the same time they have to act as power to resolve conflicts of punish violations.  Because administrators have elevated privileges, their opinions may be perceived as "special" ones, not like opinions of regular users. 
- Administrators are often perceived as "the law", and for that they may become targets for backlash or retaliation for doing their work, e.g., when they block some user for a violation, that user may see it as personal and/or unfair, and blame the administrator for being biased, selective, too strict, etc., or try to appeal the measure taken, reaching privately to the administrator that put the measure in action, even if it was a collective agreement of several administrators. 
- There is no established way to complain when someone misbehaves.  People may denounce misbehaviour publicly in the group, or they may contact administrators privately, but neither way is good enough.  Public opposition often causes the opposite to what was intended, and contacting the moderators privately is absolutely non-transparent, is impossible to formalise, and highly subjective.
- If there are several administrators, they have to be in touch with each other all the time in order to provide consistent response to violations, otherwise they naturally turn into "good ones" and "bad ones" in the eyes of the public, which gives additional grounds to those who tend to see actions of administrators as subjective and unfair.

The biggest problem of the standard approach is that all actions in the group are visible and at the same time personal, which makes every participant an easy target for attacks.

## Solution

This feature fixes some of the flaws explained above:
- A concept of _moderator_ is introduced.  Moderators are regular participants, they have no additional privileges in terms of Telegram group permissions, but they have a special role (duty) of evaluating complaints coming from other participants.  Moderators have a special group where they handle the complaints aka "moderation chat".
- The bot acts as complaint manager.  Any participant may send to the bot a request to moderate a message.  When the bot accumulates certain number of requests to a single message, it elevates the complaint to the moderation chat.
- The moderators accept or reject the complaints by voting in polls posted by the bot to the moderation chat.  When the poll gets enough votes for making the decision, the bot announces that in the moderation chat.
- Should the complaint be accepted, the bot proceeds with the moderation action (see next section).

The moderation is now performed by the community, and there are no steps where any single person could be blamed for making unfair decision.  Sending and evaluating complaints are group actions, which makes the process less sensitive to personal perception and opinion of any participant.

## Process

**Proposal status.**  This is still being discussed and is subject to change during the development.

Three types of actions are possible:
- Warning: the bot announces that the original message violated the rules, and reminds its author that they should behave well, otherwise they may be restricted.  No restriction is applied at this time.
- Restriction: the author of the original message is muted for certain time
- Ban: the author of the original message is banned.  The administrators will kick that person (bots cannot do this).

A sequence of moderation actions can be configured, so that when someone violates the rules the first time, they get a warning, next time they may be muted for some time, the third time they may be muted for a longer time, etc. up to being banned and kicked.  This may be viewed as levels: initially a participant is at level 0, but every time they violate the rules, they will move to the next level, until they reach the last one.  Every level has a cooldown time, so if the person behaves well during that period of time and do not trigger new complaints, they will be forgiven and reset to level 0.

When a complaint is approved, time comes to restrict the author of the original message.  This has several steps.
1. The moderation action is performed according to the current level of the violator.
2. All existing complaints and unfinished moderation polls related to the violator are frozen, and no new requests are accepted for messages that came prior to the moment of performing the action
3. The cooldown period starts after the restriction is lifted.  New moderation requests are accepted only for new messages that the person posted after they got their voice back.

The restriction is stored in the database, so it is possible to track a record for any user.

When a restriction is put on a user, all existing complaints against that user are frozen, and no new complaints are accepted until the restriction ends.  After that, complaints are accepted only to new messages from the user.
