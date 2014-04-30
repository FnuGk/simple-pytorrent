from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import sys
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

    while (1):
        for peer in torrent.peers:
            reply = peer.socket.get_reply(block=True, timeout=0.01)
            if reply is None: continue

            if reply.reply == SocketReply.ERROR:
                print("Error:", str(reply.payload))
                continue
            elif reply.reply == SocketReply.SUCCESS:
                print("Connected to: {}".format(peer))

            print("payload:", reply.payload)


if __name__ == "__main__":
    main(sys.argv)
