import { createContext, useContext } from "react";

export type BusinessCategory = "RETAIL" | "EDUCATION" | "ONLINE" | "SERVICES";
interface Profile {
  name: string; examples: string; title: string; description: string;
  customer: string; customers: string; item: string; items: string; invoice: string;
  invoices: string; receipts: string; sales: string; newInvoice: string;
  revenue: string; outstanding: string; itemPlaceholder: string; unit: string;
  workflow: string; limitation: string;
}
export const businessProfiles: Record<BusinessCategory, Profile> = {
  RETAIL: {
    name: "فروشگاه و مغازه", examples: "پوشاک، لوازم‌التحریر، کتاب‌فروشی و فروشگاه کالا",
    title: "داشبورد فروشگاه", description: "نمای کلی فروش، دریافت و بدهی‌های فروشگاه",
    customer: "مشتری", customers: "مشتریان من", item: "کالا/خدمت", items: "کالا و خدمات",
    invoice: "فاکتور", invoices: "فاکتورها", receipts: "دریافت‌ها", sales: "فروش و دریافت",
    newInvoice: "ثبت فاکتور جدید", revenue: "درآمد", outstanding: "مانده مطالبات",
    itemPlaceholder: "نام کالا یا خدمت", unit: "عدد", workflow: "مشتری ← فاکتور فروش ← دریافت وجه",
    limitation: "",
  },
  EDUCATION: {
    name: "آموزشگاه و مؤسسه آموزشی", examples: "مدرسه، آموزشگاه زبان، موسیقی و مهارت‌آموزی",
    title: "داشبورد مالی آموزشگاه", description: "شهریه‌ها، دریافت‌ها و مانده حساب پرداخت‌کنندگان",
    customer: "هنرجو یا پرداخت‌کننده", customers: "پرونده‌های شهریه", item: "دوره/خدمت آموزشی", items: "دوره‌ها و خدمات آموزشی",
    invoice: "صورتحساب شهریه", invoices: "صورتحساب‌های شهریه", receipts: "دریافت شهریه", sales: "شهریه و دریافت",
    newInvoice: "ثبت صورتحساب شهریه", revenue: "درآمد آموزشی", outstanding: "شهریه دریافت‌نشده",
    itemPlaceholder: "نام دوره یا خدمت آموزشی", unit: "دوره", workflow: "پرداخت‌کننده ← صورتحساب شهریه ← دریافت شهریه",
    limitation: "این بخش پرونده مالی شهریه است؛ ثبت‌نام کلاس، حضور و غیاب و پرونده مستقل سرپرست ارائه نمی‌کند.",
  },
  ONLINE: {
    name: "کسب‌وکار آنلاین", examples: "فروشگاه اینترنتی، فروش اینستاگرامی و محصولات دست‌ساز",
    title: "داشبورد فروش آنلاین", description: "فاکتور سفارش‌ها، دریافت وجه و مانده مشتریان",
    customer: "خریدار", customers: "خریداران من", item: "محصول/خدمت", items: "محصولات فروشگاه",
    invoice: "فاکتور سفارش", invoices: "فاکتورهای سفارش", receipts: "دریافت سفارش‌ها", sales: "سفارش و دریافت",
    newInvoice: "ثبت فاکتور سفارش", revenue: "درآمد فروش آنلاین", outstanding: "مانده سفارش‌ها",
    itemPlaceholder: "نام محصول یا خدمت سفارش", unit: "عدد", workflow: "خریدار ← فاکتور سفارش ← دریافت وجه",
    limitation: "وضعیت‌های این بخش مالی هستند؛ ارسال، تحویل و اتصال به فروشگاه اینترنتی در این نسخه وجود ندارد.",
  },
  SERVICES: {
    name: "خدمات نوبتی و دوره‌ای", examples: "سالن زیبایی، باشگاه، خدمات نظافت و نگهداری",
    title: "داشبورد مالی خدمات", description: "صورتحساب خدمات، بسته‌ها و دریافت‌های مراجعان",
    customer: "مراجع", customers: "پرونده مراجعان", item: "خدمت/بسته", items: "خدمات و بسته‌ها",
    invoice: "صورتحساب خدمات", invoices: "صورتحساب‌های خدمات", receipts: "دریافت خدمات", sales: "خدمات و دریافت",
    newInvoice: "ثبت صورتحساب خدمات", revenue: "درآمد خدمات", outstanding: "مانده مراجعان",
    itemPlaceholder: "نام خدمت یا بسته خدماتی", unit: "جلسه", workflow: "مراجع ← صورتحساب خدمت ← دریافت وجه",
    limitation: "این بخش حسابداری خدمات است؛ رزرو نوبت، مصرف جلسات بسته و صدور خودکار صورتحساب دوره‌ای ارائه نمی‌کند.",
  },
};

export const BusinessContext = createContext<BusinessCategory>("RETAIL");
export function businessText(category: BusinessCategory, text: string): string {
  if (category === "RETAIL") return text;
  const p = businessProfiles[category];
  const labels: Record<string, string> = {
    "مشتری": p.customer, "نام مشتری": `نام ${p.customer}`, "انتخاب مشتری": `انتخاب ${p.customer}`,
    "مشتریان من": p.customers, "فهرست خصوصی مشتریان، سابقه خرید و وضعیت کامل بدهکار و بستانکار": `پرونده مالی ${p.customer}، صورتحساب‌ها و مانده حساب`,
    "کالا و خدمات": p.items, "کالا/خدمات": p.item, "کالا/خدمت": p.item,
    "کالا یا خدمت جدید": `ثبت ${p.item}`, "ویرایش کالا یا خدمت": `ویرایش ${p.item}`,
    "کد کالا": `کد ${p.item}`, "نام کالا یا خدمت": p.itemPlaceholder,
    "فهرست اقلام قابل استفاده در فاکتور": `فهرست اقلام قابل استفاده در ${p.invoice}`,
    "فاکتورها": p.invoices, "فاکتور": p.invoice, "فاکتور جدید": p.newInvoice,
    "صدور و پیگیری فاکتورهای فروش": `صدور و پیگیری ${p.invoices}`,
    "ثبت دریافت و تخصیص آن به فاکتورها": `ثبت ${p.receipts} و تخصیص به ${p.invoices}`,
    "فاکتور فروش جدید": p.newInvoice, "ثبت فاکتور جدید": p.newInvoice,
    "شماره فاکتور": `شماره ${p.invoice}`, "اقلام فاکتور": `اقلام ${p.invoice}`,
    "آخرین فاکتورها": `آخرین ${p.invoices}`, "فاکتوری ثبت نشده است": `${p.invoice} ثبت نشده است`,
    "فروش و دریافت": p.sales, "پرداخت‌ها": p.receipts, "آخرین دریافت‌ها": `آخرین ${p.receipts}`,
    "ثبت دریافت جدید": `ثبت ${p.receipts}`, "مبلغ دریافت (ریال)": `مبلغ ${p.receipts} (ریال)`,
    "مشتریان و تأمین‌کنندگان کسب‌وکار": `${p.customer} و تأمین‌کنندگان`,
    "تعداد خرید": "تعداد صورتحساب قطعی", "مجموع خرید": "مجموع صورتحساب قطعی",
    "بدهی مشتری": `بدهی ${p.customer}`, "اعتبار مشتری": `اعتبار ${p.customer}`,
    "تنظیمات نمایش": "تنظیمات کسب‌وکار و نمایش",
  };
  return labels[text] ?? text;
}
export function useBusiness() {
  const category = useContext(BusinessContext);
  return { category, profile: businessProfiles[category], t: (text: string) => businessText(category, text) };
}
