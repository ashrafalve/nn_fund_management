from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class FundBill(models.Model):
    """Bill against an approved requisition.

    Workflow: draft -> posted -> cancelled
    """

    _name = 'fund.bill'
    _description = 'Fund Bill'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ------------------------------------------------------------------ #
    # Sequence & identity
    # ------------------------------------------------------------------ #
    bill_number = fields.Char(
        string='Bill Number', required=True, readonly=True, copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('fund.bill')
    )
    requisition_id = fields.Many2one(
        'fund.requisition', string='Requisition', required=True,
        domain=[('state', '=', 'approved')], tracking=True
    )
    budget_line_id = fields.Many2one(
        'fund.budget.line', string='Budget Line', related='requisition_id.budget_line_id',
        store=True, readonly=True
    )
    amount = fields.Monetary(
        string='Amount', currency_field='currency_id', required=True, tracking=True
    )
    date = fields.Date(
        string='Date', required=True,
        default=fields.Date.context_today, tracking=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled'),
    ], string='State', required=True, default='draft', tracking=True)

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id
    )

    # ------------------------------------------------------------------ #
    # Constraints
    # ------------------------------------------------------------------ #
    @api.constrains('requisition_id', 'budget_line_id')
    def _check_budget_line_match(self):
        """A bill's budget_line must match its requisition's budget_line.

        This enforces "Project A cannot use Project B's requisition"
        at the model level.
        """
        for bill in self:
            if bill.requisition_id and bill.budget_line_id:
                if bill.requisition_id.budget_line_id.id != bill.budget_line_id.id:
                    raise ValidationError(_(
                        "Bill Budget Line '%s' does not match the Requisition's "
                        "Budget Line '%s'."
                    ) % (bill.budget_line_id.name, bill.requisition_id.budget_line_id.name))

    @api.constrains('requisition_id', 'amount', 'state')
    def _check_bill_amount_against_requisition(self):
        """Block if sum of non-cancelled bills would exceed requisition amount."""
        for bill in self:
            if not bill.requisition_id:
                continue
            # Sum of draft + posted (non-cancelled) bills
            related_bills = bill.requisition_id.bill_ids.filtered(
                lambda b: b.state in ('draft', 'posted')
            )
            # If we're creating a new bill (no id yet), include it
            if bill.id not in related_bills.ids:
                related_bills |= bill
            total = sum(b.amount for b in related_bills)
            if total > bill.requisition_id.requested_amount:
                raise ValidationError(_(
                    "Total bills (%s) exceed Requisition '%s' amount (%s)."
                ) % (total, bill.requisition_id.name, bill.requisition_id.requested_amount))

    # ------------------------------------------------------------------ #
    # Post / Cancel
    # ------------------------------------------------------------------ #
    def action_post(self):
        """Post a draft bill.

        Guard: amount must not exceed requisition.remaining_billable_amount.
        On post: bill state -> posted.  Computed fields on requisition and
        budget line react automatically (remaining_billable_amount decreases,
        budget_line.total_spent increases).
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Only draft bills can be posted."))

        if self.amount > self.requisition_id.remaining_billable_amount:
            raise ValidationError(_(
                "Bill amount (%s) exceeds requisition remaining billable amount (%s)."
            ) % (self.amount, self.requisition_id.remaining_billable_amount))

        self.write({'state': 'posted'})

    def action_cancel(self):
        """Cancel a posted bill and reverse balance effects.

        Idempotent: cancelling an already cancelled bill is a no-op.
        Cancelling a draft bill is also a no-op (draft bills have no balance effect).
        """
        self.ensure_one()
        if self.state == 'cancelled':
            return  # idempotent
        if self.state == 'draft':
            self.write({'state': 'cancelled'})
            return
        if self.state == 'posted':
            # Reversing the post: state -> cancelled
            # The compute formulas on fund.requisition.remaining_billable_amount
            # and fund.budget.line.total_spent will automatically increment.
            self.write({'state': 'cancelled'})
