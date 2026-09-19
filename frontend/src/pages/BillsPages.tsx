import { useState, type FormEvent } from "react";
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
  StatusBadge,
} from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { Link } from "../routes/router";
import { api } from "../services/api";
import type {
  Account,
  Bill,
  BillItem,
  BillPayment,
  BillPaymentAllocation,
  Party,
  Product,
} from "../types/api";
import { todayIso } from "../utils/date";
import { formatMoney, paymentMethodLabel } from "../utils/format";

const errorText = (reason: unknown) =>
  reason instanceof Error ? reason.message : "عملیات ناموفق بود.";

function PrerequisiteNotice({
  children,
  to,
  linkLabel,
}: {
  children: React.ReactNode;
  to: string;
  linkLabel: string;
}) {
  return (
    <div className="alert alert--warning">
      {children}{" "}
      <Link className="text-button" to={to}>
        {linkLabel}
      </Link>
    </div>
  );
}

function DetailModal({
  title,
  open,
  close,
  children,
}: {
  title: string;
  open: boolean;
  close: () => void;
  children: React.ReactNode;
}) {
  return (
    <Modal open={open} title={title} onClose={close} wide>
      {children}
    </Modal>
  );
}

export function BillsPage() {
  const { can } = useAuth();
  const state = useAsync(async () => {
    const [bills, parties, products, accounts] = await Promise.all([
      api.get<Bill[]>("/bills"),
      api.get<Party[]>("/parties"),
      api.get<Product[]>("/products"),
      api.get<Account[]>("/accounts"),
    ]);
    return { bills, parties, products, accounts };
  }, []);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<Bill | null>(null);
  const [issuing, setIssuing] = useState<Bill | null>(null);

  return (
    <>
      <PageHeader
        title="صورتحساب‌های خرید"
        description="ثبت و پیگیری بدهی به تأمین‌کنندگان"
        action={
          can("bills:write") && (
            <button
              className="button button--primary"
              onClick={() => setCreating(true)}
            >
              صورتحساب خرید جدید
            </button>
          )
        }
      />
      {state.loading ? (
        <LoadingState />
      ) : state.error ? (
        <ErrorState message={state.error} retry={state.reload} />
      ) : state.data?.bills.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>شماره</th>
                <th>تأمین‌کننده</th>
                <th>تاریخ</th>
                <th>سررسید</th>
                <th>مبلغ کل</th>
                <th>مانده</th>
                <th>وضعیت</th>
                <th>عملیات</th>
              </tr>
            </thead>
            <tbody>
              {state.data.bills.map((bill) => (
                <tr key={bill.id}>
                  <td data-label="شماره" dir="ltr">
                    <strong>{bill.bill_number}</strong>
                  </td>
                  <td data-label="تأمین‌کننده">
                    {
                      state.data?.parties.find(
                        (party) => party.id === bill.supplier_id,
                      )?.name
                    }
                  </td>
                  <td data-label="تاریخ">
                    <DateText value={bill.issue_date} />
                  </td>
                  <td data-label="سررسید">
                    <DateText value={bill.due_date} />
                  </td>
                  <td data-label="مبلغ کل">
                    <Money value={bill.total} />
                  </td>
                  <td data-label="مانده">
                    <Money value={bill.balance_due} />
                  </td>
                  <td data-label="وضعیت">
                    <StatusBadge value={bill.status} />
                  </td>
                  <td data-label="عملیات">
                    <button
                      className="text-button"
                      onClick={() => setDetail(bill)}
                    >
                      جزئیات
                    </button>
                    {bill.status === "DRAFT" && can("bills:issue") && (
                      <button
                        className="text-button"
                        onClick={() => setIssuing(bill)}
                      >
                        صدور
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="صورتحساب خریدی ثبت نشده است" />
      )}
      <BillCreate
        open={creating}
        data={state.data}
        close={() => setCreating(false)}
        saved={() => {
          setCreating(false);
          void state.reload();
        }}
      />
      <BillDetail
        item={detail}
        parties={state.data?.parties ?? []}
        close={() => setDetail(null)}
      />
      <BillIssue
        item={issuing}
        accounts={state.data?.accounts ?? []}
        close={() => setIssuing(null)}
        saved={() => {
          setIssuing(null);
          void state.reload();
        }}
      />
    </>
  );
}

function BillCreate({
  open,
  data,
  close,
  saved,
}: {
  open: boolean;
  data: {
    bills: Bill[];
    parties: Party[];
    products: Product[];
    accounts: Account[];
  } | null;
  close: () => void;
  saved: () => void;
}) {
  const activeSuppliers =
    data?.parties.filter((party) => party.is_supplier && party.is_active) ?? [];
  const [issueDate, setIssueDate] = useState(todayIso());
  const [dueDate, setDueDate] = useState(todayIso());
  const [items, setItems] = useState<BillItem[]>([
    {
      product_id: null,
      description: "",
      quantity: "1",
      unit_price: "0",
      tax: "0",
    },
  ]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const update = (index: number, key: keyof BillItem, value: string | null) =>
    setItems((old) =>
      old.map((item, i) => (i === index ? { ...item, [key]: value } : item)),
    );
  const pickProduct = (index: number, id: string) => {
    const product = data?.products.find((item) => item.id === id);
    setItems((old) =>
      old.map((item, i) =>
        i === index
          ? {
              ...item,
              product_id: id || null,
              description: product?.name ?? item.description,
              unit_price: product?.unit_price ?? item.unit_price,
            }
          : item,
      ),
    );
  };
  const preview = items.reduce(
    (sum, item) =>
      sum + Number(item.quantity) * Number(item.unit_price) + Number(item.tax),
    0,
  );
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api.post("/bills", {
        bill_number: String(form.get("number")),
        supplier_id: String(form.get("supplier")),
        issue_date: issueDate,
        due_date: dueDate,
        items: items.map((item) => ({
          product_id: item.product_id || null,
          description: item.description,
          quantity: item.quantity,
          unit_price: item.unit_price || null,
          tax: item.tax,
        })),
      });
      saved();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} title="صورتحساب خرید جدید" onClose={close} wide>
      <form className="form" onSubmit={submit}>
        <p className="form-description">
          اطلاعات خرید و بدهی ایجادشده برای تأمین‌کننده را ثبت کنید.
        </p>
        {error && <div className="alert alert--error">{error}</div>}
        {activeSuppliers.length === 0 && (
          <PrerequisiteNotice to="/parties" linkLabel="ثبت طرف حساب">
            ابتدا باید حداقل یک تأمین‌کننده فعال ثبت کنید.
          </PrerequisiteNotice>
        )}
        <div className="form-grid form-grid--2">
          <Field label="شماره صورتحساب">
            <input name="number" dir="ltr" required disabled={busy} />
          </Field>
          <Field label="تأمین‌کننده">
            <select
              name="supplier"
              required
              disabled={activeSuppliers.length === 0 || busy}
            >
              <option value="">انتخاب تأمین‌کننده</option>
              {activeSuppliers.map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
            </select>
          </Field>
          <DateField
            label="تاریخ صدور"
            value={issueDate}
            onChange={setIssueDate}
            required
          />
          <DateField
            label="تاریخ سررسید"
            value={dueDate}
            onChange={setDueDate}
            required
          />
        </div>
        <h3>اقلام صورتحساب</h3>
        <div className="invoice-items">
          {items.map((item, index) => (
            <div className="invoice-item" key={index}>
              <Field label="کالا/خدمت">
                <select
                  value={item.product_id ?? ""}
                  onChange={(event) => pickProduct(index, event.target.value)}
                  disabled={busy}
                >
                  <option value="">بدون اتصال به کالا</option>
                  {data?.products
                    .filter((product) => product.is_active)
                    .map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="شرح">
                <input
                  value={item.description}
                  onChange={(event) =>
                    update(index, "description", event.target.value)
                  }
                  required
                  disabled={busy}
                />
              </Field>
              <Field label="تعداد">
                <input
                  type="number"
                  dir="ltr"
                  min="0.0001"
                  step="0.0001"
                  value={item.quantity}
                  onChange={(event) =>
                    update(index, "quantity", event.target.value)
                  }
                  required
                  disabled={busy}
                />
              </Field>
              <Field label="قیمت واحد">
                <MoneyInput
                  min="0"
                  value={item.unit_price ?? ""}
                  onValueChange={(value) => update(index, "unit_price", value)}
                  disabled={busy}
                />
              </Field>
              <Field label="مالیات">
                <MoneyInput
                  min="0"
                  value={item.tax}
                  onValueChange={(value) => update(index, "tax", value)}
                  disabled={busy}
                />
              </Field>
              <button
                type="button"
                className="icon-button"
                disabled={items.length === 1 || busy}
                onClick={() =>
                  setItems((old) => old.filter((_, i) => i !== index))
                }
              >
                ×
              </button>
            </div>
          ))}
        </div>
        <div className="preview-total">
          <span>جمع تقریبی برای بررسی</span>
          <Money value={preview} />
          <small>
            مالیات خرید در مبلغ هزینه جذب می‌شود و مبلغ قطعی را سرور محاسبه
            می‌کند.
          </small>
        </div>
        <button
          type="button"
          className="text-button"
          disabled={busy}
          onClick={() =>
            setItems((old) => [
              ...old,
              {
                product_id: null,
                description: "",
                quantity: "1",
                unit_price: "0",
                tax: "0",
              },
            ])
          }
        >
          + افزودن قلم
        </button>
        <div className="form-actions">
          <button
            type="button"
            className="button button--secondary"
            onClick={close}
            disabled={busy}
          >
            انصراف
          </button>
          <button
            className="button button--primary"
            disabled={activeSuppliers.length === 0 || busy}
          >
            {busy ? "در حال ذخیره…" : "ذخیره پیش‌نویس"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function BillDetail({
  item,
  parties,
  close,
}: {
  item: Bill | null;
  parties: Party[];
  close: () => void;
}) {
  return (
    <DetailModal
      open={Boolean(item)}
      title={`صورتحساب ${item?.bill_number ?? ""}`}
      close={close}
    >
      {item && (
        <>
          <p className="form-description">
            جزئیات خرید، مبلغ بدهی و وضعیت پرداخت این صورتحساب را مشاهده کنید.
          </p>
          <div className="detail-summary">
            <span>
              تأمین‌کننده{" "}
              <strong>
                {parties.find((party) => party.id === item.supplier_id)?.name}
              </strong>
            </span>
            <span>
              صدور <DateText value={item.issue_date} />
            </span>
            <span>
              سررسید <DateText value={item.due_date} />
            </span>
            <StatusBadge value={item.status} />
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>شرح</th>
                  <th>تعداد</th>
                  <th>قیمت واحد</th>
                  <th>مالیات</th>
                  <th>جمع</th>
                </tr>
              </thead>
              <tbody>
                {item.items.map((line, index) => (
                  <tr key={line.id ?? index}>
                    <td data-label="شرح">{line.description}</td>
                    <td data-label="تعداد" dir="ltr">
                      {line.quantity}
                    </td>
                    <td data-label="قیمت واحد">
                      <Money value={line.unit_price ?? 0} />
                    </td>
                    <td data-label="مالیات">
                      <Money value={line.tax} />
                    </td>
                    <td data-label="جمع">
                      <Money value={line.line_total ?? 0} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="invoice-totals">
            <div>
              <span>جمع جزء</span>
              <Money value={item.subtotal} />
            </div>
            <div>
              <span>مالیات غیرقابل‌بازیافت</span>
              <Money value={item.tax} />
            </div>
            <div>
              <span>مبلغ کل هزینه</span>
              <Money value={item.total} />
            </div>
            <div>
              <span>پرداخت‌شده</span>
              <Money value={item.amount_paid} />
            </div>
            <div className="total">
              <span>مانده قابل پرداخت</span>
              <Money value={item.balance_due} />
            </div>
          </div>
        </>
      )}
    </DetailModal>
  );
}

function BillIssue({
  item,
  accounts,
  close,
  saved,
}: {
  item: Bill | null;
  accounts: Account[];
  close: () => void;
  saved: () => void;
}) {
  const expenseAccounts = accounts.filter(
    (account) => account.is_active && account.posting_role === "EXPENSE",
  );
  const payableAccounts = accounts.filter(
    (account) => account.is_active && account.posting_role === "PAYABLE",
  );
  const ready = expenseAccounts.length > 0 && payableAccounts.length > 0;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!item || busy) return;
    const form = new FormData(event.currentTarget);
    const expense = String(form.get("expense"));
    const payable = String(form.get("payable"));
    if (expense === payable) {
      setError("حساب خرید و حساب پرداختنی باید متفاوت باشند.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.post(`/bills/${item.id}/issue`, {
        expense_account_id: expense,
        payable_account_id: payable,
      });
      saved();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={Boolean(item)}
      title="صدور نهایی صورتحساب خرید"
      onClose={close}
    >
      <form className="form" onSubmit={submit}>
        <p className="form-description">
          با صدور نهایی، مبلغ خرید در حساب هزینه و بدهی تأمین‌کننده در حساب
          پرداختنی ثبت می‌شود.
        </p>
        {error && <div className="alert alert--error">{error}</div>}
        {!ready && (
          <PrerequisiteNotice to="/accounts" linkLabel="مدیریت حساب‌ها">
            ابتدا حساب‌های فعال با نقش هزینه و پرداختنی ثبت کنید.
          </PrerequisiteNotice>
        )}
        <div className="alert alert--warning">
          صدور نهایی یک سند حسابداری ایجاد می‌کند و صورتحساب پس از آن قابل
          ویرایش نیست.
        </div>
        <Field label="حساب خرید">
          <select name="expense" required disabled={!ready || busy}>
            <option value="">انتخاب کنید</option>
            {expenseAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} · {account.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="حساب پرداختنی">
          <select name="payable" required disabled={!ready || busy}>
            <option value="">انتخاب کنید</option>
            {payableAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} · {account.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-actions">
          <button
            type="button"
            className="button button--secondary"
            onClick={close}
            disabled={busy}
          >
            انصراف
          </button>
          <button className="button button--danger" disabled={!ready || busy}>
            {busy ? "در حال صدور…" : "صدور نهایی"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function BillPaymentsPage() {
  const { can } = useAuth();
  const state = useAsync(async () => {
    const [payments, parties, bills, accounts] = await Promise.all([
      api.get<BillPayment[]>("/bill-payments"),
      api.get<Party[]>("/parties"),
      api.get<Bill[]>("/bills"),
      api.get<Account[]>("/accounts"),
    ]);
    return { payments, parties, bills, accounts };
  }, []);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<BillPayment | null>(null);
  const [posting, setPosting] = useState<BillPayment | null>(null);
  return (
    <>
      <PageHeader
        title="پرداخت به تأمین‌کنندگان"
        description="ثبت پرداخت و تخصیص آن به صورتحساب‌های خرید"
        action={
          can("bill_payments:write") && (
            <button
              className="button button--primary"
              onClick={() => setCreating(true)}
            >
              ثبت پرداخت جدید
            </button>
          )
        }
      />
      {state.loading ? (
        <LoadingState />
      ) : state.error ? (
        <ErrorState message={state.error} retry={state.reload} />
      ) : state.data?.payments.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>مرجع</th>
                <th>تأمین‌کننده</th>
                <th>تاریخ</th>
                <th>روش</th>
                <th>مبلغ</th>
                <th>وضعیت</th>
                <th>عملیات</th>
              </tr>
            </thead>
            <tbody>
              {state.data.payments.map((payment) => (
                <tr key={payment.id}>
                  <td data-label="مرجع" dir="ltr">
                    <strong>{payment.reference}</strong>
                  </td>
                  <td data-label="تأمین‌کننده">
                    {
                      state.data?.parties.find(
                        (party) => party.id === payment.party_id,
                      )?.name
                    }
                  </td>
                  <td data-label="تاریخ">
                    <DateText value={payment.payment_date} />
                  </td>
                  <td data-label="روش">{paymentMethodLabel(payment.method)}</td>
                  <td data-label="مبلغ">
                    <Money value={payment.amount} />
                  </td>
                  <td data-label="وضعیت">
                    <StatusBadge value={payment.status} />
                  </td>
                  <td data-label="عملیات">
                    <button
                      className="text-button"
                      onClick={() => setDetail(payment)}
                    >
                      جزئیات
                    </button>
                    {payment.status === "DRAFT" &&
                      can("bill_payments:post") && (
                        <button
                          className="text-button"
                          onClick={() => setPosting(payment)}
                        >
                          ثبت نهایی
                        </button>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="پرداختی به تأمین‌کننده ثبت نشده است" />
      )}
      <BillPaymentCreate
        open={creating}
        data={state.data}
        close={() => setCreating(false)}
        saved={() => {
          setCreating(false);
          void state.reload();
        }}
      />
      <BillPaymentDetail
        item={detail}
        bills={state.data?.bills ?? []}
        close={() => setDetail(null)}
      />
      <BillPaymentPost
        item={posting}
        accounts={state.data?.accounts ?? []}
        close={() => setPosting(null)}
        saved={() => {
          setPosting(null);
          void state.reload();
        }}
      />
    </>
  );
}

function BillPaymentCreate({
  open,
  data,
  close,
  saved,
}: {
  open: boolean;
  data: {
    payments: BillPayment[];
    parties: Party[];
    bills: Bill[];
    accounts: Account[];
  } | null;
  close: () => void;
  saved: () => void;
}) {
  const activeSuppliers =
    data?.parties.filter((party) => party.is_supplier && party.is_active) ?? [];
  const openBills =
    data?.bills.filter((bill) =>
      ["ISSUED", "PARTIALLY_PAID"].includes(bill.status),
    ) ?? [];
  const [party, setParty] = useState("");
  const [paymentDate, setPaymentDate] = useState(todayIso());
  const [checkDueDate, setCheckDueDate] = useState(todayIso());
  const [method, setMethod] = useState("انتقال بانکی");
  const [allocations, setAllocations] = useState<BillPaymentAllocation[]>([
    { bill_id: "", amount: "0" },
  ]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const eligible = openBills.filter((bill) => bill.supplier_id === party);
  const prerequisitesReady =
    activeSuppliers.length > 0 && party !== "" && eligible.length > 0;
  const total = allocations.reduce(
    (sum, allocation) => sum + Number(allocation.amount),
    0,
  );
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    if (Math.abs(total - Number(form.get("amount"))) > 0.001) {
      setError("جمع تخصیص‌ها باید دقیقاً با مبلغ پرداخت برابر باشد.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.post("/bill-payments", {
        party_id: party,
        payment_date: paymentDate,
        amount: String(form.get("amount")),
        reference: String(form.get("reference")),
        method,
        sayad_id: method === "چک" ? String(form.get("sayadId")) || null : null,
        check_due_date: method === "چک" ? checkDueDate : null,
        allocations,
      });
      saved();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open={open} title="ثبت پرداخت به تأمین‌کننده" onClose={close} wide>
      <form className="form" onSubmit={submit}>
        <p className="form-description">
          پرداخت تأمین‌کننده را ثبت و مبلغ آن را به صورتحساب‌های خرید تخصیص
          دهید.
        </p>
        {error && <div className="alert alert--error">{error}</div>}
        {activeSuppliers.length === 0 && (
          <PrerequisiteNotice to="/parties" linkLabel="ثبت طرف حساب">
            ابتدا باید حداقل یک تأمین‌کننده فعال ثبت کنید.
          </PrerequisiteNotice>
        )}
        {activeSuppliers.length > 0 && openBills.length === 0 && (
          <PrerequisiteNotice to="/bills" linkLabel="مدیریت صورتحساب‌ها">
            ابتدا باید حداقل یک صورتحساب خرید صادرشده با مانده قابل پرداخت داشته
            باشید.
          </PrerequisiteNotice>
        )}
        {party !== "" && openBills.length > 0 && eligible.length === 0 && (
          <PrerequisiteNotice to="/bills" linkLabel="مشاهده صورتحساب‌ها">
            برای این تأمین‌کننده صورتحساب صادرشده با مانده قابل پرداخت وجود
            ندارد.
          </PrerequisiteNotice>
        )}
        <div className="form-grid form-grid--3">
          <Field label="تأمین‌کننده">
            <select
              value={party}
              onChange={(event) => {
                setParty(event.target.value);
                setAllocations([{ bill_id: "", amount: "0" }]);
              }}
              required
              disabled={activeSuppliers.length === 0 || busy}
            >
              <option value="">انتخاب تأمین‌کننده</option>
              {activeSuppliers.map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
            </select>
          </Field>
          <DateField
            label="تاریخ پرداخت"
            value={paymentDate}
            onChange={setPaymentDate}
            required
          />
          <Field label="مبلغ پرداخت (ریال)">
            <MoneyInput name="amount" min="0.01" required disabled={busy} />
          </Field>
          <Field label="شماره مرجع">
            <input name="reference" dir="ltr" required disabled={busy} />
          </Field>
          <Field label="روش پرداخت">
            <select
              value={method}
              onChange={(event) => setMethod(event.target.value)}
              disabled={busy}
            >
              <option>انتقال بانکی</option>
              <option>کارت‌خوان</option>
              <option>نقدی</option>
              <option>چک</option>
            </select>
          </Field>
          {method === "چک" && (
            <>
              <Field label="شناسه صیادی (اختیاری)">
                <input
                  name="sayadId"
                  dir="ltr"
                  maxLength={100}
                  disabled={busy}
                />
              </Field>
              <DateField
                label="تاریخ سررسید چک"
                value={checkDueDate}
                onChange={setCheckDueDate}
                required
              />
            </>
          )}
        </div>
        <h3>تخصیص به صورتحساب‌ها</h3>
        {allocations.map((allocation, index) => (
          <div className="allocation-row" key={index}>
            <Field label="صورتحساب">
              <select
                value={allocation.bill_id}
                onChange={(event) =>
                  setAllocations((old) =>
                    old.map((item, i) =>
                      i === index
                        ? { ...item, bill_id: event.target.value }
                        : item,
                    ),
                  )
                }
                required
                disabled={party === "" || eligible.length === 0 || busy}
              >
                <option value="">انتخاب صورتحساب</option>
                {eligible.map((bill) => (
                  <option key={bill.id} value={bill.id}>
                    {bill.bill_number} · مانده {formatMoney(bill.balance_due)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="مبلغ تخصیص">
              <MoneyInput
                min="0.01"
                value={allocation.amount}
                onValueChange={(value) =>
                  setAllocations((old) =>
                    old.map((item, i) =>
                      i === index ? { ...item, amount: value } : item,
                    ),
                  )
                }
                required
                disabled={busy}
              />
            </Field>
            <button
              type="button"
              className="icon-button"
              disabled={allocations.length === 1 || busy}
              onClick={() =>
                setAllocations((old) => old.filter((_, i) => i !== index))
              }
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          className="text-button"
          disabled={busy}
          onClick={() =>
            setAllocations((old) => [...old, { bill_id: "", amount: "0" }])
          }
        >
          + افزودن تخصیص
        </button>
        <p className="allocation-total">
          جمع تخصیص: <Money value={total} />
        </p>
        <div className="form-actions">
          <button
            type="button"
            className="button button--secondary"
            onClick={close}
            disabled={busy}
          >
            انصراف
          </button>
          <button
            className="button button--primary"
            disabled={!prerequisitesReady || busy}
          >
            {busy ? "در حال ذخیره…" : "ذخیره پیش‌نویس"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function BillPaymentDetail({
  item,
  bills,
  close,
}: {
  item: BillPayment | null;
  bills: Bill[];
  close: () => void;
}) {
  return (
    <DetailModal
      open={Boolean(item)}
      title={`پرداخت ${item?.reference ?? ""}`}
      close={close}
    >
      {item && (
        <>
          <p className="form-description">
            جزئیات پرداخت و نحوه تخصیص آن به صورتحساب‌های تأمین‌کننده را مشاهده
            کنید.
          </p>
          <div className="detail-summary">
            <span>
              تاریخ <DateText value={item.payment_date} />
            </span>
            <span>
              روش <strong>{paymentMethodLabel(item.method)}</strong>
            </span>
            {item.sayad_id && (
              <span>
                شناسه صیادی <strong dir="ltr">{item.sayad_id}</strong>
              </span>
            )}
            <span>
              مبلغ <Money value={item.amount} />
            </span>
            <StatusBadge value={item.status} />
          </div>
          <h3>تخصیص‌ها</h3>
          <div className="compact-list">
            {item.allocations.map((allocation, index) => (
              <div key={allocation.id ?? index}>
                <span>
                  صورتحساب{" "}
                  {bills.find((bill) => bill.id === allocation.bill_id)
                    ?.bill_number ?? allocation.bill_id}
                </span>
                <Money value={allocation.amount} />
              </div>
            ))}
          </div>
        </>
      )}
    </DetailModal>
  );
}

function BillPaymentPost({
  item,
  accounts,
  close,
  saved,
}: {
  item: BillPayment | null;
  accounts: Account[];
  close: () => void;
  saved: () => void;
}) {
  const cashAccounts = accounts.filter(
    (account) => account.is_active && account.posting_role === "CASH",
  );
  const payableAccounts = accounts.filter(
    (account) => account.is_active && account.posting_role === "PAYABLE",
  );
  const ready = cashAccounts.length > 0 && payableAccounts.length > 0;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!item || busy) return;
    const form = new FormData(event.currentTarget);
    const cash = String(form.get("cash"));
    const payable = String(form.get("payable"));
    if (cash === payable) {
      setError("حساب نقد/بانک و حساب پرداختنی باید متفاوت باشند.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.post(`/bill-payments/${item.id}/post`, {
        cash_account_id: cash,
        payable_account_id: payable,
      });
      saved();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={Boolean(item)}
      title="ثبت نهایی پرداخت تأمین‌کننده"
      onClose={close}
    >
      <form className="form" onSubmit={submit}>
        <p className="form-description">
          با ثبت نهایی، بدهی تأمین‌کننده کاهش و خروج وجه از حساب نقد/بانک ثبت
          می‌شود.
        </p>
        {error && <div className="alert alert--error">{error}</div>}
        {!ready && (
          <PrerequisiteNotice to="/accounts" linkLabel="مدیریت حساب‌ها">
            ابتدا حساب‌های فعال با نقش نقد/بانک و پرداختنی ثبت کنید.
          </PrerequisiteNotice>
        )}
        <div className="alert alert--warning">
          ثبت نهایی پرداخت یک سند حسابداری ایجاد می‌کند و قابل بازگشت به
          پیش‌نویس نیست.
        </div>
        <Field label="حساب نقد/بانک">
          <select name="cash" required disabled={!ready || busy}>
            <option value="">انتخاب کنید</option>
            {cashAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} · {account.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="حساب پرداختنی">
          <select name="payable" required disabled={!ready || busy}>
            <option value="">انتخاب کنید</option>
            {payableAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} · {account.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-actions">
          <button
            type="button"
            className="button button--secondary"
            onClick={close}
            disabled={busy}
          >
            انصراف
          </button>
          <button className="button button--danger" disabled={!ready || busy}>
            {busy ? "در حال ثبت…" : "ثبت نهایی"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
