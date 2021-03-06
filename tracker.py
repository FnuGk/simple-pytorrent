"""
Provides a minimum of functionality to interact with a bit-torrent tracker
"""

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import hashlib
import urllib
import urllib2
import sys

import bencode


if sys.version_info.major == 2:
    chr = unichr
    string_type = basestring
elif sys.version_info.major == 3:
    # chr should assume Unicode
    string_type = str


def calc_info_hash(meta_info, url_encode=False):
    """
    Calculates the info hash from a decoded torrent file (meta info).

    :param meta_info: The meta info to generate info hash from.
    :param url_encode: If true the resulting info hash will be url encoded.
    :return: sha1 info hash
    """
    info_key = bencode.encode(meta_info['info'])
    info_hash = hashlib.sha1(info_key).digest()

    if url_encode:
        # because the info_hash is a string we use quote_plus instead of
        # urlencode
        info_hash = urllib.quote_plus(info_hash)

    return info_hash


def binary_peer_extract(peers):
    """
    A tracker may choose to send the list of peers as a binary string consisting
    of multiples of 6 bytes where the first 4 bytes are the IP address and the
    last 2 bytes are the port number. All in network (big endian) notation. This
    function extracts the ip and port from the binary data and stores it in a
    dict.

    :param peers: Binary string of peers.
    :return: A dict with the keys 'ip' and 'port'
    """
    peers = [ord(c) for c in peers]  # Peers is in binary form

    # Split the peers up in multiples of 6 bytes
    peer_list = [peers[i:i + 6] for i in range(0, len(peers), 6)]

    peer_list = [dict(peer_id=None,
                      ip="{0}.{1}.{2}.{3}".format(p[0], p[1], p[2], p[3]),
                      port=(256 * p[4]) + p[5])  # Convert to an int
                 for p in peer_list]

    return peer_list


def query_announcer(announce_url, info_hash, peer_id, port="8080", uploaded=0,
                    downloaded=0, left=1000, event="",
                    numwant=50, trackerid=None):
    """
    The tracker is an HTTP/HTTPS service that responds to HTTP GET requests.
    Note: All binary data in the URL must be properly url-escaped.

    :param announce_url: The trackers base announce URL.
    :param info_hash: urlencoded 20-byte SHA1 hash of the value of the info key
    from the Metainfo file. Note that the value will be a bencoded dictionary
    :param peer_id: urlencoded 20-byte string used as a unique ID for the
    client, generated by the client at startup. This is allowed to be any
    value, and may be binary data.
    :param port: The port number that the client is listening on. Ports reserved
    for BitTorrent are typically 6881-6889. Clients may choose to give up if it
    cannot establish a port within this range
    :param uploaded: The total amount uploaded (since the client sent the
    'started' event to the tracker) in base ten ASCII. While not explicitly
    stated in the official specification, the consensus is that this should be
    the total number of bytes uploaded.
    :param downloaded:  The total amount downloaded (since the client sent the
    'started' event to the tracker) in base ten ASCII. While not explicitly
    stated in the official specification, the consensus is that this should be
    the total number of bytes downloaded.
    :param left: The number of bytes this client still has to download in base
    ten ASCII. Clarification: The number of bytes needed to download to be 100%
    complete and get all the included files in the torrent.
    :param event: If specified, must be one of started, completed, stopped, (or
    empty which is the same as not being specified). If not specified, then this
    request is one performed at regular intervals.
         started: The first request to the tracker must include the event key
          with this value.
         stopped: Must be sent to the tracker if the client is shutting down
          gracefully.
         completed: Must be sent to the tracker when the download completes.
          However, must not be sent if the download
          was already 100% complete when the client started. Presumably, this is
          to allow the tracker to increment the "completed downloads" metric
          based solely on this event.
    :param numwant: Number of peers that the client would like to receive from
    the tracker. This value is permitted to be zero. If omitted, defaults to 50
    peers.
    :param trackerid: Optional. If a previous announce contained a tracker id,
    it should be set here.
    :return: A dict of the tracker response with the following keys:
        failure reason: If present, then no other keys may be present. The value
         is a human-readable error message as to why the request failed
         (string).
        warning message: (new, optional) Similar to failure reason, but the
         response still gets processed normally. The warning message is shown
         just like an error.
        interval: Interval in seconds that the client should wait between
         sending regular requests to the tracker
        min interval: (optional) Minimum announce interval. If present clients
         must not reannounce more frequently than this.
        tracker id: A string that the client should send back on its next
         announcements. If absent and a previous announce sent a tracker id, do
         not discard the old value; keep using it.
        complete: number of peers with the entire file, i.e. seeders (integer)
        incomplete: number of non-seeder peers, aka "leechers" (integer)
        peers: Peers can in either dict form or binary form.
            dict form: A list of dicts with the following keys:
                peer id: peer's self-selected ID, as described above for the
                 tracker request (string)
                ip: peer's IP address either IPv6 (hexed) or IPv4 (dotted quad)
                 or DNS name (string)
                port: peer's port number (integer)
            binary form: binary string consisting of multiples of 6 bytes.
             First 4 bytes are the IP address and last 2 bytes are the port
             number. All in network (big endian) notation.
    """
    payload = {
        "info_hash": info_hash,
        # automatically be urlencoded so just get the raw hash
        "peer_id": peer_id,
        "port": port,
        "uploaded": uploaded,
        "downloaded": downloaded,
        "left": left,
        "compact": 1,
        "event": event,
        "numwant": numwant,
        "trackerid": trackerid
    }

    # should not use an already url encoded info hash!
    payload = urllib.urlencode(payload)

    url = announce_url + "/?" + payload

    response = urllib2.urlopen(url).read()
    decoded_response = bencode.decode(bytes(response))
    return decoded_response


def get_peers(meta_info, peer_id):
    """
    Query all trackers in the meta info for peers. Currently do not query udp
    trackers as that is more complicated.

    :param meta_info: A bdecoded torrent file
    :param peer_id: The client generated peer_id
    :return: List of peers.
    """
    peer_list = []
    info_hash = calc_info_hash(meta_info)
    for announce_list in meta_info['announce-list']:
        for announcer in announce_list:
            if not announcer.startswith("udp"):
                response = query_announcer(announcer, info_hash, peer_id)

                peers = response['peers']
                if isinstance(peers, string_type):
                    peers = binary_peer_extract(peers)

                peer_list.extend(peers)
    return peer_list


def scrape(announce_url, info_hashes=None):
    """
    By convention most trackers support another form of request, which queries
    the state of a given torrent (or all torrents) that the tracker is managing.
    This is referred to as the "scrape page" because it automates the otherwise
    tedious process of "screen scraping" the tracker's stats page.

    The scrape URL is also a HTTP GET method, similar to the one described
    above. However the base URL is different. To derive the scrape URL use the
    following steps: Begin with the announce URL. Find the last '/' in it. If
    the text immediately following that '/' isn't 'announce' it will be taken as
    a sign that that tracker doesn't support the scrape convention. If it does,
    substitute 'scrape' for 'announce' to find the scrape page.

    The scrape URL may be supplemented by the optional parameter info_hash, a
    20-byte value as described above. This restricts the tracker's report to
    that particular torrent. Otherwise stats for all torrents that the tracker
    is managing are returned. Software authors are strongly encouraged to use
    the info_hash parameter when at all possible, to reduce the load and
    bandwidth of the tracker. You may also specify multiple info_hash parameters
    to trackers that support it. While this isn't part of the official
    specifications it has become somewhat a defacto standard.

    :param announce_url: The trackers announce url
    :param info_hashes: info hashes of torrents to scrape for
    :return: A dict with the following keys:
        files: a dictionary containing one key/value pair for each torrent for
         which there are stats. If info_hash was supplied and was valid, this
         dictionary will contain a single key/value. Each key consists of a
         20-byte binary info_hash. The value of each entry is another dictionary
         containing the following:
            complete: number of peers with the entire file, i.e. seeders
             (integer)
            downloaded: total number of times the tracker has registered a
             completion ("event=complete", i.e. a client finished downloading
             the torrent)
            incomplete: number of non-seeder peers, aka "leechers" (integer)
            name: (optional) the torrent's internal name, as specified by the
             "name" file in the info section of the .torrent file
    :raise Exception: TypeError()
    """
    last_slash_pos = announce_url.rfind('/')

    if not "/announce" in announce_url[last_slash_pos:]:
        raise Exception("Cannot scrape {}".format(repr(announce_url)))

    scrape_url = announce_url.replace("/announce", "/scrape")

    if info_hashes is not None:
        if isinstance(info_hashes, string_type):
            scrape_url += "/?info_hash=" + urllib.quote_plus(info_hashes)
        elif isinstance(info_hashes, list):
            scrape_url += "/?info_hash=" + urllib.quote_plus(info_hashes[0])
            for info_hash in info_hashes[1:]:
                scrape_url += "&info_hash=" + urllib.quote_plus(info_hash)

        else:
            raise TypeError("info_hash must either be a String or List")

    if not scrape_url.startswith("udp"):
        response = urllib2.urlopen(scrape_url).read()
        decoded_response = bencode.decode(response)

        return decoded_response


