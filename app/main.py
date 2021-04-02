import asyncio
import json
import os
import sys
import time
from PIL import Image
import aiofiles.os
import magic
import aioschedule as schedule
import requests
import logging
from tempfile import NamedTemporaryFile
import datetime as dt

from nio import AsyncClient, LoginResponse, UploadResponse
from nio.events.room_events import UnknownEvent


async def send_image(client, room_id, image):
    """Send image to toom.

    Arguments:
    ---------
    client : Client
    room_id : str
    image : str, file name of image

    This is a working example for a JPG image.
        "content": {
            "body": "someimage.jpg",
            "info": {
                "size": 5420,
                "mimetype": "image/jpeg",
                "thumbnail_info": {
                    "w": 100,
                    "h": 100,
                    "mimetype": "image/jpeg",
                    "size": 2106
                },
                "w": 100,
                "h": 100,
                "thumbnail_url": "mxc://example.com/SomeStrangeThumbnailUriKey"
            },
            "msgtype": "m.image",
            "url": "mxc://example.com/SomeStrangeUriKey"
        }

    """
    mime_type = magic.from_file(image, mime=True)  # e.g. "image/jpeg"
    if not mime_type.startswith("image/"):
        print("Drop message because file does not have an image mime type.")
        return

    im = Image.open(image)
    (width, height) = im.size  # im.size returns (width,height) tuple

    # first do an upload of image, then send URI of upload to room
    file_stat = await aiofiles.os.stat(image)
    async with aiofiles.open(image, "r+b") as f:
        resp, maybe_keys = await client.upload(
            f,
            content_type=mime_type,  # image/jpeg
            filename=os.path.basename(image),
            filesize=file_stat.st_size)
    if (isinstance(resp, UploadResponse)):
        print("capybara was uploaded to matrix server")
    else:
        print(f"Failed to upload image. Failure response: {resp}")

    content = {
        "body": os.path.basename(image),  # descriptive title
        "info": {
            "size": file_stat.st_size,
            "mimetype": mime_type,
            "thumbnail_info": None,  # TODO
            "w": width,  # width in pixel
            "h": height,  # height in pixel
            "thumbnail_url": None,  # TODO
        },
        "msgtype": "m.image",
        "url": resp.content_uri,
    }

    try:
        resp = await client.room_send(
            room_id,
            message_type="m.room.message",
            content=content
        )
        with open('/storage/event_id', 'w') as event_id_file:
            event_id_file.write(resp.event_id)
        print("capybara was posted successfully")
    except Exception:
        print(f"Image send of file {image} failed.")


async def getclient() -> AsyncClient:
    password = os.environ.get('MATRIX_PASSWORD')
    user = os.environ.get('MATRIX_USER')
    homeserver = os.environ.get('MATRIX_HOMESERVER')

    if password and user and homeserver:
        client = AsyncClient(homeserver, user)
        resp = await client.login(password, device_name='capybot')

        if (isinstance(resp, LoginResponse)):
            return client
    return False


async def daily_routine() -> None:
    room_id = os.environ.get('MATRIX_ROOM')

    client = await getclient()

    if room_id:
        # get image
        print('getting capybara')
        resp = requests.get('https://capybara.lol/today')
        if resp.status_code == 200:
            f= NamedTemporaryFile()
            f.write(resp.content)
            print('posting capybara')
            await  send_image(client, room_id, f.name)
            f.close()
    
        await client.close()
    return False


async def parse_event(event):
    if isinstance(event, UnknownEvent) and event.type == 'm.reaction':
        content = event.source.get('content')
        if content:
            relates = content.get('m.relates_to')
            if relates:
                with open('/storage/event_id', 'r') as event_id_file:
                    last_capy_id = event_id_file.read()
                event_id = relates.get('event_id')
                key = relates.get('key')
                if event_id and event_id == last_capy_id:
                    if key == '😂':
                        requests.get('https://capybara.lol/vote/funny')
                        print('voted funny')
                    if key == '😍':
                        requests.get('https://capybara.lol/vote/cute')
                        print('voted cute')


async def main():
    print('starting capybara bot')
    client = await getclient()
    if client:
        print('logged in')

    at_time = os.environ.get('CAPYBOT_TIME')

    todays_capy = dt.datetime.now().replace(
        hour=int(at_time.split(':')[0]),
        minute=int(at_time.split(':')[1]),
        second=0, microsecond=0
    )
    room_id = os.environ.get('MATRIX_ROOM')

    if at_time:
        schedule.every().day.at(at_time).do(daily_routine)

        if os.path.exists('/storage/sync_token'):
            with open('/storage/sync_token','r') as sync_token:
                client.next_batch = sync_token.read()

        while True:
            await schedule.run_pending()
            sync_response = await client.sync(3000)
            now = dt.datetime.now()
            if now > todays_capy:
                if len(sync_response.rooms.join) > 0 \
                    and room_id in sync_response.rooms.join.keys():
                    room_info = sync_response.rooms.join[room_id]
                    for event in room_info.timeline.events:
                        await parse_event(event)

            with open('/storage/sync_token','w') as sync_token:
                sync_token.write(sync_response.next_batch)


asyncio.get_event_loop().run_until_complete(main())