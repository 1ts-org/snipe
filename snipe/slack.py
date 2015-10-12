# -*- encoding: utf-8 -*-
# Copyright © 2015 the Snipe contributors
# All rights reserved.
'''
snipe.slack
--------------
Backend for talking to `Slack <https://slack.com>`.
'''

_backend = 'Slack'


import os
import time
import re
import netrc
import urllib.parse
import aiohttp
import json
import pprint
import contextlib
import itertools

import asyncio

from . import messages
from . import _websocket
from . import util
from . import keymap
from . import interactive
from . import filters

SLACKDOMAIN = 'slack.com'
SLACKAPI = '/api/'

# The documentation for attachment color says that hex color
# codes start with a #.  Don't believe their lies.
HEXCOLOR = re.compile(r'^([0-9a-fA-F]{3}|([0-9a-fA-F][0-9a-fA-F]){3})$')


class Slack(messages.SnipeBackend, util.HTTP_JSONmixin):
    name = 'slack'
    loglevel = util.Level('log.slack', 'Slack')

    IGNORED_TYPES = (
        'hello', 'user_typing', 'channel_marked', 'pref_change', 'file_public',
        'file_shared', 'file_created', 'accounts_changed', 'im_marked',
        'group_marked',
        )

    def __init__(self, context, slackname=None, **kw):
        super().__init__(context, **kw)
        if slackname is None and self.name != self.__class__.name:
            slackname = self.name
        if self.name == self.__class__.name:
            self.name = Slack.name + '.' + slackname
        self.tasks.append(asyncio.Task(self.connect(slackname)))
        self.backfilling = False
        self.dests = {}
        self.connected = False
        self.messages = []
        self.nextid = itertools.count().__next__
        self.unacked = {}
        self.used_emoji = []

    @asyncio.coroutine
    def connect(self, slackname):
        try:
            hostname = slackname + '.' + SLACKDOMAIN

            try:
                rc = netrc.netrc(os.path.join(self.context.directory, 'netrc'))
                authdata = rc.authenticators(hostname)
            except netrc.NetrcParseError as e:
                self.log.warn(str(e)) # need better notification
                return
            except FileNotFoundError as e:
                self.log.warn(str(e))
                return

            self.token = authdata[2]

            self.url = 'https://' + SLACKDOMAIN + SLACKAPI

            self.log.debug('about to rtm.start')

            yield from self.emoji_update()

            self.data = yield from self.method('rtm.start')
            if not self.check_ok(self.data, 'connecting to %s', slackname):
                return

            url = self.data['url']

            self.users = {u['id']: u for u in self.data['users']}

            self.dests = dict(
                [(u['id'], SlackDest(self, 'user', u)) for u in self.data['users']] +
                [(i['id'], SlackDest(self, 'im', i)) for i in self.data['ims']] +
                [(g['id'], SlackDest(self, 'group', g)) for g in self.data['groups']] +
                [(c['id'], SlackDest(self, 'channel', c)) for c in self.data['channels']])

            self.log.debug('websocket url is %s', url)

            self.websocket = util.JSONWebSocket(self.log)
            yield from self.websocket.connect(url)

            self.connected = True

            while True:
                m = yield from self.websocket.read()
                self.log.debug('message: %s', repr(m))
                try:
                    yield from self.incoming(m)
                except:
                    self.log.exception(
                        'Processing incoming message: %s', repr(m))
        except asyncio.CancelledError:
            raise
        except:
            self.log.exception('connecting to slack')

    @asyncio.coroutine
    def incoming(self, m):
        msg = yield from self.process_message(self.messages, m)
        if msg is not None:
            self.redisplay(msg, msg)

    def find_message(self, when, m):
        try:
            msg = next(self.walk(when))
        except StopIteration:
            self.log.debug('%s for unknown message %s', m['type'], repr(m))
            return None
        if msg.time != when:
            self.log.debug(
                '%s found message %s for message %s',
                m['type'], msg, repr(m))
            return None
        return msg

    @asyncio.coroutine
    def process_message(self, messagelist, m):
        if 'reply_to' in m:
            self.log.debug('reply_to_message: %s', pprint.pformat(m))

            msgid = m['reply_to']
            if msgid not in self.unacked:
                # this is probably a response from a previous session
                return

            m.update(self.unacked[msgid])
            if 'user' not in m:
                m['user'] = self.data['self']['id']
            # because they don't include the actual message for some reason

        t = m['type'].lower()
        if t in self.IGNORED_TYPES:
            return
        elif t == 'emoji_changed':
            yield from self.emoji_update()
        elif t == 'message' and m.get('subtype') == 'message_changed':
            msg = self.find_message(float(m['message']['ts']), m)
            if msg is None:
                return
            data = dict(m['message'])
            data['_old'] = msg.data
            data['_new'] = m
            msg.data = data
            return msg
        elif t in ('reaction_removed', 'reaction_added'):
            msg = self.find_message(float(m['item']['ts']), m)
            if msg is None:
                return
            for i, reaction in enumerate(msg.data.get('reactions', [])):
                if reaction['name'] == m['reaction']:
                    break
            else:
                if t == 'reaction_added':
                    reaction = {'name': m['reaction'], 'count': 0, 'users': []}
                    msg.data.setdefault('reactions', []).append(reaction)
                else: # 'reaction_removed', but not found
                    return None
            if t == 'reaction_added':
                reaction['count'] += 1
                if m['user'] not in reaction['users']: # unreliable, but...
                    reaction['users'].append(m['user'])
            elif t == 'reaction_removed':
                reaction['count'] -= 1
                if reaction['count'] == 0:
                    del msg.data['reactions'][i] # leftover from that for loop
                else:
                    if m['user'] in reaction['users']:
                        reaction['users'].remove(m['user'])
            return msg
        elif t in ('team_join', 'user_change'):
            u = m['user']
            self.users[u['id']] = u
        elif t == 'channel_created':
            c = m['channel']
            self.dests[c['id']] = SlackDest(self, 'channel', c)
        elif t in ('channel_rename', 'group_rename'):
            c = m['channel']
            self.dests[c['id']].update(c)
        elif t == 'group_joined':
            c = m['channel']
            self.dests[c['id']] = SlackDest(self, 'group', c)
        elif t == 'im_created':
            c = m['channel']
            self.dests[c['id']] = SlackDest(self, 'im', c)
        msg = SlackMessage(self, m)
        if messagelist and msg.time <= messagelist[-1].time:
            msg.time = messagelist[-1].time + .000001
        messagelist.append(msg)
        return msg

    @asyncio.coroutine
    def emoji_update(self):
        self.log.debug('attempting to retrieve emoji')
        self.emoji = yield from self.method('emoji.list')

    @keymap.bind('S U')
    def dump_users(self, window: interactive.window):
        window.show(pprint.pformat(self.users))

    @keymap.bind('S D')
    def dump_dests(self, window: interactive.window):
        window.show(pprint.pformat(self.dests))

    @keymap.bind('S M')
    def dump_meta(self, window: interactive.window):
        window.show(pprint.pformat(self.data))

    @contextlib.contextmanager
    def backfill_guard(self):
        if self.backfilling:
            yield True
        else:
            self.log.debug('entering guard')
            self.backfilling = True
            yield False
            self.backfilling = False
            self.log.debug('leaving guard')

    def backfill(self, mfilter, target=None):
        if not self.connected:
            return
        self.tasks.append(asyncio.Task(self.do_backfill(mfilter, target)))

    @asyncio.coroutine
    def do_backfill(self, mfilter, target):
        self.log.debug('backfill([filter], %s)', repr(target))
        with self.backfill_guard() as already:
            if already:
                self.log.debug('already backfilling')
                return

            backfillers = [
                asyncio.Task(self.do_backfill_dest(dest, mfilter, target))
                for dest in self.dests if self.dests[dest].type != 'user']
            self.tasks += backfillers
            yield from asyncio.gather(*backfillers, return_exceptions=True)

    @asyncio.coroutine
    def do_backfill_dest(self, dest, mfilter, target):
        d = self.dests[dest]

        self.log.debug(
            'do_backfill_dest(%s, target=%s); oldest=%s, loaded=%s',
            str(d),
            util.timestr(target),
            d.oldest,
            d.loaded,
            )

        if target is not None and d.oldest is not None and target > d.oldest:
            return

        if d.loaded:
            return

        d.loaded=True

        data = yield from self.method(
            {
                'channel': 'channels.history',
                'im': 'im.history',
                'group': 'groups.history',
            }[d.type],
            channel=dest,
            **({'latest': d.oldest} if d.oldest is not None else {}))

        if not self.check_ok(data, 'backfilling %s', dest):
            return

        messagelist = []
        for m in reversed(data['messages']):
            m['channel'] = dest
            try:
                msg = yield from self.process_message(messagelist, m)
                if d.oldest is None or d.oldest > msg.time:
                    d.oldest = msg.time
            except:
                self.log.exception('processing message: %s', pprint.pformat(m))
                raise
        self.log.debug('%s: got %d messages', dest, len(messagelist))
        self.messages = list(messages.merge([self.messages, messagelist]))
        self.startcache = {}
        if messagelist:
            self.redisplay(messagelist[0], messagelist[-1])

    @asyncio.coroutine
    def send(self, inrecipient, body):
        inrecipient = inrecipient.strip()
        recipient = inrecipient.lstrip('+#@')

        user = None
        for d in self.dests.values():
            if d.type == 'user' and d.data['name'] == recipient:
                self.log.debug('stashing user %s', repr(d))
                user = d
            elif 'name' in d.data:
                if d.data['name'] == recipient:
                    recipient = d.data['id']
                    break
            elif 'user' in d.data:
                self.log.debug('1: %s', pprint.pformat(d))
                self.log.debug('2: %s', pprint.pformat(self.users[d.data['user']]))
                if self.users[d.data['user']]['name'] == recipient:
                    recipient = d.data['id']
                    break
        else:
            if user is None:
                raise util.SnipeException('cannot find recipient')
            # we need to open a dm session
            self.log.debug('opening dm session with %s', repr(d))
            response = yield from self.method('im.open', user=user.data['id'])

            if not self.check_ok(response, 'opening DM session'):
                return

            recipient = response['channel']['id']

        body = body.replace('&', '&amp;')
        body = body.replace('<', '&lt;')
        body = body.replace('>', '&gt;')

        response = yield from self.method(
            'chat.postMessage',
            as_user=True,
            channel=recipient,
            text=body,
            )

        self.check_ok(response, 'sending message to %s', inrecipient)

    @asyncio.coroutine
    def method(self, method, **kwargs):
        msg = dict(kwargs)
        msg['token'] = self.token
        response = yield from self.http_json(
            'POST',
            self.url + method,
            headers={'Content-type': 'application/x-www-form-urlencoded'},
            data = urllib.parse.urlencode(msg),
            )
        return response

    def check_ok(self, response, context, *args):
        # maybe should be doing this with exceptions
        try:
            self.check(response, context, *args)
        except util.SnipeException as error:
            self.messages.append(messages.SnipeErrorMessage(self, str(error)))
            return False
        return True

    def check(self, response, context, *args):
        if not response['ok']:
            raise util.SnipeException(
                '%s: %s' % (context % args, response['error']))


class SlackDest:
    def __init__(self, backend, type_, data):
        self.backend = backend
        self.type = type_
        self.data = data

        self.oldest = None
        self.loaded = False

    def update(self, data):
        self.data.update(data)

    def __repr__(self):
        return self.__class__.__name__ + '(\n    ' \
          + repr(self.type) + ',\n    ' \
          + '\n    '.join(pprint.pformat(self.data).split('\n')) \
          + '\n    )'

    def __str__(self):
        prefix = {
            'im': '@', 'user': '', 'group': '+', 'channel': '#',
            }[self.type]
        if self.type == 'im':
            return prefix + self.backend.users[self.data['user']]['name']
        else:
            return prefix + self.data['name']


class SlackAddress(messages.SnipeAddress):
    def __init__(self, backend, identifier):
        self.backend = backend
        self.id = identifier
        super().__init__(backend, [self.backend.dests[identifier].type, identifier])

    def __str__(self):
        return str(self.backend.dests[self.id])

    def reply(self):
        return self.backend.name + '; ' + str(self)



class SlackMessage(messages.SnipeMessage):
    SLACKMARKUP = re.compile(r'<(.*?)>')

    def __init__(self, backend, m):
        import pprint
        backend.log.debug('message: %s', pprint.pformat(m))
        t = m['type']

        super().__init__(
            backend,
            t + ' ' + pprint.pformat(m),
            float(m.get('ts', time.time())))

        self.data = m

        if 'user' in m:
            if isinstance(m['user'], dict):
                self._sender = SlackAddress(backend, m['user']['id'])
            else:
                self._sender = SlackAddress(backend, m['user'])
        elif 'channel' in m:
            self._sender = SlackAddress(backend, m['channel'])

        self.channel = None

        if t == 'message' and 'text' in m:
            bodylist = self.SLACKMARKUP.split(m['text'])
            self.body = ''
            for (n, s) in enumerate(bodylist):
                if n%2 == 0:
                    self.body += s
                else:
                    if '|' in s:
                        self.body += s.split('!', 1)[-1]
                    else:
                        if s[:2] in ('#C', '@U'):
                            self.body += self.displayname(s[1:])
                        else:
                            self.body += s

            ch = m['channel']
            self.channel = self.displayname(ch)
            if ch in self.backend.dests and self.backend.dests[ch].type == 'im':
                self.personal = True
        elif t == 'presence_change':
            self.body = backend.users[m['user']]['name'] + ' is ' + m['presence']
            self.noise = True

        self.unhandled = False
        if (t == 'message' and 'text' not in self.data) or t not in ('message', 'presence_change',):
            self.unhandled = True

    def displayname(self, s):
        return str(self.backend.dests.get(s, s))

    def slackmarkup(self, text, tags):
        chunk = []
        bodylist = self.SLACKMARKUP.split(text)
        for (n, s) in enumerate(bodylist):
            if n%2 == 0:
                s = s.replace('&lt;', '<')
                s = s.replace('&gt;', '>')
                s = s.replace('&amp;', '&')
                chunk += [
                    (tags, s),
                    ]
            else:
                if '|' in s:
                    chunk += [(tags + ('bold',), s.split('|', 1)[-1])]
                else:
                    if s[:2] in ('#C', '@U'):
                        nametext = self.displayname(s[1:])
                        if s[1] == 'U':
                            nametext = '@' + nametext
                        chunk += [(tags + ('bold',), nametext)]
                    else:
                        chunk += [(tags + ('bold',), s)]

        return chunk

    def display(self, decoration):
        tags = self.decotags(decoration)
        timestring = time.strftime(' %H:%M:%S', time.localtime(self.time))
        chunk = []
        if self.channel is not None:
            chunk += [((tags + ('bold',)), self.channel + ' ')]

        if 'edited' in self.data:
            chunk += [(tags, '~')]

        if self.data.get('is_starred', False):
            chunk += [(tags, '*')]

        if self.data.get('pinned_to', False):
            chunk += [(tags, '+')]

        t = self.data['type']
        t_ = self.data.get('subtype')
        if t == 'message' and 'text' in self.data:
            chunk += [(tags + ('bold',), self.sender.short())]
            if t_ != 'me_message':
                chunk += [(tags, ': ')]
            else:
                chunk += [(tags, ' ')]

            chunk += self.slackmarkup(self.data['text'], tags)

            if self.data.get('reactions'):
                chunk += [
                    (tags, '\n' + ' '.join(
                        ':%s: %d' % (reaction['name'], reaction['count'])
                        for reaction in self.data['reactions']))]

            for attachment in self.data.get('attachments', []):
                left = [(tags, '\n> ')]
                color = attachment.get('color', '')
                if color:
                    cmap = {
                        'good': 'green',
                        'warning': 'yellow',
                        'danger': 'red',
                        }
                    if color.lower() in cmap:
                        color = cmap[color.lower()]
                    elif HEXCOLOR.match(color):
                        color = '#' + color

                    left = [
                        (tags, '\n'),
                        (tags + (('bg:%s' % color),), ' '),
                        (tags, ' '),
                        ]

                for (field, markup) in [
                        #('fallback', ()),
                        ('pretext', ('bold',)),
                        ('author_name', ()),
                        ('author_link', ()),
                        ('title', ('bold',)),
                        ('title_link', ()),
                        ]:
                    if field in attachment:
                        chunk += left + [((tags + markup), attachment[field])]

                if 'text' in attachment:
                    chunk += left + self.slackmarkup(attachment['text'], tags)

                for field in attachment.get('fields', []):
                    chunk += left + [(tags + ('bold',)), field['title']]
                    chunk += left + [tags, field['value']]

            if 'file' in self.data and 'url' in self.data['file']:
                chunk += [(tags, ('\n' + self.data['file']['url']))]

            chunk += [(tags + ('right',), timestring)]
        elif t == 'presence_change':
            if self.data['presence'] == 'active':
                chunk += [(tags, '+ ')]
            else:
                chunk += [(tags, '- ')]
            chunk += [
                (tags + ('bold',), self.sender.short()),
                (tags + ('right',), timestring),
                ]
        else:
            return super().display(decoration)
        return chunk

    def followup(self):
        if self.channel is None:
            return self.reply()
        return self.backend.name + '; ' + self.channel

    def filter(self, specificity=0):
        terms = [filters.Compare('==', 'backend', self.backend.name)]
        if self.channel:
            terms.append(filters.Compare('==', 'channel', self.channel))
        if not self.channel or specificity > 0:
            terms.append(filters.Compare('==', 'sender', self.field('sender')))
        if len(terms) > 1:
            return filters.And(*terms)
        else:
            return terms[0]

    @keymap.bind('+')
    def add_reaction(self, window: interactive.window):
        """Add a reaction to a message."""
        yield from self.react(window, 'reactions.add')

    @keymap.bind('-')
    def remove_reaction(self, window: interactive.window):
        """Remove a reaction to a message."""
        yield from self.react(window, 'reactions.remove')

    @keymap.bind('e')
    def edit_message(self, window: interactive.window):
        """Edit a message."""
        self.backend.log.error('self is %s, body is %s', repr(self), self.body)
        self.backend.log.error('window->cursor is %s', repr(window.cursor))

        text = yield from window.read_string(
            'edit (destination ignored) -> ',
            height=10,
            content=self.followup() + '\n' + self.body,
            history='send',
            fill=True,
            )

        try:
            _, text = text.split('\n', 1)
        except ValueError:
            raise Exception('no body in message')

        response = yield from self.backend.method(
            'chat.update',
            channel=self.data['channel'],
            ts=self.data['ts'],
            text=text,
            )

        self.backend.check(response, 'editing message to %s', self.followup())

    @asyncio.coroutine
    def react(self, window, method):
        for reaction in self.data.get('reactions', []):
            with contextlib.suppress(ValueError):
                self.backend.used_emoji.remove(reaction['name'])
            self.backend.used_emoji[:0] = [reaction['name']]
        custom_emoji = set(self.backend.emoji.keys())
        emoji_list = (
            self.backend.used_emoji
            + list(sorted(custom_emoji - set(self.backend.used_emoji) - EMOJI))
            + list(sorted(EMOJI - custom_emoji - set(self.backend.used_emoji))))
        reaction = yield from window.read_oneof(
            'Reaction: ', emoji_list)
        if reaction not in emoji_list:
            return
        response = yield from self.backend.method(
            method,
            name=reaction,
            channel=self.data['channel'],
            timestamp=self.data['ts'],
            )
        self.backend.check(response, 'responding to message')

# the following was massaged from
# https://raw.githubusercontent.com/iamcal/emoji-data/master/emoji.json
# which is Copyright (c) 2013 Cal Henderson, who deserves much respect
# for collecting the infoformation but it is my belief that the data
# collected is not covered by copyright.
EMOJI = {
    'bicyclist', 'left_speech_bubble', 'golf', 'hash', 'shopping_bags',
    'lower_left_paintbrush', 'ticket', 'princess', 'flag-mc', 'zero',
    'vibration_mode', 'green_book', 'flag-bl', 'department_store',
    'thermometer', 'couple', 'open_file_folder', 'art', 'scissors',
    'flag-fj', 'triangular_flag_on_post', '100', 'flag-re', 'flag-mz',
    'flag-ch', 'fireworks', 'flag-mr', 'panda_face', 'flag-tt', 'flag-mn',
    'yen', 'pensive', 'robot_face', 'arrow_backward', 'flashlight',
    'small_orange_diamond', 'sweat_smile', 'flag-ao', 'womens', 'fearful',
    'woman', 'flag-rw', 'ghost', 'thinking_face', 'waxing_crescent_moon',
    'flag-tg', 'cupid', 'rain_cloud', 'flag-hk', 'bomb', 'muscle',
    'clock830', 'amphora', 'black_joker', 'seven', 'flag-cf',
    'arrows_counterclockwise', 'hand', 'face_with_rolling_eyes',
    'dark_sunglasses', 'arrow_double_down', 'menorah_with_nine_branches',
    'boat', 'registered', 'v', 'turtle', 'envelope_with_arrow',
    'passport_control', 'flag-hr', 'frowning', 'link', 'hospital',
    'congratulations', 'bust_in_silhouette', 'radio',
    'three_button_mouse', 'white_large_square', 'boot', 'tornado_cloud',
    'clock1230', 'b', 'flag-gu', 'new_moon_with_face', 'yin_yang',
    'sleeping_accommodation', 'black_nib', 'alien', 'telephone',
    'flag-gd', 'woman-woman-boy-boy', 'whale', 'hankey', 'cyclone',
    'soon', 'pencil2', 'camping', 'derelict_house_building', 'tm',
    'neutral_face', 'weary', 'fleur_de_lis', 'shaved_ice', 'flag-pk',
    'last_quarter_moon', 'cheese_wedge', 'heavy_plus_sign',
    'first_quarter_moon_with_face', 'clock9', 'construction_worker',
    'point_left', 'older_man', 'non-potable_water', 'flag-pl', 'restroom',
    'clock4', 'mahjong', 'outbox_tray', 'six_pointed_star', 'ocean',
    'stars', 'motor_boat', 'flag-mm', 'flag-gh', 'snow_capped_mountain',
    'sa', 'id', 'no_entry', 'bath', 'massage', 'chart', 'smile',
    'first_quarter_moon', 'four', 'crying_cat_face', 'clock530',
    'statue_of_liberty', 'shoe', 'camera_with_flash', 'clock7', 'flag-tk',
    'smirk_cat', 'truck', 'penguin', 'pig_nose', 'arrow_double_up',
    'railway_car', 'izakaya_lantern', 'boom', 'flag-jp', 'no_good',
    'droplet', 'cd', 'flag-ru', 'parking', 'tangerine', 'flag-nu',
    'beetle', 'flag-sy', 'factory', 'flag-no', 'lower_left_ballpoint_pen',
    'lantern', 'ledger', 'bug', 'hushed', 'alembic', 'passenger_ship',
    'flag-af', 'bridge_at_night', 'expressionless', 'curry',
    'middle_finger', 'cake', 'nerd_face', 'joystick', 'banana',
    'two_men_holding_hands', 'flag-aw', 'electric_plug', 'rice_ball',
    'runner', 'frog', 'flag-pe', 'clock230', 'tshirt', 'satisfied',
    'seat', 'file_folder', 'flushed', 'grimacing', 'walking',
    'grey_exclamation', 'man_with_turban', 'bow', 'pouch', 'older_woman',
    'monkey_face', 'slot_machine', 'keycap_star', 'hot_pepper',
    'palm_tree', 'anchor', 'dango', 'flag-pg', 'candy', 'sailboat',
    'flag-bt', 'trolleybus', 'book', 'sunglasses', 'open_mouth', 'grapes',
    'tiger2', 'abc', 'disappointed', 'spock-hand', 'flag-vu', 'flag-xk',
    'u7121', 'lower_left_fountain_pen', 'roller_coaster', 'flag-ai',
    'flag-az', 'blue_heart', 'busstop', 'flag-nz', 'guitar',
    'desert_island', 'rice', 'balloon', 'taco', 'bank', 'flag-ca',
    'exclamation', 'punch', 'shinto_shrine', 'baby_symbol', 'flag-so',
    'flag-sj', 'baby_bottle', 'one', 'mans_shoe', 'card_index_dividers',
    'question', 'no_mobile_phones', 'eye', 'paperclip',
    'heavy_multiplication_x', 'slightly_smiling_face', 'green_apple',
    'flag-er', 'grey_question', 'running_shirt_with_sash', 'bulb',
    'speech_balloon', 'helmet_with_white_cross', 'haircut', 'o2',
    'flag-br', 'flag-ir', 'flag-cx', 'flag-ls', 'gift', 'diamonds',
    'waxing_gibbous_moon', 'flag-gl', 'sleepy', 'wink',
    'linked_paperclips', 'u5408', 'aerial_tramway', 'umbrella', 'e-mail',
    'flag-fk', 'oden', 'flag-gt', 'high_heel', 'womans_clothes', 'fish',
    'flag-np', 'ng', 'frame_with_picture', 'boar', 'man_with_gua_pi_mao',
    'desktop_computer', 'person_with_ball', 'flag-dj', 'video_game',
    'flag-nf', 'mushroom', 'airplane', 'elephant', 'flag-gm', 'flag-fo',
    'construction', 'lower_left_crayon', 'comet', 'low_brightness',
    'church', 'clock330', 'heavy_exclamation_mark', 'flag-sr', 'mag',
    'flag-ci', 'camera', 'small_red_triangle', 'ferry', 'imp', 'repeat',
    'suspension_railway', 'chocolate_bar', 'star_and_crescent',
    'capricorn', 'flag-tl', 'snail', 'flag-at', 'flag-mg',
    'large_blue_circle', 'car', 'black_square_for_stop', 'cityscape',
    'purple_heart', 'name_badge', 'flag-cl', 'loop', 'bride_with_veil',
    'performing_arts', 'flag-es', 'hammer_and_wrench', 'crossed_swords',
    'bike', 'sleeping', 'speaking_head_in_silhouette', 'two_hearts',
    'facepunch', 'straight_ruler', 'shield', 'fist', 'circus_tent',
    'white_small_square', 'rocket', 'hourglass_flowing_sand', 'flag-bb',
    'flag-gq', 'flag-by', 'arrow_up_down', 'flag-kn', 'rose', 'flag-bi',
    'lollipop', 'raised_hands', 'stadium', 'mountain_cableway',
    'waning_crescent_moon', 'flag-cr', 'flag-gn', 'gemini',
    'bullettrain_front',
    'black_right_pointing_triangle_with_double_vertical_bar', 'pig',
    'relieved', 'skin-tone-2', 'flag-tz', 'heart', 'hamburger', 'shirt',
    'large_blue_diamond', 'womans_hat', 'heartpulse', 'koko', 'end',
    'clock130', 'smiley', 'abcd', 'flag-lr', 'speedboat',
    'deciduous_tree', 'film_frames', 'racehorse', 'beers',
    'man-man-girl-girl', '8ball', 'rosette', 'person_with_pouting_face',
    'children_crossing', 'man-man-girl-boy', 'film_projector',
    'radio_button', 'satellite', 'flag-lt', 'ramen', 'arrow_right',
    'microscope', 'crab', 'hotsprings', 'flag-zm', 'atm', 'bookmark',
    'woman-woman-boy', 'secret', 'arrow_up_small', 'skin-tone-6',
    'lipstick', 'mailbox', 'reminder_ribbon', 'flag-nr', 'earth_americas',
    'baby', 'cricket_bat_and_ball', 'sos', 'flag-gw', 'bear', 'innocent',
    'hatched_chick', 'flag-tj', 'flipper', 'sports_medal', 'ski', 'dash',
    'flag-ie', 'books', 'star_of_david', 'thunder_cloud_and_rain',
    'clock6', 'black_circle_for_record', 'oncoming_police_car',
    'confused', 'melon', 'hourglass', 'o', 'flag-cg', 'fuelpump',
    'crystal_ball', 'ok', 'm', 'nine', 'heart_eyes_cat', 'flag-to',
    'stuck_out_tongue_closed_eyes', 'flag-eu', 'dizzy', 'flag-gi',
    'scream', 'jack_o_lantern', 'hammer_and_pick', 'spaghetti', 'flag-sd',
    'city_sunrise', 'man-woman-boy', 'flag-kg', 'convenience_store',
    'feet', 'medal', 'wrench', 'no_entry_sign', 'full_moon_with_face',
    'clock8', 'hotel', 'flag-sc', 'oncoming_automobile', 'copyright',
    'flag-je', 'man', 'jeans', 'arrow_upper_right', 'x', 'santa',
    'flag-lv', 'family', 'flag-cm', 'couple_with_heart',
    'disappointed_relieved', 'national_park', 'symbols', 'poop',
    'money_with_wings', 'spiral_note_pad', 'unlock', 'pineapple',
    'fallen_leaf', 'cold_sweat', 'sparkling_heart', 'flag-me',
    'footprints', 'flag-ic', 'flag-bz', 'globe_with_meridians',
    'point_right', 'bamboo', 'flag-va', 'closed_lock_with_key', 'top',
    'flag-hn', 'kissing_heart', 'cocktail', 'ab', 'clock430', 'cactus',
    'dancer', 'clock11', 'large_orange_diamond', 'flag-ax', 'cow', 'up',
    'police_car', 'latin_cross', 'sound', 'train2', 'gb', 'bikini',
    'flag-sb', 'put_litter_in_its_place', 'om_symbol',
    'stuck_out_tongue_winking_eye', 'foggy', 'mountain_railway',
    'hatching_chick', 'flag-sa', 'flag-ve', 'wind_blowing_face',
    'football', 'flag-km', 'flag-am', 'notebook', 'pick', 'flag-ae',
    'notebook_with_decorative_cover', 'postbox', 'flag-fi', 'flag-py',
    'smiling_imp', 'flag-be', 'mouse2', 'joy_cat', 'kimono', 'the_horns',
    'yellow_heart', 'flag-bn', 'volleyball', 'flag-ne', 'old_key',
    'scales', 'taurus', 'scream_cat', 'flag-ea', 'flag-sh',
    'reversed_hand_with_middle_finger_extended', 'sign_of_the_horns',
    'clock2', 'arrow_lower_right', 'repeat_one', 'moon', 'flag-tr',
    'triumph', 'rugby_football', 'cop', 'face_with_thermometer',
    'black_square_button', 'wheel_of_dharma', 'money_mouth_face', 'it',
    'musical_note', 'sake', 'atom_symbol', 'flag-hu', 'woman-heart-woman',
    'flag-hm', 'jp', 'package', 'birthday', 'ambulance', 'helicopter',
    'dolphin', 'blossom', 'clubs', 'flag-pt', 'ear', 'moyai', 'u6e80',
    'ship', 'control_knobs', 'no_pedestrians', 'pisces', 'stew', 'tent',
    'sparkler', 'snowboarder', 'cloud', 'arrow_lower_left', 'hibiscus',
    'tongue', 'burrito', 'flag-mx', 'game_die', 'sleuth_or_spy', 'tada',
    'baggage_claim', 'flag-mq', 'ice_skate', 'bathtub', 'leaves',
    'surfer', 'mobile_phone_off', 'lightening', 'hocho', 'flag-sx',
    'stopwatch', 'office', 'flag-ua', 'heavy_division_sign', 'flag-gb',
    'flag-lc', 'arrow_up', 'flag-kz', 'relaxed', 'four_leaf_clover',
    'man-woman-girl', 'flag-ge', 'flag-cz', 'wc', 'tiger', 'timer_clock',
    'wave', 'icecream', 'flag-mp', 'dollar', 'clock5', 'sparkles',
    'stuck_out_tongue', 'desert', 'tulip', 'negative_squared_cross_mark',
    'man-kiss-man', 'computer', 'flag-dk', 'tennis',
    'ideograph_advantage', 'email', 'flag-za', 'key', 'lips', 'flag-fm',
    'floppy_disk', 'ok_woman', 'smoking', 'clock1130', 'flag-et',
    'lion_face', 'meat_on_bone', 'dress', 'carousel_horse', 'flag-bf',
    'worried', 'flag-lk', 'bread', 'tropical_drink', 'file_cabinet',
    'coffee', 'bellhop_bell', 'couplekiss', 'earth_asia', 'sunflower',
    'strawberry', 'radioactive_sign', 'tired_face', 'clock930', 'pill',
    'underage', 'star', 'flag-ni', 'monkey', 'woman-woman-girl',
    'peace_symbol', 'kissing', 'signal_strength', 'flag-tc',
    'man-man-boy-boy', 'school', 'flag-au', 'sweat_drops',
    'fishing_pole_and_fish', 'flag-ly', 'leftwards_arrow_with_hook',
    'bus', 'video_camera', 'flag-io', 'information_desk_person',
    'flag-eg', 'u6307', 'flag-ma', 'movie_camera', 'flag-ug', 'flag-dm',
    'de', 'champagne', 'flag-sk', 'rage', 'orthodox_cross', 'egg',
    'flag-gr', 'ring', 'flag-yt', 'rowboat', 'woman-kiss-woman', 'cat2',
    'incoming_envelope', 'musical_score', 'world_map',
    'information_source', 'point_down', 'page_facing_up', 'knife',
    'crossed_flags', 'tomato', 'phone', 'flag-gp', 'airplane_arriving',
    'wavy_dash', 'flag-kw', 'gun', 'umbrella_on_ground', 'flag-ss',
    'flag-ck', 'kissing_cat', 'mouse', 'ferris_wheel',
    'telephone_receiver', 'musical_keyboard', 'ballot_box_with_check',
    'flag-gs', 'spades', 'bow_and_arrow', 'free', 'sushi',
    'left_right_arrow', 'skin-tone-4', 'cookie', 'coffin', 'dog2',
    'fountain', 'u55b6', 'flag-uy', 'ox', 'flag-id', 'briefcase', 'shell',
    'scorpian', 'rooster', 'small_red_triangle_down', 'flag-ad',
    'flag-il', 'flag-cy', 'speak_no_evil', 'pushpin', 'flag-vn',
    'ophiuchus', 'tophat', 'popcorn', 'label', 'airplane_departure',
    'flag-al', 'alarm_clock', 'printer', 'love_letter', 'barely_sunny',
    'speaker', 'kissing_closed_eyes', 'person_frowning', 'credit_card',
    'flag-in', 'crescent_moon', 'collision', 'spider', 'sweet_potato',
    'hotdog', 'post_office', 'inbox_tray', 'flag-mu', 'saxophone',
    'flag-is', 'flag-gg', 'gear', 'arrow_upper_left', 'euro',
    'heart_decoration', 'flag-pw', 'honey_pot', 'sun_behind_rain_cloud',
    'flag-ps', 'postal_horn', 'flag-my', 'pray', 'cinema', 'flag-ms',
    'prayer_beads', 'cherry_blossom', 'closed_umbrella', 'sparkle',
    'ear_of_rice', 'hole', 'skull', 'flag-cu', 'card_index', 'trophy',
    'eight_spoked_asterisk', 'astonished', 'confetti_ball', 'tv',
    'poodle', 'custard', 'sheep', 'microphone', 'flag-us',
    'chart_with_downwards_trend', 'mountain_bicyclist', 'flag-lu',
    'no_bell', 'tractor', 'u6709', 'zap', 'fog', 'calendar',
    'waving_white_flag', 'rotating_light', 'flag-pn', 'skier',
    'upside_down_face', 'fax', 'flag-bm', 'arrow_heading_up', 'door',
    'heartbeat', 'pencil', 'fries', 'rainbow', 'nose', 'u6708', 'watch',
    'snowman', 'potable_water', 'fire_engine', 'volcano', 'golfer',
    'flag-tm', 'anger', 'mag_right', 'traffic_light', 'trident',
    'checkered_flag', 'dove_of_peace', 'black_medium_square',
    'right_anger_bubble', 'flag-ga', 'eight_pointed_black_star', 'angry',
    'fire', 'seedling', 'motorway', 'clapper', 'accept',
    'bullettrain_side', 'on', 'arrows_clockwise', 'small_blue_diamond',
    'black_circle', 'do_not_litter', 'busts_in_silhouette',
    'sun_behind_cloud', 'christmas_tree', 'mount_fuji', 'open_hands',
    'flag-pm', 'beach_with_umbrella', 'flag-nc', 'flag-um', 'pager',
    'partly_sunny_rain', 'flag-bg', 'flag-ro', 'heart_eyes',
    'white_frowning_face', 'arrow_heading_down', 'pouting_cat',
    'oil_drum', 'horse', 'flag-ag', 'flag-im', 'classical_building',
    'flag-eh', 'black_medium_small_square', '-1', 'flag-vc', 'flag-bw',
    'man-man-girl', 'blush', 'smiley_cat', 'star2', 'flag-th', 'flag-vg',
    'waning_gibbous_moon', 'flag-iq', 'arrow_right_hook', 'rabbit', 'tea',
    'woman-woman-girl-girl', 'bento', 'chestnut', 'flag-lb',
    'white_medium_small_square', 'left_luggage', 'flag-tn',
    'earth_africa', 'recycle', 'flag-ye', 'sunny', 'syringe', 'herb',
    'white_square_button', 'athletic_shoe', 'see_no_evil', 'snow_cloud',
    'sun_with_face', 'flag-kr', 'keyboard', 'lightening_cloud',
    'telescope', 'raised_hand_with_fingers_splayed', 'gift_heart',
    'capital_abcd', 'snowflake', 'hammer', 'loud_sound', 'showman',
    'girl', 'flag-wf', 'nail_care', 'double_vertical_bar',
    'ballot_box_with_ballot', '1234', 'european_post_office', 'flag-vi',
    'flag-pf', 'racing_motorcycle', 'ru', 'cool', 'flag-jm',
    'field_hockey_stick_and_ball', 'flag-li', 'clock10', 'flag-tw',
    'bangbang', 'two_women_holding_hands', 'sob', 'compression',
    'flag-tf', 'oncoming_taxi', 'closed_book', 'flag-bs',
    'black_large_square', 'fried_shrimp', 'flags', 'smile_cat', 'vhs',
    'oncoming_bus', 'u7533', 'kiss', 'rewind', 'sunrise',
    'sun_small_cloud', 'shower', 'chicken', 'snake', 'memo', 'hamster',
    'skull_and_crossbones', 'flag-mf', 'es', 'man-woman-girl-boy',
    'mountain', 'skin-tone-5', 'hear_no_evil', 'barber', 'flag-sn',
    'water_buffalo', 'japan', 'purse', 'chains', 'person_with_blond_hair',
    'flag-dg', 'bird', 'dragon', 'anguished', 'cherries', 'flag-mh',
    'grin', 'flag-as', 'flag-sl', 'sagittarius', 'mailbox_with_mail',
    'thumbsup', 'leo', 'dragon_face', 'notes', 'scorpius', 'orange_book',
    'pig2', 'dancers', 'black_small_square', 'synagogue',
    'man-woman-boy-boy', 'pear', 'flag-co', 'lock', 'flag-ws', 'clock12',
    'bowling', 'red_circle', 'admission_tickets', 'open_book', 'back',
    'arrow_left', 'love_hotel', 'gem', 'flag-pr', 'evergreen_tree',
    'writing_hand', 'thought_balloon', 'house_with_garden',
    'arrow_down_small', 'dart', 'flag-td', 'weight_lifter', 'baseball',
    'flag-gy', 'aries', 'hugging_face', 'light_rail', 'metro', 'running',
    'flag-nl', 'mailbox_closed', 'loudspeaker', 'flag-mv',
    'zipper_mouth_face', 'persevere', 'railway_track', 'eggplant',
    'flag-bd', 'cow2', 'spiral_calendar_pad', 'uk', 'mostly_sunny',
    'badminton_racquet_and_shuttlecock', 'five', 'flag-se', 'flag-cv',
    'soccer', 'doughnut', 'thumbsdown',
    'black_left_pointing_double_triangle_with_vertical_bar',
    'tropical_fish', 'clock630', 'rolled_up_newspaper', 'u7a7a',
    'watermelon', 'wheelchair', 'bookmark_tabs', 'eyes',
    'black_right_pointing_double_triangle_with_vertical_bar',
    'house_buildings', 'flag-ba', 'flag-sz', 'flag-do', 'peach', 'fr',
    'bed', 'part_alternation_mark', 'wolf', 'white_circle', 'no_smoking',
    'libra', 'heavy_minus_sign', 'flag-la', 'basketball', 'grinning',
    'wind_chime', 'flag-fr', 'clock730', 'battery', 'vs', 'flag-qa',
    'mortar_board', 'red_car', 'man-woman-girl-girl', 'flag-ki', 'pound',
    'horse_racing', 'green_heart', 'train', 'full_moon', 'flag-kh',
    'wine_glass', 'flag-tv', 'last_quarter_moon_with_face', 'ant',
    'whale2', 'flag-jo', 'virgo', 'sweat', 'candle', 'place_of_worship',
    'handbag', 'clap', 'flag-bh', 'blue_book', 'mens', 'aquarius',
    'calling', 'flag-sm', 'two', 'arrow_down', 'ribbon', 'toilet',
    'kissing_smiling_eyes', 'heavy_heart_exclamation_mark_ornament',
    'flag-rs', 'kr', 'white_flower', 'flag-ke', 'sandal', 'flag-cw',
    'ice_hockey_stick_and_puck', 'smirk', 'maple_leaf',
    'white_medium_square', 'us', 'no_bicycles', 'shit', 'flag-mt',
    'wastebasket', 'turkey', 'knife_fork_plate', 'dromedary_camel',
    'lemon', 'dvd', 'rat', 'dagger_knife', 'european_castle', 'dog',
    'eyeglasses', 'minidisc', 'flag-ta',
    'man_in_business_suit_levitating', 'racing_car', 'japanese_castle',
    'mantelpiece_clock', 'envelope', 'clock1', 'skin-tone-3', 'customs',
    'woman-woman-girl-boy', 'slightly_frowning_face', 'flag-ee',
    'flag-pa', 'rabbit2', 'flag-sg', 'beer', 'six', 'triangular_ruler',
    'crocodile', 'new_moon', 'taxi', 'hearts', 'fork_and_knife', 'kaaba',
    'paw_prints', 'keycap_ten', 'tram', 'biohazard_sign', 'unamused',
    'night_with_stars', 'flag-cc', 'pizza', 'funeral_urn', '+1', 'goat',
    'milky_way', 'tokyo_tower', 'monorail', 'boy', 'laughing', 'flag-sv',
    'ice_cream', 'cn', 'flag-bv', 'beginner', 'honeybee', 'octopus',
    'flag-ky', 'clock3', 'bell', 'flag-it', 'u7981', 'spider_web',
    'blue_car', 'cat', 'card_file_box', 'zzz', 'bar_chart', 'warning',
    'tornado', 'clock1030', 'mosque', 'flag-cd', 'studio_microphone',
    'flag-mo', 'trackball', 'broken_heart', 'date', 'school_satchel',
    'flag-ac', 'chipmunk', 'flag-na', 'a', 'space_invader', 'flag-aq',
    'cl', 'swimmer', 'nut_and_bolt', 'lock_with_ink_pen', 'poultry_leg',
    'fish_cake', 'man-man-boy', 'blowfish', 'heavy_dollar_sign', 'eight',
    'bouquet', 'flag-zw', 'flag-ar', 'flag-bj', 'cry', 'flag-st',
    'city_sunset', 'guardsman', 'cancer', 'necktie', 'three',
    'fast_forward', 'white_check_mark', 'angel', 'leopard', 'violin',
    'point_up_2', 'revolving_hearts', 'flag-de', 'small_airplane',
    'crown', 'mute', 'flag-ht', 'japanese_goblin', 'flag-md',
    'heavy_check_mark', 'flag-dz', 'flag-ml', 'mailbox_with_no_mail',
    'raised_hand', 'u5272', 'interrobang', 'table_tennis_paddle_and_ball',
    'couch_and_lamp', 'bee', 'ok_hand', 'rice_cracker', 'trumpet',
    'minibus', 'dizzy_face', 'flag-mk', 'partly_sunny', 'flag-bo',
    'building_construction', 'camel', 'arrow_forward', 'raising_hand',
    'flag-cp', 'corn', 'flag-ec', 'diamond_shape_with_a_dot_inside',
    'point_up', 'baby_chick', 'dolls', 'shamrock', 'articulated_lorry',
    'ram', 'headphones', 'level_slider', 'vertical_traffic_light',
    'rice_scene', 'mask', 'iphone', 'currency_exchange',
    'steam_locomotive', 'joy', 'chart_with_upwards_trend', 'house',
    'twisted_rightwards_arrows', 'man-heart-man', 'no_mouth',
    'high_brightness', 'clipboard', 'newspaper', 'face_with_head_bandage',
    'curly_loop', 'flag-gf', 'flag-bq', 'new', 'sunrise_over_mountains',
    'flower_playing_cards', 'flag-cn', 'page_with_curl', 'flag-ph',
    'flag-mw', 'yum', 'flag-ng', 'confounded', 'waving_black_flag',
    'scroll', 'apple', 'flag-om', 'unicorn_face', 'round_pushpin',
    'moneybag', 'koala', 'flag-si', 'wedding', 'station', 'tanabata_tree',
    'japanese_ogre', 'mega', 'flag-uz', 'flag-kp',
    }
