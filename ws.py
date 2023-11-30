import json
import aiohttp
import aiohttp.web
import PIL
import PIL.Image
import PIL.ImageGrab
import PIL.ImageChops
import pyautogui
import traceback
from controller import encode_int8, encode_int16, decode_int8, decode_int16
from io import BytesIO

# Real resolution
real_width, real_height = 0, 0

async def inputWS(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:

    # Failsafe disable
    pyautogui.FAILSAFE = False

    ws = aiohttp.web.WebSocketResponse()
    await ws.prepare(request)

    # Track pressed key state for future reset on disconnect
    state_keys = {}

    def release_keys():
        for k in state_keys.keys():
            if state_keys[k]:
                pyautogui.keyUp(k)

    def update_key_state(key, state):
        state_keys[key] = state

    # Read stream
    async def async_worker():
        try:
            # Reply to requests
            async for msg in ws:

                # Receive input data
                if msg.type == aiohttp.WSMsgType.BINARY:
                    try:
                        # Drop on invalid packet
                        if len(msg.data) == 0:
                            continue

                        # Parse params
                        packet_type = decode_int8(msg.data[0:1])
                        payload = msg.data[1:]

                        # Input request
                        if packet_type == 0x03:

                            # Unpack events data
                            data = json.loads(bytes.decode(payload, encoding='ascii'))

                            # Iterate events
                            for event in data:
                                if event[0] == 0: # mouse position
                                    mouse_x = max(0, min(real_width, event[1]))
                                    mouse_y = max(0, min(real_height, event[2]))

                                    pyautogui.moveTo(mouse_x, mouse_y)
                                elif event[0] == 1: # mouse down
                                    mouse_x = max(0, min(real_width, event[1]))
                                    mouse_y = max(0, min(real_height, event[2]))
                                    button = event[3]

                                    # Allow only left, middle, right
                                    if button < 0 or button > 2:
                                        continue

                                    pyautogui.mouseDown(mouse_x, mouse_y, button=[ 'left', 'middle', 'right' ][button])
                                elif event[0] == 2: # mouse up
                                    mouse_x = max(0, min(real_width, event[1]))
                                    mouse_y = max(0, min(real_height, event[2]))
                                    button = event[3]

                                    # Allow only left, middle, right
                                    if button < 0 or button > 2:
                                        continue

                                    pyautogui.mouseUp(mouse_x, mouse_y, button=[ 'left', 'middle', 'right' ][button])
                                elif event[0] == 3: # mouse scroll
                                    mouse_x = max(0, min(real_width, event[1]))
                                    mouse_y = max(0, min(real_height, event[2]))
                                    dy = int(event[3])

                                    pyautogui.scroll(dy, mouse_x, mouse_y)
                                elif event[0] == 4: # keypress
                                    keycode = event[1]

                                    pyautogui.keyDown(keycode)
                                    update_key_state(keycode, True)
                                elif event[0] == 5: # keypress
                                    keycode = event[1]

                                    pyautogui.keyUp(keycode)
                                    update_key_state(keycode, False)
                    except:
                        traceback.print_exc()
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f'ws connection closed with exception { ws.exception() }')
        except:
            traceback.print_exc()

    await async_worker()

    # Release stuck keys
    release_keys()

    return ws


async def streamWS(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:

    # Const config
    DOWNSAMPLE = PIL.Image.BILINEAR

    # Minimal amount of partial frames to be sent before sending full repaint frame to avoid fallback to full repaint on long delay channels
    MIN_PARTIAL_FRAMES_BEFORE_FULL_REPAINT = 60

    # Minimal amount of empty frames to be sent before sending full repaint frame to avoid fallback to full repaint on long delay channels
    MIN_EMPTY_FRAMES_BEFORE_FULL_REPAINT = 120

    ws = aiohttp.web.WebSocketResponse()
    await ws.prepare(request)

    # Frame buffer
    buffer = BytesIO()

    # Read stream
    async def async_worker():

        # Last screen frame
        last_frame = None
        # Track count of partial frames send since last full repaint frame send and prevent firing full frames on low internet
        partial_frames_since_last_full_repaint_frame = 0
        # Track count of empty frames send since last full repaint frame send and prevent firing full frames on low internet
        empty_frames_since_last_full_repaint_frame = 0

        # Store remote viewport size to force-push full repaint
        viewport_width = 0
        viewport_height = 0

        try:
            # Reply to requests
            async for msg in ws:

                # Receive input data
                if msg.type == aiohttp.WSMsgType.BINARY:
                    try:
                        # Drop on invalid packet
                        if len(msg.data) == 0:
                            continue

                        # Parse params
                        packet_type = decode_int8(msg.data[0:1])
                        payload = msg.data[1:]

                        # Frame request
                        if packet_type == 0x01:
                            req_viewport_width = decode_int16(payload[0:2])
                            req_viewport_height = decode_int16(payload[2:4])
                            quality = decode_int8(payload[4:5])

                            # Grab frame
                            image = PIL.ImageGrab.grab()

                            # Real dimensions
                            global real_width, real_height
                            real_width, real_height = image.width, image.height

                            # Resize
                            if image.width > req_viewport_width or image.height > req_viewport_height:
                                image.thumbnail((req_viewport_width, req_viewport_height), DOWNSAMPLE)

                            # Write header: frame response
                            buffer.seek(0)
                            buffer.write(encode_int8(0x02))
                            buffer.write(encode_int16(real_width))
                            buffer.write(encode_int16(real_height))

                            # Compare frames
                            if last_frame is not None:
                                diff_bbox = PIL.ImageChops.difference(last_frame, image).getbbox()

                            # Check if this is first frame of should force repaint full surface
                            if last_frame is None or \
                                    viewport_width != req_viewport_width or \
                                    viewport_height != req_viewport_height or \
                                    partial_frames_since_last_full_repaint_frame > MIN_PARTIAL_FRAMES_BEFORE_FULL_REPAINT or \
                                    empty_frames_since_last_full_repaint_frame > MIN_EMPTY_FRAMES_BEFORE_FULL_REPAINT:
                                buffer.write(encode_int8(0x01))

                                # Write body
                                image.save(fp=buffer, format='JPEG', quality=quality)
                                last_frame = image

                                viewport_width = req_viewport_width
                                viewport_height = req_viewport_height
                                partial_frames_since_last_full_repaint_frame = 0
                                empty_frames_since_last_full_repaint_frame = 0

                            # Send nop
                            elif diff_bbox is None :
                                buffer.write(encode_int8(0x00))
                                empty_frames_since_last_full_repaint_frame += 1

                            # Send partial repaint region
                            else:
                                buffer.write(encode_int8(0x02))
                                buffer.write(encode_int16(diff_bbox[0])) # crop_x
                                buffer.write(encode_int16(diff_bbox[1])) # crop_y

                                # Write body
                                cropped = image.crop(diff_bbox)
                                cropped.save(fp=buffer, format='JPEG', quality=quality)
                                last_frame = image
                                partial_frames_since_last_full_repaint_frame += 1

                            buflen = buffer.tell()
                            buffer.seek(0)
                            mbytes = buffer.read(buflen)
                            buffer.seek(0)

                            await ws.send_bytes(mbytes)

                    except:
                        traceback.print_exc()
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f'ws connection closed with exception { ws.exception() }')
        except:
            traceback.print_exc()

    await async_worker()

    return ws