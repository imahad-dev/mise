"""Seed database from JSON file.

Usage: docker compose exec -T api python scripts/seed.py [--file data/seed/trattoria_da_mario.json]
"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Mise database")
    parser.add_argument(
        "--file",
        default="data/seed/trattoria_da_mario.json",
        help="Path to seed JSON file",
    )
    args = parser.parse_args()
    # M1.2 will implement the actual seeding logic
    print(f"Seed stub — would load from {args.file}")
    print("Actual seeding implemented in M1.2")


if __name__ == "__main__":
    main()
