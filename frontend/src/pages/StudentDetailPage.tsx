import { DateText, ErrorState, LoadingState, Money, PageHeader, StatusBadge } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { Link, useRouter } from "../routes/router";
import { api } from "../services/api";
import type { Student } from "../types/api";

export function StudentDetailPage() {
  const { path } = useRouter();
  const id = path.split("/").at(-1) ?? "";
  const state = useAsync(() => api.get<Student>(`/school/students/${id}`), [id]);
  if (state.loading) return <LoadingState />;
  if (state.error || !state.data) return <ErrorState message={state.error ?? "پرونده دانش‌آموز پیدا نشد."} retry={state.reload} />;
  const student = state.data;
  const enrollment = student.enrollments[0];
  return <><PageHeader title={student.full_name} description={`پرونده دانش‌آموز · کد ملی ${student.national_id}`} action={<Link className="button button--secondary" to="/students">بازگشت به دانش‌آموزان</Link>} />
    <section className="card"><h2 className="card-title">اطلاعات ثبت‌نام</h2><div className="detail-grid"><p><b>پایه:</b> {student.grade}</p><p><b>تاریخ ثبت‌نام:</b> <DateText value={student.registration_date}/></p><p><b>نام ولی:</b> {student.guardian_full_name}</p><p><b>تلفن ولی:</b> {student.guardian_phone}</p><p><b>تلفن دانش‌آموز:</b> {student.student_phone ?? "—"}</p><p><b>رشته:</b> {student.academic_track ?? "—"}</p></div></section>
    {enrollment && <><section className="card"><h2 className="card-title">خدمات و شهریه</h2><table><thead><tr><th>خدمت</th><th>مبلغ</th></tr></thead><tbody>{enrollment.courses.map((course) => <tr key={course.course_id}><td>{course.course_name}</td><td><Money value={course.price}/></td></tr>)}</tbody></table><div className="detail-grid"><p>جمع: <Money value={enrollment.subtotal}/></p><p>تخفیف: <Money value={enrollment.discount_amount}/></p><p>شهریه نهایی: <Money value={enrollment.total_amount}/></p><p>مانده: <Money value={enrollment.balance_due}/></p></div></section><section className="card"><h2 className="card-title">پرداخت‌ها</h2><table><thead><tr><th>روش</th><th>مبلغ</th><th>سررسید</th><th>وضعیت</th></tr></thead><tbody>{enrollment.payments.map((payment) => <tr key={payment.id}><td>{payment.method}</td><td><Money value={payment.amount}/></td><td>{payment.due_date ? <DateText value={payment.due_date}/> : "—"}</td><td><StatusBadge value={payment.status}/></td></tr>)}</tbody></table></section></>}</>;
}
