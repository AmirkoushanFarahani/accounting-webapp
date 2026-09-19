import { EmptyState, ErrorState, LoadingState, Money, PageHeader, StatusBadge } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { Link } from "../routes/router";
import { api } from "../services/api";
import type { Student } from "../types/api";

export function StudentRecordsPage() {
  const state = useAsync(() => api.get<Student[]>("/school/students"), []);
  return <><PageHeader title="پرونده مشتریان / دانش‌آموزان" description="فهرست کامل دانش‌آموزان ثبت‌شده در این آموزشگاه. برای مشاهده جزئیات، روی پرونده کلیک کنید." />
    {state.loading ? <LoadingState /> : state.error ? <ErrorState message={state.error} retry={state.reload} /> : !state.data?.length ? <EmptyState title="پرونده‌ای ثبت نشده است" /> : <div className="table-wrap"><table><thead><tr><th>دانش‌آموز</th><th>ولی</th><th>خدمات</th><th>مانده</th><th>وضعیت</th><th>پرونده</th></tr></thead><tbody>{state.data.map((student) => { const enrollment = student.enrollments[0]; return <tr key={student.id}><td>{student.full_name}<small dir="ltr">{student.national_id}</small></td><td>{student.guardian_full_name}<small dir="ltr">{student.guardian_phone}</small></td><td>{enrollment?.courses.map((course) => course.course_name).join("، ") ?? "—"}</td><td>{enrollment ? <Money value={enrollment.balance_due} /> : "—"}</td><td>{enrollment ? <StatusBadge value={enrollment.status} /> : "—"}</td><td><Link className="button button--secondary" to={`/students/${student.id}`}>مشاهده کامل</Link></td></tr>; })}</tbody></table></div>}</>;
}
