#!/usr/bin/env python3

########################################################################
#
# COMPENG 4DN4 - Lab 3
# Online File Sharing Application
#
# A client-server file sharing system using:
#   - UDP broadcast for service discovery
#   - TCP for file transfer (get, put, list)
#   - Threading for concurrent client connections
#
########################################################################

import socket
import argparse
import os
import sys
import threading

########################################################################
# Protocol Constants
########################################################################

# Field lengths (bytes)
CMD_FIELD_LEN            = 1  # 1-byte command
FILE_SIZE_FIELD_LEN      = 8  # 8-byte file size
FILENAME_SIZE_FIELD_LEN  = 1  # 1-byte filename length

# Command dictionary - maps commands to 1-byte integer values
CMD = {
    "get"  : 1,
    "put"  : 2,
    "list" : 3,
}

MSG_ENCODING = "utf-8"

# Ports
SERVICE_DISCOVERY_PORT = 30000   # UDP Service Discovery Port (SDP)
FILE_SHARING_PORT      = 30001   # TCP File Sharing Port (FSP)

# Service discovery
SERVICE_DISCOVERY_MSG = "SERVICE DISCOVERY"
SERVICE_NAME = "Juan's File Sharing Service"

# Directories
SERVER_SHARE_DIR = "server_share"
CLIENT_SHARE_DIR = "client_share"

# Network
RECV_SIZE = 4096

########################################################################
# SERVER
########################################################################

class Server:

    HOSTNAME = "0.0.0.0"
    BACKLOG = 10

    def __init__(self):
        # Create shared directory if it doesn't exist
        if not os.path.exists(SERVER_SHARE_DIR):
            os.makedirs(SERVER_SHARE_DIR)

        # Display files initially available
        print("=" * 60)
        print("File Sharing Server started.")
        print("Shared directory: {}".format(os.path.abspath(SERVER_SHARE_DIR)))
        files = os.listdir(SERVER_SHARE_DIR)
        if files:
            print("Files currently available for sharing:")
            for f in files:
                size = os.path.getsize(os.path.join(SERVER_SHARE_DIR, f))
                print("  {} ({} bytes)".format(f, size))
        else:
            print("No files currently in the shared directory.")
        print("=" * 60)

        # Start UDP service discovery listener in a daemon thread
        udp_thread = threading.Thread(
            target=self.listen_for_service_discovery, daemon=True
        )
        udp_thread.start()

        # Start TCP file sharing listener (main thread)
        self.listen_for_file_sharing()

    # ------------------------------------------------------------------
    # UDP Service Discovery
    # ------------------------------------------------------------------

    def listen_for_service_discovery(self):
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.bind(("", SERVICE_DISCOVERY_PORT))
            print("Listening for service discovery messages on SDP port {}.".format(
                SERVICE_DISCOVERY_PORT))
        except Exception as msg:
            print("UDP socket error: {}".format(msg))
            return

        while True:
            try:
                data, address = self.udp_socket.recvfrom(RECV_SIZE)
                msg = data.decode(MSG_ENCODING).strip()
                if msg == SERVICE_DISCOVERY_MSG:
                    print("Service discovery request received from {}.".format(address))
                    response = SERVICE_NAME.encode(MSG_ENCODING)
                    self.udp_socket.sendto(response, address)
            except Exception as msg:
                print("UDP error: {}".format(msg))

    # ------------------------------------------------------------------
    # TCP File Sharing
    # ------------------------------------------------------------------

    def listen_for_file_sharing(self):
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_socket.bind((Server.HOSTNAME, FILE_SHARING_PORT))
            self.tcp_socket.listen(Server.BACKLOG)
            print("Listening for file sharing connections on port {}.".format(
                FILE_SHARING_PORT))
        except Exception as msg:
            print("TCP socket error: {}".format(msg))
            sys.exit(1)

        try:
            while True:
                client = self.tcp_socket.accept()
                thread = threading.Thread(
                    target=self.connection_handler, args=(client,), daemon=True
                )
                thread.start()
        except KeyboardInterrupt:
            print("\nServer shutting down.")
        finally:
            self.tcp_socket.close()

    def connection_handler(self, client):
        connection, address = client
        print("-" * 60)
        print("Connection received from {} on port {}.".format(
            address[0], address[1]))

        try:
            while True:
                # Read the 1-byte command
                cmd_bytes = connection.recv(CMD_FIELD_LEN)
                if not cmd_bytes:
                    break

                cmd = int.from_bytes(cmd_bytes, byteorder='big')

                if cmd == CMD["list"]:
                    self.handle_list(connection, address)
                elif cmd == CMD["get"]:
                    self.handle_get(connection, address)
                elif cmd == CMD["put"]:
                    self.handle_put(connection, address)
                else:
                    print("Unknown command {} from {}.".format(cmd, address))
                    break
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            print("Client {} connection lost.".format(address))
        except Exception as e:
            print("Error handling client {}: {}".format(address, e))
        finally:
            connection.close()
            print("Closing connection from {}.".format(address))

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def handle_list(self, connection, address):
        """
        Protocol:
          Client -> Server:  [cmd=3 (1B)]
          Server -> Client:  [listing_size (8B)] [listing_data]
        """
        print("LIST command received from {}.".format(address))
        files = os.listdir(SERVER_SHARE_DIR)
        listing = "\n".join(files) if files else "(empty)"
        listing_bytes = listing.encode(MSG_ENCODING)
        listing_size = len(listing_bytes).to_bytes(FILE_SIZE_FIELD_LEN, byteorder='big')
        connection.sendall(listing_size + listing_bytes)

    def handle_get(self, connection, address):
        """
        Protocol:
          Client -> Server:  [cmd=1 (1B)] [filename_bytes]
          Server -> Client:  [file_size (8B)] [file_data]
          (file_size = 0 means file not found)
        """
        filename_bytes = connection.recv(RECV_SIZE)
        if not filename_bytes:
            return
        filename = filename_bytes.decode(MSG_ENCODING)
        print("GET command received for '{}' from {}.".format(filename, address))

        filepath = os.path.join(SERVER_SHARE_DIR, filename)
        try:
            with open(filepath, 'rb') as f:
                file_data = f.read()
            file_size = len(file_data)
            file_size_field = file_size.to_bytes(FILE_SIZE_FIELD_LEN, byteorder='big')
            connection.sendall(file_size_field + file_data)
            print("Sent file '{}' ({} bytes) to {}.".format(filename, file_size, address))
        except FileNotFoundError:
            print("File '{}' not found.".format(filename))
            connection.sendall((0).to_bytes(FILE_SIZE_FIELD_LEN, byteorder='big'))

    def handle_put(self, connection, address):
        """
        Protocol:
          Client -> Server:
            [cmd=2 (1B)] [filename_size (1B)] [filename] [file_size (8B)] [file_data]

        Uses a temp file to prevent partial file remnants if the server
        exits or the connection drops during upload.
        """
        # Read filename size (1 byte)
        filename_size_bytes = self.recv_bytes(connection, FILENAME_SIZE_FIELD_LEN)
        if not filename_size_bytes:
            return
        filename_size = int.from_bytes(filename_size_bytes, byteorder='big')

        # Read filename
        filename_bytes = self.recv_bytes(connection, filename_size)
        if not filename_bytes:
            return
        filename = filename_bytes.decode(MSG_ENCODING)

        # Read file size (8 bytes)
        file_size_bytes = self.recv_bytes(connection, FILE_SIZE_FIELD_LEN)
        if not file_size_bytes:
            return
        file_size = int.from_bytes(file_size_bytes, byteorder='big')

        print("PUT command received for '{}' ({} bytes) from {}.".format(
            filename, file_size, address))

        # Write to a temp file first to prevent partial files on failure
        temp_filepath = os.path.join(SERVER_SHARE_DIR, ".tmp_" + filename)
        filepath = os.path.join(SERVER_SHARE_DIR, filename)

        try:
            received = 0
            with open(temp_filepath, 'wb') as f:
                while received < file_size:
                    chunk = connection.recv(min(RECV_SIZE, file_size - received))
                    if not chunk:
                        raise ConnectionError("Connection lost during upload")
                    f.write(chunk)
                    received += len(chunk)

            # Atomic rename: move temp file to final destination
            if os.path.exists(filepath):
                os.remove(filepath)
            os.rename(temp_filepath, filepath)
            print("File '{}' uploaded successfully ({} bytes).".format(
                filename, file_size))
        except Exception as e:
            print("Upload failed for '{}': {}".format(filename, e))
            # Clean up partial temp file
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
                print("Removed partial temp file for '{}'.".format(filename))

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def recv_bytes(self, connection, length):
        """Receive exactly `length` bytes from the connection."""
        data = bytearray()
        while len(data) < length:
            chunk = connection.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return bytes(data)


########################################################################
# CLIENT
########################################################################

class Client:

    def __init__(self):
        # Create local share directory if it doesn't exist
        if not os.path.exists(CLIENT_SHARE_DIR):
            os.makedirs(CLIENT_SHARE_DIR)

        self.tcp_socket = None
        self.connected = False
        self.command_loop()

    # ------------------------------------------------------------------
    # Command loop
    # ------------------------------------------------------------------

    def command_loop(self):
        print("File Sharing Client started.")
        print("Local directory: {}".format(os.path.abspath(CLIENT_SHARE_DIR)))
        print("Commands: scan, connect, llist, rlist, put, get, bye")
        print("-" * 60)

        while True:
            try:
                prompt = "Connected> " if self.connected else "FileSharing> "
                cmd_input = input(prompt).strip()
                if not cmd_input:
                    continue

                parts = cmd_input.split()
                command = parts[0].lower()

                if command == "scan":
                    self.scan()
                elif command == "connect":
                    if len(parts) < 3:
                        print("Usage: connect <IP address> <port>")
                    else:
                        self.connect(parts[1], int(parts[2]))
                elif command == "llist":
                    self.llist()
                elif command == "rlist":
                    self.rlist()
                elif command == "put":
                    if len(parts) < 2:
                        print("Usage: put <filename>")
                    else:
                        self.put(parts[1])
                elif command == "get":
                    if len(parts) < 2:
                        print("Usage: get <filename>")
                    else:
                        self.get(parts[1])
                elif command == "bye":
                    self.bye()
                else:
                    print("Unknown command: {}".format(command))
                    print("Commands: scan, connect, llist, rlist, put, get, bye")

            except (KeyboardInterrupt, EOFError):
                print("\nExiting client.")
                if self.connected:
                    self.bye()
                break

    # ------------------------------------------------------------------
    # scan - UDP service discovery broadcast
    # ------------------------------------------------------------------

    def scan(self):
        print("Scanning for file sharing services...")
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp_socket.settimeout(5)

            msg = SERVICE_DISCOVERY_MSG.encode(MSG_ENCODING)
            udp_socket.sendto(msg, ("255.255.255.255", SERVICE_DISCOVERY_PORT))

            found = False
            try:
                while True:
                    data, address = udp_socket.recvfrom(RECV_SIZE)
                    service_name = data.decode(MSG_ENCODING)
                    print("{} found at IP address/port {}, {}".format(
                        service_name, address[0], FILE_SHARING_PORT))
                    found = True
            except socket.timeout:
                if not found:
                    print("No file sharing services found.")

            udp_socket.close()
        except Exception as e:
            print("Scan error: {}".format(e))

    # ------------------------------------------------------------------
    # connect - TCP connection to server
    # ------------------------------------------------------------------

    def connect(self, ip, port):
        if self.connected:
            print("Already connected. Use 'bye' to disconnect first.")
            return
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((ip, port))
            self.connected = True
            print("Connected to {} on port {}.".format(ip, port))
        except Exception as e:
            print("Connection failed: {}".format(e))
            self.tcp_socket = None

    # ------------------------------------------------------------------
    # llist - local directory listing
    # ------------------------------------------------------------------

    def llist(self):
        print("Local file sharing directory ({}):" .format(
            os.path.abspath(CLIENT_SHARE_DIR)))
        files = os.listdir(CLIENT_SHARE_DIR)
        if files:
            for f in files:
                filepath = os.path.join(CLIENT_SHARE_DIR, f)
                size = os.path.getsize(filepath)
                print("  {} ({} bytes)".format(f, size))
        else:
            print("  (empty)")

    # ------------------------------------------------------------------
    # rlist - remote directory listing from server
    # ------------------------------------------------------------------

    def rlist(self):
        if not self.connected:
            print("Not connected to a server. Use 'connect' first.")
            return

        try:
            # Send list command
            cmd_bytes = CMD["list"].to_bytes(CMD_FIELD_LEN, byteorder='big')
            self.tcp_socket.sendall(cmd_bytes)

            # Receive listing size (8 bytes)
            listing_size_bytes = self.recv_bytes(FILE_SIZE_FIELD_LEN)
            if not listing_size_bytes:
                self.handle_disconnect()
                return
            listing_size = int.from_bytes(listing_size_bytes, byteorder='big')

            # Receive listing data
            listing_bytes = self.recv_bytes(listing_size)
            if not listing_bytes:
                self.handle_disconnect()
                return

            listing = listing_bytes.decode(MSG_ENCODING)
            print("Remote file sharing directory:")
            for line in listing.split("\n"):
                print("  {}".format(line))
        except Exception as e:
            print("Error getting remote listing: {}".format(e))
            self.handle_disconnect()

    # ------------------------------------------------------------------
    # put - upload file to server
    # ------------------------------------------------------------------

    def put(self, filename):
        if not self.connected:
            print("Not connected to a server. Use 'connect' first.")
            return

        filepath = os.path.join(CLIENT_SHARE_DIR, filename)
        if not os.path.isfile(filepath):
            print("File '{}' not found in local share directory.".format(filename))
            return

        try:
            with open(filepath, 'rb') as f:
                file_data = f.read()

            file_size = len(file_data)
            filename_bytes = filename.encode(MSG_ENCODING)
            filename_size = len(filename_bytes)

            # Build packet:
            # [cmd=2 (1B)] [filename_size (1B)] [filename] [file_size (8B)] [file_data]
            cmd_bytes = CMD["put"].to_bytes(CMD_FIELD_LEN, byteorder='big')
            filename_size_bytes = filename_size.to_bytes(
                FILENAME_SIZE_FIELD_LEN, byteorder='big')
            file_size_bytes = file_size.to_bytes(FILE_SIZE_FIELD_LEN, byteorder='big')

            header = cmd_bytes + filename_size_bytes + filename_bytes + file_size_bytes
            self.tcp_socket.sendall(header + file_data)
            print("Uploaded '{}' ({} bytes).".format(filename, file_size))
        except Exception as e:
            print("Error uploading file: {}".format(e))
            self.handle_disconnect()

    # ------------------------------------------------------------------
    # get - download file from server
    # ------------------------------------------------------------------

    def get(self, filename):
        if not self.connected:
            print("Not connected to a server. Use 'connect' first.")
            return

        try:
            # Send get command + filename
            cmd_bytes = CMD["get"].to_bytes(CMD_FIELD_LEN, byteorder='big')
            filename_bytes = filename.encode(MSG_ENCODING)
            self.tcp_socket.sendall(cmd_bytes + filename_bytes)

            # Receive file size (8 bytes)
            file_size_bytes = self.recv_bytes(FILE_SIZE_FIELD_LEN)
            if not file_size_bytes:
                self.handle_disconnect()
                return
            file_size = int.from_bytes(file_size_bytes, byteorder='big')

            if file_size == 0:
                print("File '{}' not found on server.".format(filename))
                return

            # Receive file data
            received = 0
            file_data = bytearray()
            while received < file_size:
                chunk = self.tcp_socket.recv(min(RECV_SIZE, file_size - received))
                if not chunk:
                    print("Connection lost during download.")
                    self.handle_disconnect()
                    return
                file_data += chunk
                received += len(chunk)

            # Save file locally
            filepath = os.path.join(CLIENT_SHARE_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(file_data)

            print("Downloaded '{}' ({} bytes).".format(filename, file_size))
        except Exception as e:
            print("Error downloading file: {}".format(e))
            self.handle_disconnect()

    # ------------------------------------------------------------------
    # bye - disconnect from server
    # ------------------------------------------------------------------

    def bye(self):
        if not self.connected:
            print("Not connected to a server.")
            return
        try:
            self.tcp_socket.close()
        except Exception:
            pass
        self.tcp_socket = None
        self.connected = False
        print("Disconnected from server.")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def recv_bytes(self, length):
        """Receive exactly `length` bytes from the TCP socket."""
        data = bytearray()
        while len(data) < length:
            chunk = self.tcp_socket.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return bytes(data)

    def handle_disconnect(self):
        """Handle an unexpected disconnection."""
        print("Lost connection to server.")
        try:
            self.tcp_socket.close()
        except Exception:
            pass
        self.tcp_socket = None
        self.connected = False


########################################################################
# MAIN
########################################################################

if __name__ == '__main__':
    roles = {'client': Client, 'server': Server}
    parser = argparse.ArgumentParser(description="COMPENG 4DN4 - File Sharing Application")

    parser.add_argument('-r', '--role',
                        choices=roles,
                        help='server or client role',
                        required=True, type=str)

    args = parser.parse_args()
    roles[args.role]()

########################################################################
