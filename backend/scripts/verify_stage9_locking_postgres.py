"""Reproduce Stage 9 period/account locking races on disposable PostgreSQL."""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Event
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from backend.app.db.bootstrap import seed_rbac
from backend.app.db.database import SessionLocal, engine
from backend.app.db.models import (
    Account,
    AccountCategory,
    FinancialPeriod,
    JournalEntry,
    Role,
    User,
)
from backend.app.schemas.accounting import AccountUpdate, JournalCreate
from backend.app.services.accounting import AccountingService, ConflictError
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

EXPECTED_DATABASE = "azari_stage9_locking_test"
WAIT_SECONDS = 10.0


def _set_application_name(session: Session, name: str) -> None:
    session.execute(text("select set_config('application_name', :name, false)"), {"name": name})


def _wait_until_blocked(application_name: str) -> None:
    deadline = monotonic() + WAIT_SECONDS
    statement = text(
        """
        select exists (
            select 1
            from pg_stat_activity
            where datname = current_database()
              and application_name = :application_name
              and wait_event_type = 'Lock'
        )
        """
    )
    while monotonic() < deadline:
        with engine.connect() as connection:
            if connection.scalar(statement, {"application_name": application_name}):
                return
    raise AssertionError(f"{application_name} did not block on the expected row lock")


def _hold_before_commit(session: Session, acquired: Event, release: Event) -> None:
    def hold(_: Session) -> None:
        acquired.set()
        if not release.wait(WAIT_SECONDS):
            raise TimeoutError("Timed out while holding the concurrency-test transaction")

    event.listen(session, "before_commit", hold, once=True)


def _close_period(
    period_id: UUID,
    actor_id: UUID,
    acquired: Event,
    release: Event,
) -> str:
    with SessionLocal() as session:
        actor = session.get_one(User, actor_id)
        _hold_before_commit(session, acquired, release)
        AccountingService(session, actor).close_period(period_id)
    return "CLOSED"


def _post_journal(
    journal_id: UUID,
    actor_id: UUID,
    application_name: str,
    started: Event | None = None,
    acquired: Event | None = None,
    release: Event | None = None,
) -> str:
    with SessionLocal() as session:
        _set_application_name(session, application_name)
        actor = session.get_one(User, actor_id)
        if acquired is not None and release is not None:
            _hold_before_commit(session, acquired, release)
        if started is not None:
            started.set()
        try:
            AccountingService(session, actor).post_journal(journal_id)
        except ConflictError:
            return "REJECTED"
    return "POSTED"


def _mutate_account(
    account_id: UUID,
    actor_id: UUID,
    update: AccountUpdate,
    application_name: str,
    started: Event,
) -> str:
    with SessionLocal() as session:
        _set_application_name(session, application_name)
        actor = session.get_one(User, actor_id)
        started.set()
        try:
            AccountingService(session, actor).update_account(account_id, update)
        except ConflictError:
            return "REJECTED"
    return "UPDATED"


def _result(future: Future[str]) -> str:
    return future.result(timeout=WAIT_SECONDS)


def _journal(
    service: AccountingService,
    *,
    number: str,
    entry_date: date,
    period_id: UUID,
    debit_account_id: UUID,
    credit_account_id: UUID,
) -> JournalEntry:
    return service.create_journal(
        JournalCreate(
            entry_number=number,
            entry_date=entry_date,
            description=f"Concurrency check {number}",
            period_id=period_id,
            lines=[
                {"account_id": debit_account_id, "debit": Decimal("100"), "credit": 0},
                {"account_id": credit_account_id, "debit": 0, "credit": Decimal("100")},
            ],
        )
    )


def _verify_close_vs_post(period_id: UUID, journal_id: UUID, actor_id: UUID) -> None:
    close_holds_lock = Event()
    release_close = Event()
    post_started = Event()
    application_name = "azari_stage9_period_post"
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            close_future = executor.submit(
                _close_period,
                period_id,
                actor_id,
                close_holds_lock,
                release_close,
            )
            assert close_holds_lock.wait(WAIT_SECONDS)
            post_future = executor.submit(
                _post_journal,
                journal_id,
                actor_id,
                application_name,
                post_started,
            )
            assert post_started.wait(WAIT_SECONDS)
            _wait_until_blocked(application_name)
            release_close.set()
            assert _result(close_future) == "CLOSED"
            assert _result(post_future) == "REJECTED"
    finally:
        release_close.set()

    with SessionLocal() as session:
        assert session.get_one(FinancialPeriod, period_id).status == "CLOSED"
        assert session.get_one(JournalEntry, journal_id).status == "DRAFT"


def _verify_account_mutation_vs_first_post(
    *,
    account_id: UUID,
    journal_id: UUID,
    actor_id: UUID,
    update: AccountUpdate,
    expected_category_id: UUID,
    expected_posting_role: str,
    case: Literal["category", "role"],
) -> None:
    post_holds_locks = Event()
    release_post = Event()
    mutation_started = Event()
    application_name = f"azari_stage9_account_{case}"
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            post_future = executor.submit(
                _post_journal,
                journal_id,
                actor_id,
                f"azari_stage9_first_post_{case}",
                None,
                post_holds_locks,
                release_post,
            )
            assert post_holds_locks.wait(WAIT_SECONDS)
            update_future = executor.submit(
                _mutate_account,
                account_id,
                actor_id,
                update,
                application_name,
                mutation_started,
            )
            assert mutation_started.wait(WAIT_SECONDS)
            _wait_until_blocked(application_name)
            release_post.set()
            assert _result(post_future) == "POSTED"
            assert _result(update_future) == "REJECTED"
    finally:
        release_post.set()

    with SessionLocal() as session:
        account = session.get_one(Account, account_id)
        assert account.category_id == expected_category_id
        assert account.posting_role == expected_posting_role
        assert session.get_one(JournalEntry, journal_id).status == "POSTED"


def main() -> None:
    with engine.connect() as connection:
        database = connection.scalar(text("select current_database()"))
        if database != EXPECTED_DATABASE:
            raise RuntimeError(f"Refusing Stage 9 locking verification against {database!r}")

    suffix = uuid4().hex[:8]
    with SessionLocal.begin() as session:
        seed_rbac(session)
    with SessionLocal() as session:
        admin_role = session.scalar(select(Role).where(Role.name == "ADMIN"))
        assert admin_role is not None
        actor = User(
            email=f"stage9-locking-{suffix}@example.com",
            password_hash="unused",
            first_name="Stage",
            last_name="Nine",
            roles=[admin_role],
        )
        session.add(actor)
        session.flush()
        assets = AccountCategory(owner_id=actor.id, name=f"Assets {suffix}", account_type="ASSET")
        expenses = AccountCategory(
            owner_id=actor.id, name=f"Expenses {suffix}", account_type="EXPENSE"
        )
        revenues = AccountCategory(
            owner_id=actor.id, name=f"Revenue {suffix}", account_type="REVENUE"
        )
        session.add_all([actor, assets, expenses, revenues])
        session.flush()
        counterpart = Account(code=f"REV-{suffix}", name="Counterpart", category=revenues)
        period_account = Account(code=f"PER-{suffix}", name="Period race debit", category=assets)
        category_account = Account(
            code=f"CAT-{suffix}", name="Category race debit", category=assets
        )
        role_account = Account(code=f"ROLE-{suffix}", name="Role race debit", category=assets)
        closing_period = FinancialPeriod(
            name=f"Closing race {suffix}",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
        )
        posting_period = FinancialPeriod(
            name=f"Account race {suffix}",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
        )
        for item in (
            counterpart,
            period_account,
            category_account,
            role_account,
            closing_period,
            posting_period,
        ):
            item.owner_id = actor.id
        session.add_all(
            [
                counterpart,
                period_account,
                category_account,
                role_account,
                closing_period,
                posting_period,
            ]
        )
        session.flush()
        service = AccountingService(session, actor)
        period_journal = _journal(
            service,
            number=f"PER-{suffix}",
            entry_date=date(2026, 5, 20),
            period_id=closing_period.id,
            debit_account_id=period_account.id,
            credit_account_id=counterpart.id,
        )
        category_journal = _journal(
            service,
            number=f"CAT-{suffix}",
            entry_date=date(2026, 8, 20),
            period_id=posting_period.id,
            debit_account_id=category_account.id,
            credit_account_id=counterpart.id,
        )
        role_journal = _journal(
            service,
            number=f"ROLE-{suffix}",
            entry_date=date(2026, 8, 21),
            period_id=posting_period.id,
            debit_account_id=role_account.id,
            credit_account_id=counterpart.id,
        )
        actor_id = actor.id
        closing_period_id = closing_period.id
        period_journal_id = period_journal.id
        assets_id = assets.id
        expenses_id = expenses.id
        category_account_id = category_account.id
        category_journal_id = category_journal.id
        role_account_id = role_account.id
        role_journal_id = role_journal.id

    _verify_close_vs_post(closing_period_id, period_journal_id, actor_id)
    _verify_account_mutation_vs_first_post(
        account_id=category_account_id,
        journal_id=category_journal_id,
        actor_id=actor_id,
        update=AccountUpdate(category_id=expenses_id),
        expected_category_id=assets_id,
        expected_posting_role="GENERAL",
        case="category",
    )
    _verify_account_mutation_vs_first_post(
        account_id=role_account_id,
        journal_id=role_journal_id,
        actor_id=actor_id,
        update=AccountUpdate(posting_role="CASH"),
        expected_category_id=assets_id,
        expected_posting_role="GENERAL",
        case="role",
    )

    print(
        "Stage 9 PostgreSQL locking checks passed: "
        "close blocked post; first post blocked category and role mutation"
    )


if __name__ == "__main__":
    main()
