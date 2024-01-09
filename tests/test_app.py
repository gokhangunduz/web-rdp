import asyncio
import base64
import json

import aiohttp
import PIL.Image
import pytest

import ws
from config import Config
from controller import PACKET_FRAME_RESPONSE, FRAME_FULL, FRAME_NOP

AUTH = {"Authorization": "Basic " + base64.b64encode(b"admin:secret").decode()}


@pytest.fixture
def screen_image(monkeypatch):
    monkeypatch.setattr(ws, "grab_screen", lambda: PIL.Image.new("RGB", (1000, 500), "navy"))


@pytest.fixture
async def client(aiohttp_client, web_rdp, backend, screen_image, monkeypatch):
    monkeypatch.setattr("auth.FAILED_LOGIN_DELAY", 0)
    config = Config(username="admin", password="secret")
    return await aiohttp_client(web_rdp.make_app(config, input_backend=backend))


def frame_request(width, height, quality=60):
    return bytes([0x01]) + width.to_bytes(2, "little") + height.to_bytes(2, "little") + bytes([quality])


def input_packet(events):
    return bytes([0x03]) + json.dumps(events).encode("ascii")


async def test_requires_login(client):
    assert (await client.get("/")).status == 401
    assert (await client.get("/", headers=AUTH)).status == 200


async def test_serves_static_files(client):
    for path, content_type in [
        ("/", "text/html"),
        ("/script.js", "application/javascript"),
        ("/style.css", "text/css"),
        ("/keys.json", "application/json"),
    ]:
        response = await client.get(path, headers=AUTH)
        assert response.status == 200
        assert response.content_type == content_type


async def test_websocket_rejects_cross_origin(client):
    response = await client.get("/streamWS", headers={**AUTH, "Origin": "http://evil.example"})
    assert response.status == 403


async def test_stream_sends_full_then_nop_frame(client):
    async with client.ws_connect("/streamWS", headers=AUTH) as socket:
        await socket.send_bytes(frame_request(500, 250))
        first = await socket.receive_bytes()
        assert first[0] == PACKET_FRAME_RESPONSE
        assert int.from_bytes(first[1:3], "little") == 1000  # real width
        assert int.from_bytes(first[3:5], "little") == 500  # real height
        assert first[5] == FRAME_FULL

        await socket.send_bytes(frame_request(500, 250))
        second = await socket.receive_bytes()
        assert second[5] == FRAME_NOP


async def test_stream_survives_viewport_resize(client):
    async with client.ws_connect("/streamWS", headers=AUTH) as socket:
        for size in [(500, 250), (300, 150), (500, 250)]:
            await socket.send_bytes(frame_request(*size))
            frame = await socket.receive_bytes()
            assert frame[5] == FRAME_FULL


async def test_stream_ignores_garbage(client):
    async with client.ws_connect("/streamWS", headers=AUTH) as socket:
        await socket.send_bytes(b"")
        await socket.send_bytes(b"\x01\x01")  # truncated frame request
        await socket.send_bytes(frame_request(500, 250))
        assert (await socket.receive_bytes())[5] == FRAME_FULL


async def test_input_is_replayed_and_released_on_disconnect(client, backend):
    async with client.ws_connect("/streamWS", headers=AUTH) as stream:
        await stream.send_bytes(frame_request(500, 250))
        await stream.receive_bytes()

    socket = await client.ws_connect("/inputWS", headers=AUTH)
    await socket.send_bytes(input_packet([[0, 100, 200], [4, "a"], [1, 10, 10, 0]]))
    await socket.send_bytes(input_packet([[4, "not a real key"], [1, 10, 10, 9]]))
    await socket.close()

    # The server releases held inputs once it notices the disconnect
    for _ in range(100):
        if {"keyUp", "mouseUp"} <= {call[0] for call in backend.calls}:
            break
        await asyncio.sleep(0.02)

    names = [call[0] for call in backend.calls]
    assert names[:3] == ["moveTo", "keyDown", "mouseDown"]
    assert "keyUp" in names[3:] and "mouseUp" in names[3:]
    assert names.count("keyDown") == 1  # the invalid key was dropped
