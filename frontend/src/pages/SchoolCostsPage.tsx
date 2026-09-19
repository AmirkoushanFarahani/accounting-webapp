import { useState, type FormEvent } from "react";
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
import { api, query } from "../services/api";
import { todayIso } from "../utils/date";

interface SchoolCost {
  id: string;
  factor_number: string;
  vendor_name: string | null;
  reason: string;
  amount: string;
  cost_date: string;
  payment_method: "CASH" | "CHECK" | "BANK_TRANSFER";
  check_due_date: string | null;
  tracking_code: string | null;
  notes: string | null;
}
interface SchoolCostList {
  items: SchoolCost[];
  total: string;
}
const methodLabels: Record<SchoolCost["payment_method"], string> = {
  CASH: "نقدی",
  CHECK: "چک",
  BANK_TRANSFER: "انتقال بین‌بانکی",
};

export function SchoolCostsPage() {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [range, setRange] = useState({ start: "", end: "" });
  const state = useAsync(
    () =>
      api.get<SchoolCostList>(
        query("/school/costs", {
          start_date: range.start,
          end_date: range.end,
        }),
      ),
    [range],
  );
  const invalid = Boolean(start && end && start > end);
  return (
    <>
      <PageHeader
        title="هزینه‌های آموزشگاه"
        description="ثبت فاکتور هزینه مانند اجاره، آب‌وبرق، کتاب، حقوق یا خدمات. این فاکتورها در نمای مالی آموزشگاه محاسبه می‌شوند."
        action={
          <button
            className="button button--primary"
            onClick={() => setOpen(true)}
          >
            ثبت فاکتور هزینه
          </button>
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
            نمایش فاکتورها
          </button>
        </div>
        {invalid && (
          <p className="alert alert--error">
            تاریخ پایان باید بعد از تاریخ شروع باشد.
          </p>
        )}
      </form>
      {state.loading ? (
        <LoadingState />
      ) : state.error ? (
        <ErrorState message={state.error} retry={state.reload} />
      ) : (
        <>
          <p className="allocation-total">
            جمع هزینه‌های ثبت‌شده: <Money value={state.data?.total ?? "0"} />
          </p>
          {state.data?.items.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>شماره فاکتور</th>
                    <th>دلیل هزینه</th>
                    <th>فروشنده / دریافت‌کننده</th>
                    <th>مبلغ</th>
                    <th>تاریخ</th>
                    <th>روش پرداخت</th>
                    <th>سررسید چک</th>
                    <th>کد پیگیری</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((cost) => (
                    <tr key={cost.id}>
                      <td dir="ltr">{cost.factor_number}</td>
                      <td>
                        {cost.reason}
                        <small>{cost.notes ?? ""}</small>
                      </td>
                      <td>{cost.vendor_name ?? "—"}</td>
                      <td>
                        <Money value={cost.amount} />
                      </td>
                      <td>
                        <DateText value={cost.cost_date} />
                      </td>
                      <td>{methodLabels[cost.payment_method]}</td>
                      <td>
                        <DateText value={cost.check_due_date} />
                      </td>
                      <td dir="ltr">{cost.tracking_code ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="فاکتور هزینه‌ای ثبت نشده است" />
          )}
        </>
      )}
      {open && (
        <SchoolCostForm
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

function SchoolCostForm({
  close,
  saved,
}: {
  close: () => void;
  saved: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayIso());
  const [checkDueDate, setCheckDueDate] = useState(todayIso());
  const [method, setMethod] = useState<SchoolCost["payment_method"]>("CASH");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api.post("/school/costs", {
        factor_number: form.get("factor_number"),
        vendor_name: form.get("vendor_name") || null,
        reason: form.get("reason"),
        amount,
        cost_date: date,
        payment_method: method,
        check_due_date: method === "CHECK" ? checkDueDate : null,
        tracking_code: form.get("tracking_code") || null,
        notes: form.get("notes") || null,
      });
      saved();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "ثبت فاکتور هزینه ناموفق بود.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open title="ثبت فاکتور هزینه" onClose={close}>
      <form className="form" onSubmit={submit}>
        {error && <p className="alert alert--error">{error}</p>}
        <Field label="شماره فاکتور">
          <input
            name="factor_number"
            dir="ltr"
            required
            maxLength={100}
            placeholder="COST-001"
          />
        </Field>
        <Field label="دلیل هزینه">
          <input
            name="reason"
            required
            maxLength={300}
            placeholder="مثلاً هزینه برق"
          />
        </Field>
        <Field label="فروشنده / دریافت‌کننده (اختیاری)">
          <input
            name="vendor_name"
            maxLength={200}
            placeholder="مثلاً شرکت برق"
          />
        </Field>
        <Field label="مبلغ (ریال)">
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
            onChange={(event) =>
              setMethod(event.target.value as SchoolCost["payment_method"])
            }
          >
            {Object.entries(methodLabels).map(([value, label]) => (
              <option key={value} value={value}>
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
          <input name="tracking_code" dir="ltr" maxLength={100} />
        </Field>
        <Field label="یادداشت (اختیاری)">
          <textarea name="notes" maxLength={1000} />
        </Field>
        <button className="button button--primary" disabled={busy}>
          {busy ? "در حال ذخیره…" : "ثبت فاکتور هزینه"}
        </button>
      </form>
    </Modal>
  );
}
