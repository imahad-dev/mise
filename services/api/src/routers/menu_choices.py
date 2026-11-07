"""Owner editing of dish choices. Past orders hold their own snapshot, so edits never reach them."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.access import RestaurantAccess, owner_access
from src.database import get_db
from src.models.audit import AuditLog
from src.models.menu import MenuChoice, MenuChoiceGroup, MenuItem
from src.schemas.owner import (
    CreateChoice,
    CreateChoiceGroup,
    OwnerChoice,
    OwnerChoiceGroup,
    PatchChoice,
    PatchChoiceGroup,
    StatusOkResponse,
)
from src.services.choices import check_choice, check_label

router = APIRouter(prefix="/api/restaurants/{slug}", tags=["owner"])

MAX_GROUPS = 8
MAX_CHOICES = 20
ANIMAL = {"milk", "eggs", "fish", "crustaceans", "molluscs"}
SEAFOOD = {"fish", "crustaceans", "molluscs"}


def _refuse(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _audit(db: AsyncSession, access: RestaurantAccess, action: str, target: uuid.UUID) -> None:
    db.add(
        AuditLog(
            restaurant_id=access.restaurant.id,
            event_type="owner_choice_edit",
            actor=f"user:{access.user.id}",
            payload={"action": action, "id": str(target)},
        )
    )


async def _item(db: AsyncSession, access: RestaurantAccess, item_id: uuid.UUID) -> MenuItem:
    item = await db.scalar(
        select(MenuItem)
        .options(selectinload(MenuItem.choice_groups))
        .execution_options(populate_existing=True)
        .where(
            MenuItem.id == item_id,
            MenuItem.restaurant_id == access.restaurant.id,
            MenuItem.deleted_at.is_(None),
        )
    )
    if item is None:
        raise _not_found()
    return item


async def _group(
    db: AsyncSession, access: RestaurantAccess, group_id: uuid.UUID
) -> MenuChoiceGroup:
    group = await db.scalar(
        select(MenuChoiceGroup)
        .join(MenuItem)
        .options(selectinload(MenuChoiceGroup.choices))
        .execution_options(populate_existing=True)
        .where(MenuChoiceGroup.id == group_id, MenuItem.restaurant_id == access.restaurant.id)
    )
    if group is None:
        raise _not_found()
    return group


async def _choice(
    db: AsyncSession, access: RestaurantAccess, choice_id: uuid.UUID
) -> tuple[MenuChoice, MenuChoiceGroup]:
    group_id = await db.scalar(select(MenuChoice.group_id).where(MenuChoice.id == choice_id))
    if group_id is None:
        raise _not_found()
    group = await _group(db, access, group_id)
    return next(c for c in group.choices if c.id == choice_id), group


def _check_defaults(group: MenuChoiceGroup) -> None:
    if sum(c.is_default for c in group.choices) > group.max_select:
        raise _refuse("Too many choices start selected for this group")


def _check_flags(is_vegetarian: bool, is_vegan: bool, allergens: list[str]) -> None:
    if is_vegan and (not is_vegetarian or ANIMAL & set(allergens)):
        raise _refuse("A vegan choice must be vegetarian and carry no animal allergen")
    if is_vegetarian and SEAFOOD & set(allergens):
        raise _refuse("A vegetarian choice can't carry fish or shellfish")


def _settle_leave_out(group: MenuChoiceGroup, c: MenuChoice) -> None:
    """A leave-out adds nothing, so it has nothing to confirm and suits every diet."""
    if group.kind == "leave_out":
        c.allergen_verified = c.is_vegetarian = c.is_vegan = True


def _check_unique(labels: list[str], label: str) -> None:
    if label in labels:
        raise _refuse("That name is already used here")


@router.post(
    "/menu-items/{item_id}/choice-groups",
    response_model=OwnerChoiceGroup,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    item_id: uuid.UUID,
    payload: CreateChoiceGroup,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerChoiceGroup:
    item = await _item(db, access, item_id)
    if item.is_pay_forward:
        raise _refuse("A pay-it-forward dish can't have choices")
    if len(item.choice_groups) >= MAX_GROUPS:
        raise _refuse(f"A dish can have up to {MAX_GROUPS} groups")
    check_label(payload.label)
    _check_unique([g.label for g in item.choice_groups], payload.label)
    group = MenuChoiceGroup(menu_item_id=item.id, **payload.model_dump())
    db.add(group)
    await db.flush()
    _audit(db, access, "create_group", group.id)
    response = OwnerChoiceGroup(id=group.id, choices=[], **payload.model_dump())
    await db.commit()
    return response


@router.patch("/choice-groups/{group_id}", response_model=OwnerChoiceGroup)
async def patch_group(
    group_id: uuid.UUID,
    payload: PatchChoiceGroup,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerChoiceGroup:
    group = await _group(db, access, group_id)
    changes = payload.model_dump(exclude_none=True)
    if "label" in changes:
        check_label(changes["label"])
    for field, value in changes.items():
        setattr(group, field, value)
    if group.min_select > group.max_select:
        raise _refuse("The minimum can't be above the maximum")
    _check_defaults(group)
    _audit(db, access, "patch_group", group.id)
    response = OwnerChoiceGroup.model_validate(group)
    await db.commit()
    return response


@router.delete("/choice-groups/{group_id}", response_model=StatusOkResponse)
async def delete_group(
    group_id: uuid.UUID,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> StatusOkResponse:
    group = await _group(db, access, group_id)
    await db.delete(group)
    _audit(db, access, "delete_group", group_id)
    await db.commit()
    return StatusOkResponse(status="ok")


@router.post(
    "/choice-groups/{group_id}/choices",
    response_model=OwnerChoice,
    status_code=status.HTTP_201_CREATED,
)
async def create_choice(
    group_id: uuid.UUID,
    payload: CreateChoice,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerChoice:
    group = await _group(db, access, group_id)
    if len(group.choices) >= MAX_CHOICES:
        raise _refuse(f"A group can have up to {MAX_CHOICES} choices")
    check_label(payload.label)
    _check_unique([c.label for c in group.choices], payload.label)
    check_choice(
        group.kind,
        price_delta=payload.price_delta,
        cost_delta=payload.cost_delta,
        allergens=payload.allergens,
    )
    _check_flags(payload.is_vegetarian, payload.is_vegan, payload.allergens)
    choice = MenuChoice(**payload.model_dump())
    _settle_leave_out(group, choice)
    group.choices.append(choice)
    _check_defaults(group)
    await db.flush()
    _audit(db, access, "create_choice", choice.id)
    response = OwnerChoice.model_validate(choice)
    await db.commit()
    return response


@router.patch("/choices/{choice_id}", response_model=OwnerChoice)
async def patch_choice(
    choice_id: uuid.UUID,
    payload: PatchChoice,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerChoice:
    choice, group = await _choice(db, access, choice_id)
    changes = payload.model_dump(exclude_none=True)
    if "label" in changes:
        check_label(changes["label"])
    # Same rule as dishes: changed allergens are unconfirmed until someone says otherwise.
    if "allergens" in changes and changes["allergens"] != choice.allergens:
        changes.setdefault("allergen_verified", False)
    for field, value in changes.items():
        setattr(choice, field, value)
    _settle_leave_out(group, choice)
    check_choice(
        group.kind,
        price_delta=choice.price_delta,
        cost_delta=choice.cost_delta,
        allergens=choice.allergens,
    )
    _check_flags(choice.is_vegetarian, choice.is_vegan, choice.allergens)
    _check_defaults(group)
    _audit(db, access, "patch_choice", choice.id)
    response = OwnerChoice.model_validate(choice)
    await db.commit()
    return response


@router.delete("/choices/{choice_id}", response_model=StatusOkResponse)
async def delete_choice(
    choice_id: uuid.UUID,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> StatusOkResponse:
    choice, group = await _choice(db, access, choice_id)
    group.choices.remove(choice)
    _audit(db, access, "delete_choice", choice_id)
    await db.commit()
    return StatusOkResponse(status="ok")
