from telethon import TelegramClient
from telethon import TelegramBareClient

from telethon.tl.types import Channel

from telethon.tl.functions.updates import GetChannelDifferenceRequest
from telethon.tl.functions.messages import EditMessageRequest
from telethon.tl.functions.channels import DeleteMessagesRequest
from telethon.tl.functions.messages import SendMessageRequest

from telethon.tl.types import ChannelMessagesFilterEmpty
from telethon.tl.types.updates import ChannelDifference
from telethon.tl.types.updates import ChannelDifferenceEmpty
from telethon.tl.types.updates import ChannelDifferenceTooLong
from telethon.tl.types import Message

from telethon.errors import FloodWaitError
from telethon.utils import get_input_peer

from time import sleep
import threading
import datetime
from urllib.request import urlopen

print('initialize')

api_id = 12345
api_hash = '12345789abcefg'
phone = '<< place here your phone number >> '

client = TelegramClient('my_session', api_id, api_hash)
print('try connect')
client.connect()
print('connected')

if not client.is_user_authorized():
    print('try authentication')
    client.send_code_request(phone)
    client.sign_in(phone, input('enter code: '))

print('authenticated')

(dialogs, user_or_chats) = client.get_dialogs()
dest_channels = []

class DestChannel:
    pts = None
    channel = None

    def __init__(self, pts, channel):
        self.pts = pts
        self.channel = channel

    def get_updates(self, client: TelegramClient):
        updates = client.invoke(GetChannelDifferenceRequest(get_input_peer(self.channel), ChannelMessagesFilterEmpty(), self.pts, -1))
        if type(updates) is ChannelDifference:
            self.pts = updates.pts
            return updates
        elif type(updates) is ChannelDifferenceTooLong:
            self.pts = updates.pts
            return updates
        else:
            return None


for i, user_or_chat in enumerate(user_or_chats):
    if type(user_or_chat) is Channel:
        print('channel fetched: ' + user_or_chat.title)
        dest_channels.append(DestChannel(dialogs[i].pts, user_or_chat))

class WaitToClose(threading.Thread):
    work = True

    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        print('enter to exit')
        input()
        self.work = False


waiter = WaitToClose()
waiter.start()

class SolCleaner:
    client = None
    channel = None
    msg = None
    me_id = None

    scanned = 0
    deleted = 0
    offset_id = 0
    current_date = None
    limit = 90

    del_list = []

    def __init__(self, client: TelegramClient, msg: Message, channel: Channel, me_id):
        self.client = client
        self.msg = msg
        self.channel = channel
        self.me_id = me_id

    def run(self):
        self.update('실행 대기중...', True)
        quit = False

        while True:
            sleep(0.2)
            print('> current offset: %d' % self.offset_id)
            count = None
            messages = None
            entities = None

            while True:
                try:
                    count, messages, entities = self.client.get_message_history(self.channel, limit=self.limit, offset_id=self.offset_id, max_id=self.msg.id)
                    break
                except ValueError:
                    self.client.disconnect()
                    self.client.connect()
                except FloodWaitError as e:
                    sleep(e.seconds + 2)

            min_id = None

            for message in messages:
                if min_id is None or min_id > message.id:
                    min_id = message.id
                self.scanned = self.scanned + 1
                if message.from_id == self.me_id or message.from_id is None:
                    self.deleted = self.deleted + 1
                    self.current_date = message.date
                    self.delete(message.id)
                    print("> %d, %s (%d confirmed, %d deleted)" % (
                        self.offset_id,
                        self.current_date.strftime('%Y/%m/%d %H:%M:%S'),
                        self.scanned, self.deleted
                    ))
                    if hasattr(message, 'message'):
                        if message.message == '#솔클리너포인트':
                            quit = True
                            break

            if count < self.limit: break
            if quit: break
            if min_id is not None: self.offset_id = min_id
            else: break

        self.flush_delete()
        self.update('종료됨', True)
        sleep(10)
        self.edit('#솔클리너포인트')
        self.flush_delete(False)
        print('done.')

    def flush_delete(self, with_update=True):
        while True:
            try:
                print('try processing delete queue...')
                self.client.invoke(DeleteMessagesRequest(get_input_peer(self.channel), self.del_list))
                break
            except ValueError:
                self.client.disconnect()
                self.client.connect()
            except FloodWaitError as e:
                print('flood error occurred, waiting...')
                sleep(e.seconds + 2)
        self.del_list.clear()
        if with_update: self.update('작동중')

    def update(self, status, force=False):
        datestr = 'N/A'
        print('update message...')
        if self.current_date is not None:
            datestr = self.current_date.strftime('%Y/%m/%d %H:%M:%S')

        self.edit("<< 솔클리너 " + status + " >>\n%d (%s)\n(%d개 확인됨, %d개 삭제 예정 또는 처리됨)" % (
            self.offset_id,
            datestr,
            self.scanned, self.deleted
        ), force)


    def edit(self, msg, force=False):
        while True:
            try:
                self.client.invoke(EditMessageRequest(get_input_peer(self.channel), self.msg.id, message=msg))
                break
            except ValueError:
                self.client.disconnect()
                self.client.connect()
            except FloodWaitError as e:
                if not force: break
                print('flood error occurred, waiting...')
                sleep(e.seconds + 2)

    def delete(self, msg_id):
        self.del_list.append(msg_id)
        if len(self.del_list) >= self.limit:
            self.flush_delete()


def edit_message(msg: Message, text: str):
    EditMessageRequest(msg, str)

me_id = client.get_me().id
print('me_id = %d' % me_id)

while waiter.work:
    sleep(0.1)
    for dest_channel in dest_channels:
        updates = dest_channel.get_updates(client)
        if updates is None: continue
        elif type(updates) is ChannelDifference:
            for msg in updates.new_messages:
                if (msg.from_id == me_id or msg.from_id is None) and hasattr(msg, 'message'):
                    if '#솔클리너실행' in msg.message:
                        print('command detected, start cleaning...')
                        SolCleaner(client, msg, dest_channel.channel, me_id).run()
                    elif '#업데이트확인' in msg.message:
                        try:
                            url = urlopen('http://comic.naver.com/webtoon/list.nhn?titleId=119874&weekday=')
                            html = url.read().decode('utf-8')
                            url.close()
                            spt = html.split('<a href="/webtoon/detail.nhn?titleId=119874&no=')
                            toon_id = spt[1].split('&')[0]
                            update_date = spt[2].split('<td class="num">')[1].split('</')[0]
                            sleep(0.5)
                            client.invoke(EditMessageRequest(get_input_peer(dest_channel.channel), msg.id, message='< 업데이트 정보 >\n%s\nhttp://comic.naver.com/webtoon/detail.nhn?titleId=119874&no=%s&weekday=tue' % (update_date, toon_id)))
                        except:
                            client.invoke(EditMessageRequest(get_input_peer(dest_channel.channel), msg.id, message='< 업데이트 정보 >\n일시적인 오류로 업데이트를 확인할 수 없습니다.'))


client.disconnect()
