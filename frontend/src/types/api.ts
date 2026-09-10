export type UUID = string;
export type Money = string;
export type PipelineName = "transaction_classification" | "payment_delay_risk" | "cash_flow_forecast" | "customer_segmentation";
export type BusinessCategory = "RETAIL" | "EDUCATION" | "ONLINE" | "SERVICES";
export interface User { id: UUID; email: string | null; phone_number: string | null; first_name: string; last_name: string; is_active: boolean; plan_status: "FREE" | "PRO"; business_category: BusinessCategory; created_at: string; updated_at: string; last_login_at: string | null; roles: string[]; permissions: string[] }
export interface TokenResponse { access_token: string; token_type: string }
export interface RegisterRequest { email?: string | null; phone_number?: string | null; password: string; first_name: string; last_name: string; business_category?: BusinessCategory }
export interface Party { id: UUID; name: string; email: string | null; phone: string | null; address: string | null; is_customer: boolean; is_supplier: boolean; is_active: boolean; created_at: string; updated_at: string }
export interface Product { id: UUID; sku: string; name: string; description: string | null; unit: string; unit_price: Money; is_active: boolean; created_at: string; updated_at: string }
export interface AccountCategory { id: UUID; name: string; account_type: "ASSET" | "LIABILITY" | "EQUITY" | "REVENUE" | "EXPENSE" }
export type AccountPostingRole = "GENERAL" | "CASH" | "RECEIVABLE" | "REVENUE" | "TAX_LIABILITY" | "PAYABLE" | "EXPENSE" | "CUSTOMER_CREDIT";
export interface Account { id: UUID; code: string; name: string; category_id: UUID; parent_id: UUID | null; is_active: boolean; posting_role: AccountPostingRole }
export interface Period { id: UUID; name: string; start_date: string; end_date: string; status: string }
export interface JournalLine { id?: UUID; account_id: UUID; description: string | null; debit: Money; credit: Money }
export interface Journal { id: UUID; entry_number: string; entry_date: string; description: string; period_id: UUID; status: string; reversal_of_id: UUID | null; lines: JournalLine[] }
export interface InvoiceItem { id?: UUID; product_id: UUID | null; description: string; quantity: string; unit_price: Money | null; tax: Money; line_subtotal?: Money; line_total?: Money }
export interface InvoiceCheck { id: UUID; amount: Money; sayad_id: string | null; due_date: string; status: "PENDING" | "CLEARED" | "BOUNCED"; cleared_date: string | null; cleared_payment_id: UUID | null }
export interface Invoice { id: UUID; invoice_number: string; customer_id: UUID; issue_date: string; due_date: string; status: string; payment_method: "CASH" | "CHECK" | null; subtotal: Money; tax: Money; total: Money; amount_paid: Money; balance_due: Money; journal_id: UUID | null; items: InvoiceItem[]; checks: InvoiceCheck[]; created_at: string }
export interface Allocation { id?: UUID; invoice_id: UUID; amount: Money }
export interface Payment { id: UUID; party_id: UUID; payment_date: string; amount: Money; reference: string; method: string; sayad_id: string | null; customer_credit_account_id: UUID | null; status: string; journal_id: UUID | null; allocations: Allocation[] }
export interface BillItem { id?: UUID; product_id: UUID | null; description: string; quantity: string; unit_price: Money | null; tax: Money; line_subtotal?: Money; line_total?: Money }
export interface Bill { id: UUID; bill_number: string; supplier_id: UUID; issue_date: string; due_date: string; status: string; subtotal: Money; tax: Money; total: Money; amount_paid: Money; balance_due: Money; journal_id: UUID | null; items: BillItem[] }
export interface BillPaymentAllocation { id?: UUID; bill_id: UUID; amount: Money }
export interface BillPayment { id: UUID; party_id: UUID; payment_date: string; amount: Money; reference: string; method: string; sayad_id: string | null; status: string; journal_id: UUID | null; allocations: BillPaymentAllocation[] }
export interface AccountReportLine { account_id: UUID; code: string; name: string; account_type: string; debit: Money; credit: Money; balance: Money }
export interface DashboardReport { start_date: string | null; end_date: string | null; as_of: string; total_revenue: Money; total_expenses: Money; net_income: Money; net_cash_flow: Money; outstanding_invoices: Money; overdue_invoices: Money; outstanding_invoice_count: number; overdue_invoice_count: number }
export interface TrialBalance { start_date: string | null; end_date: string | null; lines: AccountReportLine[]; total_debit: Money; total_credit: Money; balanced: boolean }
export interface IncomeStatement { start_date: string | null; end_date: string | null; revenue: AccountReportLine[]; expenses: AccountReportLine[]; total_revenue: Money; total_expenses: Money; net_income: Money }
export interface AccountSummary { start_date: string | null; end_date: string | null; account_type: string; lines: AccountReportLine[]; total: Money }
export interface BalanceSheet { as_of: string; assets: AccountReportLine[]; liabilities: AccountReportLine[]; equity: AccountReportLine[]; total_assets: Money; total_liabilities: Money; total_equity: Money; current_earnings: Money; total_liabilities_and_equity: Money; balanced: boolean }
export interface ReceivableLine { invoice_id: UUID; invoice_number: string; customer_id: UUID; customer_name: string; issue_date: string; due_date: string; status: string; total: Money; amount_paid: Money; balance_due: Money; days_overdue: number }
export interface Receivables { as_of: string; customer_id: UUID | null; lines: ReceivableLine[]; total_outstanding: Money; total_overdue: Money }
export interface PayableLine { bill_id: UUID; bill_number: string; supplier_id: UUID; supplier_name: string; issue_date: string; due_date: string; status: string; total: Money; amount_paid: Money; balance_due: Money; days_overdue: number }
export interface Payables { as_of: string; lines: PayableLine[]; total_payables: Money; supplier_detail_available: boolean }
export interface CashFlowPoint { date: string; inflow: Money; outflow: Money; net: Money }
export interface CashFlow { start_date: string | null; end_date: string | null; points: CashFlowPoint[]; total_inflow: Money; total_outflow: Money; net_cash_flow: Money }
export interface PartyTransaction { kind: string; record_id: UUID; reference: string; date: string; amount: Money; status: string }
export interface CustomerSummary { party_id: UUID; name: string; email: string | null; phone: string | null; address: string | null; is_active: boolean; purchase_count: number; total_purchased: Money; total_received: Money; receivable_balance: Money; customer_credit_balance: Money; net_balance: Money; balance_direction: "CUSTOMER_OWES" | "BUSINESS_OWES" | "SETTLED" }
export interface CustomerPurchaseItem { description: string; quantity: string; unit_price: Money; tax: Money; line_total: Money }
export interface CustomerCheckHistory { check_id: UUID; amount: Money; sayad_id: string | null; due_date: string; status: string; cleared_date: string | null }
export interface CustomerInvoiceHistory { invoice_id: UUID; invoice_number: string; issue_date: string; due_date: string; status: string; subtotal: Money; tax: Money; total: Money; amount_paid: Money; balance_due: Money; items: CustomerPurchaseItem[]; checks: CustomerCheckHistory[] }
export interface CustomerPaymentHistory { payment_id: UUID; reference: string; payment_date: string; amount: Money; method: string; sayad_id: string | null; status: string }
export interface PartyHistory { party_id: UUID; party_name: string; start_date: string | null; end_date: string | null; email: string | null; phone: string | null; address: string | null; purchase_count: number; total_purchased: Money; total_received: Money; receivable_balance: Money; customer_credit_balance: Money; net_balance: Money; balance_direction: "CUSTOMER_OWES" | "BUSINESS_OWES" | "SETTLED"; invoices: CustomerInvoiceHistory[]; payments: CustomerPaymentHistory[]; transactions: PartyTransaction[] }
export interface ModelVersion { id: UUID; pipeline: PipelineName; model_version: string; artifact_schema_version: string; dataset_fingerprint: string; feature_schema: string[]; training_configuration: Record<string, unknown>; metrics: Record<string, number>; dependencies: Record<string, string>; synthetic_data: boolean; is_active: boolean; activated_at: string | null; created_at: string; updated_at: string }
export interface Feedback { id: UUID; prediction_id: UUID; feedback_type: string; actual_value: string | null; comment: string | null; submitted_by_id: UUID | null; submitted_at: string }
export interface Prediction { id: UUID; model_version_id: UUID; pipeline: PipelineName; source_type: string | null; source_id: string | null; predicted_value: Record<string, unknown>; confidence: number | null; review_required: boolean | null; explanation: Record<string, unknown> | null; requested_by_id: UUID | null; predicted_at: string; feedback: Feedback[] }
export interface ClassificationResult { prediction_id: UUID; category: string; confidence: number; manual_review: boolean; model_version: string; prediction_timestamp: string }
export interface RiskResult { prediction_id: UUID; invoice_id: UUID; risk_category: string; probability: number; model_version: string; explanation: Record<string, number>; explanation_scope: string; prediction_timestamp: string; as_of: string }
export interface ForecastPoint { date: string; predicted: number; lower: number; upper: number }
export interface ForecastResult { prediction_id: UUID; model_version: string; forecast_timestamp: string; as_of: string; horizon: number; points: ForecastPoint[] }
export interface SegmentResult { prediction_id: UUID; party_id: UUID; segment: number; behavioral_description: string; model_version: string; prediction_timestamp: string; as_of: string }
export type ApiErrorBody = { detail?: string | Array<{ msg?: string }> };
