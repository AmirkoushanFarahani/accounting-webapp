import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { Card, Confirm, DateText, EmptyState, ErrorState, LoadingState, Modal, PageHeader, StatusBadge } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, ApiError } from "../services/api";
import { usePreferences } from "../theme/ThemeContext";
import type { User } from "../types/api";
import { businessProfiles, useBusiness, type BusinessCategory } from "../business/BusinessContext";

const roleLabels: Record<string, string> = { ADMIN: "مدیر سامانه", OWNER: "مالک فضای کاری", ACCOUNTANT: "حسابدار", MANAGER: "مدیر", VIEWER: "مشاهده‌گر" };
const canonicalRoles = ["ADMIN", "OWNER", "ACCOUNTANT", "MANAGER", "VIEWER"];
type PendingChange = { kind: "roles"; user: User; roles: string[] } | { kind: "status"; user: User; isActive: boolean };
const managementError = (reason: unknown) => reason instanceof ApiError && reason.status === 409 ? "این تغییر امکان‌پذیر نیست؛ سامانه باید همیشه حداقل یک مدیر فعال داشته باشد و مدیر نمی‌تواند حساب خودش را غیرفعال کند." : reason instanceof Error ? reason.message : "تغییر کاربر ناموفق بود.";

export function UsersPage() {
  const { can } = useAuth();
  const state = useAsync(() => api.get<User[]>("/users"), []);
  const [detail, setDetail] = useState<User | null>(null);
  const [editing, setEditing] = useState<User | null>(null);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const editRoles = (user: User) => { setEditing(user); setSelectedRoles(user.roles); setError(""); };
  const applyChange = async () => {
    if (!pending || busy) return;
    setBusy(true); setError("");
    try {
      if (pending.kind === "roles") await api.patch(`/users/${pending.user.id}/roles`, { roles: pending.roles });
      else await api.patch(`/users/${pending.user.id}/status`, { is_active: pending.isActive });
      setPending(null); await state.reload();
    } catch (reason) { setError(managementError(reason)); setPending(null); }
    finally { setBusy(false); }
  };
  return <>
    <PageHeader title="کاربران" description="فهرست کاربران، نقش‌ها و وضعیت دسترسی"/>
    {error && <div className="alert alert--error" role="alert">{error}</div>}
    {state.loading ? <LoadingState/> : state.error ? <ErrorState message={state.error} retry={state.reload}/> : state.data?.length ? <div className="table-wrap"><table><thead><tr><th>نام</th><th>ایمیل یا تلفن</th><th>نقش‌ها</th><th>آخرین ورود</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>{state.data.map((user) => <tr key={user.id}><td data-label="نام"><strong>{user.first_name} {user.last_name}</strong></td><td data-label="ایمیل یا تلفن" dir="ltr">{user.email ?? user.phone_number}</td><td data-label="نقش‌ها">{user.roles.length ? user.roles.map((role) => roleLabels[role] ?? role).join("، ") : "بدون نقش"}</td><td data-label="آخرین ورود"><DateText value={user.last_login_at}/></td><td data-label="وضعیت"><StatusBadge value={user.is_active ? "ACTIVE" : "INACTIVE"}/></td><td data-label="عملیات"><button className="text-button" onClick={() => setDetail(user)}>جزئیات</button>{can("users:manage") && <><button className="text-button" onClick={() => editRoles(user)}>ویرایش نقش‌ها</button><button className="text-button" onClick={() => setPending({ kind: "status", user, isActive: !user.is_active })}>{user.is_active ? "غیرفعال‌سازی" : "فعال‌سازی"}</button></>}</td></tr>)}</tbody></table></div> : <EmptyState title="کاربری وجود ندارد"/>}
    <Modal open={Boolean(detail)} title="جزئیات کاربر" onClose={() => setDetail(null)}>{detail && <div className="detail-summary"><span>نام <strong>{detail.first_name} {detail.last_name}</strong></span><span>ایمیل <strong dir="ltr">{detail.email ?? "—"}</strong></span><span>شماره تلفن <strong dir="ltr">{detail.phone_number ?? "—"}</strong></span><span>نقش‌ها <strong>{detail.roles.length ? detail.roles.map((role) => roleLabels[role] ?? role).join("، ") : "بدون نقش"}</strong></span><span>وضعیت <StatusBadge value={detail.is_active ? "ACTIVE" : "INACTIVE"}/></span><span>آخرین ورود <DateText value={detail.last_login_at}/></span></div>}</Modal>
    <Modal open={Boolean(editing)} title="ویرایش نقش‌های کاربر" onClose={() => setEditing(null)}><p>نقش‌های موردنظر را برای {editing?.first_name} {editing?.last_name} انتخاب کنید.</p><div className="choice-row">{canonicalRoles.map((role) => <label key={role} className="theme-choice"><input type="checkbox" checked={selectedRoles.includes(role)} onChange={(event) => setSelectedRoles((old) => event.target.checked ? [...old, role] : old.filter((item) => item !== role))}/><span>{roleLabels[role]}</span></label>)}</div><div className="form-actions"><button className="button button--secondary" onClick={() => setEditing(null)}>انصراف</button><button className="button button--primary" onClick={() => { if (editing) setPending({ kind: "roles", user: editing, roles: selectedRoles }); setEditing(null); }}>بررسی و تأیید</button></div></Modal>
    <Confirm open={Boolean(pending)} title={pending?.kind === "roles" ? "تأیید تغییر نقش‌ها" : pending?.isActive ? "تأیید فعال‌سازی کاربر" : "تأیید غیرفعال‌سازی کاربر"} message={pending?.kind === "roles" ? `نقش‌های ${pending.user.first_name} ${pending.user.last_name} جایگزین شود؟ تغییر نقش مدیر ممکن است دسترسی مدیریتی او را حذف کند.` : `${pending?.user.first_name ?? ""} ${pending?.user.last_name ?? ""} ${pending?.isActive ? "فعال" : "غیرفعال"} شود؟`} confirmLabel="تأیید تغییر" onConfirm={() => void applyChange()} onClose={() => !busy && setPending(null)} busy={busy}/>
  </>;
}
function BusinessSettings() {
  const { updateBusiness } = useAuth();
  const { category } = useBusiness();
  const [selected, setSelected] = useState<BusinessCategory>(category);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const save = async () => {
    setBusy(true); setMessage("");
    try { await updateBusiness(selected); setMessage("نوع کسب‌وکار ذخیره شد؛ اطلاعات مالی شما بدون تغییر باقی ماند."); }
    catch { setMessage("ذخیره انجام نشد. دوباره تلاش کنید."); }
    finally { setBusy(false); }
  };
  return <Card title="نوع کسب‌وکار"><p>منوها و فرم‌ها را متناسب با فعالیت خود انتخاب کنید. این انتخاب در حساب شما ذخیره می‌شود و طرح اشتراک یا مجوزهای دسترسی را تغییر نمی‌دهد.</p><div className="business-options">{Object.entries(businessProfiles).map(([key, p]) => <label key={key} className={selected === key ? "business-option selected" : "business-option"}><input type="radio" name="business_category" value={key} checked={selected === key} onChange={() => setSelected(key as BusinessCategory)} disabled={busy}/><span><strong>{p.name}</strong><small>{p.examples}</small></span></label>)}</div>{businessProfiles[selected].limitation && <p className="form-note">{businessProfiles[selected].limitation}</p>}<button className="button button--primary" disabled={busy || selected === category} onClick={() => void save()}>{busy ? "در حال ذخیره…" : "ذخیره نوع کسب‌وکار"}</button>{message && <p role="status">{message}</p>}</Card>;
}
export function SettingsPage() { const { theme, calendar, toggleTheme, setCalendar } = usePreferences(); return <><PageHeader title="تنظیمات نمایش" description="انتخاب ظاهر و تقویم دلخواه شما"/><BusinessSettings/><div className="settings-grid"><Card title="رنگ‌بندی"><p>حالت روشن به‌طور پیش‌فرض فعال است. انتخاب شما در همین مرورگر ذخیره می‌شود.</p><div className="choice-row"><button className={`theme-choice ${theme === "light" ? "selected" : ""}`} onClick={() => theme === "dark" && toggleTheme()}><span className="theme-preview light"/>روشن</button><button className={`theme-choice ${theme === "dark" ? "selected" : ""}`} onClick={() => theme === "light" && toggleTheme()}><span className="theme-preview dark"/>تاریک</button></div></Card><Card title="تقویم"><p>ورودی و نمایش تاریخ می‌تواند شمسی یا میلادی باشد. داده‌ها همیشه با تاریخ میلادی استاندارد به سرور ارسال می‌شوند.</p><div className="choice-row"><button className={`calendar-choice ${calendar === "jalali" ? "selected" : ""}`} onClick={() => setCalendar("jalali")}><strong dir="ltr">1405/06/03</strong><span>تقویم شمسی</span></button><button className={`calendar-choice ${calendar === "gregorian" ? "selected" : ""}`} onClick={() => setCalendar("gregorian")}><strong dir="ltr">2026-08-25</strong><span>تقویم میلادی</span></button></div></Card></div></>;
}
