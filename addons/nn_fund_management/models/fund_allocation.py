from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class FundAllocation(models.Model):
    """Prototype configurable approval rule target for allocations.

    Allocation requests inherit fund.approval.mixin.  The mixin looks up
    fund.approval.rule records matching this model's request type
    ('allocation') and dynamically determines the required approval steps.

    Workflow:
        draft -> submitted -> gm_approval -> md_approval -> approved
                                           -> rejected / cancelled

    Balance side-effects (all handled via computed fields, no direct writes):
        - submit:   unassigned_balance -> held (blocked if insufficient)
        - approve:  held -> budget line available + assigned
        - reject / cancel: held -> unassigned_balance (released)
    """

    _name = 'fund.allocation'
    _description = 'Fund Allocation'
    _inherit = ['fund.approval.mixin']
    _approval_request_type = 'allocation'

    request_number = fields.Char(
        string='Request Number', required=True, readonly=True, copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('fund.allocation')
    )
    fund_account_id = fields.Many2one(
        'fund.account', string='Fund Account', required=True, tracking=True
    )
    budget_line_id = fields.Many2one(
        'fund.budget.line', string='Budget Line', required=True, tracking=True
    )
    amount = fields.Monetary(
        string='Amount', currency_field='currency_id', required=True, tracking=True
    )
    purpose = fields.Text(string='Purpose', tracking=True)
    request_date = fields.Date(
        string='Request Date', required=True,
        default=fields.Date.context_today, tracking=True
    )
    requested_by = fields.Many2one(
        'res.users', string='Requested By', required=True,
        default=lambda self: self.env.user, tracking=True
    )
    attachment = fields.Binary(string='Attachment', attachment=True)

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('gm_approval', 'GM Approval'),
        ('md_approval', 'MD Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='Status', required=True, default='draft', tracking=True)

    @api.constrains('amount', 'fund_account_id', 'state')
    def _check_sufficient_unassigned_balance(self):
        """Block submit/approval if amount exceeds fund account unassigned balance."""
        for rec in self:
            if rec.state == 'draft' and rec.fund_account_id and rec.amount:
                if rec.amount > rec.fund_account_id.unassigned_balance:
                    raise ValidationError(_(
                        "Insufficient unassigned balance in Fund Account '%s'. "
                        "Available: %s, Requested: %s."
                    ) % (
                        rec.fund_account_id.name,
                        rec.fund_account_id.unassigned_balance,
                        rec.amount,
                    ))

    def _on_submit(self, **kwargs):
        """Mark a draft allocation as submitted."""
        self.ensure_one()

    def _on_gm_approve(self, **kwargs):
        """GM approved -- moving toward final approval."""
        self.ensure_one()

    def _on_md_approve(self, **kwargs):
        """Final approval -- money becomes available on the budget line."""
        self.ensure_one()

    def _on_reject(self, **kwargs):
        """Release held funds back to unassigned."""
        self.ensure_one()

    def _on_cancel(self, **kwargs):
        """Cancel from draft/submitted/gm_approval -- release any holds."""
        self.ensure_one()

    def unlink(self):
        """Prevent deletion of approved/cancelled allocations."""
        for rec in self:
            if rec.state in ('approved', 'cancelled'):
                raise UserError(_(
                    "Cannot delete allocation '%s' in state '%s'. "
                    "Use Cancel action to reverse."
                ) % (rec.request_number, rec.state))
        return super().unlink()
