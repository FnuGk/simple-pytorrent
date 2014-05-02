"""
Peer wire protocol (TCP)

The peer protocol facilitates the exchange of pieces as described in the
'metainfo file (.torrent file). Note here that the original specification also
used the term "piece" when describing the peer protocol, but as a different term
than "piece" in the metainfo file. For that reason, the term "block" will be
used in this specification to describe the data that is exchanged between peers
over the wire.
"""

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import struct
import sys
import socketthread


if sys.version_info.major == 2:
    chr = unichr
    string_type = basestring
elif sys.version_info.major == 3:
    # chr should assume Unicode
    string_type = str

LENGTH_PREFIX_SIZE = 4


class HandshakeException(Exception):
    """
    Base exception for peer wire hand shake
    """

    def __init__(self, peer):
        self.peer = peer

    def __str__(self):
        return "{} Refused the handshake".format(self.peer)


def generate_handshake(info_hash, peer_id):
    """
    The handshake is a required message and must be the first message
    transmitted by the client. It is (49+len(pstr)) bytes long in the form:

    <pstrlen><pstr><reserved><info_hash><peer_id>

    Where:
    pstrlen: string length of <pstr>, as a single raw byte
    pstr: string identifier of the protocol
    reserved: eight (8) reserved bytes. All current implementations use all
     zeroes. Each bit in these bytes can be used to change the behavior of the
     protocol.
    info_hash: 20-byte SHA1 hash of the info key in the meta info file. This is
     the same info_hash that is transmitted in tracker requests.
    peer_id: 20-byte string used as a unique ID for the client. This is usually
     the same peer_id that is transmitted in tracker requests

    In version 1.0 of the BitTorrent protocol:
    pstrlen = 19 and pstr = "BitTorrent protocol".

    :param info_hash:
    :param peer_id:
    :return:
    """
    pstr = b"BitTorrent protocol"
    pstrlen = bytes(chr(len(pstr)))

    reserved = b"\x00" * 8  # 8 zeroes

    handshake = pstrlen + pstr + reserved + info_hash + peer_id

    assert len(handshake) == 49 + len(pstr)
    assert pstrlen == bytes(chr(19))

    return handshake


def decode_handshake(handshake):
    """
    Decodes a received handshake.

    :param handshake: The raw byte string that is received.
    :return: Dict with the keys pstr, pstrlen, reserved, info_hash and peer_id
    """
    handshake = list(handshake)
    handshake.reverse()

    pstrlen = ord(handshake.pop())

    pstr = b""
    for _ in range(pstrlen):
        pstr += handshake.pop()

    reserved = b""
    for _ in range(8):
        reserved += handshake.pop()

    info_hash = b""
    for _ in range(20):
        info_hash += handshake.pop()

    peer_id = b""
    for _ in range(20):
        peer_id += handshake.pop()

    decoded_handshake = dict(pstr=pstr, pstrlen=pstrlen, reserved=reserved,
                             info_hash=info_hash, peer_id=peer_id)

    return decoded_handshake


class Peer(object):
    # TODO: Somehow make the Peer do I/O in a threaded manner
    def __init__(self, ip, port, peer_id):
        self.ip = ip
        self.port = port

        self.handshake = None

        self.peers_info_hash = None
        self.has_shook_hands = False

        # TODO: Should we inherit from this instead ?
        self.socket = socketthread.SocketThread()

        self.peer_id = peer_id

        # Peer state
        self.am_choking = True  # this client is choking the peer
        self.am_interested = False  # this client is interested in the peer
        self.peer_choking = True  # peer is choking this client
        self.peer_interested = False  # peer is interested in this client

        self.bitfield = Bitfield()  # Contains info on what pieces the peer has

    def __str__(self):
        return "Peer: {ip}:{port}".format(ip=self.ip, port=self.port)

    def connect(self):
        """
        Creates and initiates a tcp connection to the peer.
        """

        address = (self.ip, self.port)
        self.socket.connect(address)

    def send_handshake(self, handshake):
        """
        Sends the handshake to the peer
        :param handshake: The handshake to be send
        """
        self.socket.send(handshake)

    def receive_handshake(self):
        # TODO: to implement this we need to a way to this async
        handshake_length_without_pstr = 49  # taken from the specification
        pstrlen_byte_len = 1 # pstrlen is a single raw byte

        self.socket.receive(pstrlen_byte_len)  # pstrlen is a single raw byte
        reply = self.socket.get_reply(block=True)
        if reply.status != socketthread.SocketReply.SUCCESS:
            raise HandshakeException(self)
        pstrlen = reply.payload

        self.socket.receive(pstrlen
                            + handshake_length_without_pstr
                            - pstrlen_byte_len)

        reply = self.socket.get_reply(block=True)
        if reply.status != socketthread.SocketReply.SUCCESS:
            raise HandshakeException(self)

        raw_handshake = pstrlen + reply.payload

        self.handshake = decode_handshake(raw_handshake)

    def receive_message(self):
        """
        All messages comes on the form  <length prefix><message ID><payload>.
        Where <length prefix> is a four byte big-endian value. <message ID> is a
        single decimal byte and <payload> is message depended.

        :return:
        """

        # length prefix is a four byte big-endian value
        length_prefix = socketthread.receive_all(self.socket, LENGTH_PREFIX_SIZE)
        length_prefix = struct.unpack(b">I", length_prefix)[0]  # it's a tuple
        if length_prefix == 0:
            # keep-alive: <len=0000>

            # he keep-alive message is a message with zero bytes, specified with
            # the length prefix set to zero. There is no message ID and no
            # payload. Peers may close a connection if they receive no messages
            # (keep-alive or any other message) for a certain period of time, so
            # a keep-alive message must be sent to maintain the connection alive
            # if no command have been sent for a given amount of time. This
            # amount of time is generally two minutes.
            print("keep alive")
            return
        message = socketthread.receive_all(self.socket, length_prefix)

        # The message ID is a single decimal byte so just extract it from the
        # received message
        message_id = ord(message[0])

        # id 0, 1, 2 and 3 have no payload.
        if message_id >= 4:
            # The payload is the rest of the message.
            payload = message[1:]
        else:
            payload = None

        # TODO: handle received messages!
        if message_id == 0:
            # choke: <len=0001><id=0>
            # The choke message is fixed-length and has no payload.

            self.peer_choking = True
        elif message_id == 1:
            # unchoke: <len=0001><id=1>
            # The unchoke message is fixed-length and has no payload

            self.peer_choking = False
        elif message_id == 2:
            # interested: <len=0001><id=2>
            # The interested message is fixed-length and has no payload

            self.peer_interested = True
        elif message_id == 3:
            # not interested: <len=0001><id=3>
            # The not interested message is fixed-length and has no payload

            self.peer_interested = False
        elif message_id == 4:
            # have: <len=0005><id=4><piece index>
            # The have message is fixed length. The payload is the zero-based
            # index of a piece that has just been successfully downloaded and
            # verified via the hash.

            piece_index = int(payload.encode('hex'), 16)  # Convert to Integer
            self.bitfield.add_index(piece_index)
        elif message_id == 5:
            # bitfield: <len=0001+X><id=5><bitfield>
            # The bitfield message may only be sent immediately after the
            # handshaking sequence is completed, and before any other messages
            # are sent. It is optional, and need not be sent if a client has no
            # pieces. The bitfield message is variable length, where X is the
            # length of the bitfield. The payload is a bitfield representing the
            # pieces that have been successfully downloaded. The high bit in the
            # first byte corresponds to piece index 0. Bits that are cleared
            # indicated a missing piece, and set bits indicate a valid and
            # available piece. Spare bits at the end are set to zero.

            # i.e. '\xfe\xff' = 1111111011111111 (pieces 0-15, piece 7 is
            # missing). Any spare bits at the end of the last byte are left
            # unset (0)

            # Some clients (Deluge for example) send bitfield with missing
            # pieces even if it has all data. Then it sends rest of pieces as
            # have messages. They are saying this helps against ISP filtering of
            # BitTorrent protocol. It is called lazy bitfield. A bitfield of the
            # wrong length is considered an error. Clients should drop the
            # connection if they receive bitfields that are not of the correct
            # size, or if the bitfield has any of the spare bits set.

            self.bitfield = Bitfield(payload)
        elif message_id == 6:
            # request: <len=0013><id=6><index><begin><length>
            # The request message is fixed length, and is used to request a
            # block. The payload contains the following information:
            #  index: integer specifying the zero-based piece index
            #  begin: integer specifying the zero-based byte offset within
            #   the piece
            #  length: integer specifying the requested length.

            pass  # TODO: Implement this
        elif message_id == 7:
            # piece: <len=0009+X><id=7><index><begin><block>
            # piece message is variable length, where X is the length of the
            # block. The payload contains the following information:
            #  index: integer specifying the zero-based piece index
            #  begin: integer specifying the zero-based byte offset within the
            #  piece block: block of data, which is a subset of the piece
            #  specified by index

            pass  # TODO: Implement this
        elif message_id == 8:
            # cancel: <len=0013><id=8><index><begin><length
            # cancel message is fixed length, and is used to cancel block
            # requests. The payload is identical to that of the "request"
            # message. It is typically used during "End Game".

            pass  # TODO: Implement this
        elif message_id == 9:
            # port: <len=0003><id=9><listen-port>
            # The port message is sent by newer versions of the Mainline that
            # implements a DHT tracker. The listen port is the port this peer's
            # DHT node is listening on. This peer should be inserted in the
            # local routing table (if DHT tracker is supported).

            pass  # TODO: Implement this
        else:
            # !!! Unknown message id

            pass  # TODO: Implement this

        print(repr(message_id), repr(payload))


class Bitfield(object):
    """
    Super simple and very inefficient way to store the bit-torrent bitfield.

    We simply take a bitfield and convert it to a list of boolean values. So the
    bitfield "11011" is converted to the list [True, True, False, True, True]
    This way we can use the add_index(2) to change this to
    [True, True, True, True, True] and has_index(2) will return True. If
    add_index is called on an index that is out of range the missing indexes is
    simply set to False.
    """

    def __init__(self, bitfield=b""):
        self.bitfield = []

        # Add the bits as Boolean values in the bitfield
        for byte in bitfield:
            for bit in reversed(range(8)):  # Reverse to get correct endian
                self.bitfield.append(bool(ord(byte) >> bit & 1))

    def __str__(self):
        return "".join(["{}".format(int(bit)) for bit in self.bitfield])

    def add_index(self, index):
        while len(self.bitfield) <= index:
            self.bitfield.append(False)
        self.bitfield[index] = True

    def has_index(self, index):
        if len(self.bitfield) >= index:
            return self.bitfield[index]
        else:
            return False


if __name__ == "__main__":
    pass
