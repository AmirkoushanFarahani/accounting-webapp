import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import indexHtml from "../index.html?raw";
import mainSource from "../src/main.tsx?raw";
import styleSource from "../src/styles.css?raw";
import appSource from "../src/App.tsx?raw";
import adminSource from "../src/pages/AdminPages.tsx?raw";
import dashboardSource from "../src/pages/DashboardPage.tsx?raw";
import customersSource from "../src/pages/CustomersPage.tsx?raw";
import loginPageSource from "../src/pages/LoginPage.tsx?raw";
import masterDataSource from "../src/pages/MasterDataPages.tsx?raw";
import layoutSource from "../src/layouts/AppLayout.tsx?raw";
import transactionSource from "../src/pages/TransactionsPages.tsx?raw";
import billSource from "../src/pages/BillsPages.tsx?raw";
import uiSource from "../src/components/ui.tsx?raw";
import { configureApi, api, ApiError } from "../src/services/api";
import { explanationScopeLabel, formatMoney, formatNumber, formatPercent, paymentMethodLabel, riskSignalLabel, segmentDescriptionLabel, toEnglishDigits, transactionCategoryLabel } from "../src/utils/format";
import { gregorianToJalali, jalaliToGregorian } from "../src/utils/date";
import { visibleNavigationPaths } from "../src/layouts/AppLayout";
import { formatMoneyInput, MoneyInput, normalizeMoneyInput } from "../src/components/ui";
import { defaultTheme, nextTheme, ThemeProvider } from "../src/theme/ThemeContext";
import { Kpi } from "../src/pages/DashboardPage";
import { ReportResult } from "../src/pages/ReportsPage";
import { postingRolesForAccountType } from "../src/pages/MasterDataPages";
import { ClassificationPage, ForecastPage } from "../src/pages/AiPages";
import { routes } from "../src/App";
import { suggestNextInvoiceNumber } from "../src/pages/TransactionsPages";
import { calendarMonth } from "../src/components/DatePicker";
import { BusinessContext, businessProfiles, businessText, type BusinessCategory } from "../src/business/BusinessContext";
import { navigationForBusiness } from "../src/layouts/AppLayout";
import { Field, PageHeader } from "../src/components/ui";

test("business profiles change presentation but preserve financial routes and values", () => {
  const paths = (category: BusinessCategory) => navigationForBusiness(category).flatMap((entry) => "path" in entry ? [entry.path] : entry.items.map((item) => item.path)).sort();
  for (const category of Object.keys(businessProfiles) as BusinessCategory[]) {
    assert.deepEqual(paths(category), paths("RETAIL"));
    const profile = businessProfiles[category];
    const html = renderToStaticMarkup(<BusinessContext.Provider value={category}><PageHeader title="فاکتورها" action={<button>ثبت فاکتور جدید</button>}/><Field label="نام مشتری"><input placeholder="نام کالا یا خدمت"/></Field><Kpi title={profile.revenue} value="1250000.00"/></BusinessContext.Provider>);
    assert.ok(html.includes(profile.invoices));
    assert.ok(html.includes(profile.newInvoice));
    assert.ok(html.includes(profile.customer));
    assert.ok(html.includes(profile.itemPlaceholder));
    assert.ok(html.includes("1,250,000"));
    assert.equal(businessText(category, "بدهکار"), "بدهکار");
    assert.equal(businessText(category, "مالیات"), "مالیات");
  }
});

test("calendar picker handles Persian leap years and emits Gregorian API dates", () => {
  const farvardin = calendarMonth(1405, 1, "jalali");
  assert.equal(farvardin.offset, 0);
  assert.equal(farvardin.days.length, 31);
  assert.equal(farvardin.days[0].iso, "2026-03-21");
  assert.equal(calendarMonth(1403, 12, "jalali").days.length, 30);
  assert.equal(calendarMonth(1404, 12, "jalali").days.length, 29);
  assert.equal(calendarMonth(2024, 2, "gregorian").days.length, 29);
  assert.equal(calendarMonth(2025, 2, "gregorian").days.length, 28);
});

const storage = new Map<string, string>();
Object.assign(globalThis, {
  localStorage: { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) },
  sessionStorage: { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) },
});

test("document is Persian and RTL", () => { assert.match(indexHtml, /<html lang="fa" dir="rtl">/); assert.match(indexHtml, /حسابداری آذری/); });
test("Persian typography is self-hosted with Vazirmatn", () => { assert.match(mainSource, /@fontsource\/vazirmatn\/400\.css/); assert.match(mainSource, /@fontsource\/vazirmatn\/800\.css/); assert.match(styleSource, /font-family: Vazirmatn/); });
test("financial formatting always uses English digits", () => { assert.equal(formatMoney("123456.7"), "123,456.70"); assert.equal(formatMoney("123456.00"), "123,456"); assert.equal(formatMoney("0.00"), "0"); assert.equal(formatMoney("-123456.00"), "-123,456"); assert.equal(formatNumber(1234.5), "1,234.5"); assert.equal(formatPercent(.831), "83.1%"); assert.equal(toEnglishDigits("۱۲۳٤٥"), "12345"); });
test("Jalali and Gregorian conversion round trip", () => { assert.equal(gregorianToJalali("2026-08-25"), "1405/06/03"); assert.equal(jalaliToGregorian("۱۴۰۵/۰۶/۰۳"), "2026-08-25"); assert.throws(() => jalaliToGregorian("1404/12/30")); });
test("light theme is default and switching is deterministic", () => { assert.equal(defaultTheme(null), "light"); assert.equal(defaultTheme("dark"), "dark"); assert.equal(nextTheme("light"), "dark"); assert.equal(nextTheme("dark"), "light"); });
test("Rial inputs group thousands while preserving the raw submitted value", () => { assert.equal(formatMoneyInput("1234567890.50"), "1,234,567,890.50"); assert.equal(normalizeMoneyInput("۱٬۲۳۴٬۵۶۷٫۸۹"), "1234567.89"); const html = renderToStaticMarkup(<MoneyInput name="amount" value="1234567.89" required/>); assert.match(html, /value="1,234,567\.89"/); assert.match(html, /type="hidden" name="amount" value="1234567\.89"/); });
test("desktop navigation keeps one menu open and closes it when the pointer leaves", () => { assert.match(layoutSource, /openGroup === entry\.label/); assert.match(layoutSource, /onMouseLeave=\{\(\) => setOpenGroup\(null\)\}/); assert.match(layoutSource, /onMouseEnter=\{\(\) => setOpenGroup\(entry\.label\)\}/); });
test("desktop submenu has a hover bridge between its trigger and options", () => { assert.match(styleSource, /\.nav-menu::before/); assert.match(styleSource, /top: -10px; height: 10px/); });
test("account category filters posting roles and parent-account choices", () => { assert.deepEqual(postingRolesForAccountType("ASSET"), ["GENERAL", "CASH", "RECEIVABLE"]); assert.deepEqual(postingRolesForAccountType("REVENUE"), ["GENERAL", "REVENUE"]); assert.deepEqual(postingRolesForAccountType("LIABILITY"), ["GENERAL", "TAX_LIABILITY", "PAYABLE", "CUSTOMER_CREDIT"]); assert.deepEqual(postingRolesForAccountType("EXPENSE"), ["GENERAL", "EXPENSE"]); assert.deepEqual(postingRolesForAccountType("EQUITY"), ["GENERAL"]); assert.match(masterDataSource, /account\.category_id === categoryId/); assert.match(masterDataSource, /setPostingRole\(""\); setParentId\(""\)/); assert.match(masterDataSource, /disabled=\{!selectedType\}/); });
test("invoice number suggestion uses the latest creation timestamp and trailing digits", () => { const invoice = (invoice_number: string, created_at = "2026-01-01T00:00:00Z") => ({ invoice_number, created_at }) as never; assert.equal(suggestNextInvoiceNumber([invoice("INV-0099")]), "INV-0100"); assert.equal(suggestNextInvoiceNumber([invoice("NEW-0042", "2026-02-01T00:00:00Z"), invoice("OLD-9", "2026-01-01T00:00:00Z")]), "NEW-0043"); assert.equal(suggestNextInvoiceNumber([invoice("INVOICE")]), ""); assert.equal(suggestNextInvoiceNumber([]), ""); assert.match(transactionSource, /defaultValue=\{suggestNextInvoiceNumber\(invoices\)\}/); });
test("customer and invoice-check balances expose receivables, customer credit and optional Sayad", () => { assert.match(transactionSource, /posting_role === "CUSTOMER_CREDIT"/); assert.match(transactionSource, /checkShortfall/); assert.match(transactionSource, /مبلغ اضافه/); assert.match(transactionSource, /customer_credit_account_id/); assert.match(transactionSource, /شناسه صیادی \(اختیاری\)/); assert.match(transactionSource, /sayad_id: check\.sayad_id\.trim\(\) \|\| null/); assert.doesNotMatch(transactionSource, /checkTotal \+ 0\.009 < preview/); assert.doesNotMatch(transactionSource, /جمع مبلغ چک‌ها باید دقیقاً با مبلغ کل فاکتور برابر باشد/); assert.match(billSource, /sayad_id: method === "چک"/); assert.match(billSource, /شناسه صیادی \(اختیاری\)/); });
test("private customer ledger shows purchases, both balances and complete history", () => { assert.match(appSource, /path: "\/customers"/); assert.match(layoutSource, /مشتریان من/); assert.match(customersSource, /\/reports\/customers/); assert.match(customersSource, /purchase_count/); assert.match(customersSource, /receivable_balance/); assert.match(customersSource, /customer_credit_balance/); assert.match(customersSource, /balance_direction/); assert.match(customersSource, /invoice\.items/); assert.match(customersSource, /invoice\.checks/); assert.match(customersSource, /report\.payments/); });
test("permission-aware navigation hides unauthorized areas", () => { const viewer = visibleNavigationPaths((permission) => ["reports:read", "ml:read"].includes(permission)); assert.ok(viewer.includes("/dashboard")); assert.ok(viewer.includes("/reports/trial-balance")); assert.ok(viewer.includes("/ai")); assert.ok(!viewer.includes("/journals")); assert.ok(!viewer.includes("/ai/models")); assert.ok(viewer.includes("/settings")); });
test("protected routes declare their backend permission", () => { assert.equal(routes.find((route) => route.path === "/customers")?.permission, "reports:read"); assert.equal(routes.find((route) => route.path === "/journals")?.permission, "journals:read"); assert.equal(routes.find((route) => route.path === "/bills")?.permission, "bills:read"); assert.equal(routes.find((route) => route.path === "/bill-payments")?.permission, "bill_payments:read"); assert.equal(routes.find((route) => route.path === "/ai/models")?.permission, "ml:manage"); assert.equal(routes.find((route) => route.path === "/settings")?.permission, undefined); });
test("authentication requests support email or phone with the existing JWT contract", async () => { const calls: Array<{ url: string; auth: string | null; body: string }> = []; globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => { const url = String(input); calls.push({ url, auth: new Headers(init?.headers).get("Authorization"), body: String(init?.body ?? "") }); if (url.endsWith("/auth/login")) return new Response(JSON.stringify({ access_token: "jwt-token", token_type: "bearer" }), { status: 200, headers: { "Content-Type": "application/json" } }); return new Response(JSON.stringify({ id: "1", email: "a@example.com", phone_number: null, first_name: "علی", last_name: "آذری", is_active: true, plan_status: "FREE", roles: ["ADMIN"], permissions: ["reports:read"] }), { status: 200, headers: { "Content-Type": "application/json" } }); }) as typeof fetch; configureApi(() => null, () => undefined); const token = await api.login("+989121234567", "strong-password"); assert.equal(token.access_token, "jwt-token"); assert.match(calls[0].body, /"phone_number":"\+989121234567"/); assert.doesNotMatch(calls[0].body, /"email"/); configureApi(() => token.access_token, () => undefined); const user = await api.me(); assert.equal(user.first_name, "علی"); assert.equal(calls[1].auth, "Bearer jwt-token"); });
test("registration UI and API allow either identity with private OWNER access", async () => { let requestBody = ""; globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => { requestBody = String(init?.body); assert.match(String(input), /\/auth\/register$/); return new Response(JSON.stringify({ id: "1", email: null, phone_number: "+989121234567", first_name: "سارا", last_name: "آذری", is_active: true, plan_status: "FREE", roles: ["OWNER"], permissions: ["invoices:write", "ml:manage"], created_at: "", updated_at: "", last_login_at: null }), { status: 201, headers: { "Content-Type": "application/json" } }); }) as typeof fetch; const user = await api.register({ email: null, phone_number: "+989121234567", password: "secure-pass-123", first_name: "سارا", last_name: "آذری" }); assert.equal(user.email, null); assert.deepEqual(user.roles, ["OWNER"]); assert.ok(!user.permissions.some((permission) => permission.startsWith("users:"))); assert.match(requestBody, /"first_name":"سارا"/); assert.match(requestBody, /"phone_number":"\+989121234567"/); assert.match(loginPageSource, /name="phone_number"/); assert.match(loginPageSource, /حداقل یکی از ایمیل یا شماره تلفن/); assert.match(loginPageSource, /ایمیل یا شماره تلفن/); assert.match(loginPageSource, /to="\/register"/); assert.match(loginPageSource, /ثبت‌نام و ورود/); assert.match(appSource, /path === "\/register"/); });
test("API errors are translated and 401 clears authentication", async () => { let unauthorized = false; globalThis.fetch = (async () => new Response(JSON.stringify({ detail: "Insufficient permission" }), { status: 403, headers: { "Content-Type": "application/json" } })) as typeof fetch; configureApi(() => "token", () => { unauthorized = true; }); await assert.rejects(api.get("/users"), (error: unknown) => error instanceof ApiError && error.status === 403 && error.message.includes("اجازه")); assert.equal(unauthorized, false); globalThis.fetch = (async () => new Response(JSON.stringify({ detail: "Authentication required" }), { status: 401, headers: { "Content-Type": "application/json" } })) as typeof fetch; await assert.rejects(api.me(), ApiError); assert.equal(unauthorized, true); });
test("validation errors never leak backend English into the Persian UI", async () => { globalThis.fetch = (async () => new Response(JSON.stringify({ detail: [{ msg: "Field required" }] }), { status: 422, headers: { "Content-Type": "application/json" } })) as typeof fetch; await assert.rejects(api.post("/parties", {}), (error: unknown) => error instanceof ApiError && error.message === "لطفاً اطلاعات واردشده را بررسی کنید."); });
test("important transaction form is rendered in Persian", () => { const html = renderToStaticMarkup(<ClassificationPage/>); assert.match(html, /شرح تراکنش/); assert.match(html, /تحلیل تراکنش/); assert.match(html, /اطلاعات حساس/); assert.doesNotMatch(html, /lorem ipsum/i); });
test("dashboard KPI renders backend-provided values without substitution", () => { const html = renderToStaticMarkup(<Kpi title="درآمد" value="987654.32"/>); assert.match(html, /987,654.32/); assert.match(html, /درآمد/); });
test("report result renders actual response totals and balanced status", () => { const html = renderToStaticMarkup(<ReportResult kind="trial-balance" data={{ start_date: null, end_date: null, lines: [], total_debit: "500.00", total_credit: "500.00", balanced: true }}/>); assert.match(html, />500 <small>/); assert.doesNotMatch(html, /500\.00/); assert.match(html, /ثبت‌شده/); assert.match(html, /گردش مالی وجود ندارد/); });
test("AI forecast workflow exposes horizon, date and uncertainty language", () => { const html = renderToStaticMarkup(<ThemeProvider><ForecastPage/></ThemeProvider>); assert.match(html, /افق پیش‌بینی/); assert.match(html, /اطلاعات تا تاریخ/); assert.match(html, /پیش‌بینی جریان نقدی/); });
test("backend enum values have Persian user-facing labels", () => { assert.equal(transactionCategoryLabel("office_supplies"), "لوازم اداری"); assert.equal(riskSignalLabel("prior_average_delay"), "میانگین تأخیر پیشین"); assert.equal(explanationScopeLabel("model-level heuristic"), "برآورد اکتشافی در سطح مدل"); assert.equal(segmentDescriptionLabel("high-value, reliable-paying, low-outstanding customers"), "ارزش بالا، پرداخت منظم، مانده باز پایین"); assert.equal(paymentMethodLabel("bank"), "انتقال بانکی"); });
test("sensitive actions use accessible in-app confirmation", () => { assert.doesNotMatch(transactionSource, /\bconfirm\s*\(/); assert.match(transactionSource, /صدور نهایی یک سند حسابداری ایجاد می‌کند/); assert.match(transactionSource, /ثبت نهایی دریافت یک سند حسابداری ایجاد می‌کند/); assert.match(uiSource, /e\.key !== "Tab"/); assert.match(uiSource, /previous\?\.focus\(\)/); });
test("invoice entry uses typed customer and product names and tracks check details", () => { assert.match(transactionSource, /name="customerName"/); assert.match(transactionSource, /profile.itemPlaceholder/); assert.equal(businessProfiles.RETAIL.itemPlaceholder, "نام کالا یا خدمت"); assert.doesNotMatch(transactionSource, /label="تاریخ سررسید"/); assert.match(transactionSource, /due_date: issueDate/); assert.match(transactionSource, /تعداد چک/); assert.match(transactionSource, /شناسه صیادی \(اختیاری\)/); assert.match(transactionSource, /تاریخ سررسید چک/); assert.match(transactionSource, /بدهی مشتری به فروشنده باقی می‌ماند/); assert.match(transactionSource, /اعتبار مشتری و بدهی فروشنده ثبت می‌شود/); assert.doesNotMatch(transactionSource, /جمع چک‌ها نباید کمتر از مبلغ فاکتور باشد/); assert.match(transactionSource, /وصول‌شده/); assert.match(transactionSource, /برگشتی/); });

test("transaction forms explain remaining prerequisites and block empty required selects", () => { assert.match(transactionSource, /ابتدا باید حداقل یک فاکتور صادرشده با مانده قابل دریافت داشته باشید/); assert.match(transactionSource, /ابتدا باید حداقل یک دوره مالی باز داشته باشید/); assert.match(transactionSource, /ابتدا باید حداقل یک حساب فعال ثبت کنید/); assert.match(transactionSource, /to="\/accounts"/); assert.match(transactionSource, /to="\/periods"/); assert.match(transactionSource, /disabled=\{!prerequisitesReady\}/); });
test("financial posting forms enforce semantic roles and block duplicate submissions", () => { assert.match(transactionSource, /posting_role === "CASH"/); assert.match(transactionSource, /posting_role === "RECEIVABLE"/); assert.match(transactionSource, /posting_role === "REVENUE"/); assert.match(transactionSource, /posting_role === "TAX_LIABILITY"/); assert.match(transactionSource, /tax_liability_account_id/); assert.match(transactionSource, /حساب نقد\/بانک و حساب دریافتنی باید متفاوت باشند/); assert.match(transactionSource, /if \(!item \|\| busy\) return/); assert.match(transactionSource, /در حال صدور…/); assert.match(transactionSource, /در حال ذخیره…/); });
test("supplier bill workflows use purchase labels, descriptions and payable roles", () => { assert.match(billSource, /ابتدا باید حداقل یک تأمین‌کننده فعال ثبت کنید/); assert.match(billSource, /ابتدا باید حداقل یک صورتحساب خرید صادرشده با مانده قابل پرداخت داشته باشید/); assert.match(billSource, /posting_role === "EXPENSE"/); assert.match(billSource, /posting_role === "PAYABLE"/); assert.match(billSource, /label="حساب خرید"/); assert.match(transactionSource, /label="حساب فروش"/); assert.match(billSource, /جزئیات خرید، مبلغ بدهی و وضعیت پرداخت/); assert.match(billSource, /با صدور نهایی، مبلغ خرید در حساب هزینه/); assert.match(billSource, /جزئیات پرداخت و نحوه تخصیص آن/); assert.match(billSource, /با ثبت نهایی، بدهی تأمین‌کننده کاهش/); assert.match(billSource, /disabled=\{activeSuppliers.length === 0 \|\| busy\}/); assert.match(billSource, /disabled=\{!prerequisitesReady \|\| busy\}/); assert.match(billSource, /مالیات خرید در مبلغ هزینه جذب می‌شود/); assert.doesNotMatch(billSource, /tax_liability_account_id/); });
test("dashboard write action is permission-aware", () => { assert.match(dashboardSource, /can\("invoices:write"\) \?/); });
test("user role and status controls require users manage permission", () => { assert.match(adminSource, /OWNER: "مالک فضای کاری"/); assert.match(layoutSource, /OWNER: "مالک فضای کاری"/); assert.match(adminSource, /can\("users:manage"\) &&/); assert.match(adminSource, /ویرایش نقش‌ها/); assert.match(adminSource, /غیرفعال‌سازی/); assert.match(adminSource, /<Confirm/); assert.match(adminSource, /حداقل یک مدیر فعال/); });
import { matchesParty } from "../src/components/PartySelect";
test("payment party search matches names, email and localized phone digits", () => {
  const party = { name: "علی کریمی", email: "ALI@example.com", phone: "+989121234567" };
  assert.equal(matchesParty(party, " علي "), true);
  assert.equal(matchesParty(party, "كریمی"), true);
  assert.equal(matchesParty(party, "ali@EXAMPLE"), true);
  assert.equal(matchesParty(party, "۹۱۲۱۲۳"), true);
  assert.equal(matchesParty(party, "unknown"), false);
  assert.equal(matchesParty({ name: "Sara", phone: null, email: null }, ""), true);
});
test("party suggestions include every matching Maryam and exclude unrelated names", () => {
  const names = ["مریم کریمی", "مریم احمدی", "سارا محمدی", "سیده مریم رضایی"];
  const results = names.filter((name) => matchesParty({ name, email: null, phone: null }, "مریم"));
  assert.deepEqual(results, ["مریم کریمی", "مریم احمدی", "سیده مریم رضایی"]);
});
import { expenseMethods, ExpensesPage } from "../src/pages/ExpensesPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeContext";
import expenseSource from "../src/pages/ExpensesPage.tsx?raw";
test("paid expenses have a dedicated purchase menu, filters and immediate-payment guidance", () => {
  assert.deepEqual(Object.keys(expenseMethods), ["CASH", "CHECK", "BANK_TRANSFER"]);
  const html = renderToStaticMarkup(<ThemeProvider><AuthProvider><ExpensesPage/></AuthProvider></ThemeProvider>);
  assert.match(html, /هزینه‌ها/);
  assert.match(html, /از تاریخ/);
  assert.match(html, /تا تاریخ/);
  assert.match(expenseSource, /کد پیگیری \(اختیاری\)/);
  assert.match(expenseSource, /وصول جداگانه ندارد/);
  assert.match(expenseSource, /api.post\("\/expenses"/);
});
