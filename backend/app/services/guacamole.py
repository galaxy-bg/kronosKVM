"""Bounded Guacamole framing and the server-side guacd handshake."""

import asyncio
import codecs

MAX_INSTRUCTION = 4 * 1024 * 1024


def instruction(*values: str) -> str:
    return ",".join(f"{len(value)}.{value}" for value in values) + ";"


def parse_instruction(data: str):
    """Return (elements, consumed characters), or None for an incomplete frame."""
    elements = []
    offset = 0
    while True:
        dot = data.find(".", offset)
        if dot == -1:
            if len(data) - offset > 7:
                raise ValueError("Invalid instruction length")
            return None
        prefix = data[offset:dot]
        if not prefix or len(prefix) > 7 or not prefix.isascii() or not prefix.isdigit():
            raise ValueError("Invalid instruction length")
        length = int(prefix)
        end = dot + 1 + length
        if end > MAX_INSTRUCTION:
            raise ValueError("Instruction too large")
        if end >= len(data):
            return None
        elements.append(data[dot + 1 : end])
        if len(elements) > 256:
            raise ValueError("Too many instruction elements")
        if data[end] == ";":
            return elements, end + 1
        if data[end] != ",":
            raise ValueError("Invalid instruction delimiter")
        offset = end + 1


class InstructionReader:
    def __init__(self, reader):
        self.reader = reader
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.buffer = ""

    async def read(self):
        while True:
            parsed = parse_instruction(self.buffer)
            if parsed:
                values, end = parsed
                raw, self.buffer = self.buffer[:end], self.buffer[end:]
                return values, raw
            chunk = await self.reader.read(16384)
            if not chunk:
                if self.buffer or self.decoder.getstate()[0]:
                    raise ValueError("Truncated instruction")
                raise EOFError("Gateway disconnected")
            self.buffer += self.decoder.decode(chunk)
            if len(self.buffer) > MAX_INSTRUCTION:
                raise ValueError("Instruction too large")


async def handshake(reader, writer, protocol, parameters, width, height):
    writer.write(instruction("select", protocol).encode())
    await writer.drain()
    values, _ = await asyncio.wait_for(reader.read(), timeout=15)
    if values[0] != "args":
        raise ValueError("Gateway rejected protocol")
    arguments = values[1:]
    messages = [
        instruction("size", str(width), str(height), "96"),
        instruction("audio"),
        instruction("video"),
        instruction("image", "image/png", "image/jpeg"),
        instruction(
            "connect",
            *[
                "VERSION_1_5_0" if name.startswith("VERSION_") else parameters.get(name, "")
                for name in arguments
            ],
        ),
    ]
    writer.write("".join(messages).encode())
    await writer.drain()
    values, _ = await asyncio.wait_for(reader.read(), timeout=20)
    if values[0] != "ready" or len(values) != 2:
        raise ValueError("Gateway could not establish the session")
    return values[1]
