import { useEffect, useRef, useState, type ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";
import { Link, useRouter } from "../routes/router";
import { usePreferences } from "../theme/ThemeContext";

import { businessText, useBusiness, type BusinessCategory } from "../business/BusinessContext";

interface NavItem { label: string; path: string; permission?: string }
interface NavGroup { label: string; items: NavItem[] }
const profileRoleLabels: Record<string, string> = { ADMIN: "مدیر سامانه", OWNER: "مالک فضای کاری", ACCOUNTANT: "حسابدار", MANAGER: "مدیر", VIEWER: "مشاهده‌گر" };
export const navigation: Array<NavItem | NavGroup> = [
  { label: "داشبورد", path: "/dashboard", permission: "reports:read" },
  { label: "حسابداری", items: [
    { label: "طرف حساب‌ها", path: "/parties", permission: "parties:read" }, { label: "کالا و خدمات", path: "/products", permission: "products:read" },
    { label: "حساب‌ها و سرفصل‌ها", path: "/accounts", permission: "accounts:read" }, { label: "اسناد حسابداری", path: "/journals", permission: "journals:read" }, { label: "دوره‌های مالی", path: "/periods", permission: "periods:read" },
  ]},
  { label: "فروش و دریافت", items: [{ label: "مشتریان من", path: "/customers", permission: "reports:read" }, { label: "فاکتورها", path: "/invoices", permission: "invoices:read" }, { label: "پرداخت‌ها", path: "/payments", permission: "payments:read" }] },
  { label: "خرید و پرداخت", items: [{ label: "هزینه‌ها", path: "/expenses", permission: "bills:read" }, { label: "صورتحساب‌های خرید", path: "/bills", permission: "bills:read" }, { label: "پرداخت به تأمین‌کنندگان", path: "/bill-payments", permission: "bill_payments:read" }] },
  { label: "گزارش‌ها", items: [
    { label: "تراز آزمایشی", path: "/reports/trial-balance", permission: "reports:read" }, { label: "صورت سود و زیان", path: "/reports/income-statement", permission: "reports:read" }, { label: "ترازنامه", path: "/reports/balance-sheet", permission: "reports:read" },
    { label: "درآمدها", path: "/reports/revenue", permission: "reports:read" }, { label: "هزینه‌ها", path: "/reports/expenses", permission: "reports:read" }, { label: "مطالبات", path: "/reports/receivables", permission: "reports:read" },
    { label: "پرداختنی‌ها", path: "/reports/payables", permission: "reports:read" }, { label: "جریان نقدی", path: "/reports/cash-flow", permission: "reports:read" }, { label: "گردش طرف حساب", path: "/reports/party-history", permission: "reports:read" },
  ]},
  { label: "هوش مصنوعی", items: [
    { label: "داشبورد هوش مصنوعی", path: "/ai", permission: "ml:read" }, { label: "طبقه‌بندی تراکنش", path: "/ai/classification", permission: "ml:predict" }, { label: "ریسک تأخیر پرداخت", path: "/ai/risk", permission: "ml:predict" },
    { label: "پیش‌بینی جریان نقدی", path: "/ai/forecast", permission: "ml:predict" }, { label: "بخش‌بندی مشتریان", path: "/ai/segments", permission: "ml:predict" }, { label: "مدیریت مدل‌ها", path: "/ai/models", permission: "ml:manage" },
  ]},
  { label: "مدیریت", items: [{ label: "کاربران", path: "/users", permission: "users:read" }, { label: "تنظیمات نمایش", path: "/settings" }] },
];
export function navigationForBusiness(category: BusinessCategory) {
  const entries = category === "RETAIL" ? navigation : [navigation[0], navigation[2], navigation[1], ...navigation.slice(3)];
  return entries.map((entry) => "path" in entry
    ? { ...entry, label: businessText(category, entry.label) }
    : { ...entry, label: businessText(category, entry.label), items: entry.items.map((item) => ({ ...item, label: businessText(category, item.path === "/payments" ? "پرداخت‌ها" : item.label) })) });
}
export function visibleNavigationPaths(can: (permission: string) => boolean) { return navigation.flatMap((entry) => "path" in entry ? (allowed(entry, can) ? [entry.path] : []) : entry.items.filter((item) => allowed(item, can)).map((item) => item.path)); }

function allowed(item: NavItem, can: (p: string) => boolean) { return !item.permission || can(item.permission); }
function DesktopNavigation() { const { category } = useBusiness(); const { can } = useAuth(); const { path } = useRouter(); const [openGroup, setOpenGroup] = useState<string | null>(null); return <nav className="desktop-nav" aria-label="پیمایش اصلی" onMouseLeave={() => setOpenGroup(null)}>{navigationForBusiness(category).map((entry) => "path" in entry ? allowed(entry, can) && <Link key={entry.path} to={entry.path} className={path === entry.path ? "active" : ""} onClick={() => setOpenGroup(null)}>{entry.label}</Link> : (() => { const items = entry.items.filter((item) => allowed(item, can)); const open = openGroup === entry.label; return items.length ? <details className="nav-group" key={entry.label} open={open} onMouseEnter={() => setOpenGroup(entry.label)} onMouseLeave={() => setOpenGroup(null)}><summary onClick={(event) => { event.preventDefault(); setOpenGroup(open ? null : entry.label); }}>{entry.label}<span aria-hidden>⌄</span></summary><div className="nav-menu">{items.map((item) => <Link key={item.path} to={item.path} className={path === item.path ? "active" : ""} onClick={() => setOpenGroup(null)}>{item.label}</Link>)}</div></details> : null; })())}</nav>; }
function MobileNavigation({ open, close }: { open: boolean; close: () => void }) { const { category } = useBusiness(); const { can } = useAuth(); const { path } = useRouter(); const drawer = useRef<HTMLElement>(null); useEffect(() => { if (open) drawer.current?.focus(); }, [open]); return <><div className={`drawer-backdrop ${open ? "open" : ""}`} onClick={close} /><aside ref={drawer} tabIndex={-1} className={`drawer ${open ? "open" : ""}`} aria-hidden={!open}><header><Brand /><button className="icon-button" onClick={close} aria-label="بستن منو">×</button></header><nav>{navigationForBusiness(category).map((entry) => "path" in entry ? allowed(entry, can) && <Link key={entry.path} to={entry.path} onClick={close} className={path === entry.path ? "active" : ""}>{entry.label}</Link> : <section key={entry.label}><h3>{entry.label}</h3>{entry.items.filter((item) => allowed(item, can)).map((item) => <Link key={item.path} to={item.path} onClick={close} className={path === item.path ? "active" : ""}>{item.label}</Link>)}</section>)}</nav></aside></>; }
function Brand() { const { category, profile } = useBusiness(); return <Link to="/dashboard" className="brand"><span aria-hidden>آ</span><strong>حسابداری آذری<small>{category === "RETAIL" ? "مدیریت مالی هوشمند" : profile.name}</small></strong></Link>; }
export function AppLayout({ children }: { children: ReactNode }) { const [drawer, setDrawer] = useState(false); const [profile, setProfile] = useState(false); const { user, logout } = useAuth(); const { theme, toggleTheme } = usePreferences(); return <div className="app"><header className="topbar"><button className="menu-button" onClick={() => setDrawer(true)} aria-label="باز کردن منو">☰</button><Brand /><DesktopNavigation /><div className="top-actions"><button className="icon-button" onClick={toggleTheme} aria-label={theme === "light" ? "فعال‌کردن حالت تاریک" : "فعال‌کردن حالت روشن"}>{theme === "light" ? "◐" : "☀"}</button><div className="profile"><button className="profile-button" onClick={() => setProfile((v) => !v)} aria-expanded={profile}><span className="avatar">{user?.first_name.slice(0, 1)}</span><span>{user?.first_name} {user?.last_name}<small>{user?.roles.map((role) => profileRoleLabels[role] ?? role).join("، ")}</small></span><span aria-hidden>⌄</span></button>{profile && <div className="profile-menu"><Link to="/settings" onClick={() => setProfile(false)}>تنظیمات نمایش</Link><button onClick={logout}>خروج از حساب</button></div>}</div></div></header><MobileNavigation open={drawer} close={() => setDrawer(false)} /><main className="content">{children}</main><footer>آذری · اطلاعات مالی فقط از سامانه حسابداری خوانده می‌شود.</footer></div>; }
