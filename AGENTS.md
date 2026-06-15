You are acting as a senior Odoo developer pair-programming with me on a technical
assessment. We are building a single Odoo addon called `nn_fund_management`.

ENVIRONMENT / CONSTRAINTS
- Odoo version: 17.0 (Community Edition), Python 3.10+, PostgreSQL (Odoo's built-in ORM —
  do NOT design a separate database schema or use any non-Odoo ORM/framework).
- The module lives at addons/nn_fund_management inside a standard Odoo source checkout,
  run via docker-compose (odoo + postgres services).
- All persistence goes through Odoo models (models.Model / models.AbstractModel). Use
  fields.Monetary with a currency_id / company_id, not plain Float, for money fields.
- UI = standard Odoo backend: XML form/list/kanban/search views, menus, window actions,
  and (only for the bonus dashboard) OWL components under static/src.
- No hardcoded user IDs, database IDs, or company IDs anywhere. No raw SQL unless there is
  no reasonable ORM equivalent — if you must use raw SQL, add a code comment explaining why.
- Every monetary/state-changing model must extend `mail.thread` and `mail.activity.mixin`
  so chatter gives us the audit trail "for free" (creator, dates, messages, activities).
- Write docstrings and inline comments as if explaining the code to someone who will be
  interviewed on it — clarity over cleverness.

DOMAIN MODEL (target design — refine if you see a cleaner Odoo-idiomatic approach, but tell
me what you changed and why)

- fund.account            Bank/cash accounts. Fields: name, account_type
                           (selection: bank/cash/other), company_id, currency_id, and
                           computed: total_received, unassigned_balance, held_amount,
                           assigned_amount.

- fund.incoming           Incoming fund transactions. Fields: fund_account_id, date, amount
                           (Monetary), transaction_reference (Char), partner_id (sender/
                           source), description, attachment (Binary), company_id,
                           state (draft/confirmed). SQL/ORM constraint: transaction_reference
                           must be unique per fund_account_id. On confirm, increases the
                           fund account's unassigned_balance.

- fund.expense.head        Simple master data: name, code, company_id, active.

- fund.budget.line          The unified "allocation target" — represents either a
                           project.project or a fund.expense.head. Fields: name,
                           target_type (selection: project/expense_head), project_id
                           (Many2one project.project), expense_head_id (Many2one
                           fund.expense.head), company_id, and computed balance fields:
                           total_allocated, available, requisition_hold, transfer_hold,
                           approved_unspent, total_spent, incoming_transfers,
                           outgoing_transfers. Constraint: exactly one of project_id /
                           expense_head_id must be set, matching target_type. All balance
                           fields are computed (store=True, recomputed via dependencies) and
                           NOT manually editable (readonly in views AND no write access via
                           ACL on those fields' "logical" meaning — enforce via compute,
                           never via direct write).

- fund.approval.mixin      AbstractModel providing: state (selection: draft/submitted/
                           gm_approval/md_approval/approved/rejected/cancelled, default
                           draft, plus extra states per model where noted), approval_ids
                           (One2many to fund.approval.line), and methods
                           action_submit / action_gm_approve / action_md_approve /
                           action_reject / action_cancel. Concrete models override hook
                           methods (_on_submit, _on_gm_approve, _on_md_approve,
                           _on_reject, _on_cancel) to apply their own balance-movement
                           side effects. The mixin must guard against duplicate
                           approvals/fund movements (idempotency) — e.g. check current
                           state before acting, never re-apply a hold/release.

- fund.approval.line       History rows: res_model, res_id (or a Reference field),
                           approver_id, approval_level (selection: gm/md/other), date,
                           comment, result (approved/rejected). Created automatically by
                           the mixin on every decision — never user-editable afterward.

- fund.allocation          request_number (via ir.sequence), fund_account_id,
                           budget_line_id (target), amount, purpose, request_date,
                           requested_by (Many2one res.users), attachment, inherits
                           fund.approval.mixin. Workflow: Draft -> Submitted ->
                           GM Approval -> MD Approval -> Approved / Rejected / Cancelled.
                           On submit: amount moved from fund_account unassigned_balance to
                           held; block if amount > available unassigned balance. On
                           approve: held amount becomes budget_line.total_allocated /
                           available. On reject/cancel: held amount returns to unassigned.

- fund.requisition         requisition_number (ir.sequence), budget_line_id,
                           requested_amount, purpose, request_date, required_date,
                           requested_by, attachment, remaining_billable_amount
                           (computed), inherits fund.approval.mixin, extra states
                           Closed. Workflow: Draft -> Submitted -> GM Approval ->
                           MD Approval -> Approved / Rejected / Cancelled / Closed. On
                           submit: amount placed on requisition_hold on the budget line;
                           block if > available. On approve: amount stays reserved
                           (requisition_hold), remaining_billable_amount = approved amount.
                           On reject/cancel: hold released back to available.

- fund.bill                bill_number (ir.sequence), requisition_id (Many2one
                           fund.requisition, required, domain restricted to approved
                           requisitions), budget_line_id (related/compute from
                           requisition, stored, used for the "same project/expense head"
                           check), amount, date, state (draft/posted/cancelled).
                           Constraints: budget_line_id must equal requisition's
                           budget_line_id; sum of posted bills for a requisition must not
                           exceed requisition.requested_amount (approved amount); a single
                           bill cannot exceed requisition.remaining_billable_amount at the
                           time of posting. On post: decreases
                           requisition.remaining_billable_amount and increases
                           budget_line.total_spent (and requisition_hold decreases by the
                           same amount). On cancel/reverse of a posted bill: reverse both
                           effects exactly (no new funds created — clamp/validate).

- fund.transfer            transfer_number (ir.sequence), source_budget_line_id,
                           destination_budget_line_id, amount, reason, requested_by,
                           request_date, inherits fund.approval.mixin. Constraint:
                           source != destination. On submit: amount deducted from
                           source.available and placed in source.transfer_hold; block if
                           amount > source available. On approve: transfer_hold on source
                           is cleared, destination.total_allocated/available increases by
                           amount. On reject/cancel: amount returns to source.available.

SECURITY (build incrementally, finalize in the security phase)
Groups: Fund User, Finance User, GM Approver, MD Approver, Fund Administrator (all defined
in XML under nn_fund_management/security/, never hardcoded in Python). Record rules must
restrict by company (multi-company safe) and by "own records vs all records" where the spec
implies it. ACL (ir.model.access.csv) must give each group the minimum rights it needs.

GENERAL RULES
- Negative balances anywhere (unassigned, held, available, etc.) are a bug — add
  @api.constrains to make them impossible, not just UI validation.
- Every state transition must go through the approval mixin's action_* methods — never let
  a balance field be mutated from more than one code path.
- After generating code for a phase, list the files you created/changed and a one-paragraph
  summary of the design decisions, so I can review before we continue.