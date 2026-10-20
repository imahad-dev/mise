"""Generate synthetic (source='simulated') demo orders for a restaurant.

Usage:
    docker compose exec -T api python scripts/simulate.py [--slug trattoria-da-mario]
        [--days 56] [--seed 42] [--no-promo]

Replaces any previously simulated orders for that restaurant. Live orders are untouched.
"""

import argparse
import asyncio
import json

from sqlalchemy import select
from src.database import async_session_factory
from src.models.restaurant import Restaurant
from src.services.simulator import SimAssumptions, persist_simulation


async def async_main(args: argparse.Namespace) -> None:
    async with async_session_factory() as session:
        res = await session.execute(
            select(Restaurant).where(Restaurant.slug == args.slug)
        )
        restaurant = res.scalar_one_or_none()
        if restaurant is None:
            raise SystemExit(
                f"Restaurant '{args.slug}' not found. Run `make seed` first."
            )
        assumptions = SimAssumptions(
            days=args.days,
            seed=args.seed,
            promo_item_rank=None if args.no_promo else SimAssumptions.promo_item_rank,
        )
        summary = await persist_simulation(session, restaurant, assumptions)
        await session.commit()
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate simulated Mise orders")
    parser.add_argument("--slug", default="trattoria-da-mario")
    parser.add_argument("--days", type=int, default=56)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-promo", action="store_true", default=False)
    asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    main()
