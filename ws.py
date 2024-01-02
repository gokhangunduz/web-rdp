import asyncio
import logging

import aiohttp
import aiohttp.web

from controller import (
    PACKET_FRAME_REQUEST,
    PACKET_INPUT,
    decode_int8,
    decode_int16,
)
from frames import FrameEncoder, grab_screen
from inputs import InputController, decode_input_packet

log = logging.getLogger(__name__)

# Seconds between websocket pings, dead peers are dropped after missing one
HEARTBEAT = 20

# Largest message accepted from a client
MAX_MESSAGE_SIZE = 64 * 1024

# Size of a frame request: viewport width, viewport height, quality
FRAME_REQUEST_SIZE = 2 + 2 + 1


def render_frame(encoder: FrameEncoder, screen, viewport_width, viewport_height, quality):
    """Capture and encode one frame. Blocking, run it in an executor."""
    image = grab_screen()
    screen.update(image.width, image.height)
    return encoder.encode(image, viewport_width, viewport_height, quality)


async def inputWS(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
    ws = aiohttp.web.WebSocketResponse(heartbeat=HEARTBEAT, max_msg_size=MAX_MESSAGE_SIZE)
    await ws.prepare(request)

    loop = asyncio.get_running_loop()
    controller = InputController(
        request.app["input_backend"], request.app["screen"], request.app["allowed_keys"]
    )

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                if len(msg.data) == 0:
                    continue  # drop invalid packet

                try:
                    packet_type = decode_int8(msg.data[0:1])
                    payload = msg.data[1:]

                    if packet_type == PACKET_INPUT:
                        events = decode_input_packet(payload)
                        if events is not None:
                            await loop.run_in_executor(None, controller.apply, events)
                except Exception:
                    log.exception("failed to handle input packet")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.warning("input connection closed with exception %s", ws.exception())
    finally:
        # Release stuck keys and buttons, the browser can not do it anymore
        await loop.run_in_executor(None, controller.release_all)

    return ws


async def streamWS(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
    ws = aiohttp.web.WebSocketResponse(heartbeat=HEARTBEAT, max_msg_size=MAX_MESSAGE_SIZE)
    await ws.prepare(request)

    loop = asyncio.get_running_loop()
    screen = request.app["screen"]
    encoder = FrameEncoder()

    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.BINARY:
            if len(msg.data) == 0:
                continue  # drop invalid packet

            try:
                packet_type = decode_int8(msg.data[0:1])
                payload = msg.data[1:]

                if packet_type == PACKET_FRAME_REQUEST and len(payload) >= FRAME_REQUEST_SIZE:
                    viewport_width = max(1, decode_int16(payload[0:2]))
                    viewport_height = max(1, decode_int16(payload[2:4]))
                    quality = max(1, min(100, decode_int8(payload[4:5])))

                    frame = await loop.run_in_executor(
                        None,
                        render_frame,
                        encoder,
                        screen,
                        viewport_width,
                        viewport_height,
                        quality,
                    )
                    await ws.send_bytes(frame)
            except ConnectionResetError:
                break
            except Exception:
                # The client waits for an answer to every request, so hanging up
                # makes it reconnect instead of stalling forever.
                log.exception("failed to produce frame")
                await ws.close(code=aiohttp.WSCloseCode.INTERNAL_ERROR)
                break
        elif msg.type == aiohttp.WSMsgType.ERROR:
            log.warning("stream connection closed with exception %s", ws.exception())

    return ws
