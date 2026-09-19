import { useMemo, useState } from "react";
import { DateText, ErrorState, LoadingState, Money, PageHeader, StatusBadge } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import type { Payables, Student } from "../types/api";

interface ExpenseList { total: string }
interface StudentSegment { student_id: string; segment: number; behavioral_description: string; model_version: string; prediction_timestamp: string; as_of: string }
function Kpi({ title, value, tone = "" }: { title: string; value: string; tone?: string }) { return <article className={`kpi ${tone}`}><span>{title}</span><Money value={value} /></article>; }

export function SchoolAccountingPage() {
  const state = useAsync(async () => {
    const [students, expenses, payables] = await Promise.all([
      api.get<Student[]>("/school/students"),
      api.get<ExpenseList>("/school/costs"),
      api.get<Payables>("/reports/payables"),
    ]);
    return { students, expenses, payables };
  }, []);
  const [segments, setSegments] = useState<Record<string, StudentSegment>>({});
  const [segmentError, setSegmentError] = useState("");
  const [runningId, setRunningId] = useState<string | null>(null);
  const totals = useMemo(() => {
    const enrollments = state.data?.students.flatMap((student) => student.enrollments) ?? [];
    const billed = enrollments.reduce((sum, enrollment) => sum + Number(enrollment.total_amount), 0);
    const received = enrollments.reduce((sum, enrollment) => sum + Number(enrollment.amount_paid), 0);
    const receivable = enrollments.reduce((sum, enrollment) => sum + Number(enrollment.balance_due), 0);
    const expenses = Number(state.data?.expenses.total ?? 0);
    const payables = Number(state.data?.payables.total_payables ?? 0);
    return { billed, received, receivable, expenses, payables, net: received - expenses };
  }, [state.data]);
  async function cluster(student: Student) {
    setRunningId(student.id); setSegmentError("");
    try { const result = await api.post<StudentSegment>(`/school/accounting/students/${student.id}/segment`, {}); setSegments((current) => ({ ...current, [student.id]: result })); }
    catch (reason) { setSegmentError(reason instanceof Error ? reason.message : "اجرای بخش‌بندی هوشمند ناموفق بود."); }
    finally { setRunningId(null); }
  }
  if (state.loading) return <LoadingState />;
  if (state.error || !state.data) return <ErrorState message={state.error} retry={state.reload} />;
  return <><PageHeader title="حسابداری آموزشگاه" description="نمای مالی شهریه، هزینه‌ها، بدهی‌ها و تحلیل هوشمند دانش‌آموزان. این بخش فقط برای مدیر آموزشگاه است." />
    <section className="kpi-grid kpi-grid--3"><Kpi title="کل شهریه ثبت‌شده" value={totals.billed.toString()} tone="positive" /><Kpi title="شهریه دریافت‌شده" value={totals.received.toString()} tone="positive" /><Kpi title="مانده بدهی دانش‌آموزان" value={totals.receivable.toString()} tone={totals.receivable > 0 ? "negative" : "positive"} /><Kpi title="هزینه‌های ثبت‌شده" value={totals.expenses.toString()} /><Kpi title="بدهی به تأمین‌کنندگان" value={totals.payables.toString()} tone={totals.payables > 0 ? "negative" : "positive"} /><Kpi title="خالص دریافتی پس از هزینه" value={totals.net.toString()} tone={totals.net >= 0 ? "positive" : "negative"} /></section>
    <section className="card"><h2 className="card-title">راهنمای مانده‌ها</h2><div className="detail-grid"><p><strong>دانش‌آموزان بدهکار:</strong> شهریه‌ای که هنوز دریافت نشده است.</p><p><strong>بدهی به دیگران:</strong> صورتحساب‌های خرید صادرشده که هنوز پرداخت نشده‌اند.</p><p><strong>هزینه‌ها:</strong> پرداخت‌های هزینه‌ای که از بخش هزینه‌ها ثبت شده‌اند.</p></div></section>
    <section className="card"><h2 className="card-title">بخش‌بندی هوشمند دانش‌آموزان</h2><p className="form-description">مدل خوشه‌بندی با مبلغ شهریه، پرداخت‌ها، مانده، تعداد ثبت‌نام و نظم پرداخت همان دانش‌آموز کار می‌کند. این نتیجه فقط یک تحلیل کمکی است و هیچ مبلغ یا وضعیت مالی را تغییر نمی‌دهد.</p>{segmentError && <p className="alert alert--error">{segmentError}</p>}
      <div className="table-wrap"><table><thead><tr><th>دانش‌آموز</th><th>کل شهریه</th><th>پرداخت‌شده</th><th>مانده</th><th>وضعیت</th><th>تحلیل هوشمند</th></tr></thead><tbody>{state.data.students.map((student) => { const enrollment = student.enrollments[0]; const segment = segments[student.id]; return <tr key={student.id}><td><strong>{student.full_name}</strong><small>{student.guardian_full_name}</small></td><td>{enrollment ? <Money value={enrollment.total_amount} /> : "—"}</td><td>{enrollment ? <Money value={enrollment.amount_paid} /> : "—"}</td><td>{enrollment ? <Money value={enrollment.balance_due} /> : "—"}</td><td>{enrollment ? <StatusBadge value={enrollment.status} /> : "—"}</td><td>{segment ? <div><strong>گروه {segment.segment + 1}</strong><small>{segment.behavioral_description}</small><small>مدل {segment.model_version} · <DateText value={segment.as_of} /></small></div> : <button className="button button--secondary" disabled={runningId === student.id || !enrollment} onClick={() => void cluster(student)}>{runningId === student.id ? "در حال تحلیل…" : "تحلیل دانش‌آموز"}</button>}</td></tr>; })}</tbody></table></div>
    </section>
  </>;
}
