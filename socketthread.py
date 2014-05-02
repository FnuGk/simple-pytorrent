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
    command must be either:     payload must be:

    SocketCommand.CONNECT       (host, port) tuple
    SocketCommand.SEND          Binary data string
    SocketCommand.RECEIVE       Number of bytes to receive
    SocketCommand.CLOSE         None
    """

    # The available socket commands:
    CONNECT = "connect"
    SEND = "send"
    RECEIVE = "receive"
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
    """
    # TODO: write description for SocketReply.SUCCESS above

    # The available socket replies
    SUCCESS = "success"
    ERROR = "error"

    def __init__(self, status, payload=None):
        self.status = status
        self.payload = payload


class SocketThread(threading.Thread):
    """
    Implements the threading.Thread interface
    """
    # TODO: should we keep track of what command corresponds to what reply?

    def __init__(self):
        super(SocketThread, self).__init__()

        self.command_queue = queue.Queue()
        self.reply_queue = queue.Queue()
        self.socket = None

        self.alive = threading.Event()
        self.start() # TODO: Should we really call this here?
        self.alive.set()

    def run(self):
        while self.alive.isSet():
            try:
                # Use a timeout value so we don't block forever
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
                else:
                    # TODO: Handle invalid command
                    pass
                # TODO: should we call command_queue.task_done() here?
            except queue.Empty:
                continue

    def join(self, timeout=None):
        self.alive.clear()
        threading.Thread.join(self, timeout)


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
            return None


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
            self.reply_queue.put(SocketReply(SocketReply.SUCCESS))
        except socket.error as e:
            self.reply_queue.put(SocketReply(SocketReply.ERROR, e))

    def _handle_CLOSE(self):
        """
        Handles the close command. This requires that a socket already has been
        opened.
        """
        self.socket.close()
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
