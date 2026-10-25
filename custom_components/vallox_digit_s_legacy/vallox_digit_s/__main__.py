"""Read-only command-line interface."""
import argparse
import json

from .client import Client
from .models import ConnectionState


def main() -> int:
    parser = argparse.ArgumentParser(description="Read a legacy Vallox Digit S controller")
    parser.add_argument("connection", help="Serial device or socket://host:port")
    args = parser.parse_args()
    with Client(args.connection) as unit:
        state = unit.read()
        print(json.dumps(state.to_dict(), indent=2))
        return 0 if state.state == ConnectionState.READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
