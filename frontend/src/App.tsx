import { useEffect } from "react";
import { ExpensesPage } from "./pages/ExpensesPage";
import { useAuth } from "./auth/AuthContext";
import { LoadingState } from "./components/ui";
import { AppLayout } from "./layouts/AppLayout";
import { SettingsPage, UsersPage } from "./pages/AdminPages";
import { AiDashboardPage, ClassificationPage, ForecastPage, ModelsPage, RiskPage, SegmentsPage } from "./pages/AiPages";
import { DashboardPage } from "./pages/DashboardPage";
import { CustomersPage } from "./pages/CustomersPage";
import { BillPaymentsPage, BillsPage } from "./pages/BillsPages";
import { LoginPage, RegisterPage } from "./pages/LoginPage";
import { AccountsPage, PartiesPage, PeriodsPage, ProductsPage } from "./pages/MasterDataPages";
import { ReportsPage } from "./pages/ReportsPage";
import { InvoicesPage, JournalsPage, PaymentsPage } from "./pages/TransactionsPages";
import { Link, useRouter } from "./routes/router";
import "./styles.css";
interface Route { path: string; component: () => React.JSX.Element; permission?: string; prefix?: boolean }
export const routes: Route[] = [
  { path: "/expenses", component: ExpensesPage, permission: "bills:read" },
  { path: "/dashboard", component: DashboardPage, permission: "reports:read" }, { path: "/customers", component: CustomersPage, permission: "reports:read" }, { path: "/parties", component: PartiesPage, permission: "parties:read" }, { path: "/products", component: ProductsPage, permission: "products:read" }, { path: "/accounts", component: AccountsPage, permission: "accounts:read" }, { path: "/periods", component: PeriodsPage, permission: "periods:read" }, { path: "/journals", component: JournalsPage, permission: "journals:read" }, { path: "/invoices", component: InvoicesPage, permission: "invoices:read" }, { path: "/payments", component: PaymentsPage, permission: "payments:read" },
  { path: "/bills", component: BillsPage, permission: "bills:read" }, { path: "/bill-payments", component: BillPaymentsPage, permission: "bill_payments:read" },
  { path: "/reports/", component: ReportsPage, permission: "reports:read", prefix: true }, { path: "/ai", component: AiDashboardPage, permission: "ml:read" }, { path: "/ai/classification", component: ClassificationPage, permission: "ml:predict" }, { path: "/ai/risk", component: RiskPage, permission: "ml:predict" }, { path: "/ai/forecast", component: ForecastPage, permission: "ml:predict" }, { path: "/ai/segments", component: SegmentsPage, permission: "ml:predict" }, { path: "/ai/models", component: ModelsPage, permission: "ml:manage" }, { path: "/users", component: UsersPage, permission: "users:read" }, { path: "/settings", component: SettingsPage },
];
function MessagePage({ forbidden = false }: { forbidden?: boolean }) { return <div className="message-page"><span>{forbidden ? "!" : "؟"}</span><h1>{forbidden ? "دسترسی مجاز نیست" : "صفحه پیدا نشد"}</h1><p>{forbidden ? "نقش کاربری شما اجازه مشاهده این بخش را ندارد." : "نشانی واردشده در سامانه وجود ندارد."}</p><Link to="/dashboard" className="button button--primary">بازگشت به داشبورد</Link></div>; }
function Redirect({ to }: { to: string }) { const { navigate } = useRouter(); useEffect(() => navigate(to, true), [navigate, to]); return <LoadingState label="در حال انتقال…"/>; }
export default function App() { const { user, loading, can } = useAuth(); const { path } = useRouter(); if (loading) return <main className="boot"><div className="login-mark">آ</div><LoadingState label="در حال بررسی حساب کاربری…"/></main>; if (!user) return path === "/login" ? <LoginPage/> : path === "/register" ? <RegisterPage/> : <Redirect to="/login"/>; if (path === "/login" || path === "/register" || path === "/") return <Redirect to="/dashboard"/>; const route = routes.find((r) => r.prefix ? path.startsWith(r.path) : path === r.path); const Page = route?.component; return <AppLayout>{!route ? <MessagePage/> : route.permission && !can(route.permission) ? <MessagePage forbidden/> : Page ? <Page/> : null}</AppLayout>; }
