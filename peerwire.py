"""
Peer wire protocol (TCP)

The peer protocol facilitates the exchange of pieces as described in the 'metainfo file (.torrent file).
Note here that the original specification also used the term "piece" when describing the peer protocol, but as a
different term than "piece" in the metainfo file. For that reason, the term "block" will be used in this specification
to describe the data that is exchanged between peers over the wire.
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


if sys.version_info.major == 2:
    chr = unichr
    string_type = basestring
elif sys.version_info.major == 3:
    # chr should assume Unicode
    string_type = str

LENGTH_PREFIX_SIZE = 4

def receive_all(sock, n):
    """
    Helper function to fully receive an arbitrary amount of data from a socket
    :param sock: Socket connection
    :param n: Number of bytes to receive
    :return: Received data
    """
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

class HandshakeException(Exception):
    """
    Base exception for peer wire hand shake
    """
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

    def __str__(self):
        return "{}:{} Refused the handshake".format(self.ip, self.port)


def generate_handshake(info_hash, peer_id):
    """
    The handshake is a required message and must be the first message transmitted by the client. It is (49+len(pstr))
    bytes long in the form:

    <pstrlen><pstr><reserved><info_hash><peer_id>

    Where:
    pstrlen: string length of <pstr>, as a single raw byte
    pstr: string identifier of the protocol
    reserved: eight (8) reserved bytes. All current implementations use all zeroes. Each bit in these bytes can be used
     to change the behavior of the protocol.
    info_hash: 20-byte SHA1 hash of the info key in the metainfo file. This is the same info_hash that is transmitted in
     tracker requests.
    peer_id: 20-byte string used as a unique ID for the client. This is usually the same peer_id that is transmitted in
     tracker requests

    In version 1.0 of the BitTorrent protocol, pstrlen = 19, and pstr = "BitTorrent protocol".

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


def send_handshake(handshake, ip, port):
    """
    Opens a connection to the given ip, port tries to send the handshake.
    :param handshake: The handshake that is send
    :param ip: The ip that the socket is opened on
    :param port: The port the receiver is listening on.
    :return: The open Socket and the response data
    :raise HandshakeException: a HandshakeException is raised if unable to establish connection or the handshake was
    refused.
    """
    address = (ip, port)

    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # tcp connection

    try:
        tcp_sock.connect(address)

        tcp_sock.send(handshake)

        response_data = receive_all(tcp_sock, len(handshake))  # tcp_sock.recv(len(handshake))

        if response_data is None:
            tcp_sock.close()
            raise HandshakeException(ip, port)
    except socket.error:
        tcp_sock.close()
        raise HandshakeException(ip, port)

    return tcp_sock, response_data


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

    decoded_handshake = dict(pstr=pstr, pstrlen=pstrlen, reserved=reserved, info_hash=info_hash, peer_id=peer_id)

    return decoded_handshake


class Peer(object):
    def __init__(self, ip, port, peer_id):
        self.ip = ip
        self.port = port
        self.peer_id = peer_id

        self.am_choking = True  # this client is choking the peer
        self.am_interested = False  # this client is interested in the peer
        self.peer_choking = True  # peer is choking this client
        self.peer_interested = False  # peer is interested in this client

        self.peers_info_hash = None

        self.has_shook_hands = False
        self.socket = None

        self.bitfield = Bitfield()

    def __str__(self):
        return "Peer: {ip}:{port}".format(ip=self.ip, port=self.port)

    def initiate_connection(self, handshake):
        """
        Creates and initiates a tcp connection to the peer
        :param handshake: The handshake that is send to the peer.
        :return: True if success, False on failure
        """
        try:
            self.socket, response = send_handshake(handshake, self.ip, self.port)
            received_handshake = decode_handshake(response)

            self.peer_id = received_handshake['peer_id']
            self.peers_info_hash = received_handshake['info_hash']

            self.has_shook_hands = True
        except HandshakeException:
            self.has_shook_hands = False

        return self.has_shook_hands

    def receive_message(self):

        # length prefix is a four byte big-endian value
        length_prefix = receive_all(self.socket, LENGTH_PREFIX_SIZE) #self.socket.recv(LENGTH_PREFIX_SIZE)
        length_prefix = struct.unpack(b">I", length_prefix)[0]  # struct.unpack always returns a tuple.
        if length_prefix == 0:
            # keep-alive: <len=0000>

            # he keep-alive message is a message with zero bytes, specified with the length prefix set to zero. There is
            # no message ID and no payload. Peers may close a connection if they receive no messages (keep-alive or any
            # other message) for a certain period of time, so a keep-alive message must be sent to maintain the
            # connection alive if no command have been sent for a given amount of time. This amount of time is generally
            # two minutes.
            print("keep alive")
            return
        message =  receive_all(self.socket, length_prefix) # self.socket.recv(length_prefix)

        message_id = ord(message[0])

        payload = None

        # id 0, 1, 2 and 3 have no payload
        if message_id >= 4:
            payload = message[1:]


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
            pass
        elif message_id == 3:
            # not interested: <len=0001><id=3>

            # The not interested message is fixed-length and has no payload
            pass
        elif message_id == 4:
            # have: <len=0005><id=4><piece index>

            # The have message is fixed length. The payload is the zero-based index of a piece that has just been
            # successfully downloaded and verified via the hash.

            piece_index = int(payload.encode('hex'), 16)  # Convert to Integer
            self.bitfield.add_index(piece_index)
        elif message_id == 5:
            # bitfield: <len=0001+X><id=5><bitfield>

            # The bitfield message may only be sent immediately after the handshaking sequence is completed, and before
            # any other messages are sent. It is optional, and need not be sent if a client has no pieces.
            # The bitfield message is variable length, where X is the length of the bitfield. The payload is a bitfield
            # representing the pieces that have been successfully downloaded. The high bit in the first byte corresponds
            # to piece index 0. Bits that are cleared indicated a missing piece, and set bits indicate a valid and
            # available piece. Spare bits at the end are set to zero.

            # i.e. '\xfe\xff' = 1111111011111111 (pieces 0-15, piece 7 is missing). Any spare bits at the end of the
            # last byte are left unset (0)

            # Some clients (Deluge for example) send bitfield with missing pieces even if it has all data. Then it sends
            # rest of pieces as have messages. They are saying this helps against ISP filtering of BitTorrent protocol.
            # It is called lazy bitfield.
            # A bitfield of the wrong length is considered an error. Clients should drop the connection if they receive
            # bitfields that are not of the correct size, or if the bitfield has any of the spare bits set.

            self.bitfield = Bitfield(payload)
        elif message_id == 6:
            # request: <len=0013><id=6><index><begin><length>

            # The request message is fixed length, and is used to request a block. The payload contains the following
            # information:
            #  index: integer specifying the zero-based piece index
            #  begin: integer specifying the zero-based byte offset within the piece
            #  length: integer specifying the requested length.

            pass
        elif message_id == 7:
            # piece: <len=0009+X><id=7><index><begin><block>

            #  piece message is variable length, where X is the length of the block. The payload contains the following
            #  information:
            #   index: integer specifying the zero-based piece index
            #   begin: integer specifying the zero-based byte offset within the piece
            #   block: block of data, which is a subset of the piece specified by index
            pass
        elif message_id == 8:
            # cancel: <len=0013><id=8><index><begin><length

            # cancel message is fixed length, and is used to cancel block requests. The payload is identical to that of
            # the "request" message. It is typically used during "End Game".
            pass
        elif message_id == 9:
            # port: <len=0003><id=9><listen-port>

            # The port message is sent by newer versions of the Mainline that implements a DHT tracker. The listen port
            # is the port this peer's DHT node is listening on. This peer should be inserted in the local routing table
            # (if DHT tracker is supported).
            pass
        else:
            # !!! Unknown message id
            pass

        print(repr(message_id), repr(payload))



class Bitfield(object):
    def __init__(self, bitfield=b""):
        self.bitfield = []

        # Add the bits as Boolean values in the bitfield
        for byte in bitfield:
            for bit in reversed(range(8)): # Reverse to get correct endian
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