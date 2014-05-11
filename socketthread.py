"""
Socket Threaded.

Aims to provide some simplified abstraction over raw sockets such as making
concurrent socket connection easier.
"""

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)
import socket
import struct

import sys
import threading

if sys.version_info.major == 2:
    chr = unichr
    string_type = basestring
    import Queue as queue
elif sys.version_info.major == 3:
    # chr should assume Unicode
    string_type = str
    import queue


def receive_all(sock, n):
    """
    Helper function to fully receive an arbitrary amount of data from a socket.

    :param sock: Socket connection
    :param n: Number of bytes to receive
    :return: Received data
    """
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            break
            #return None
        data += packet
    return data


class SocketCommand(object):
    """
    Command object for communicating with SocketThread.
    command must be either:             payload must be:

    SocketCommand.CONNECT               (host, port) tuple
    SocketCommand.SEND                  Binary data string
    SocketCommand.RECEIVE               Number of bytes to receive
    SocketCommand.RECEIVE_WITH_PREFIX   byte size of the prefix
    SocketCommand.CLOSE                 None
    """

    # The available socket commands:
    CONNECT = "connect"
    SEND = "send"
    RECEIVE = "receive"
    RECEIVE_WITH_PREFIX = "receive_with_prefix"
    CLOSE = "close"

    def __init__(self, command, payload=None):
        self.command = command
        self.payload = payload


class SocketReply(object):
    """
    Reply object for communicating with SocketThread.
    The reply must be either:       payload must be:

    SocketReply.ERROR               The Error object
    SocketReply.SUCCESS
    SocketReply.None                None
    """
    # TODO: write description for SocketReply.SUCCESS above

    # The available socket replies
    SUCCESS = "success"
    ERROR = "error"
    NONE = None

    def __init__(self, status, payload=None):
        self.status = status
        self.payload = payload


class SocketThread(threading.Thread):
    """
    Implements the threading.Thread interface and wraps a normal network socket.
    This makes it possible to do non blocking network I/O
    """
    # TODO: should we keep track of what command corresponds to what reply?

    def __init__(self):
        super(SocketThread, self).__init__()

        self.command_queue = queue.Queue()
        self.reply_queue = queue.Queue()
        self.socket = None

        self.alive = threading.Event()
        self.alive.set()

        self.connected = threading.Event()
        self.connected.clear()

    def run(self):
        """
        Overrides the threading.Thread method run. We keep polling the
        command_queue to see if there a new command should be handled.
        """
        while self.alive.isSet():
            try:
                # We have to have a timeout value to not block indefinitely
                # because otherwise we cant do the alive check in the outer
                # while loop because we would be stuck here in the loop body.
                cmd = self.command_queue.get(block=True, timeout=0.1)
                if cmd.command == SocketCommand.CONNECT:
                    address = cmd.payload
                    self._handle_CONNECT(address)
                elif cmd.command == SocketCommand.CLOSE:
                    self._handle_CLOSE()
                elif cmd.command == SocketCommand.SEND:
                    payload = cmd.payload
                    self._handle_SEND(payload)
                elif cmd.command == SocketCommand.RECEIVE:
                    number_of_bytes = cmd.payload
                    self._handle_RECEIVE(number_of_bytes)
                elif cmd.command == SocketCommand.RECEIVE_WITH_PREFIX:
                    prefix_size = cmd.payload
                    self._handle_RECEIVE_WITH_PREFIX(prefix_size)
                else:
                    # TODO: Handle invalid command
                    pass

                # TODO: should we call command_queue.task_done() here?
            except queue.Empty:
                continue

    def join(self, timeout=None):
        """
        Overrides the threading.Thread method join. We clear the alive event so
        that the thread knows to stop listening for new commands.
        :param timeout: Same as threading.Thread
        """
        self.alive.clear()
        threading.Thread.join(self, timeout)

    def is_connected(self):
        """
        Check if the socket has been connected.
        @note That even though this value update automatically when when successfully
        connected or closed the socket. It is still necessary to check the reply
        queue if the connect/close command was successful.
        :return: {Boolean}
        """
        return self.connected.isSet()

    def connect(self, address):
        """
        Connects the socket the the given address
        :param address: (host, port) Tuple
        """
        self.command_queue.put(SocketCommand(SocketCommand.CONNECT, address))

    def close(self):
        """
        Closes the socket
        """
        self.command_queue.put(SocketCommand(SocketCommand.CONNECT))

    def send(self, payload):
        """
        Sends the given payload to the socket. Requires an open and valid socket
        :param payload: Byte string of data
        """
        self.command_queue.put(SocketCommand(SocketCommand.SEND, payload))

    def receive(self, n):
        """
        Receives a specified number of bytes from the socket. Requires an open
        and valid socket.
        :param n: Number of bytes to receive from the socket.
        """
        self.command_queue.put(SocketCommand(SocketCommand.RECEIVE, n))

    def receive_with_prefix(self, prefix_size):
        """
        Receive a message that has a length prefix that is prefix_size bytes
        long.
        :param prefix_size: byte size of the prefix
        """
        self.command_queue.put(SocketCommand(SocketCommand.RECEIVE_WITH_PREFIX,
                                             prefix_size))

    def get_reply(self, block=True, timeout=None):
        """
        Fetches a reply from the reply queue.
        :param block: Boolean whether the call should block until a reply i
        present
        :param timeout: If block is true wait maximum timeout number of seconds
        :return: A SocketReply object is returned if possible. Else if returns
        None.
        """
        try:
            reply = self.reply_queue.get(block=block, timeout=timeout)
            # TODO: should we call reply_queue.task_done() here?
            return reply
        except queue.Empty:
            return SocketReply(SocketReply.NONE, None)

    def _handle_CONNECT(self, address):
        """
        Handles the connection command by creating a tcp connection to the given
        address.

        :param address: (host, port) tuple
        """
        self.socket = socket.socket(socket.AF_INET,
                                    socket.SOCK_STREAM)  # tcp connection

        try:
            self.socket.connect(address)
            self.connected.set()
            self.reply_queue.put(SocketReply(SocketReply.SUCCESS))
        except socket.error as e:
            self.reply_queue.put(SocketReply(SocketReply.ERROR, e))

    def _handle_CLOSE(self):
        """
        Handles the close command. This requires that a socket already has been
        opened.
        """
        self.socket.close()
        self.connected.clear()
        self.reply_queue.put(SocketReply(SocketReply.SUCCESS))

    def _handle_SEND(self, payload):
        """
        Handles the send command. This requires an open and valid socket
        connection.
        :param payload:
        """
        try:
            self.socket.sendall(payload)
            self.reply_queue.put(SocketReply(SocketReply.SUCCESS))
        except socket.error as e:
            self.reply_queue.put(SocketReply(SocketReply.ERROR, e))

    def _handle_RECEIVE(self, n):
        """
        Handles the receive command. This requires an open and valid socket
        connection.
        :param n: number of bytes to receive
        """
        try:
            received_data = receive_all(self.socket, n)
            self.reply_queue.put(
                SocketReply(SocketReply.SUCCESS, received_data))
        except socket.error as e:
            self.reply_queue.put(SocketReply(SocketReply.ERROR, e))

    def _handle_RECEIVE_WITH_PREFIX(self, prefix_size):
        """
        Handles the receive with prefix command. This require an open and valid
        socket connection.
        :param prefix_size: byte size of the prefix
        :return:
        """
        try:
            length_prefix = receive_all(self.socket, prefix_size)
            if len(length_prefix) == prefix_size:
                if prefix_size == 1:
                    message_length = struct.unpack(b"!B", length_prefix)[0]
                elif prefix_size == 2:
                    message_length = struct.unpack(b"!H", length_prefix)[0]
                elif prefix_size == 4:
                    message_length = struct.unpack(b"!I", length_prefix)[0]
                elif prefix_size == 8:
                    message_length = struct.unpack(b"!Q", length_prefix)[0]
                else:
                    error = "prefix_size must be either 1,2,4 or 8 got {}".\
                        format(prefix_size)
                    raise TypeError(error)

                if message_length == 0:
                    received_data = b''
                else:
                    received_data = receive_all(self.socket, message_length)

                if len(received_data) == message_length:
                    message = (length_prefix, received_data)
                    self.reply_queue.put(SocketReply(SocketReply.SUCCESS,
                                                     message))
                    return
            self.reply_queue.put(SocketReply(
                SocketReply.ERROR, socket.error("Socket closed prematurely")))
        except socket.error as e:
            self.reply_queue.put(SocketReply(SocketReply.ERROR, e))

