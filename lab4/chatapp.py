#!/usr/bin/env python3

"""
Computer Engineering 4DN4 - Laboratory #4
Online Group Chatting Application

A client/server network application for multi-group online chatting.
Server (CRDS) manages a chat room directory over TCP.
Clients chat via IP multicast.

Usage:
    python chatapp.py -s                  # Start the server (CRDS)
    python chatapp.py                     # Start a client
    python chatapp.py -p 50000           # Custom port
    python chatapp.py --host 192.168.1.5 # Connect to remote CRDS
"""

import socket
import threading
import sys
import struct
import json
import argparse

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
CRDS_DEFAULT_PORT = 50000
BUFFER_SIZE = 4096
MULTICAST_TTL = 1


# ─────────────────────────────────────────────────────────────────────────────
# Server – Chat Room Directory Server (CRDS)
# ─────────────────────────────────────────────────────────────────────────────
class Server:
    """Maintains a Chat Room Directory (CRD) and serves it to clients via TCP."""

    def __init__(self, port=CRDS_DEFAULT_PORT):
        self.port = port
        self.crd = {}          # {room_name: {"address": str, "port": int}}
        self.lock = threading.Lock()

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", self.port))
        self.server_socket.listen(5)
        print(f"Chat Room Directory Server listening on port {self.port}...")

        try:
            while True:
                conn, addr = self.server_socket.accept()
                print(f"Client connected from {addr}")
                threading.Thread(
                    target=self.handle_client, args=(conn, addr), daemon=True
                ).start()
        except KeyboardInterrupt:
            print("\nServer shutting down.")
        finally:
            self.server_socket.close()

    def handle_client(self, conn, addr):
        try:
            while True:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    break

                command = data.decode().strip()
                parts = command.split()
                if not parts:
                    continue
                cmd = parts[0].lower()

                if cmd == "getdir":
                    with self.lock:
                        response = json.dumps(self.crd)
                    conn.sendall(response.encode())

                elif cmd == "makeroom":
                    self._handle_makeroom(conn, parts)

                elif cmd == "deleteroom":
                    self._handle_deleteroom(conn, parts)

                elif cmd == "bye":
                    conn.sendall(b"Goodbye!")
                    break

                else:
                    conn.sendall(f"Error: Unknown command '{cmd}'".encode())

        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass
        finally:
            print(f"Client at {addr} disconnected.")
            conn.close()

    def _handle_makeroom(self, conn, parts):
        if len(parts) != 4:
            conn.sendall(b"Error: Usage: makeroom <name> <address> <port>")
            return

        room_name, address = parts[1], parts[2]
        try:
            port = int(parts[3])
        except ValueError:
            conn.sendall(b"Error: Port must be a number")
            return

        with self.lock:
            # Check address/port uniqueness
            for existing, info in self.crd.items():
                if info["address"] == address and info["port"] == port:
                    conn.sendall(
                        f"Error: {address}:{port} already used by '{existing}'".encode()
                    )
                    return

            self.crd[room_name] = {"address": address, "port": port}

        msg = f"Chat room '{room_name}' created at {address}:{port}"
        conn.sendall(msg.encode())
        print(msg)

    def _handle_deleteroom(self, conn, parts):
        if len(parts) != 2:
            conn.sendall(b"Error: Usage: deleteroom <name>")
            return

        room_name = parts[1]
        with self.lock:
            if room_name in self.crd:
                del self.crd[room_name]
                msg = f"Chat room '{room_name}' deleted."
                conn.sendall(msg.encode())
                print(msg)
            else:
                conn.sendall(f"Error: Chat room '{room_name}' not found.".encode())


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────
class Client:
    """Connects to CRDS for room management, chats via IP multicast."""

    def __init__(self, server_host="localhost", server_port=CRDS_DEFAULT_PORT):
        self.server_host = server_host
        self.server_port = server_port
        self.tcp_socket = None
        self.connected = False
        self.chat_name = "Anonymous"
        self.chatting = False

    # ── Main loop ────────────────────────────────────────────────────────
    def start(self):
        print("Welcome to the Chat Room Client!")
        print("Commands: connect, name, chat, quit  (type 'help' for more)\n")

        try:
            while True:
                prompt = "(CRDS connected) > " if self.connected else "(main) > "
                try:
                    user_input = input(prompt).strip()
                except EOFError:
                    break

                if not user_input:
                    continue

                parts = user_input.split()
                cmd = parts[0].lower()

                if self.connected:
                    self._handle_crds_cmd(cmd, parts, user_input)
                else:
                    self._handle_main_cmd(cmd, parts)

        except KeyboardInterrupt:
            print("\nExiting client.")
        finally:
            if self.tcp_socket:
                try:
                    self.tcp_socket.close()
                except OSError:
                    pass

    # ── Main-prompt commands ─────────────────────────────────────────────
    def _handle_main_cmd(self, cmd, parts):
        if cmd == "connect":
            self._connect_to_server()

        elif cmd == "name":
            if len(parts) < 2:
                print("Usage: name <chat name>")
            else:
                self.chat_name = " ".join(parts[1:])
                print(f"Chat name set to '{self.chat_name}'")

        elif cmd == "chat":
            if len(parts) < 2:
                print("Usage: chat <chat room name>")
            else:
                self._enter_chat_mode(parts[1])

        elif cmd in ("quit", "exit"):
            print("Goodbye!")
            sys.exit(0)

        elif cmd == "help":
            print("Main Commands:")
            print("  connect                          – Connect to the CRDS")
            print("  name <chat name>                 – Set your chat name")
            print("  chat <chat room name>            – Enter a chat room")
            print("  quit                             – Exit")

        else:
            print(f"Unknown command: '{cmd}'. Type 'help' for commands.")

    # ── CRDS-connected commands ──────────────────────────────────────────
    def _handle_crds_cmd(self, cmd, parts, raw):
        if cmd == "getdir":
            response = self._send_to_server("getdir")
            if response:
                self._print_directory(response)

        elif cmd == "makeroom":
            if len(parts) != 4:
                print("Usage: makeroom <name> <address> <port>")
            else:
                response = self._send_to_server(raw)
                if response:
                    print(response)

        elif cmd == "deleteroom":
            if len(parts) != 2:
                print("Usage: deleteroom <name>")
            else:
                response = self._send_to_server(raw)
                if response:
                    print(response)

        elif cmd == "bye":
            self._send_to_server("bye")
            try:
                self.tcp_socket.close()
            except OSError:
                pass
            self.tcp_socket = None
            self.connected = False
            print("Disconnected from CRDS.")

        elif cmd == "help":
            print("CRDS Commands:")
            print("  getdir                                   – List chat rooms")
            print("  makeroom <name> <address> <port>         – Create a room")
            print("  deleteroom <name>                        – Delete a room")
            print("  bye                                      – Disconnect")

        else:
            print(f"Unknown CRDS command: '{cmd}'. Type 'help' for commands.")

    # ── TCP helpers ──────────────────────────────────────────────────────
    def _connect_to_server(self):
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((self.server_host, self.server_port))
            self.connected = True
            print(f"Connected to CRDS at {self.server_host}:{self.server_port}")
        except Exception as e:
            print(f"Failed to connect to CRDS: {e}")
            self.tcp_socket = None

    def _send_to_server(self, message):
        try:
            self.tcp_socket.sendall(message.encode())
            response = self.tcp_socket.recv(BUFFER_SIZE)
            return response.decode()
        except Exception as e:
            print(f"Connection error: {e}")
            self.tcp_socket = None
            self.connected = False
            return None

    def _print_directory(self, response):
        try:
            directory = json.loads(response)
            if not directory:
                print("Chat room directory is empty.")
            else:
                print(f"\n{'Room Name':<20} {'Multicast Addr':<20} {'Port':<10}")
                print("-" * 50)
                for name, info in directory.items():
                    print(f"{name:<20} {info['address']:<20} {info['port']:<10}")
                print()
        except json.JSONDecodeError:
            print(response)

    # ── Room lookup ──────────────────────────────────────────────────────
    def _get_room_info(self, room_name):
        """Connect to CRDS, fetch directory, return room info or None."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.server_host, self.server_port))
            sock.sendall(b"getdir")
            response = sock.recv(BUFFER_SIZE).decode()
            sock.sendall(b"bye")
            try:
                sock.recv(BUFFER_SIZE)
            except OSError:
                pass
            sock.close()

            directory = json.loads(response)
            return directory.get(room_name)
        except Exception as e:
            print(f"Error fetching room info from CRDS: {e}")
            return None

    # ── Chat mode (IP multicast) ─────────────────────────────────────────
    def _enter_chat_mode(self, room_name):
        room_info = self._get_room_info(room_name)
        if not room_info:
            print(f"Chat room '{room_name}' not found on CRDS.")
            return

        mcast_addr = room_info["address"]
        mcast_port = room_info["port"]

        print(f"Entering chat room '{room_name}' at {mcast_addr}:{mcast_port}")
        print(f"Chatting as '{self.chat_name}'. Type '/exit' or press Ctrl+C to leave.\n")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", mcast_port))

            # Join multicast group
            mreq = struct.pack("4sl", socket.inet_aton(mcast_addr), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        except Exception as e:
            print(f"Failed to set up multicast socket: {e}")
            return

        self.chatting = True

        recv_thread = threading.Thread(
            target=self._receive_chat, args=(sock,), daemon=True
        )
        recv_thread.start()

        try:
            while self.chatting:
                try:
                    msg = input(f"({room_name}) > ")
                except EOFError:
                    break

                if msg.strip().lower() == "/exit":
                    break

                if msg.strip():
                    full_msg = f"{self.chat_name}: {msg}"
                    sock.sendto(full_msg.encode(), (mcast_addr, mcast_port))
        except KeyboardInterrupt:
            pass
        finally:
            self.chatting = False
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
                sock.close()
            except OSError:
                pass
            print(f"\nLeft chat room '{room_name}'.")

    def _receive_chat(self, sock):
        """Background thread: print incoming multicast messages."""
        while self.chatting:
            try:
                sock.settimeout(1.0)
                data, _ = sock.recvfrom(BUFFER_SIZE)
                message = data.decode()
                # Print received message (will interleave with input prompt)
                print(f"\r{message}")
            except socket.timeout:
                continue
            except OSError:
                break


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="4DN4 Lab 4 – Group Chat App")
    parser.add_argument("-s", "--server", action="store_true",
                        help="Run as Chat Room Directory Server (CRDS)")
    parser.add_argument("-p", "--port", type=int, default=CRDS_DEFAULT_PORT,
                        help=f"CRDS port (default: {CRDS_DEFAULT_PORT})")
    parser.add_argument("--host", type=str, default="localhost",
                        help="CRDS host to connect to (client mode, default: localhost)")
    args = parser.parse_args()

    if args.server:
        Server(port=args.port).start()
    else:
        Client(server_host=args.host, server_port=args.port).start()
