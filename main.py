from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import sys
import time
import peerwire
from socketthread import SocketReply

from torrent import Torrent


if sys.version_info.major == 2:
    chr = unichr
    string_type = basestring
elif sys.version_info.major == 3:
    # chr should assume Unicode
    string_type = str


def main(argv):
    path = argv[1]

    torrent = Torrent(path)
    torrent.get_peers()
    for peer in torrent.peers:
        print("Connecting to: {}".format(peer))
        peer.connect()

    while 1:
        time.sleep(1)

        for peer in torrent.peers:
            reply = peer.socket.get_reply(block=False)
            if reply is None:
                continue

            if reply.status == SocketReply.ERROR:
                print("Error:", reply.payload, "from {}".format(peer))
                continue
            elif reply.status == SocketReply.SUCCESS:
                print("Connected to: {}".format(peer))
                peer.send_handshake(torrent.handshake)
                if peer.socket.get_reply(block=True).status == "success":
                    try:
                        print("Receiving handshake from {}".format(peer))
                        peer.receive_handshake()
                        print(repr(peer.handshake))
                    except peerwire.HandshakeException as e:
                        print(e)

            print("{} reply: {}".format(peer, reply.status))
            print("{} payload: {}".format(peer, reply.payload))


if __name__ == "__main__":
    main(sys.argv)
