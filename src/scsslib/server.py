import json
import socket
import struct
import threading
from typing import Any, Dict, Optional


class Server:
    def __init__(self, host: str = "127.0.0.1", port: int = 5000) -> None:
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start(self,pre_process_stream=lambda x:x, post_process_stream=lambda x:x) -> None:
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"Server listening on {self.host}:{self.port}")

        while True:
            client_socket, client_address = self.server_socket.accept()
            print(f"Accepted connection from {client_address}")

            thread = threading.Thread(
                target=self.handle_client,
                args=(client_socket,pre_process_stream,post_process_stream),
                daemon=True,
            )
            thread.start()

    def handle_client(self, client_socket: socket.socket, pre_process_stream, post_process_stream) -> None:
        try:
            while True:
                message = self.recv_json(client_socket,pre_process_stream)
                if message is None:
                    break

                response = self.dispatch(message)
                self.send_json(client_socket, response, post_process_stream)

        except ConnectionError:
            pass
        except Exception as exc:
            try:
                self.send_json(client_socket, self.make_error(f"Error: {exc}"),post_process_stream)
            except Exception:
                pass
        finally:
            client_socket.close()


    
    def pre_process_json(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(message, dict):
            raise ValueError("Incoming message must be a JSON object")

        username = message.get("username")
        command = message.get("command")
        args = message.get("args", {})

        if isinstance(username, str):
            username = username.strip()

        if isinstance(command, str):
            command = command.strip().lower()

        if args is None:
            args = {}

        if not isinstance(args, dict):
            raise ValueError("'args' must be a dictionary")

        return {
            "username": username,
            "command": command,
            "args": args,
        }

    def post_process_json(self, response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(response, dict):
            raise ValueError("Response must be a dictionary")

        if "status" not in response:
            response["status"] = "success"

        return response

    def dispatch(self, message: Dict[str, Any]) -> Dict[str, Any]:
        try:
            message = self.pre_process_json(message)

            username = message.get("username")
            command = message.get("command")
            args = message.get("args", {})

            if not isinstance(username, str) or not username:
                response = self.make_error("Missing or invalid 'username'")
            elif not isinstance(command, str) or not command:
                response = self.make_error("Missing or invalid 'command'")
            elif not isinstance(args, dict):
                response = self.make_error("'args' must be a dictionary")
            else:
                handler_name = f"on_{command}"
                handler = getattr(self, handler_name, None)

                if handler is None or not callable(handler):
                    response = self.make_error(f"Unknown command: {command}")
                else:
                    response = handler(username, args)

        except Exception as exc:
            response = self.make_error(str(exc))

        try:
            return self.post_process_json(response)
        except Exception as exc:
            return self.make_error(f"Post-processing error: {exc}")

    @staticmethod
    def make_error(error_message: str) -> Dict[str, Any]:
        return {
            "status": "failed",
            "error": error_message,
        }

    @staticmethod
    def send_json(sock: socket.socket, data: Dict[str, Any], post_process_stream) -> None:
        payload = post_process_stream(json.dumps(data).encode("utf-8"))
        header = struct.pack("!I", len(payload))
        sock.sendall(header + payload)

    @staticmethod
    def recv_json(sock: socket.socket, pre_process_stream) -> Optional[Dict[str, Any]]:
        header = Server.recv_exact(sock, 4)
        if not header:
            return None

        message_length = struct.unpack("!I", header)[0]
        payload = pre_process_stream(Server.recv_exact(sock, message_length))
        if not payload:
            return None

        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def recv_exact(sock: socket.socket, size: int) -> Optional[bytes]:
        data = b""
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                return None
            data += chunk
        return data

