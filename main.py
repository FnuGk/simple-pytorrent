from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import sys

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
    torrent.serve_forever()

if __name__ == "__main__":
    main(sys.argv)
