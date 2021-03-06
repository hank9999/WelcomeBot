# -*- encoding : utf-8 -*-
import io
import json
import os
import time
import uuid

import aiohttp
from PIL import Image, ImageDraw, ImageFont
import aiofiles

from khl import Bot, Message, Cert, EventTypes, Event, ChannelPrivacyTypes, MessageTypes

# webhook
# bot = Bot(cert=Cert(token='token', verify_token='verify_token'), port=3000,
#           route='/khl-wh')

# websocket
bot = Bot(token='token')


async def get_user(user_id: str):
    result = (await bot.client.gate.request('GET', 'user/view', params={'user_id': user_id}))
    return result


async def get_guild(guild_id):
    result = await bot.client.gate.request('GET', 'guild/view', params={'guild_id': guild_id})
    return result


async def get_greeting_text(guild: str) -> (str, str):
    if not os.path.exists(f'greetings/{guild}.json'):
        return '', ''
    else:
        async with aiofiles.open(f'greetings/{guild}.json', 'r', encoding='utf-8') as f:
            d = json.loads(await f.read())
        return d['text'], d['pic_text']


async def get_channel_id(guild: str):
    if not os.path.exists(f'greetings/{guild}.json'):
        return ''
    else:
        async with aiofiles.open(f'greetings/{guild}.json', 'r', encoding='utf-8') as f:
            d = json.loads(await f.read())
        return d['channel']


async def set_setting(guild_id, setting, text):
    if not os.path.exists(f'greetings/{guild_id}.json'):
        async with aiofiles.open(f'greetings/{guild_id}.json', 'w', encoding='utf-8') as f:
            await f.write(json.dumps({'text': '', 'pic_text': '', 'channel': ''}))
    async with aiofiles.open(f'greetings/{guild_id}.json', 'r', encoding='utf-8') as f:
        d = json.loads(await f.read())
    d[setting] = text
    async with aiofiles.open(f'greetings/{guild_id}.json', 'w', encoding='utf-8') as f:
        await f.write(json.dumps(d))


async def replace_text(text: str, user_id: str, username: str, guild_name: str, time_text: str):
    text = text.replace('%at%', f'(met){user_id}(met)')
    text = text.replace('%name%', f'{username}')
    text = text.replace('%guild_name%', f'{guild_name}')
    text = text.replace('%time%', time_text)
    text = text.replace('%n%', '\n')
    return text


async def generate_welcome_pic(pic_text: str, avatar_url: str, guild_id: str):
    uid = str(uuid.uuid4())
    avatar_size = (180, 180)
    bg_path = f'greetings/{guild_id}.png'
    pic_path = f'tempImage/{uid}-pic.png'
    async with aiohttp.ClientSession() as session:
        async with session.get(avatar_url) as resp:
            avatar = await resp.read()

    bg = Image.open(bg_path)
    bg_size = bg.size
    avatar = Image.open(io.BytesIO(avatar))
    avatar = avatar.resize(avatar_size)

    # ?????????????????????, ??????????????? RGBA ??????
    mask = Image.new('RGBA', avatar_size, color=(0, 0, 0, 0))
    # ????????????
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, avatar_size[0], avatar_size[1]), fill=(0, 0, 0, 255))

    # ??????????????????
    # x?????? y??????
    x, y = int((bg_size[0] - avatar_size[0]) / 2), int((bg_size[1] - avatar_size[1]) / 2.5)
    # box ???????????? bg ????????????
    # box(x1, y1, x2, y2)
    # x1,y1 ???????????????????????????
    # x2,y2 ???????????????????????????
    box = (x, y, (x + avatar_size[0]), (y + avatar_size[1]))
    # ???????????????paste(img, box=None, mask=None)??????
    #   img ???????????????????????????
    #   box ????????? ????????? bg ????????????
    #   mask ????????????????????? ps??? ????????? mask ??? Alpha ?????????????????????1?????????
    bg.paste(avatar, box, mask)

    draw = ImageDraw.Draw(bg)

    font = ImageFont.truetype('???????????????.ttf', 25)
    # ????????????????????????????????????
    # ???????????? tuple (width, height)
    # ???????????????????????????????????????
    find_n = pic_text.find('\n')
    if find_n >= 0:
        text_used_for_get_width = pic_text[:find_n]
        text_init_width = font.getsize(text_used_for_get_width)
        # ??????????????????
        is_first = True
        text_coordinate = int((bg_size[0] - text_init_width[0]) / 2), int(bg_size[1] * 0.73)
        for i in pic_text.split('\n'):
            if not is_first:
                text_width = font.getsize(i)
                text_coordinate = int((bg_size[0] - text_width[0]) / 2), text_coordinate[1] + text_init_width[1] + 10
            else:
                is_first = False
            draw.text(text_coordinate, i, font=font)

    else:
        text_width = font.getsize(pic_text)
        # ??????????????????
        text_coordinate = int((bg_size[0] - text_width[0]) / 2), int(bg_size[1] * 0.73)
        draw.text(text_coordinate, pic_text, font=font)

    bg.save(pic_path)
    return pic_path


@bot.on_event(EventTypes.JOINED_GUILD)
async def greet(_: Bot, e: Event):
    if e.channel_type != ChannelPrivacyTypes.GROUP:
        return
    guild_id = e.target_id
    user_id = e.body['user_id']
    join_time = e.body['joined_at']
    channel_id = await get_channel_id(guild_id)
    if len(channel_id) == 0:
        return
    text, pic_text = await get_greeting_text(guild_id)
    if text == '' and pic_text == '':
        return
    user = await get_user(user_id)
    guild = await get_guild(guild_id)
    time_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(str(join_time)[:-3])))
    text = await replace_text(text, user_id, user['username'], guild['name'], time_text)
    pic_text = await replace_text(pic_text, user_id, user['username'], guild['name'], time_text)
    pic_path = await generate_welcome_pic(pic_text, user['avatar'], guild_id)
    pic_url = (await bot.client.gate.request('POST', 'asset/create', data={'file': open(pic_path, 'rb')}))['url']
    ch = await bot.fetch_public_channel(channel_id)
    await ch.send(text)
    await ch.send(pic_url, type=MessageTypes.IMG)
    os.remove(pic_path)


async def get_master_id(guild: str):
    result = await bot.client.gate.request('GET', 'guild/view', params={'guild_id': guild})
    return result['master_id']


async def check_permission(guild: str, user_id: str) -> bool:
    result = False
    master_id = await get_master_id(guild)
    if master_id == user_id:
        result = True
    return result


@bot.command(regex='.???????????????(.*)')
async def set_text(msg: Message, text: str):
    guild_id = msg.ctx.guild.id
    user_id = msg.author_id
    text = text.strip()
    if not (await check_permission(guild_id, user_id)):
        await msg.reply('??????????????????????????????')
        return
    await set_setting(guild_id, 'text', text)
    await msg.reply('?????????????????????')


@bot.command(regex='.?????????????????????(.*)')
async def set_pic_text(msg: Message, text: str):
    guild_id = msg.ctx.guild.id
    user_id = msg.author_id
    text = text.strip()
    if not (await check_permission(guild_id, user_id)):
        await msg.reply('??????????????????????????????')
        return
    await set_setting(guild_id, 'pic_text', text)
    await msg.reply('???????????????????????????')


@bot.command(name='????????????', prefixes=['.'])
async def set_channel(msg: Message):
    guild_id = msg.ctx.guild.id
    user_id = msg.author_id
    channel_id = msg.ctx.channel.id
    if not (await check_permission(guild_id, user_id)):
        await msg.reply('??????????????????????????????')
        return
    await set_setting(guild_id, 'channel', channel_id)
    await msg.reply('??????????????????')


if __name__ == '__main__':
    bot.run()
