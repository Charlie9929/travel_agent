from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Query
from sqlalchemy import delete, select

from app.api.dependencies import CurrentUser, DbSession, require_trip_member
from app.core.errors import AppError, NotFoundError
from app.db.models import Expense, ExpenseSplit, TripMember, User
from app.schemas.collaboration import (
    ExpenseCreate,
    ExpenseRead,
    ExpenseSettlementRequest,
    ExpenseSplitInput,
    ExpenseSplitRead,
    ExpenseUpdate,
    SettlementTransfer,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/trips/{trip_id}/expenses", tags=["expenses"])
CENT = Decimal("0.01")


async def _member_users(session: DbSession, trip_id: int) -> dict[int, User]:
    rows = (
        await session.execute(
            select(User)
            .join(TripMember, TripMember.user_id == User.id)
            .where(TripMember.trip_id == trip_id)
        )
    ).scalars()
    return {user.id: user for user in rows.all()}


def _equal_splits(
    amount: Decimal, participant_ids: list[int]
) -> list[tuple[int, Decimal, Decimal]]:
    ids = list(dict.fromkeys(participant_ids))
    if not ids:
        raise AppError("INVALID_EXPENSE_SPLIT", "至少需要一名分摊成员", status_code=422)
    count = len(ids)
    base = (amount / count).quantize(CENT, rounding=ROUND_HALF_UP)
    values = [base] * count
    difference = amount - sum(values, Decimal("0"))
    values[-1] += difference
    ratio = (Decimal("1") / count).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    ratios = [ratio] * count
    ratios[-1] += Decimal("1") - sum(ratios, Decimal("0"))
    return list(zip(ids, ratios, values, strict=True))


def _ratio_splits(
    amount: Decimal, splits: list[ExpenseSplitInput]
) -> list[tuple[int, Decimal, Decimal]]:
    if len({item.user_id for item in splits}) != len(splits):
        raise AppError("INVALID_EXPENSE_SPLIT", "分摊成员不能重复", status_code=422)
    if all(item.ratio is not None for item in splits):
        ratio_total = sum((item.ratio or Decimal("0")) for item in splits)
        if abs(ratio_total - Decimal("1")) > Decimal("0.0001"):
            raise AppError("INVALID_EXPENSE_SPLIT", "分摊比例之和必须为 1", status_code=422)
        amounts = [
            (amount * (item.ratio or Decimal("0"))).quantize(CENT, rounding=ROUND_HALF_UP)
            for item in splits
        ]
        amounts[-1] += amount - sum(amounts, Decimal("0"))
        return [
            (item.user_id, item.ratio or Decimal("0"), value)
            for item, value in zip(splits, amounts, strict=True)
        ]
    if all(item.should_pay is not None for item in splits):
        total = sum((item.should_pay or Decimal("0")) for item in splits)
        if abs(total - amount) > CENT:
            raise AppError("INVALID_EXPENSE_SPLIT", "分摊金额之和必须等于账单金额", status_code=422)
        return [
            (
                item.user_id,
                ((item.should_pay or Decimal("0")) / amount).quantize(Decimal("0.0001")),
                (item.should_pay or Decimal("0")).quantize(CENT),
            )
            for item in splits
        ]
    raise AppError(
        "INVALID_EXPENSE_SPLIT",
        "ratio 分摊必须全部填写比例，或全部填写应付金额",
        status_code=422,
    )


async def _replace_splits(
    session: DbSession,
    *,
    expense: Expense,
    member_users: dict[int, User],
    split_type: str,
    participant_ids: list[int],
    splits: list[ExpenseSplitInput],
) -> None:
    calculated = (
        _equal_splits(expense.amount, participant_ids)
        if split_type == "equal"
        else _ratio_splits(expense.amount, splits)
    )
    invalid_ids = {user_id for user_id, _, _ in calculated} - set(member_users)
    if invalid_ids:
        raise AppError(
            "INVALID_EXPENSE_MEMBER",
            "分摊人必须是行程成员",
            status_code=422,
            detail={"user_ids": sorted(invalid_ids)},
        )
    if expense.id is not None:
        await session.execute(delete(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id))
    for user_id, ratio, should_pay in calculated:
        session.add(
            ExpenseSplit(
                expense_id=expense.id,
                user_id=user_id,
                ratio=ratio,
                should_pay=should_pay,
            )
        )


async def _expense_read(
    session: DbSession, expense: Expense, users: dict[int, User] | None = None
) -> ExpenseRead:
    users = users or await _member_users(session, expense.trip_id)
    payer = users.get(expense.payer_id) or await session.get(User, expense.payer_id)
    splits = list(
        (
            await session.scalars(
                select(ExpenseSplit)
                .where(ExpenseSplit.expense_id == expense.id)
                .order_by(ExpenseSplit.id)
            )
        ).all()
    )
    return ExpenseRead(
        id=expense.id,
        trip_id=expense.trip_id,
        activity_id=expense.activity_id,
        payer_id=expense.payer_id,
        payer_nickname=payer.nickname if payer else f"用户 {expense.payer_id}",
        title=expense.title,
        amount=expense.amount,
        split_type=expense.split_type,
        is_settled=expense.is_settled,
        settled_at=expense.settled_at,
        settled_by=expense.settled_by,
        splits=[
            ExpenseSplitRead(
                user_id=item.user_id,
                nickname=(
                    users[item.user_id].nickname
                    if item.user_id in users
                    else f"用户 {item.user_id}"
                ),
                ratio=item.ratio,
                should_pay=item.should_pay,
            )
            for item in splits
        ],
        created_at=expense.created_at,
        updated_at=expense.updated_at,
    )


@router.get("", response_model=ApiResponse[list[ExpenseRead]])
async def list_expenses(
    trip_id: int,
    session: DbSession,
    current_user: CurrentUser,
    settled: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ApiResponse[list[ExpenseRead]]:
    await require_trip_member(session, trip_id, current_user.id)
    statement = (
        select(Expense)
        .where(Expense.trip_id == trip_id)
        .order_by(Expense.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if settled is not None:
        statement = statement.where(Expense.is_settled == settled)
    expenses = list((await session.scalars(statement)).all())
    users = await _member_users(session, trip_id)
    return ApiResponse(data=[await _expense_read(session, item, users) for item in expenses])


@router.post("", response_model=ApiResponse[ExpenseRead], status_code=201)
async def create_expense(
    trip_id: int,
    payload: ExpenseCreate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[ExpenseRead]:
    await require_trip_member(session, trip_id, current_user.id)
    users = await _member_users(session, trip_id)
    if payload.payer_id not in users:
        raise AppError("INVALID_EXPENSE_MEMBER", "付款人必须是行程成员", status_code=422)
    expense = Expense(
        trip_id=trip_id,
        activity_id=payload.activity_id,
        payer_id=payload.payer_id,
        title=payload.title,
        amount=payload.amount,
        split_type=payload.split_type,
    )
    session.add(expense)
    await session.flush()
    await _replace_splits(
        session,
        expense=expense,
        member_users=users,
        split_type=payload.split_type,
        participant_ids=payload.participant_ids,
        splits=payload.splits,
    )
    await session.commit()
    await session.refresh(expense)
    return ApiResponse(data=await _expense_read(session, expense, users))


@router.put("/{expense_id:int}", response_model=ApiResponse[ExpenseRead])
async def update_expense(
    trip_id: int,
    expense_id: int,
    payload: ExpenseUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[ExpenseRead]:
    await require_trip_member(session, trip_id, current_user.id)
    expense = await session.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.trip_id == trip_id)
    )
    if expense is None:
        raise NotFoundError("账单不存在")
    users = await _member_users(session, trip_id)
    if payload.payer_id is not None and payload.payer_id not in users:
        raise AppError("INVALID_EXPENSE_MEMBER", "付款人必须是行程成员", status_code=422)
    for field in ("title", "amount", "payer_id", "activity_id", "split_type"):
        if field in payload.model_fields_set:
            setattr(expense, field, getattr(payload, field))
    needs_rebuild = bool(
        {"amount", "split_type", "participant_ids", "splits"} & payload.model_fields_set
    )
    if needs_rebuild:
        existing = list(
            (
                await session.scalars(
                    select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
                )
            ).all()
        )
        split_type = expense.split_type
        if split_type == "equal":
            participant_ids = payload.participant_ids or [item.user_id for item in existing]
            split_inputs: list[ExpenseSplitInput] = []
        else:
            participant_ids = []
            split_inputs = payload.splits or [
                ExpenseSplitInput(user_id=item.user_id, ratio=item.ratio) for item in existing
            ]
        await _replace_splits(
            session,
            expense=expense,
            member_users=users,
            split_type=split_type,
            participant_ids=participant_ids,
            splits=split_inputs,
        )
    await session.commit()
    await session.refresh(expense)
    return ApiResponse(data=await _expense_read(session, expense, users))


@router.delete("/{expense_id:int}", response_model=ApiResponse[dict[str, bool]])
async def delete_expense(
    trip_id: int, expense_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[dict[str, bool]]:
    await require_trip_member(session, trip_id, current_user.id)
    expense = await session.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.trip_id == trip_id)
    )
    if expense is None:
        raise NotFoundError("账单不存在")
    await session.delete(expense)
    await session.commit()
    return ApiResponse(data={"deleted": True})


@router.get("/settlement", response_model=ApiResponse[list[SettlementTransfer]])
async def calculate_settlement(
    trip_id: int, session: DbSession, current_user: CurrentUser
) -> ApiResponse[list[SettlementTransfer]]:
    await require_trip_member(session, trip_id, current_user.id)
    expenses = list(
        (
            await session.scalars(
                select(Expense).where(Expense.trip_id == trip_id, Expense.is_settled.is_(False))
            )
        ).all()
    )
    users = await _member_users(session, trip_id)
    balances = {user_id: Decimal("0") for user_id in users}
    for expense in expenses:
        balances.setdefault(expense.payer_id, Decimal("0"))
        balances[expense.payer_id] += expense.amount
        splits = list(
            (
                await session.scalars(
                    select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
                )
            ).all()
        )
        for split in splits:
            balances.setdefault(split.user_id, Decimal("0"))
            balances[split.user_id] -= split.should_pay
    debtors = [[uid, -value] for uid, value in balances.items() if value < -CENT / 2]
    creditors = [[uid, value] for uid, value in balances.items() if value > CENT / 2]
    transfers: list[SettlementTransfer] = []
    debtor_index = creditor_index = 0
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        debtor_id, debt = debtors[debtor_index]
        creditor_id, credit = creditors[creditor_index]
        amount = min(debt, credit).quantize(CENT)
        transfers.append(
            SettlementTransfer(
                from_user_id=debtor_id,
                from_nickname=users[debtor_id].nickname,
                to_user_id=creditor_id,
                to_nickname=users[creditor_id].nickname,
                amount=amount,
            )
        )
        debtors[debtor_index][1] -= amount
        creditors[creditor_index][1] -= amount
        if debtors[debtor_index][1] <= CENT / 2:
            debtor_index += 1
        if creditors[creditor_index][1] <= CENT / 2:
            creditor_index += 1
    return ApiResponse(data=transfers)


@router.post("/settle", response_model=ApiResponse[dict[str, object]])
async def mark_expenses_settled(
    trip_id: int,
    payload: ExpenseSettlementRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[dict[str, object]]:
    await require_trip_member(session, trip_id, current_user.id)
    statement = select(Expense).where(Expense.trip_id == trip_id)
    if payload.expense_ids:
        statement = statement.where(Expense.id.in_(payload.expense_ids))
    expenses = list((await session.scalars(statement)).all())
    if payload.expense_ids and len(expenses) != len(set(payload.expense_ids)):
        raise NotFoundError("部分账单不存在")
    now = datetime.now(UTC)
    for expense in expenses:
        expense.is_settled = payload.settled
        expense.settled_at = now if payload.settled else None
        expense.settled_by = current_user.id if payload.settled else None
    await session.commit()
    return ApiResponse(data={"updated": len(expenses), "settled": payload.settled})
