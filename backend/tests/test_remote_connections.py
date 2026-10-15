import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.api import remote
from backend.app.main import create_app
from backend.app.services.guacamole import (
    InstructionReader,
    handshake,
    instruction,
    parse_instruction,
)


def profile(protocol="rdp"):
    return SimpleNamespace(
        id="target-1",
        type=protocol,
        host="192.0.2.10",
        port=3389,
        username="operator",
        name="Test target",
    )


class Writer:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


@pytest.mark.parametrize("value", ["semi;comma,dot.", "Türkçe 🔑", ""])
def test_instruction_preserves_delimiters_and_unicode(value):
    frame = instruction("value", value)
    for offset in range(len(frame)):
        assert parse_instruction(frame[:offset]) is None
    assert parse_instruction(frame) == (["value", value], len(frame))


@pytest.mark.parametrize("frame", ["x.test;", "9999999.x;", "3.foo!", "1.a!"])
def test_invalid_frames_are_rejected(frame):
    with pytest.raises(ValueError):
        parse_instruction(frame)


@pytest.mark.asyncio
async def test_handshake_obeys_server_argument_order_and_utf8_fragmentation():
    stream = asyncio.StreamReader()
    incoming = (
        instruction("args", "VERSION_1_5_0", "password", "hostname", "port", "ignore-cert")
        + instruction("ready", "tunnel-1")
        + instruction("name", "Türkçe 🔑")
    ).encode()
    reader = InstructionReader(stream)
    writer = Writer()

    async def feed():
        for byte in incoming:
            stream.feed_data(bytes([byte]))
            await asyncio.sleep(0)
        stream.feed_eof()

    feeder = asyncio.create_task(feed())
    parameters = remote.connection_parameters(
        profile(), remote.SessionInput(profile_id="target-1", password="secret,;🔑")
    )
    assert await handshake(reader, writer, "rdp", parameters, 1280, 720) == "tunnel-1"
    assert (await reader.read())[0] == ["name", "Türkçe 🔑"]
    await feeder
    outgoing = writer.data.decode()
    frames = []
    while outgoing:
        elements, end = parse_instruction(outgoing)
        frames.append(elements)
        outgoing = outgoing[end:]
    assert frames[0] == ["select", "rdp"]
    assert frames[-1] == ["connect", "VERSION_1_5_0", "secret,;🔑", "192.0.2.10", "3389", "false"]
    assert frames[1] == ["size", "1280", "720", "96"]


@pytest.mark.parametrize("protocol", ["telnet", "rdp", "vnc"])
def test_websocket_relays_saved_target_and_closes_gateway(monkeypatch, protocol):
    writer = Writer()
    stream_holder = {}
    monkeypatch.setattr(remote, "list_connections", lambda: [profile(protocol)])
    monkeypatch.setattr(remote, "start_task", lambda *args, **kwargs: None)
    monkeypatch.setattr(remote, "finish_task", lambda *args, **kwargs: None)

    async def connect(host, port):
        assert (host, port) == ("127.0.0.1", 4822)
        stream = asyncio.StreamReader()
        stream.feed_data(
            (
                instruction("args", "hostname", "password")
                + instruction("ready", "tunnel-1")
                + instruction("sync", "123")
            ).encode()
        )
        stream_holder["stream"] = stream
        return stream, writer

    monkeypatch.setattr(remote.asyncio, "open_connection", connect)
    with TestClient(create_app()).websocket_connect("/api/v1/remote/ws") as socket:
        socket.send_json({"profile_id": "target-1", "password": "not-saved"})
        assert socket.receive_text() == instruction("", "tunnel-1")
        assert socket.receive_text() == instruction("sync", "123")
        socket.send_text(instruction("key", "65", "1"))
        # The server responds to invalid input after forwarding the key in order.
        socket.send_text(instruction("select", "ssh"))
        assert parse_instruction(socket.receive_text())[0][0] == "error"
    assert instruction("key", "65", "1").encode() in writer.data
    assert b"192.0.2.10" in writer.data and b"not-saved" in writer.data
    assert writer.closed and not remote._active


def test_invalid_profile_never_connects_to_gateway(monkeypatch):
    monkeypatch.setattr(remote, "list_connections", lambda: [profile("ssh")])

    async def forbidden(*args, **kwargs):
        pytest.fail("Gateway must not be contacted for invalid profiles")

    monkeypatch.setattr(remote.asyncio, "open_connection", forbidden)
    with TestClient(create_app()).websocket_connect("/api/v1/remote/ws") as socket:
        socket.send_json({"profile_id": "target-1"})
        assert parse_instruction(socket.receive_text())[0][0] == "error"
    assert not remote._active


def test_session_limit_does_not_remove_existing_sessions(monkeypatch):
    monkeypatch.setattr(remote, "_active", {"one", "two", "three", "four"})
    with TestClient(create_app()).websocket_connect("/api/v1/remote/ws") as socket:
        assert "Four remote sessions" in socket.receive_text()
    assert remote._active == {"one", "two", "three", "four"}


def test_certificate_validation_defaults_on_and_password_is_not_a_profile_field():
    value = remote.SessionInput(profile_id="target-1", password="secret")
    target = profile()
    assert remote.connection_parameters(target, value)["ignore-cert"] == "false"
    value.ignore_certificate = True
    assert remote.connection_parameters(target, value)["ignore-cert"] == "true"
    assert "secret" not in json.dumps(vars(target))
