from __future__ import annotations

import socket
import shutil
import subprocess
import uuid

from . import config


def ami_configured() -> bool:
    return bool(config.AMI_HOST and config.AMI_SECRET)


def asterisk_available() -> bool:
    return shutil.which("asterisk") is not None or ami_configured()


def _cli_local(command: str) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["asterisk", "-rx", command],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except OSError as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        return False, output or f"asterisk salió con código {completed.returncode}"
    return True, output


def _ami_command(command: str) -> tuple[bool, str]:
    try:
        return True, _Ami().command(command)
    except Exception as exc:
        return False, str(exc)


def _cli(command: str) -> tuple[bool, str]:
    if shutil.which("asterisk"):
        return _cli_local(command)
    if ami_configured():
        return _ami_command(command)
    return False, "Asterisk no está instalado en este equipo (modo desarrollo)."


def version() -> str:
    ok, output = _cli("core show version")
    if not ok:
        return output
    return output.splitlines()[0] if output else "Asterisk OK"


def db_get(family: str, key: str) -> str | None:
    if ami_configured() and not shutil.which("asterisk"):
        try:
            return _Ami().db_get(family, key)
        except Exception:
            return None
    ok, output = _cli(f"database get {family} {key}")
    if not ok:
        return None
    if "Database entry not found" in output:
        return None
    if "Value:" in output:
        return output.split("Value:", 1)[1].strip()
    parts = output.split()
    return parts[-1] if parts else None


def db_put(family: str, key: str, value: str) -> tuple[bool, str]:
    if ami_configured() and not shutil.which("asterisk"):
        try:
            _Ami().db_put(family, key, value)
            return True, "OK"
        except Exception as exc:
            return False, str(exc)
    return _cli(f"database put {family} {key} {value}")


def reload_dialplan() -> tuple[bool, str]:
    return _cli("dialplan reload")


def context_loaded(exten: str) -> bool:
    ok, output = _cli("dialplan show farmacia-turno")
    return ok and exten in output


class _Ami:
    def __init__(self) -> None:
        self.sock = socket.create_connection((config.AMI_HOST, config.AMI_PORT), timeout=8)
        self.sock.settimeout(8)
        self._read_until_blank()
        login = self._action(
            {
                "Action": "Login",
                "Username": config.AMI_USER,
                "Secret": config.AMI_SECRET,
            }
        )
        if login.get("Response") != "Success":
            self.sock.close()
            raise RuntimeError(login.get("Message", "AMI login falló"))

    def command(self, command: str) -> str:
        try:
            return self._command(command)
        finally:
            self._close()

    def db_get(self, family: str, key: str) -> str | None:
        try:
            block = self._action({"Action": "DBGet", "Family": family, "Key": key}, extra=True)
            if "Val" in block:
                return block["Val"]
            if block.get("Response") == "Error":
                return None
            return None
        finally:
            self._close()

    def db_put(self, family: str, key: str, value: str) -> None:
        try:
            block = self._action(
                {"Action": "DBPut", "Family": family, "Key": key, "Val": value}
            )
            if block.get("Response") != "Success":
                raise RuntimeError(block.get("Message", "DBPut falló"))
        finally:
            self._close()

    def _command(self, command: str) -> str:
        action_id = uuid.uuid4().hex
        payload = (
            f"Action: Command\r\n"
            f"ActionID: {action_id}\r\n"
            f"Command: {command}\r\n"
            f"\r\n"
        )
        self.sock.sendall(payload.encode("utf-8"))
        raw = self._recv_until(b"--END COMMAND--")
        text = raw.decode("utf-8", errors="replace")
        if "Response: Error" in text.split("\r\n", 4)[0] or "Response: Error" in text[:80]:
            raise RuntimeError(text.strip() or "AMI Command error")
        start = text.find("\r\n\r\n")
        body = text[start + 4 :] if start >= 0 else text
        body = body.replace("--END COMMAND--", "").strip()
        return body

    def _action(self, fields: dict[str, str], extra: bool = False) -> dict[str, str]:
        action_id = uuid.uuid4().hex
        fields = dict(fields)
        fields["ActionID"] = action_id
        lines = [f"{k}: {v}" for k, v in fields.items()] + ["", ""]
        self.sock.sendall("\r\n".join(lines).encode("utf-8"))
        parsed = self._read_block()
        if extra and parsed.get("Response") == "Success":
            more = self._read_block()
            parsed.update(more)
        return parsed

    def _read_until_blank(self) -> str:
        return self._read_block_raw()

    def _read_block(self) -> dict[str, str]:
        raw = self._read_block_raw()
        result: dict[str, str] = {}
        for line in raw.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                result[key.strip()] = val.strip()
        return result

    def _read_block_raw(self) -> str:
        chunks: list[bytes] = []
        while True:
            piece = self.sock.recv(4096)
            if not piece:
                break
            chunks.append(piece)
            data = b"".join(chunks)
            if b"\r\n\r\n" in data:
                return data.decode("utf-8", errors="replace")
        return b"".join(chunks).decode("utf-8", errors="replace")

    def _recv_until(self, marker: bytes) -> bytes:
        chunks: list[bytes] = []
        data = b""
        while marker not in data:
            piece = self.sock.recv(4096)
            if not piece:
                break
            chunks.append(piece)
            data = b"".join(chunks)
        return data

    def _close(self) -> None:
        try:
            self.sock.sendall(b"Action: Logoff\r\n\r\n")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
