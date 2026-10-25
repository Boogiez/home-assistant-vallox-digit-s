"""Read every 60 seconds until interrupted."""

import argparse
import asyncio
import json

from vallox_digit_s import AsyncClient


async def poll(connection):
    async with AsyncClient(connection) as unit:
        while True:
            print(json.dumps((await unit.read()).to_dict()))
            await asyncio.sleep(60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("connection")
    args = parser.parse_args()
    asyncio.run(poll(args.connection))


if __name__ == "__main__":
    main()
