import { useBusiness } from "../business/BusinessContext";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { Confirm, DateField, DateText, EmptyState, ErrorState, Field, LoadingState, Modal, Money, MoneyInput, PageHeader, StatusBadge } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import type { Account, AccountCategory, Party, Period, Product } from "../types/api";
import { ACCOUNT_TYPE_LABELS } from "../utils/format";

const POSTING_ROLE_LABELS = {
  GENERAL: "عمومی (ثبت دستی)",
  CASH: "نقد و بانک",
  RECEIVABLE: "دریافتنی تجاری",
  REVENUE: "درآمد فروش",
  TAX_LIABILITY: "بدهی مالیات",
  PAYABLE: "پرداختنی تجاری",
  EXPENSE: "هزینه خرید",
  CUSTOMER_CREDIT: "اعتبار مشتری",
} as const;

const POSTING_ROLES_BY_ACCOUNT_TYPE: Record<AccountCategory["account_type"], Array<keyof typeof POSTING_ROLE_LABELS>> = {
  ASSET: ["GENERAL", "CASH", "RECEIVABLE"],
  LIABILITY: ["GENERAL", "TAX_LIABILITY", "PAYABLE", "CUSTOMER_CREDIT"],
  EQUITY: ["GENERAL"],
  REVENUE: ["GENERAL", "REVENUE"],
  EXPENSE: ["GENERAL", "EXPENSE"],
};

export const postingRolesForAccountType = (accountType: AccountCategory["account_type"] | undefined) => accountType ? POSTING_ROLES_BY_ACCOUNT_TYPE[accountType] : [];

function SaveError({ value }: { value: string }) { return value ? <div className="alert alert--error" role="alert">{value}</div> : null; }
function TableShell({ columns, children }: { columns: string[]; children: React.ReactNode }) { const { t } = useBusiness(); return <div className="table-wrap"><table><thead><tr>{columns.map((c) => <th key={c}>{t(c)}</th>)}</tr></thead><tbody>{children}</tbody></table></div>; }

export function PartiesPage() { const { t } = useBusiness(); const { can } = useAuth(); const state = useAsync(() => api.get<Party[]>("/parties"), []); const [open, setOpen] = useState(false); const [editing, setEditing] = useState<Party | null>(null); const [search, setSearch] = useState(""); const items = useMemo(() => (state.data ?? []).filter((p) => p.name.includes(search) || p.phone?.includes(search) || p.email?.toLowerCase().includes(search.toLowerCase())), [state.data, search]);
  const edit = (party?: Party) => { setEditing(party ?? null); setOpen(true); };
  return <><PageHeader title="طرف حساب‌ها" description="مشتریان و تأمین‌کنندگان کسب‌وکار" action={can("parties:write") && <button className="button button--primary" onClick={() => edit()}>طرف حساب جدید</button>}/><div className="toolbar"><label className="search"><span aria-hidden>⌕</span><input aria-label="جست‌وجوی طرف حساب" placeholder="جست‌وجو در نام، تلفن یا ایمیل" value={search} onChange={(e) => setSearch(e.target.value)}/></label><span>{items.length} مورد</span></div>{state.loading ? <LoadingState/> : state.error ? <ErrorState message={state.error} retry={state.reload}/> : items.length ? <TableShell columns={["نام", "نوع همکاری", "تلفن", "ایمیل", "وضعیت", "عملیات"]}>{items.map((p) => <tr key={p.id}><td data-label="نام"><strong>{p.name}</strong><small>{p.address}</small></td><td data-label="نوع همکاری"><div className="badges">{p.is_customer && <span className="badge">{t("مشتری")}</span>}{p.is_supplier && <span className="badge">تأمین‌کننده</span>}</div></td><td data-label="تلفن" dir="ltr">{p.phone ?? "—"}</td><td data-label="ایمیل" dir="ltr">{p.email ?? "—"}</td><td data-label="وضعیت"><StatusBadge value={p.is_active ? "ACTIVE" : "INACTIVE"}/></td><td data-label="عملیات">{can("parties:write") && <button className="text-button" onClick={() => edit(p)}>ویرایش</button>}</td></tr>)}</TableShell> : <EmptyState title="طرف حسابی ثبت نشده است" detail="برای ثبت نخستین مشتری یا تأمین‌کننده از دکمه بالا استفاده کنید."/>}<PartyForm open={open} item={editing} close={() => setOpen(false)} saved={() => { setOpen(false); void state.reload(); }}/></>;
}
function PartyForm({ open, item, close, saved }: { open: boolean; item: Party | null; close: () => void; saved: () => void }) { const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const submit = async (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget); const body = { name: String(f.get("name")), email: String(f.get("email")) || null, phone: String(f.get("phone")) || null, address: String(f.get("address")) || null, is_customer: f.has("customer"), is_supplier: f.has("supplier"), ...(item ? { is_active: f.has("active") } : {}) }; if (!body.is_customer && !body.is_supplier) { setError("حداقل نوع مشتری یا تأمین‌کننده را انتخاب کنید."); return; } setBusy(true); setError(""); try { if (item) await api.patch(`/parties/${item.id}`, body); else await api.post("/parties", body); saved(); } catch (reason) { setError(reason instanceof Error ? reason.message : "ذخیره ناموفق بود."); } finally { setBusy(false); } };
  return <Modal open={open} title={item ? "ویرایش طرف حساب" : "طرف حساب جدید"} onClose={close}><form className="form" onSubmit={submit}><SaveError value={error}/><Field label="نام یا عنوان"><input name="name" defaultValue={item?.name} required/></Field><div className="form-grid"><Field label="تلفن"><input name="phone" dir="ltr" defaultValue={item?.phone ?? ""}/></Field><Field label="ایمیل"><input name="email" type="email" dir="ltr" defaultValue={item?.email ?? ""}/></Field></div><Field label="نشانی"><textarea name="address" defaultValue={item?.address ?? ""}/></Field><fieldset><legend>نوع همکاری</legend><label className="check"><input type="checkbox" name="customer" defaultChecked={item?.is_customer}/> مشتری</label><label className="check"><input type="checkbox" name="supplier" defaultChecked={item?.is_supplier}/> تأمین‌کننده</label>{item && <label className="check"><input type="checkbox" name="active" defaultChecked={item.is_active}/> فعال</label>}</fieldset><div className="form-actions"><button type="button" className="button button--secondary" onClick={close}>انصراف</button><button className="button button--primary" disabled={busy}>{busy ? "در حال ذخیره…" : "ذخیره"}</button></div></form></Modal>;
}

export function ProductsPage() { const { can } = useAuth(); const state = useAsync(() => api.get<Product[]>("/products"), []); const [open, setOpen] = useState(false); const [item, setItem] = useState<Product | null>(null); return <><PageHeader title="کالا و خدمات" description="فهرست اقلام قابل استفاده در فاکتور" action={can("products:write") && <button className="button button--primary" onClick={() => { setItem(null); setOpen(true); }}>کالا یا خدمت جدید</button>}/>{state.loading ? <LoadingState/> : state.error ? <ErrorState message={state.error} retry={state.reload}/> : state.data?.length ? <div className="product-grid">{state.data.map((p) => <article className="product-card" key={p.id}><div><span className="product-code" dir="ltr">{p.sku}</span><StatusBadge value={p.is_active ? "ACTIVE" : "INACTIVE"}/></div><h2>{p.name}</h2><p>{p.description || "بدون توضیح"}</p><footer><Money value={p.unit_price}/><span>هر {p.unit}</span>{can("products:write") && <button className="text-button" onClick={() => { setItem(p); setOpen(true); }}>ویرایش</button>}</footer></article>)}</div> : <EmptyState title="کالا یا خدمتی ثبت نشده است"/>}<ProductForm open={open} item={item} close={() => setOpen(false)} saved={() => { setOpen(false); void state.reload(); }}/></>;
}
function ProductForm({ open, item, close, saved }: { open: boolean; item: Product | null; close: () => void; saved: () => void }) { const { profile } = useBusiness(); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const submit = async (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget); const body = { ...(item ? {} : { sku: String(f.get("sku")) }), name: String(f.get("name")), description: String(f.get("description")) || null, unit: String(f.get("unit")), unit_price: String(f.get("price")), ...(item ? { is_active: f.has("active") } : {}) }; setBusy(true); setError(""); try { if (item) await api.patch(`/products/${item.id}`, body); else await api.post("/products", body); saved(); } catch (reason) { setError(reason instanceof Error ? reason.message : "ذخیره ناموفق بود."); } finally { setBusy(false); } }; return <Modal open={open} title={item ? "ویرایش کالا یا خدمت" : "کالا یا خدمت جدید"} onClose={close}><form className="form" onSubmit={submit}><SaveError value={error}/><div className="form-grid"><Field label="کد کالا"><input name="sku" dir="ltr" defaultValue={item?.sku} disabled={Boolean(item)} required/></Field><Field label="نام"><input name="name" defaultValue={item?.name} required/></Field></div><Field label="توضیحات"><textarea name="description" defaultValue={item?.description ?? ""}/></Field><div className="form-grid"><Field label="واحد"><input name="unit" defaultValue={item?.unit ?? profile.unit} required/></Field><Field label="قیمت واحد (ریال)"><MoneyInput name="price" min="0" defaultValue={item?.unit_price} required/></Field></div>{item && <label className="check"><input name="active" type="checkbox" defaultChecked={item.is_active}/> فعال</label>}<div className="form-actions"><button type="button" className="button button--secondary" onClick={close}>انصراف</button><button className="button button--primary" disabled={busy}>ذخیره</button></div></form></Modal>; }

export function AccountsPage() { const { can } = useAuth(); const state = useAsync(async () => { const [accounts, categories] = await Promise.all([api.get<Account[]>("/accounts"), api.get<AccountCategory[]>("/account-categories")]); return { accounts, categories }; }, []); const [mode, setMode] = useState<"account" | "category" | null>(null); const category = (id: string) => state.data?.categories.find((c) => c.id === id); return <><PageHeader title="حساب‌ها و سرفصل‌ها" description="ساختار درختی حساب‌های دفتر کل" action={can("accounts:write") && <div className="button-group"><button className="button button--secondary" onClick={() => setMode("category")}>سرفصل جدید</button><button className="button button--primary" onClick={() => setMode("account")}>حساب جدید</button></div>}/>{state.loading ? <LoadingState/> : state.error ? <ErrorState message={state.error} retry={state.reload}/> : state.data?.accounts.length ? <TableShell columns={["کد", "نام حساب", "نوع", "حساب والد", "وضعیت"]}>{state.data.accounts.map((a) => <tr key={a.id}><td data-label="کد" dir="ltr"><strong>{a.code}</strong></td><td data-label="نام حساب">{a.parent_id && <span className="tree-mark">└</span>}{a.name}</td><td data-label="نوع">{ACCOUNT_TYPE_LABELS[category(a.category_id)?.account_type ?? ""]}</td><td data-label="حساب والد">{state.data?.accounts.find((p) => p.id === a.parent_id)?.name ?? "—"}</td><td data-label="وضعیت"><StatusBadge value={a.is_active ? "ACTIVE" : "INACTIVE"}/></td></tr>)}</TableShell> : <EmptyState title="حسابی تعریف نشده است"/>}<AccountForm open={mode !== null} mode={mode} data={state.data} close={() => setMode(null)} saved={() => { setMode(null); void state.reload(); }}/></>;
}
function AccountForm({ open, mode, data, close, saved }: { open: boolean; mode: "account" | "category" | null; data: { accounts: Account[]; categories: AccountCategory[] } | null; close: () => void; saved: () => void }) {
  const [error, setError] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [postingRole, setPostingRole] = useState("");
  const [parentId, setParentId] = useState("");
  const selectedType = data?.categories.find((category) => category.id === categoryId)?.account_type;
  const compatibleRoles = postingRolesForAccountType(selectedType);
  const compatibleParents = data?.accounts.filter((account) => account.category_id === categoryId) ?? [];
  useEffect(() => {
    if (open) {
      setError("");
      setCategoryId("");
      setPostingRole("");
      setParentId("");
    }
  }, [open, mode]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      if (mode === "category") {
        await api.post("/account-categories", { name: String(form.get("name")), account_type: String(form.get("type")) });
      } else {
        await api.post("/accounts", {
          code: String(form.get("code")),
          name: String(form.get("name")),
          category_id: categoryId,
          parent_id: parentId || null,
          posting_role: postingRole,
        });
      }
      saved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ذخیره ناموفق بود.");
    }
  };
  return <Modal open={open} title={mode === "category" ? "سرفصل حساب جدید" : "حساب جدید"} onClose={close}><form className="form" onSubmit={submit}><SaveError value={error}/>{mode === "account" && <Field label="کد حساب"><input name="code" dir="ltr" required/></Field>}<Field label="نام"><input name="name" required/></Field>{mode === "category" ? <Field label="نوع حساب"><select name="type" required>{Object.entries(ACCOUNT_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field> : <><Field label="سرفصل"><select value={categoryId} onChange={(event) => { setCategoryId(event.target.value); setPostingRole(""); setParentId(""); }} required><option value="">انتخاب کنید</option>{data?.categories.map((category) => <option key={category.id} value={category.id}>{category.name} · {ACCOUNT_TYPE_LABELS[category.account_type]}</option>)}</select></Field><Field label="نقش ثبت حسابداری"><select value={postingRole} onChange={(event) => setPostingRole(event.target.value)} required disabled={!selectedType}><option value="">انتخاب کنید</option>{compatibleRoles.map((role) => <option key={role} value={role}>{POSTING_ROLE_LABELS[role]}</option>)}</select></Field><Field label="حساب والد (اختیاری)"><select value={parentId} onChange={(event) => setParentId(event.target.value)} disabled={!selectedType}><option value="">بدون والد</option>{compatibleParents.map((account) => <option key={account.id} value={account.id}>{account.code} · {account.name}</option>)}</select></Field></>}<div className="form-actions"><button type="button" className="button button--secondary" onClick={close}>انصراف</button><button className="button button--primary">ذخیره</button></div></form></Modal>;
}

export function PeriodsPage() { const { can } = useAuth(); const state = useAsync(() => api.get<Period[]>("/periods"), []); const [open, setOpen] = useState(false); const [closing, setClosing] = useState<Period | null>(null); const [dates, setDates] = useState({ start: "", end: "" }); const create = async (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget); await api.post("/periods", { name: String(f.get("name")), start_date: dates.start, end_date: dates.end }); setOpen(false); void state.reload(); }; const closePeriod = async () => { if (!closing) return; await api.post(`/periods/${closing.id}/close`); setClosing(null); void state.reload(); };
  return <><PageHeader title="دوره‌های مالی" description="بازه‌های مجاز برای ثبت اسناد حسابداری" action={can("periods:manage") && <button className="button button--primary" onClick={() => setOpen(true)}>دوره جدید</button>}/>{state.loading ? <LoadingState/> : state.error ? <ErrorState message={state.error} retry={state.reload}/> : state.data?.length ? <div className="period-grid">{state.data.map((p) => <CardPeriod key={p.id} p={p} canClose={can("periods:manage") && p.status === "OPEN"} close={() => setClosing(p)}/>)}</div> : <EmptyState title="دوره مالی تعریف نشده است"/>}<Modal open={open} title="دوره مالی جدید" onClose={() => setOpen(false)}><form className="form" onSubmit={create}><Field label="نام دوره"><input name="name" required/></Field><div className="form-grid"><DateField label="تاریخ شروع" value={dates.start} onChange={(start) => setDates((v) => ({ ...v, start }))} required/><DateField label="تاریخ پایان" value={dates.end} onChange={(end) => setDates((v) => ({ ...v, end }))} required/></div><div className="form-actions"><button type="button" className="button button--secondary" onClick={() => setOpen(false)}>انصراف</button><button className="button button--primary">ذخیره</button></div></form></Modal><Confirm open={Boolean(closing)} title="بستن دوره مالی" message={`پس از بستن «${closing?.name ?? ""}» ثبت سند در این بازه ممکن نیست. ادامه می‌دهید؟`} confirmLabel="بستن دوره" onConfirm={() => void closePeriod()} onClose={() => setClosing(null)}/></>;
}
function CardPeriod({ p, canClose, close }: { p: Period; canClose: boolean; close: () => void }) { return <article className="period-card"><div><h2>{p.name}</h2><StatusBadge value={p.status}/></div><dl><div><dt>شروع</dt><dd><DateText value={p.start_date}/></dd></div><div><dt>پایان</dt><dd><DateText value={p.end_date}/></dd></div></dl>{canClose && <button className="button button--secondary" onClick={close}>بستن دوره</button>}</article>; }
