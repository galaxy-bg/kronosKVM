#!/usr/bin/env python3
"""Read-only anonymous FTP for files explicitly published to Recovery."""
import argparse
import logging

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="192.168.34.100")
    parser.add_argument("--port", type=int, default=21)
    parser.add_argument("--directory", default="/mnt/kronoskvm-storage/recovery")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    authorizer = DummyAuthorizer()
    authorizer.add_anonymous(args.directory, perm="elr")
    FTPHandler.authorizer = authorizer
    FTPHandler.banner = "InfraBox Recovery - read-only anonymous FTP"
    FTPHandler.passive_ports = range(30000, 30011)
    server = FTPServer((args.bind, args.port), FTPHandler)
    server.max_cons = 32
    server.max_cons_per_ip = 8
    server.serve_forever()


if __name__ == "__main__":
    main()
