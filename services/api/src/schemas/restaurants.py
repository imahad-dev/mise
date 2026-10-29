"""Restaurants the signed-in user belongs to."""

from typing import Literal

from pydantic import BaseModel


class MyRestaurant(BaseModel):
    slug: str
    name: str
    city: str | None
    currency: str
    role: Literal["owner", "staff"]


class MyRestaurantsResponse(BaseModel):
    restaurants: list[MyRestaurant]
