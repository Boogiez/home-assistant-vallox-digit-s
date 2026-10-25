"""Print temperatures from a transparent RS485 TCP bridge."""

import argparse

from vallox_digit_s import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("connection")
    args = parser.parse_args()
    with Client(args.connection) as unit:
        status = unit.read()
        print(f"Supply: {status.supply_temperature} °C")
        print(f"Extract: {status.extract_temperature} °C")
        print(f"State: {status.state}")


if __name__ == "__main__":
    main()
