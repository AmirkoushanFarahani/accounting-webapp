import { useEffect, useId, useRef, useState } from "react";
import { usePreferences } from "../theme/ThemeContext";
import { formatDate, gregorianToJalali, jalaliToGregorian, type CalendarMode } from "../utils/date";
import { isValidJalaaliDate } from "../utils/jalaali";

const months = {
  jalali: ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"],
  gregorian: ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"],
};
const weekdays = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];
const digits = new Intl.NumberFormat("fa-IR", { useGrouping: false });
const pad = (n: number) => String(n).padStart(2, "0");
function localToday() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
function monthOf(iso: string, mode: CalendarMode) {
  const [year, month] = (mode === "jalali" ? gregorianToJalali(iso) : iso).split(/[-/]/).map(Number);
  return { year, month };
}
export function calendarMonth(year: number, month: number, mode: CalendarMode) {
  const iso = (day: number) => mode === "jalali" ? jalaliToGregorian(`${year}/${month}/${day}`) : `${year}-${pad(month)}-${pad(day)}`;
  let length = mode === "gregorian" ? new Date(Date.UTC(year, month, 0)).getUTCDate() : 31;
  if (mode === "jalali") while (!isValidJalaaliDate(year, month, length)) length--;
  const offset = (new Date(`${iso(1)}T12:00:00Z`).getUTCDay() + 1) % 7;
  return { offset, days: Array.from({ length }, (_, i) => ({ day: i + 1, iso: iso(i + 1) })) };
}

export function DatePicker({ label, value, onChange, required }: {
  label: string; value: string; onChange: (iso: string) => void; required?: boolean;
}) {
  const { calendar } = usePreferences();
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(value ? formatDate(value, calendar) : "");
  const [error, setError] = useState("");
  const [view, setView] = useState(() => monthOf(value || localToday(), calendar));
  const { days, offset } = calendarMonth(view.year, view.month, calendar);
  const today = localToday();
  const currentYear = monthOf(today, calendar).year;
  useEffect(() => {
    setText(value ? formatDate(value, calendar) : "");
    setView(monthOf(value || localToday(), calendar));
  }, [value, calendar]);
  const close = () => { setOpen(false); input.current?.focus(); };
  const choose = (iso: string) => {
    setText(iso ? formatDate(iso, calendar) : ""); setError("");
    input.current?.setCustomValidity(""); onChange(iso); close();
  };
  const show = () => { setView(monthOf(value || today, calendar)); setOpen(true); };
  useEffect(() => {
    if (!open || !popup.current) return;
    const element = popup.current;
    element.showPopover();
    const position = () => {
      const bounds = input.current!.getBoundingClientRect();
      const height = element.getBoundingClientRect().height;
      element.style.left = `${Math.max(8, Math.min(bounds.right - element.offsetWidth, window.innerWidth - element.offsetWidth - 8))}px`;
      element.style.top = `${Math.max(8, bounds.bottom + height + 8 < window.innerHeight ? bounds.bottom + 6 : bounds.top - height - 6)}px`;
    };
    position();
    element.querySelector<HTMLButtonElement>(`[data-date="${value || today}"]`)?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => {
      element.hidePopover();
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
    };
  }, [open]);
  const moveMonth = (amount: number) => {
    const absolute = view.year * 12 + view.month - 1 + amount;
    setView({ year: Math.floor(absolute / 12), month: absolute % 12 + 1 });
  };
  const typeDate = (next: string) => {
    setText(next);
    try {
      if (!next) { onChange(""); setError(""); input.current?.setCustomValidity(""); return; }
      const iso = calendar === "jalali" ? jalaliToGregorian(next) : next;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(iso) || Number.isNaN(Date.parse(iso)) || new Date(iso).toISOString().slice(0, 10) !== iso) throw new Error();
      setError(""); input.current?.setCustomValidity(""); onChange(iso);
    } catch {
      const message = "تاریخ معتبر انتخاب یا وارد کنید.";
      setError(message); input.current?.setCustomValidity(message);
    }
  };
  return <div ref={root} className="field date-picker" onBlur={(event) => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
  }} onKeyDown={(event) => {
    if (open && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
  }}>
    <label htmlFor={id}>{label} ({calendar === "jalali" ? "شمسی" : "میلادی"})</label>
    <div className="date-picker-input">
      <input ref={input} id={id} value={text} dir="ltr" required={required} placeholder="انتخاب تاریخ"
        aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined}
        aria-haspopup="dialog" aria-expanded={open} aria-controls={`${id}-calendar`}
        onClick={show} onChange={(event) => typeDate(event.target.value)}
        onKeyDown={(event) => { if (event.key === "ArrowDown") { event.preventDefault(); show(); } }}/>
      <button type="button" aria-label={`انتخاب ${label}`} aria-expanded={open} onClick={() => open ? close() : show()}>
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4M17 3v4M3 11h18M7 15h2m3 0h2m3 0h1M7 18h2m3 0h2"/></svg>
      </button>
    </div>
    {error && <small id={`${id}-error`} role="alert">{error}</small>}
    {open && <div ref={popup} id={`${id}-calendar`} popover="manual" role="dialog" aria-label={`تقویم ${label}`} className="date-calendar" dir="rtl">
      <div className="date-calendar-header">
        <button type="button" aria-label="ماه قبل" onClick={() => moveMonth(-1)}>❮</button>
        <select aria-label="ماه" value={view.month} onChange={(event) => setView({ ...view, month: Number(event.target.value) })}>
          {months[calendar].map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
        </select>
        <select aria-label="سال" value={view.year} onChange={(event) => setView({ ...view, year: Number(event.target.value) })}>
          {Array.from({ length: Math.max(currentYear + 100, view.year) - Math.min(currentYear - 100, view.year) + 1 }, (_, i) => Math.min(currentYear - 100, view.year) + i).map((year) => <option key={year} value={year}>{digits.format(year)}</option>)}
        </select>
        <button type="button" aria-label="ماه بعد" onClick={() => moveMonth(1)}>❯</button>
      </div>
      <div className="date-calendar-grid">
        {weekdays.map((day) => <span className="date-weekday" key={day}>{day}</span>)}
        {Array.from({ length: offset }, (_, i) => <span key={`empty-${i}`} aria-hidden="true"/>)}
        {days.map(({ day, iso }) => <button type="button" key={iso} data-date={iso}
          className={`${iso === value ? "selected" : ""} ${iso === today ? "today" : ""} ${(day + offset) % 7 === 0 ? "friday" : ""}`}
          aria-label={formatDate(iso, calendar)} aria-pressed={iso === value} aria-current={iso === today ? "date" : undefined}
          onClick={() => choose(iso)}>{digits.format(day)}</button>)}
      </div>
      <div className="date-calendar-footer">
        <button type="button" onClick={() => choose(today)}>امروز</button>
        <button type="button" onClick={() => choose("")}>پاک کردن</button>
        <button type="button" onClick={close}>بستن</button>
      </div>
    </div>}
  </div>;
}
