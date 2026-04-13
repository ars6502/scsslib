import json
import socket
import struct
from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, Callable, Dict, Optional


def command(name: Optional[str] = None) -> Callable:
    """
    Decorator for subclass do_<command> methods.

    Example:
        @command()
        def do_add(self, result, username, **kwargs):
            return result

    The wrapper will call:
        result = self.send_command(username, "<command>", **kwargs)

    and then pass that result into the decorated method.
    """
    def decorator(func: Callable) -> Callable:
        command_name = name
        if command_name is None:
            if not func.__name__.startswith("do_"):
                raise ValueError(
                    "Decorated method must be named do_<command> "
                    "or an explicit command name must be provided."
                )
            command_name = func.__name__[3:]

        @wraps(func)
        def wrapper(self, username: str, **kwargs: Any) -> Dict[str, Any]:
            result = self.send_command(
                username=username,
                command=command_name,
                **kwargs,
            )
            return func(self, result, username, **kwargs)

        return wrapper

    return decorator


class Client(ABC):
    def __init__(self, host: str = "127.0.0.1", port: int = 7000) -> None:
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None

    def connect(self) -> None:
        if self.sock is not None:
            return

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    @abstractmethod
    def pre_process_json(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Subclass hook for preprocessing outgoing messages.
        """
        raise NotImplementedError

    @abstractmethod
    def post_process_json(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Subclass hook for postprocessing incoming responses.
        """
        raise NotImplementedError



    def send_command(self, username: str, command: str, pre_process_stream=lambda x:x, post_process_stream=lambda x:x,**kwargs: Any) -> Dict[str, Any]:
        if self.sock is None:
            raise RuntimeError("Client is not connected")

        message = {
            "username": username,
            "command": command,
            "args": kwargs,
        }

        message = self.pre_process_json(message)
        self.send_json(self.sock, message,pre_process_stream)

        response = self.recv_json(self.sock,post_process_stream)
        if response is None:
            raise ConnectionError("Server closed the connection")

        response = self.post_process_json(response)
        return response

    @staticmethod
    def send_json(sock: socket.socket, data: Dict[str, Any], pre_process_stream) -> None:
        payload = pre_process_stream(json.dumps(data).encode("utf-8"))
        header = struct.pack("!I", len(payload))
        sock.sendall(header + payload)

    @staticmethod
    def recv_json(sock: socket.socket,post_process_stream) -> Optional[Dict[str, Any]]:
        header = Client.recv_exact(sock, 4)
        if not header:
            return None

        message_length = struct.unpack("!I", header)[0]
        payload = post_process_stream(Client.recv_exact(sock, message_length))
        if not payload:
            return None

        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def recv_exact(sock: socket.socket, size: int) -> Optional[bytes]:
        data = b""
        while len(data) < size:
            print(size,len(data))
            chunk = sock.recv(size - len(data))
            if not chunk:
                return None
            data += chunk
        return data

