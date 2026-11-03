"""Generate synthetic (source='simulated') demo orders and settled bills for restaurants.

Usage:
    docker compose exec -T api python scripts/simulate.py [--slug angeethi-house ...]
        [--days 56] [--seed 42] [--no-promo]

Without --slug, every demo venue (settings.demo_restaurant_slugs) is simulated, each with its
own profile from restaurant.onboarding["simulation"]. Replaces any previously simulated orders
and bills for those restaurants. Live orders are untouched.
"""

import argparse
import asyncio
import json
from dataclasses import replace

from sqlalchemy import select
from src.config import settings
from src.database import async_session_factory
from src.models.restaurant import Restaurant
from src.services.simulator import SimAssumptions, persist_simulation


async def simulate_slug(slug: str, args: argparse.Namespace) -> dict:
    async with async_session_factory() as session:
        res = await session.execute(select(Restaurant).where(Restaurant.slug == slug))
        restaurant = res.scalar_one_or_none()
        if restaurant is None:
            raise SystemExit(f"Restaurant '{slug}' not found. Run `make seed` first.")
        base = SimAssumptions.from_profile(restaurant.onboarding.get("simulation", {}))
        assumptions = replace(
            base,
            days=args.days,
            seed=args.seed,
            promo_item_rank=None if args.no_promo else base.promo_item_rank,
        )
        summary = await persist_simulation(session, restaurant, assumptions)
        await session.commit()
    return {"slug": slug, **summary}


async def async_main(args: argparse.Namespace) -> None:
    for slug in args.slug or settings.demo_restaurant_slugs:
        print(json.dumps(await simulate_slug(slug, args), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate simulated Mise orders")
    parser.add_argument(
        "--slug", action="append", help="repeatable; default: every demo venue"
    )
    parser.add_argument("--days", type=int, default=56)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-promo", action="store_true", default=False)
    asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    main()
