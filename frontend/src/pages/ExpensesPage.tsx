import { useCallback, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  DateField,
  DateText,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Modal,
  Money,
  MoneyInput,
  PageHeader,
} from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { Link } from "../routes/router";
import { api, query } from "../services/api";
import type { Account, Period } from "../types/api";
import { todayIso } from "../utils/date";

interface Expense {
  id: string;
  name: string;
  amount: string;
  payment_date: string;
  method: string;
  tracking_code: string | null;
  journal_id: string;
}
interface ExpenseList {
  items: Expense[];
  total: string;
}
export const expenseMethods: Record<string, string> = {
  CASH: "نقدی",
  CHECK: "چک",
  BANK_TRANSFER: "انتقال بین بانکی",
};

export function ExpensesPage() {
  const { can } = useAuth();
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [range, setRange] = useState({ start: "", end: "" });
  const [open, setOpen] = useState(false);
  const state = useAsync(
    () =>
      api.get<ExpenseList>(
        query("/expenses", { start_date: range.start, end_date: range.end }),
      ),
    [range],
  );
  const invalid = Boolean(start && end && start > end);
  return (
    <>
      <PageHeader
        title="هزینه‌ها"
        description="ثبت هزینه‌های پرداخت‌شده مانند آب و برق، اجاره و خدمات"
        action={
          can("bills:issue") &&
          can("bill_payments:post") && (
            <button
              className="button button--primary"
              onClick={() => setOpen(true)}
            >
              ثبت هزینه جدید
            </button>
          )
        }
      />
      <form
        className="form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!invalid) setRange({ start, end });
        }}
      >
        <div className="form-grid form-grid--3">
          <DateField label="از تاریخ" value={start} onChange={setStart} />
          <DateField label="تا تاریخ" value={end} onChange={setEnd} />
          <button className="button button--secondary" disabled={invalid}>
            نمایش هزینه‌ها
          </button>
        </div>
        {invalid && (
          <p role="alert">تاریخ پایان باید بعد از تاریخ شروع باشد.</p>
        )}
      </form>
      {state.loading ? (
        <LoadingState />
      ) : state.error ? (
        <ErrorState message={state.error} retry={state.reload} />
      ) : (
        <>
          <p className="allocation-total">
            جمع هزینه‌های ثبت‌شده در این بخش در بازه انتخابی:{" "}
            <Money value={state.data?.total ?? "0"} />
          </p>
          {state.data?.items.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>نام هزینه</th>
                    <th>مبلغ</th>
                    <th>تاریخ پرداخت</th>
                    <th>روش پرداخت</th>
                    <th>کد پیگیری</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((expense) => (
                    <tr key={expense.id}>
                      <td>{expense.name}</td>
                      <td>
                        <Money value={expense.amount} />
                      </td>
                      <td>
                        <DateText value={expense.payment_date} />
                      </td>
                      <td>{expenseMethods[expense.method]}</td>
                      <td>{expense.tracking_code || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="در این بازه هزینه‌ای ثبت نشده است" />
          )}
        </>
      )}
      {open && (
        <ExpenseForm
          close={() => setOpen(false)}
          saved={() => {
            setOpen(false);
            void state.reload();
          }}
        />
      )}
    </>
  );
}

function ExpenseForm({
  close,
  saved,
}: {
  close: () => void;
  saved: () => void;
}) {
  const [date, setDate] = useState(todayIso());
  const [checkDueDate, setCheckDueDate] = useState(todayIso());
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("CASH");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestClose = useCallback(() => {
    if (!busy) close();
  }, [busy, close]);
  const setup = useAsync(async () => {
    const [accounts, periods] = await Promise.all([
      api.get<Account[]>("/accounts"),
      api.get<Period[]>("/periods"),
    ]);
    return { accounts, periods };
  }, []);
  const cash =
    setup.data?.accounts.filter(
      (account) => account.is_active && account.posting_role === "CASH",
    ) ?? [];
  const expenses =
    setup.data?.accounts.filter(
      (account) => account.is_active && account.posting_role === "EXPENSE",
    ) ?? [];
  const period = setup.data?.periods.some(
    (p) => p.status === "OPEN" && p.start_date <= date && date <= p.end_date,
  );
  const ready = cash.length > 0 && expenses.length > 0 && period;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !ready) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api.post("/expenses", {
        name: String(form.get("name")),
        amount,
        payment_date: date,
        method,
        check_due_date: method === "CHECK" ? checkDueDate : null,
        tracking_code: String(form.get("tracking_code") || "") || null,
        expense_account_id: String(form.get("expense_account_id")),
        cash_account_id: String(form.get("cash_account_id")),
      });
      saved();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "ثبت هزینه ناموفق بود.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open title="ثبت هزینه جدید" onClose={requestClose}>
      <form className="form" onSubmit={submit}>
        {error && (
          <p className="alert alert--error" role="alert">
            {error}
          </p>
        )}
        <Field label="نام هزینه">
          <input
            name="name"
            required
            maxLength={200}
            placeholder="مثلاً هزینه برق"
          />
        </Field>
        <Field label="مبلغ هزینه (ریال)">
          <MoneyInput
            value={amount}
            onValueChange={setAmount}
            min="0.01"
            required
          />
        </Field>
        <DateField
          label="تاریخ پرداخت"
          value={date}
          onChange={setDate}
          required
        />
        <Field label="روش پرداخت">
          <select
            value={method}
            onChange={(event) => setMethod(event.target.value)}
          >
            {Object.entries(expenseMethods).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        {method === "CHECK" && (
          <DateField
            label="تاریخ سررسید چک"
            value={checkDueDate}
            onChange={setCheckDueDate}
            required
          />
        )}
        <Field label="کد پیگیری (اختیاری)">
          <input name="tracking_code" maxLength={100} />
        </Field>
        {setup.loading ? (
          <LoadingState />
        ) : setup.error ? (
          <ErrorState message={setup.error} retry={setup.reload} />
        ) : (
          <>
            {(!cash.length || !expenses.length) && (
              <p className="alert alert--warning">
                ابتدا حساب فعال هزینه و نقد/بانک ثبت کنید.{" "}
                <Link to="/accounts">مدیریت حساب‌ها</Link>
              </p>
            )}
            {!period && (
              <p className="alert alert--warning">
                برای تاریخ پرداخت یک دوره مالی باز لازم است.{" "}
                <Link to="/periods">دوره‌های مالی</Link>
              </p>
            )}
            <Field label="حساب هزینه">
              <select
                name="expense_account_id"
                required
                defaultValue={expenses.length === 1 ? expenses[0].id : ""}
              >
                <option value="">انتخاب حساب هزینه</option>
                {expenses.map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="حساب پرداخت (نقد/بانک)">
              <select
                name="cash_account_id"
                required
                defaultValue={cash.length === 1 ? cash[0].id : ""}
              >
                <option value="">انتخاب حساب پرداخت</option>
                {cash.map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </Field>
          </>
        )}
        <p className="alert alert--warning">
          ذخیره، هزینه و خروج وجه را بلافاصله قطعی می‌کند و قابل ویرایش نیست.
          این هزینه را دوباره در صورتحساب خرید ثبت نکنید.
          {method === "CHECK" &&
            " پرداخت با چک نیز همین حالا از مانده حساب کسر می‌شود؛ وصول جداگانه ندارد."}
        </p>
        <button className="button button--primary" disabled={busy || !ready}>
          {busy ? "در حال ثبت…" : "ثبت و پرداخت هزینه"}
        </button>
      </form>
    </Modal>
  );
}
