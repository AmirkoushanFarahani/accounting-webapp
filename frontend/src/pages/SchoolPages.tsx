import { useMemo, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  DateField,
  DateText,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Modal,
  Money,
  MoneyInput,
  PageHeader,
  StatusBadge,
} from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { todayIso } from "../utils/date";
import type {
  Course,
  DiscountCode,
  EnrollmentPayment,
  Student,
} from "../types/api";

export const grades = [
  ["GRADE_1", "دوره اول دبستان · کلاس اول"],
  ["GRADE_2", "دوره اول دبستان · کلاس دوم"],
  ["GRADE_3", "دوره اول دبستان · کلاس سوم"],
  ["GRADE_4", "دوره دوم دبستان · کلاس چهارم"],
  ["GRADE_5", "دوره دوم دبستان · کلاس پنجم"],
  ["GRADE_6", "دوره دوم دبستان · کلاس ششم"],
  ["GRADE_7", "متوسطه اول · کلاس هفتم"],
  ["GRADE_8", "متوسطه اول · کلاس هشتم"],
  ["GRADE_9", "متوسطه اول · کلاس نهم"],
  ["GRADE_10", "متوسطه دوم · کلاس دهم"],
  ["GRADE_11", "متوسطه دوم · کلاس یازدهم"],
  ["GRADE_12", "متوسطه دوم · کلاس دوازدهم"],
] as const;
const gradeName = (value: string) =>
  grades.find(([key]) => key === value)?.[1] ?? value;
const methodName: Record<string, string> = {
  CASH: "نقدی",
  BANK_TRANSFER: "انتقال بانکی",
  CHECK: "چک",
  INSTALLMENT: "اقساطی",
};

export function CoursesPage() {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const [discount, setDiscount] = useState(false);
  const courses = useAsync(() => api.get<Course[]>("/school/courses"), []);
  const discounts = useAsync(
    () =>
      can("school:manage")
        ? api.get<DiscountCode[]>("/school/discounts")
        : Promise.resolve([]),
    [can],
  );
  return (
    <>
      <PageHeader
        title="دوره‌ها و شهریه‌ها"
        description="مدیر مدرسه دوره‌های هر پایه، قیمت و کدهای تخفیف را تعریف می‌کند."
        action={
          can("school:manage") && (
            <div className="button-row">
              <button
                className="button button--secondary"
                onClick={() => setDiscount(true)}
              >
                کد تخفیف جدید
              </button>
              <button
                className="button button--primary"
                onClick={() => setOpen(true)}
              >
                دوره جدید
              </button>
            </div>
          )
        }
      />
      {courses.loading ? (
        <LoadingState />
      ) : courses.error ? (
        <ErrorState message={courses.error} retry={courses.reload} />
      ) : courses.data?.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>دوره</th>
                <th>پایه</th>
                <th>شهریه</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {courses.data.map((course) => (
                <tr key={course.id}>
                  <td>{course.name}</td>
                  <td>{gradeName(course.grade)}</td>
                  <td>
                    <Money value={course.price} />
                  </td>
                  <td>
                    <StatusBadge
                      value={course.is_active ? "ACTIVE" : "INACTIVE"}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="هنوز دوره‌ای تعریف نشده است"
          detail="مدیر باید ابتدا برای هر پایه دوره و شهریه ثبت کند."
        />
      )}
      {can("school:manage") && (
        <section className="card">
          <h2 className="card-title">کدهای تخفیف</h2>
          {discounts.data?.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>کد</th>
                    <th>درصد</th>
                    <th>تاریخ انقضا</th>
                    <th>دفعات استفاده</th>
                  </tr>
                </thead>
                <tbody>
                  {discounts.data.map((code) => (
                    <tr key={code.id}>
                      <td dir="ltr">{code.code}</td>
                      <td>{code.percentage}٪</td>
                      <td>
                        {code.expires_on ? (
                          <DateText value={code.expires_on} />
                        ) : (
                          "بدون انقضا"
                        )}
                      </td>
                      <td>
                        {code.uses_count}
                        {code.max_uses ? ` از ${code.max_uses}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="کد تخفیفی ثبت نشده است" />
          )}
        </section>
      )}
      {open && (
        <CourseForm
          close={() => setOpen(false)}
          saved={() => {
            setOpen(false);
            void courses.reload();
          }}
        />
      )}{" "}
      {discount && (
        <DiscountForm
          close={() => setDiscount(false)}
          saved={() => {
            setDiscount(false);
            void discounts.reload();
          }}
        />
      )}
    </>
  );
}

function CourseForm({
  close,
  saved,
}: {
  close: () => void;
  saved: () => void;
}) {
  const [price, setPrice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api.post("/school/courses", {
        name: f.get("name"),
        grade: f.get("grade"),
        price,
      });
      saved();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "ثبت دوره ناموفق بود.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open title="دوره جدید" onClose={close}>
      <form className="form" onSubmit={submit}>
        {error && <p className="alert alert--error">{error}</p>}
        <Field label="نام دوره">
          <input name="name" required placeholder="مثلاً ریاضی تقویتی" />
        </Field>
        <GradeField />
        <Field label="شهریه (ریال)">
          <MoneyInput value={price} onValueChange={setPrice} required min="0" />
        </Field>
        <button className="button button--primary" disabled={busy}>
          {busy ? "در حال ثبت…" : "ثبت دوره"}
        </button>
      </form>
    </Modal>
  );
}
function DiscountForm({
  close,
  saved,
}: {
  close: () => void;
  saved: () => void;
}) {
  const [expiresOn, setExpiresOn] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    try {
      await api.post("/school/discounts", {
        code: f.get("code"),
        percentage: f.get("percentage"),
        expires_on: expiresOn || null,
        max_uses: f.get("max_uses") || null,
      });
      saved();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "ثبت کد تخفیف ناموفق بود.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open title="کد تخفیف جدید" onClose={close}>
      <form className="form" onSubmit={submit}>
        {error && <p className="alert alert--error">{error}</p>}
        <Field label="کد تخفیف">
          <input name="code" dir="ltr" required placeholder="SCHOOL10" />
        </Field>
        <Field label="درصد تخفیف">
          <input
            name="percentage"
            type="number"
            min="1"
            max="100"
            step="0.01"
            required
          />
        </Field>
        <DateField
          label="تاریخ انقضا (اختیاری)"
          value={expiresOn}
          onChange={setExpiresOn}
        />
        <Field label="حداکثر استفاده (اختیاری)">
          <input name="max_uses" type="number" min="1" />
        </Field>
        <button className="button button--primary" disabled={busy}>
          {busy ? "در حال ثبت…" : "ثبت کد"}
        </button>
      </form>
    </Modal>
  );
}

export function StudentsPage() {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const students = useAsync(() => api.get<Student[]>("/school/students"), []);
  return (
    <>
      <PageHeader
        title="دانش‌آموزان"
        description="پرونده دانش‌آموز، دوره‌های انتخاب‌شده، شهریه و وضعیت پرداخت در یک محل ثبت می‌شود."
        action={
          can("school:enroll") && (
            <button
              className="button button--primary"
              onClick={() => setOpen(true)}
            >
              ثبت‌نام دانش‌آموز
            </button>
          )
        }
      />
      {students.loading ? (
        <LoadingState />
      ) : students.error ? (
        <ErrorState message={students.error} retry={students.reload} />
      ) : students.data?.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>دانش‌آموز</th>
                <th>پایه</th>
                <th>ولی</th>
                <th>دوره‌ها</th>
                <th>مانده</th>
                <th>وضعیت</th>
                <th>پرداخت‌ها</th>
              </tr>
            </thead>
            <tbody>
              {students.data.map((student) => {
                const enrollment = student.enrollments[0];
                return (
                  <tr key={student.id}>
                    <td>
                      <strong>{student.full_name}</strong>
                      <small dir="ltr">{student.national_id}</small>
                    </td>
                    <td>{gradeName(student.grade)}</td>
                    <td>
                      {student.guardian_full_name}
                      <small dir="ltr">{student.guardian_phone}</small>
                    </td>
                    <td>
                      {enrollment?.courses
                        .map((course) => course.course_name)
                        .join("، ") ?? "—"}
                    </td>
                    <td>
                      {enrollment ? (
                        <Money value={enrollment.balance_due} />
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {enrollment ? (
                        <StatusBadge value={enrollment.status} />
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {enrollment ? (
                        <PaymentActions
                          payments={enrollment.payments}
                          reload={students.reload}
                          enabled={can("school:payments")}
                        />
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="دانش‌آموزی ثبت نشده است"
          detail="کارمند می‌تواند از همین صفحه ثبت‌نام جدید را آغاز کند."
        />
      )}
      {open && (
        <StudentRegistrationForm
          close={() => setOpen(false)}
          saved={() => {
            setOpen(false);
            void students.reload();
          }}
        />
      )}
    </>
  );
}

function StudentRegistrationForm({
  close,
  saved,
}: {
  close: () => void;
  saved: () => void;
}) {
  const [birthDate, setBirthDate] = useState("");
  const [registrationDate, setRegistrationDate] = useState(todayIso());
  const [firstExamDate, setFirstExamDate] = useState("");
  const [grade, setGrade] = useState("");
  const [academicTrack, setAcademicTrack] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [bookVoucher, setBookVoucher] = useState(false);
  const [examRegistered, setExamRegistered] = useState(false);
  const [payments, setPayments] = useState<
    Array<{
      amount: string;
      method: string;
      due_date: string;
      tracking_code: string;
      sayad_id: string;
    }>
  >([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const courses = useAsync(() => api.get<Course[]>("/school/courses"), []);
  const available = useMemo(
    () =>
      courses.data?.filter(
        (course) => course.grade === grade && course.is_active,
      ) ?? [],
    [courses.data, grade],
  );
  const needsAcademicTrack = ["GRADE_10", "GRADE_11", "GRADE_12"].includes(
    grade,
  );
  const chosen = available.filter((course) => selected.includes(course.id));
  const courseTotal = chosen.reduce(
    (total, course) => total + Number(course.price),
    0,
  );
  const plannedTotal = payments.reduce(
    (total, payment) => total + Number(payment.amount || 0),
    0,
  );
  const previewBalance = Math.max(0, courseTotal - plannedTotal);
  const updatePayment = (
    index: number,
    patch: Partial<(typeof payments)[number]>,
  ) =>
    setPayments((list) =>
      list.map((row, itemIndex) =>
        itemIndex === index ? { ...row, ...patch } : row,
      ),
    );

  function toggleCourse(courseId: string) {
    setSelected((current) =>
      current.includes(courseId)
        ? current.filter((id) => id !== courseId)
        : [...current, courseId],
    );
  }
  function addPayment() {
    setPayments((current) => [
      ...current,
      {
        amount: "",
        method: "CASH",
        due_date: todayIso(),
        tracking_code: "",
        sayad_id: "",
      },
    ]);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected.length || busy) return;
    const form = new FormData(event.currentTarget);
    const firstName = String(form.get("first_name") ?? "").trim();
    const lastName = String(form.get("last_name") ?? "").trim();
    setBusy(true);
    setError("");
    try {
      await api.post("/school/students/enroll", {
        full_name: `${firstName} ${lastName}`.trim(),
        national_id: form.get("national_id"),
        student_phone: form.get("student_phone") || null,
        birth_date: birthDate,
        registration_date: registrationDate || null,
        first_exam_date: firstExamDate || null,
        grade,
        academic_track: academicTrack || null,
        book_voucher_eligible: bookVoucher,
        exam_registered: examRegistered,
        guardian_full_name: form.get("guardian_full_name"),
        guardian_phone: form.get("guardian_phone"),
        address: form.get("address") || null,
        previous_school: form.get("previous_school") || null,
        emergency_contact: form.get("emergency_contact") || null,
        notes: form.get("notes") || null,
        course_ids: selected,
        discount_code: form.get("discount_code") || null,
        payments: payments.map((payment) => ({
          ...payment,
          due_date: payment.due_date || null,
          tracking_code: payment.tracking_code || null,
          sayad_id: payment.sayad_id || null,
        })),
      });
      saved();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "ثبت‌نام ناموفق بود.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open wide title="فرم ثبت‌نام دانش‌آموز" onClose={close}>
      <form className="form" onSubmit={submit}>
        {error && <p className="alert alert--error">{error}</p>}
        <section className="card">
          <h2 className="card-title">اطلاعات ثبت‌نام</h2>
          <p className="form-description">
            شماره پرونده پس از ذخیره به‌صورت خودکار ایجاد می‌شود.
          </p>
          <div className="form-grid form-grid--3">
            <DateField
              label="تاریخ ثبت‌نام"
              value={registrationDate}
              onChange={setRegistrationDate}
              required
            />
            <DateField
              label="تاریخ شروع اولین آزمون"
              value={firstExamDate}
              onChange={setFirstExamDate}
            />
            <GradeField
              value={grade}
              onChange={(value) => {
                setGrade(value);
                setSelected([]);
                if (!["GRADE_10", "GRADE_11", "GRADE_12"].includes(value))
                  setAcademicTrack("");
              }}
            />
          </div>
          {needsAcademicTrack && (
            <Field label="رشته تحصیلی">
              <select
                value={academicTrack}
                onChange={(event) => setAcademicTrack(event.target.value)}
                required
              >
                <option value="">انتخاب رشته</option>
                <option value="EXPERIMENTAL">تجربی</option>
                <option value="MATHEMATICS_PHYSICS">ریاضی فیزیک</option>
                <option value="HUMANITIES">انسانی</option>
              </select>
            </Field>
          )}
        </section>
        <section className="card">
          <h2 className="card-title">اطلاعات دانش‌آموز</h2>
          <div className="form-grid form-grid--3">
            <Field label="نام دانش‌آموز">
              <input name="first_name" required />
            </Field>
            <Field label="نام خانوادگی دانش‌آموز">
              <input name="last_name" required />
            </Field>
            <Field label="کد ملی">
              <input name="national_id" dir="ltr" required />
            </Field>
            <Field label="تلفن همراه دانش‌آموز">
              <input name="student_phone" dir="ltr" />
            </Field>
            <DateField
              label="تاریخ تولد"
              value={birthDate}
              onChange={setBirthDate}
              required
            />
          </div>
        </section>
        <section className="card">
          <h2 className="card-title">اطلاعات ولی و تماس</h2>
          <div className="form-grid form-grid--2">
            <Field label="نام و نام خانوادگی ولی">
              <input name="guardian_full_name" required />
            </Field>
            <Field label="تلفن همراه ولی">
              <input name="guardian_phone" dir="ltr" required />
            </Field>
            <Field label="مدرسه قبلی (اختیاری)">
              <input name="previous_school" />
            </Field>
            <Field label="تماس اضطراری (اختیاری)">
              <input name="emergency_contact" />
            </Field>
          </div>
          <Field label="نشانی (اختیاری)">
            <textarea name="address" />
          </Field>
          <Field label="توضیحات (اختیاری)">
            <textarea name="notes" />
          </Field>
        </section>
        <section className="card">
          <h2 className="card-title">خدمات آموزشی و شهریه</h2>
          <div className="form-grid form-grid--2">
            <Field label="مشمول بن کتاب">
              <select
                value={bookVoucher ? "YES" : "NO"}
                onChange={(event) =>
                  setBookVoucher(event.target.value === "YES")
                }
              >
                <option value="NO">خیر</option>
                <option value="YES">بله</option>
              </select>
            </Field>
            <Field label="ثبت‌نام آزمون">
              <select
                value={examRegistered ? "YES" : "NO"}
                onChange={(event) =>
                  setExamRegistered(event.target.value === "YES")
                }
              >
                <option value="NO">خیر</option>
                <option value="YES">بله</option>
              </select>
            </Field>
          </div>
          {!grade ? (
            <p>ابتدا پایه تحصیلی را انتخاب کنید.</p>
          ) : courses.loading ? (
            <LoadingState />
          ) : available.length ? (
            <div className="course-picker">
              {available.map((course) => (
                <label key={course.id} className="course-choice">
                  <input
                    type="checkbox"
                    checked={selected.includes(course.id)}
                    onChange={() => toggleCourse(course.id)}
                  />
                  <span>
                    <strong>{course.name}</strong>
                    {course.instructor_name && (
                      <small>دبیر: {course.instructor_name}</small>
                    )}
                  </span>
                  <Money value={course.price} />
                </label>
              ))}
            </div>
          ) : (
            <p className="alert alert--warning">
              برای این پایه هنوز دوره فعالی تعریف نشده است.
            </p>
          )}
          <Field label="کد تخفیف (اختیاری)">
            <input
              name="discount_code"
              dir="ltr"
              placeholder="کد تخفیف را وارد کنید"
            />
          </Field>
          <div className="detail-grid">
            <p>
              شهریه کلاس‌ها: <Money value={courseTotal} />
            </p>
            <p>تخفیف: پس از بررسی کد تخفیف محاسبه می‌شود</p>
            <p>شهریه نهایی: در زمان ذخیره توسط سامانه محاسبه می‌شود</p>
          </div>
        </section>
        <section className="card">
          <h2 className="card-title">پرداختی‌های دانش‌آموز</h2>
          <p className="form-description">
            برای هر قسط یا چک یک ردیف اضافه کنید. نقدی و انتقال بانکی همان لحظه
            پرداخت‌شده ثبت می‌شوند.
          </p>
          {payments.map((payment, index) => (
            <div className="form-grid form-grid--3" key={index}>
              <Field label="مبلغ">
                <MoneyInput
                  value={payment.amount}
                  onValueChange={(amount) => updatePayment(index, { amount })}
                  required
                />
              </Field>
              <Field label="نوع پرداخت">
                <select
                  value={payment.method}
                  onChange={(event) =>
                    updatePayment(index, { method: event.target.value })
                  }
                >
                  {Object.entries(methodName).map(([key, label]) => (
                    <option value={key} key={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              {(payment.method === "CHECK" || payment.method === "INSTALLMENT") && (
                <DateField
                  label={payment.method === "CHECK" ? "تاریخ سررسید چک" : "تاریخ سررسید قسط"}
                  value={payment.due_date}
                  onChange={(due_date) => updatePayment(index, { due_date })}
                  required
                />
              )}
              <Field label="کد پیگیری (اختیاری)">
                <input
                  value={payment.tracking_code}
                  onChange={(event) =>
                    updatePayment(index, { tracking_code: event.target.value })
                  }
                />
              </Field>
              <Field label="شناسه صیادی (اختیاری)">
                <input
                  dir="ltr"
                  value={payment.sayad_id}
                  onChange={(event) =>
                    updatePayment(index, { sayad_id: event.target.value })
                  }
                />
              </Field>
              <button
                type="button"
                className="button button--secondary"
                onClick={() =>
                  setPayments((list) =>
                    list.filter((_, itemIndex) => itemIndex !== index),
                  )
                }
              >
                حذف
              </button>
            </div>
          ))}
          <button
            type="button"
            className="button button--secondary"
            onClick={addPayment}
          >
            + افزودن پرداخت
          </button>
          <div className="detail-grid">
            <p>
              جمع پرداخت‌های ثبت‌شده: <Money value={plannedTotal} />
            </p>
            <p>
              مانده پیش‌نمایش: <Money value={previewBalance} />
            </p>
          </div>
        </section>
        <button
          className="button button--primary"
          disabled={busy || !selected.length}
        >
          {busy ? "در حال ذخیره…" : "ثبت‌نام و ذخیره پرونده"}
        </button>
      </form>
    </Modal>
  );
}

function PaymentActions({
  payments,
  reload,
  enabled,
}: {
  payments: EnrollmentPayment[];
  reload: () => Promise<void>;
  enabled: boolean;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const pending = payments.filter((payment) => payment.status === "PENDING");
  if (!payments.length) return <>—</>;
  return (
    <div className="button-row">
      {payments.map((payment) => (
        <span key={payment.id}>
          <StatusBadge value={payment.status} />
          {enabled && payment.status === "PENDING" && (
            <button
              className="text-button"
              disabled={busy === payment.id}
              onClick={() => {
                setBusy(payment.id);
                void api
                  .patch(`/school/payments/${payment.id}`, { status: "PAID" })
                  .then(reload)
                  .finally(() => setBusy(null));
              }}
            >
              وصول شد
            </button>
          )}
        </span>
      ))}
    </div>
  );
}

function GradeField({
  value,
  onChange,
}: {
  value?: string;
  onChange?: (value: string) => void;
}) {
  return (
    <Field label="پایه تحصیلی">
      <select
        name="grade"
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        required
      >
        <option value="">انتخاب پایه</option>
        {grades.map(([key, label]) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
      </select>
    </Field>
  );
}

function EnrollmentForm({
  close,
  saved,
}: {
  close: () => void;
  saved: () => void;
}) {
  const [birthDate, setBirthDate] = useState("");
  const [grade, setGrade] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [payments, setPayments] = useState<
    Array<{
      amount: string;
      method: string;
      due_date: string;
      tracking_code: string;
      sayad_id: string;
    }>
  >([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const courses = useAsync(() => api.get<Course[]>("/school/courses"), []);
  const available = useMemo(
    () =>
      courses.data?.filter(
        (course) => course.grade === grade && course.is_active,
      ) ?? [],
    [courses.data, grade],
  );
  const chosen = available.filter((course) => selected.includes(course.id));
  const subtotal = chosen.reduce(
    (total, course) => total + Number(course.price),
    0,
  );
  const planned = payments.reduce(
    (total, payment) => total + Number(payment.amount || 0),
    0,
  );
  function toggle(courseId: string) {
    setSelected((current) =>
      current.includes(courseId)
        ? current.filter((id) => id !== courseId)
        : [...current, courseId],
    );
  }
  function addPayment() {
    setPayments((current) => [
      ...current,
      {
        amount: "",
        method: "CASH",
        due_date: todayIso(),
        tracking_code: "",
        sayad_id: "",
      },
    ]);
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected.length || busy) return;
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api.post("/school/students/enroll", {
        full_name: f.get("full_name"),
        national_id: f.get("national_id"),
        birth_date: birthDate,
        grade,
        guardian_full_name: f.get("guardian_full_name"),
        guardian_phone: f.get("guardian_phone"),
        address: f.get("address") || null,
        previous_school: f.get("previous_school") || null,
        emergency_contact: f.get("emergency_contact") || null,
        notes: f.get("notes") || null,
        course_ids: selected,
        discount_code: f.get("discount_code") || null,
        payments: payments.map((payment) => ({
          ...payment,
          due_date: payment.due_date || null,
          tracking_code: payment.tracking_code || null,
          sayad_id: payment.sayad_id || null,
        })),
      });
      saved();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "ثبت‌نام ناموفق بود.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open wide title="ثبت‌نام دانش‌آموز" onClose={close}>
      <form className="form" onSubmit={submit}>
        {error && <p className="alert alert--error">{error}</p>}
        <div className="form-grid form-grid--2">
          <Field label="نام و نام خانوادگی">
            <input name="full_name" required />
          </Field>
          <Field label="کد ملی">
            <input name="national_id" dir="ltr" required />
          </Field>
          <DateField
            label="تاریخ تولد"
            value={birthDate}
            onChange={setBirthDate}
            required
          />
          <GradeField
            value={grade}
            onChange={(value) => {
              setGrade(value);
              setSelected([]);
            }}
          />
          <Field label="نام ولی">
            <input name="guardian_full_name" required />
          </Field>
          <Field label="تلفن ولی">
            <input name="guardian_phone" dir="ltr" required />
          </Field>
          <Field label="مدرسه قبلی (اختیاری)">
            <input name="previous_school" />
          </Field>
          <Field label="تماس اضطراری (اختیاری)">
            <input name="emergency_contact" />
          </Field>
        </div>
        <Field label="نشانی (اختیاری)">
          <textarea name="address" />
        </Field>
        <Field label="یادداشت (اختیاری)">
          <textarea name="notes" />
        </Field>
        <Field label="کد تخفیف (اختیاری)">
          <input name="discount_code" dir="ltr" placeholder="کد را وارد کنید" />
        </Field>
        <section className="card">
          <h2 className="card-title">انتخاب دوره‌ها</h2>
          {!grade ? (
            <p>ابتدا پایه تحصیلی را انتخاب کنید.</p>
          ) : courses.loading ? (
            <LoadingState />
          ) : available.length ? (
            <div className="course-picker">
              {available.map((course) => (
                <label key={course.id} className="course-choice">
                  <input
                    type="checkbox"
                    checked={selected.includes(course.id)}
                    onChange={() => toggle(course.id)}
                  />
                  <span>{course.name}</span>
                  <Money value={course.price} />
                </label>
              ))}
            </div>
          ) : (
            <p className="alert alert--warning">
              برای این پایه هنوز دوره فعالی تعریف نشده است.
            </p>
          )}
          <p className="allocation-total">
            جمع شهریه پیش از تخفیف: <Money value={subtotal} />
          </p>
        </section>
        <section className="card">
          <h2 className="card-title">روش پرداخت</h2>
          <p>
            برای نقدی و انتقال بانکی، پرداخت همان لحظه ثبت می‌شود. چک و اقساط تا
            زمان وصول، در انتظار می‌مانند.
          </p>
          {payments.map((payment, index) => (
            <div className="form-grid form-grid--3" key={index}>
              <Field label="مبلغ">
                <MoneyInput
                  value={payment.amount}
                  onValueChange={(amount) =>
                    setPayments((list) =>
                      list.map((row, i) =>
                        i === index ? { ...row, amount } : row,
                      ),
                    )
                  }
                  required
                />
              </Field>
              <Field label="روش">
                <select
                  value={payment.method}
                  onChange={(e) =>
                    setPayments((list) =>
                      list.map((row, i) =>
                        i === index ? { ...row, method: e.target.value } : row,
                      ),
                    )
                  }
                >
                  {Object.entries(methodName).map(([key, label]) => (
                    <option value={key} key={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              {(payment.method === "CHECK" || payment.method === "INSTALLMENT") && (
                <DateField
                  label={payment.method === "CHECK" ? "تاریخ سررسید چک" : "تاریخ سررسید قسط"}
                  value={payment.due_date}
                  onChange={(due_date) =>
                    setPayments((list) =>
                      list.map((row, i) =>
                        i === index ? { ...row, due_date } : row,
                      ),
                    )
                  }
                  required
                />
              )}
              <Field label="کد پیگیری (اختیاری)">
                <input
                  value={payment.tracking_code}
                  onChange={(e) =>
                    setPayments((list) =>
                      list.map((row, i) =>
                        i === index
                          ? { ...row, tracking_code: e.target.value }
                          : row,
                      ),
                    )
                  }
                />
              </Field>
              <Field label="شناسه صیادی (اختیاری)">
                <input
                  dir="ltr"
                  value={payment.sayad_id}
                  onChange={(e) =>
                    setPayments((list) =>
                      list.map((row, i) =>
                        i === index
                          ? { ...row, sayad_id: e.target.value }
                          : row,
                      ),
                    )
                  }
                />
              </Field>
              <button
                type="button"
                className="button button--secondary"
                onClick={() =>
                  setPayments((list) => list.filter((_, i) => i !== index))
                }
              >
                حذف
              </button>
            </div>
          ))}
          <button
            type="button"
            className="button button--secondary"
            onClick={addPayment}
          >
            + افزودن پرداخت
          </button>
          <p className="allocation-total">
            جمع برنامه پرداخت: <Money value={planned} />
          </p>
        </section>
        <button
          className="button button--primary"
          disabled={busy || !selected.length}
        >
          {busy ? "در حال ثبت…" : "ثبت‌نام و ذخیره پرونده"}
        </button>
      </form>
    </Modal>
  );
}
