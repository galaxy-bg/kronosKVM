"""Root/service-account CLI; never accepts secrets as command-line arguments."""

import argparse
import os
import secrets
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .config import Settings
from .crypto import digest
from .models import Administrator, now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=["keygen", "admin-create", "admin-disable", "public-key", "cleanup"]
    )
    parser.add_argument("--name", default="lab-admin")
    parser.add_argument("--role", choices=["admin", "viewer"], default="admin")
    args = parser.parse_args()
    cfg = Settings()
    if args.command == "keygen":
        path = Path(cfg.signing_key)
        key = Ed25519PrivateKey.generate()
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        print("Created signing key; back up securely and pin public key on clients.")
    elif args.command == "public-key":
        import base64

        from .crypto import load_signer

        print(
            base64.b64encode(
                load_signer(cfg.signing_key)
                .public_key()
                .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            ).decode()
        )
    else:
        with Session(create_engine(cfg.database_url)) as db:
            if args.command == "admin-create":
                token = secrets.token_urlsafe(48)
                db.add(
                    Administrator(
                        name=args.name,
                        token_hash=digest(token),
                        role=args.role,
                        expires_at=now() + timedelta(days=90),
                    )
                )
                db.commit()
                print(token)
            elif args.command == "admin-disable":
                admin = db.scalar(select(Administrator).where(Administrator.name == args.name))
                if not admin:
                    raise SystemExit("Administrator not found")
                admin.active = False
                db.commit()
            else:
                from sqlalchemy import delete

                from .models import Challenge, DeviceSession

                for model in (Challenge, DeviceSession):
                    db.execute(delete(model).where(model.expires_at < now() - timedelta(days=1)))
                db.commit()


if __name__ == "__main__":
    main()
