"""Serve a built GRN Shows repository for local/LAN testing."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent / 'dist')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not (directory / 'addons.xml').is_file():
        parser.error('Build the repository first with build.py --base-url YOUR_URL')
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    with ThreadingHTTPServer((args.bind, args.port), handler) as server:
        print('Serving GRN Shows on %s:%s' % (args.bind, args.port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
