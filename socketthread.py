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


class SocketThread(threading.Thread):
    """
    Implements the threading.Thread interface
    """

    def __init__(self):
        super(SocketThread, self).__init__()

        self.command_queue = queue.Queue()
        self.reply_queue = queue.Queue()
        self.alive = threading.Event()
        self.alive.set()
        self.socket = None

    def run(self):
        while self.alive.isSet():
            try:
                # Use a timeout value so we don't block forever
                cmd = self.command_queue.get(True, 0.1)
                # TODO: Do something with the received command
            except queue.Empty:
                continue

    def join(self, timeout=None):
        self.alive.clear()
        threading.Thread.join(self, timeout)


    def _handle_connect(self, host, port):
        address = (host, port)

        self.socket = socket.socket(socket.AF_INET,
                                    socket.SOCK_STREAM)  # tcp connection

        try:
            self.socket.connect(address)
            # TODO: put SUCCESS in the reply_queue
        except socket.error:
            # TODO: put ERROR in the reply_queue
            pass

    def _handle_CLOSE(self):
        self.socket.close()
        # TODO: put SUCCESS in the reply_queue
