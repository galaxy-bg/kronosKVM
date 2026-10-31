"""Password-based setup: credentials stay in API memory, never in the host queue."""

import asyncio
import json
import re

import asyncssh

from backend.app.services.remote_assist_config import ProfileError
from backend.app.services.wireguard_provisioning import registration_request, registration_response

COMMAND = "/usr/local/sbin/kdx-wg-register.py"


def target(value):
    if not isinstance(value, dict):
        raise ProfileError("Enter the VPN server address")
    host = value.get("host", "")
    port = value.get("port", 22)
    if (not isinstance(host, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host)
            or type(port) is not int or not 1 <= port <= 65535):
        raise ProfileError("Enter a valid server address and SSH port")
    return host, port


async def server_key(value):
    host, port = target(value)
    try:
        key = await asyncio.wait_for(asyncssh.get_server_host_key(
            host, port, config=None), timeout=10)
        if key is None:
            raise ProfileError("The server did not provide an SSH identity")
        return key
    except (OSError, asyncio.TimeoutError, asyncssh.Error):
        raise ProfileError("Cannot reach server. Check address, SSH port and firewall") from None


async def register(value, public):
    host, port = target(value)
    username, password = value.get("username", ""), value.get("password", "")
    if (not isinstance(username, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}",
                                                        username)
            or not isinstance(password, str) or not 1 <= len(password) <= 1024):
        raise ProfileError("Enter a username and password")
    endpoint = value.get("endpoint", "")
    if not isinstance(endpoint, str) or (endpoint and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}:[0-9]{1,5}", endpoint)):
        raise ProfileError("Enter a valid public VPN address and UDP port in Advanced settings")
    public = registration_request(public)
    key = await server_key(value)
    if key.get_fingerprint() != value.get("fingerprint"):
        raise ProfileError("Server identity changed. Verify the server before trying again")
    command = COMMAND if username == "root" else "sudo -n " + COMMAND
    try:
        async with asyncssh.connect(
            host, port=port, config=None, username=username, password=password,
            known_hosts=([key], [], []), client_keys=[], agent_path=None,
            connect_timeout=10, login_timeout=15,
        ) as connection:
            async with connection.create_process(command, encoding="utf-8") as process:
                process.stdin.write(json.dumps({"request": public, "endpoint": endpoint}))
                process.stdin.write_eof()
                output, _ = await asyncio.wait_for(asyncio.gather(
                    process.stdout.read(4097), process.stderr.read(1025)), timeout=50)
                if len(output) > 4096:
                    raise ProfileError("The server returned an invalid registration")
                await asyncio.wait_for(process.wait_closed(), timeout=5)
                if process.exit_status:
                    raise ProfileError("Server setup failed. Check the account permissions and "
                                       "registration service installed on the VPN server")
        response = registration_response(json.loads(output))
        if any(response[k] != public[k] for k in public):
            raise ProfileError("The server registration does not match this InfraBox")
        return response
    except asyncssh.PermissionDenied:
        raise ProfileError("Server login failed. Check the username and password") from None
    except (OSError, asyncio.TimeoutError, asyncssh.Error):
        raise ProfileError("Server connection failed. Check server access and retry") from None
    except (ValueError, TypeError, AttributeError):
        raise ProfileError("The server returned an invalid registration") from None
