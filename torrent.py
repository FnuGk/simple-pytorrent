from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)
import random
import string
import sys
import time

import bencode
import peerwire
import tracker


if sys.version_info.major == 2:
    chr = unichr
    string_type = basestring
elif sys.version_info.major == 3:
    # chr should assume Unicode
    string_type = str


def generate_peer_id():
    """
    Generate a 20 bytes (characters) long peer id

    :return: 20 bytes String
    """
    CLIENT_ID = b"py"
    CLIENT_VERSION = b"0001"

    peer_id = b"-" + CLIENT_ID + CLIENT_VERSION + b"-"

    # Generate rest of the id from a pool of random letters and digits.
    # Optimally we would include something specific for this machine
    # in order to make the peer_id more unique for this machine but
    # we omit that for simplicity
    # TODO: Should this be wrapped in a call to bytes?
    while len(peer_id) != 20:
        peer_id += random.choice(string.digits + string.ascii_letters)

    return peer_id


PEER_ID = generate_peer_id()


class Torrent(object):
    def __init__(self, path_to_torrent):
        with open(path_to_torrent, "rb") as f:
            file_content = bytes(f.read())
            self.meta_info = bencode.decode(file_content)

        self.handshake = peerwire.generate_handshake(
            tracker.calc_info_hash(self.meta_info), PEER_ID)
        self.peers = []
        self.bitfield = peerwire.Bitfield()

    def get_peers(self):
        peers = tracker.get_peers(self.meta_info, PEER_ID)
        peers = [peerwire.Peer(peer['ip'], peer['port'], peer['peer_id'])
                 for peer in peers]

        # Maybe check for duplicates?
        self.peers.extend(peers)

    def serve_forever(self):
        self.get_peers()  # We need some peers to talk to

        for peer in self.peers:
            print("Connecting to: {}".format(peer))
            peer.connect()

        while 1:
            time.sleep(1)

            for peer in self.peers:
                if not peer.is_connected():
                    continue

                replies = peer.get_all_replies(block=False)

                for reply in replies:
                    if not peer.has_shook_hands:
                        try:
                            print("Sending handshake to {}".format(peer))
                            peer.send_handshake(self.handshake)
                            reply = peer.get_reply(block=True)
                            if reply.status == "error":
                                error = reply.payload
                                raise error

                            assert reply.status == "success"

                            peer.receive_handshake()

                            print("{} shook hands: {}".format(peer,
                                                              repr(peer.handshake)))
                            if not peer.handshake == self.handshake:
                                # TODO: better way to handle this error?
                                peer.has_shook_hands = False
                                continue
                            print("hands shook with {}".format(peer))
                        except peerwire.HandshakeException:
                            continue

                    
                    print("{} reply: {}".format(peer, reply.status))
                    print("{} payload: {}".format(peer, reply.payload))
