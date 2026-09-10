from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.db.models import Account, Party
from backend.app.repositories.reporting import ReportingRepository
from backend.app.schemas.reporting import (
    AccountReportLine,
    AccountSummaryReport,
    BalanceSheetReport,
    CashFlowPoint,
    CashFlowReport,
    CustomerCheckHistory,
    CustomerInvoiceHistory,
    CustomerPaymentHistory,
    CustomerPurchaseItem,
    CustomerSummary,
    DashboardReport,
    IncomeStatementReport,
    PartyHistoryReport,
    PartyTransaction,
    PayableExposureReport,
    PayableLine,
    ReceivableLine,
    ReceivablesReport,
    TrialBalanceReport,
)
from backend.app.services.accounting import AccountingError, NotFoundError, money

ZERO = Decimal("0.00")


class ReportingService:
    def __init__(self, session: Session, owner_id: UUID) -> None:
        self.repo = ReportingRepository(session, owner_id)

    @staticmethod
    def _validate_range(start_date: date | None, end_date: date | None) -> None:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise AccountingError("start_date must not exceed end_date")

    @staticmethod
    def _line(
        account: Account, account_type: str, debit: Decimal, credit: Decimal
    ) -> AccountReportLine:
        normal_debit = account_type in {"ASSET", "EXPENSE"}
        balance = debit - credit if normal_debit else credit - debit
        return AccountReportLine(
            account_id=account.id,
            code=account.code,
            name=account.name,
            account_type=account_type,
            debit=money(debit),
            credit=money(credit),
            balance=money(balance),
        )

    def _activity(
        self,
        start_date: date | None,
        end_date: date | None,
        account_types: set[str] | None = None,
    ) -> list[AccountReportLine]:
        self._validate_range(start_date, end_date)
        return [
            self._line(account, account_type, debit, credit)
            for account, account_type, debit, credit in self.repo.account_activity(
                start_date=start_date, end_date=end_date, account_types=account_types
            )
        ]

    def trial_balance(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> TrialBalanceReport:
        lines = self._activity(start_date, end_date)
        total_debit = money(sum((line.debit for line in lines), ZERO))
        total_credit = money(sum((line.credit for line in lines), ZERO))
        return TrialBalanceReport(
            start_date=start_date,
            end_date=end_date,
            lines=lines,
            total_debit=total_debit,
            total_credit=total_credit,
            balanced=total_debit == total_credit,
        )

    def income_statement(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> IncomeStatementReport:
        lines = self._activity(start_date, end_date, {"REVENUE", "EXPENSE"})
        revenue = [line for line in lines if line.account_type == "REVENUE"]
        expenses = [line for line in lines if line.account_type == "EXPENSE"]
        total_revenue = money(sum((line.balance for line in revenue), ZERO))
        total_expenses = money(sum((line.balance for line in expenses), ZERO))
        return IncomeStatementReport(
            start_date=start_date,
            end_date=end_date,
            revenue=revenue,
            expenses=expenses,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            net_income=money(total_revenue - total_expenses),
        )

    def account_summary(
        self,
        account_type: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> AccountSummaryReport:
        lines = self._activity(start_date, end_date, {account_type})
        return AccountSummaryReport(
            start_date=start_date,
            end_date=end_date,
            account_type=account_type,
            lines=lines,
            total=money(sum((line.balance for line in lines), ZERO)),
        )

    def balance_sheet(self, as_of: date) -> BalanceSheetReport:
        lines = self._activity(None, as_of)
        assets = [line for line in lines if line.account_type == "ASSET"]
        liabilities = [line for line in lines if line.account_type == "LIABILITY"]
        equity = [line for line in lines if line.account_type == "EQUITY"]
        revenue = sum((line.balance for line in lines if line.account_type == "REVENUE"), ZERO)
        expenses = sum((line.balance for line in lines if line.account_type == "EXPENSE"), ZERO)
        total_assets = money(sum((line.balance for line in assets), ZERO))
        total_liabilities = money(sum((line.balance for line in liabilities), ZERO))
        total_equity = money(sum((line.balance for line in equity), ZERO))
        current_earnings = money(revenue - expenses)
        right_side = money(total_liabilities + total_equity + current_earnings)
        return BalanceSheetReport(
            as_of=as_of,
            assets=assets,
            liabilities=liabilities,
            equity=equity,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            total_equity=total_equity,
            current_earnings=current_earnings,
            total_liabilities_and_equity=right_side,
            balanced=total_assets == right_side,
        )

    def receivables(self, as_of: date, customer_id: UUID | None = None) -> ReceivablesReport:
        rows = self.repo.receivables_as_of(as_of=as_of, customer_id=customer_id)
        lines: list[ReceivableLine] = []
        for invoice, paid in rows:
            balance = money(invoice.total - paid)
            overdue_days = max((as_of - invoice.due_date).days, 0)
            status = "OVERDUE" if overdue_days else "PARTIALLY_PAID" if paid else "ISSUED"
            lines.append(
                ReceivableLine(
                    invoice_id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    customer_id=invoice.customer_id,
                    customer_name=invoice.customer.name,
                    issue_date=invoice.issue_date,
                    due_date=invoice.due_date,
                    status=status,
                    total=invoice.total,
                    amount_paid=money(paid),
                    balance_due=balance,
                    days_overdue=overdue_days,
                )
            )
        return ReceivablesReport(
            as_of=as_of,
            customer_id=customer_id,
            lines=lines,
            total_outstanding=money(sum((line.balance_due for line in lines), ZERO)),
            total_overdue=money(
                sum((line.balance_due for line in lines if line.days_overdue > 0), ZERO)
            ),
        )

    def payables(self, as_of: date) -> PayableExposureReport:
        lines: list[PayableLine] = []
        for bill, paid in self.repo.payables_as_of(as_of=as_of):
            balance = money(bill.total - paid)
            overdue_days = max((as_of - bill.due_date).days, 0)
            status = "OVERDUE" if overdue_days else "PARTIALLY_PAID" if paid else "ISSUED"
            lines.append(
                PayableLine(
                    bill_id=bill.id,
                    bill_number=bill.bill_number,
                    supplier_id=bill.supplier_id,
                    supplier_name=bill.supplier.name,
                    issue_date=bill.issue_date,
                    due_date=bill.due_date,
                    status=status,
                    total=bill.total,
                    amount_paid=money(paid),
                    balance_due=balance,
                    days_overdue=overdue_days,
                )
            )
        return PayableExposureReport(
            as_of=as_of,
            lines=lines,
            total_payables=money(sum((line.balance_due for line in lines), ZERO)),
        )

    def cash_flow(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> CashFlowReport:
        self._validate_range(start_date, end_date)
        inflows: dict[date, Decimal] = defaultdict(lambda: ZERO)
        outflows: dict[date, Decimal] = defaultdict(lambda: ZERO)
        for receipt in self.repo.posted_payments(start_date, end_date):
            inflows[receipt.payment_date] += receipt.amount
        for disbursement in self.repo.posted_bill_payments(start_date, end_date):
            outflows[disbursement.payment_date] += disbursement.amount
        for expense in self.repo.paid_expenses(start_date, end_date):
            outflows[expense.payment_date] += expense.amount
        points = [
            CashFlowPoint(
                date=value,
                inflow=money(inflows[value]),
                outflow=money(outflows[value]),
                net=money(inflows[value] - outflows[value]),
            )
            for value in sorted(inflows.keys() | outflows.keys())
        ]
        total_inflow = money(sum((point.inflow for point in points), ZERO))
        total_outflow = money(sum((point.outflow for point in points), ZERO))
        return CashFlowReport(
            start_date=start_date,
            end_date=end_date,
            points=points,
            total_inflow=total_inflow,
            total_outflow=total_outflow,
            net_cash_flow=money(total_inflow - total_outflow),
        )

    @staticmethod
    def _balance_direction(net_balance: Decimal) -> str:
        if net_balance > 0:
            return "CUSTOMER_OWES"
        if net_balance < 0:
            return "BUSINESS_OWES"
        return "SETTLED"

    def _customer_summary(self, party: Party) -> CustomerSummary:
        invoices = self.repo.customer_accounting_invoices(party.id)
        posted_payments = [
            payment
            for payment in self.repo.party_payments(party.id, None, None)
            if payment.status == "POSTED"
        ]
        total_purchased = money(sum((invoice.total for invoice in invoices), ZERO))
        total_received = money(sum((payment.amount for payment in posted_payments), ZERO))
        receivable = money(sum((invoice.balance_due for invoice in invoices), ZERO))
        credit = money(self.repo.customer_credit_balance(party.id))
        net = money(receivable - credit)
        return CustomerSummary(
            party_id=party.id,
            name=party.name,
            email=party.email,
            phone=party.phone,
            address=party.address,
            is_active=party.is_active,
            purchase_count=len(invoices),
            total_purchased=total_purchased,
            total_received=total_received,
            receivable_balance=receivable,
            customer_credit_balance=credit,
            net_balance=net,
            balance_direction=self._balance_direction(net),
        )

    def customers(self) -> list[CustomerSummary]:
        totals = self.repo.customer_totals()
        result = []
        for party in self.repo.customers():
            count, purchased, receivable, received, credit = totals.get(
                party.id, (0, ZERO, ZERO, ZERO, ZERO)
            )
            net = money(receivable - credit)
            result.append(CustomerSummary(
                party_id=party.id, name=party.name, email=party.email, phone=party.phone,
                address=party.address, is_active=party.is_active, purchase_count=count,
                total_purchased=money(purchased), total_received=money(received),
                receivable_balance=money(receivable), customer_credit_balance=money(credit),
                net_balance=net, balance_direction=self._balance_direction(net),
            ))
        return result

    def party_history(
        self,
        party_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> PartyHistoryReport:
        self._validate_range(start_date, end_date)
        party = self.repo.party(party_id)
        if party is None or not party.is_customer:
            raise NotFoundError("Customer not found")
        summary = self._customer_summary(party)
        invoices = self.repo.party_invoices(party_id, start_date, end_date)
        payments = self.repo.party_payments(party_id, start_date, end_date)
        transactions = [
            PartyTransaction(
                kind="INVOICE",
                record_id=item.id,
                reference=item.invoice_number,
                date=item.issue_date,
                amount=item.total,
                status=item.status,
            )
            for item in invoices
        ]
        transactions.extend(
            PartyTransaction(
                kind="PAYMENT",
                record_id=item.id,
                reference=item.reference,
                date=item.payment_date,
                amount=item.amount,
                status=item.status,
            )
            for item in payments
        )
        transactions.sort(key=lambda item: (item.date, item.kind, item.reference))
        return PartyHistoryReport(
            party_id=party.id,
            party_name=party.name,
            start_date=start_date,
            end_date=end_date,
            email=party.email,
            phone=party.phone,
            address=party.address,
            purchase_count=summary.purchase_count,
            total_purchased=summary.total_purchased,
            total_received=summary.total_received,
            receivable_balance=summary.receivable_balance,
            customer_credit_balance=summary.customer_credit_balance,
            net_balance=summary.net_balance,
            balance_direction=summary.balance_direction,
            invoices=[
                CustomerInvoiceHistory(
                    invoice_id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    issue_date=invoice.issue_date,
                    due_date=invoice.due_date,
                    status=invoice.status,
                    subtotal=invoice.subtotal,
                    tax=invoice.tax,
                    total=invoice.total,
                    amount_paid=invoice.amount_paid,
                    balance_due=invoice.balance_due,
                    items=[
                        CustomerPurchaseItem(
                            description=item.description,
                            quantity=item.quantity,
                            unit_price=item.unit_price,
                            tax=item.tax,
                            line_total=item.line_total,
                        )
                        for item in invoice.items
                    ],
                    checks=[
                        CustomerCheckHistory(
                            check_id=check.id,
                            amount=check.amount,
                            sayad_id=check.sayad_id,
                            due_date=check.due_date,
                            status=check.status,
                            cleared_date=check.cleared_date,
                        )
                        for check in invoice.checks
                    ],
                )
                for invoice in invoices
            ],
            payments=[
                CustomerPaymentHistory(
                    payment_id=payment.id,
                    reference=payment.reference,
                    payment_date=payment.payment_date,
                    amount=payment.amount,
                    method=payment.method,
                    sayad_id=payment.sayad_id,
                    status=payment.status,
                )
                for payment in payments
            ],
            transactions=transactions,
        )

    def dashboard(
        self,
        *,
        as_of: date,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> DashboardReport:
        income = self.income_statement(start_date, end_date)
        cash = self.cash_flow(start_date, end_date)
        receivables = self.receivables(as_of)
        overdue = [line for line in receivables.lines if line.days_overdue > 0]
        return DashboardReport(
            start_date=start_date,
            end_date=end_date,
            as_of=as_of,
            total_revenue=income.total_revenue,
            total_expenses=income.total_expenses,
            net_income=income.net_income,
            net_cash_flow=cash.net_cash_flow,
            outstanding_invoices=receivables.total_outstanding,
            overdue_invoices=receivables.total_overdue,
            outstanding_invoice_count=len(receivables.lines),
            overdue_invoice_count=len(overdue),
        )
