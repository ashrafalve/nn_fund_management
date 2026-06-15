from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class FundTransfer(models.Model):
    """Fund transfer between budget lines.

    Workflow (via inherited fund.approval.mixin):
        draft -> submitted -> gm_approval -> md_approval -> approved
                                           -> rejected / cancelled

    Balance side-effects (computed fields react to state changes):
        - submit:   amount deducted from source.available → source.transfer_hold
                    (blocked if amount > source.available)
        - approve:  source.transfer_hold cleared, destination.total_allocated /
                    destination.available increased by amount, source.outgoing /
                    destination.incoming records updated
        - reject / cancel: source.transfer_hold released → source.available
    """

    _name = 'fund.transfer'
    _description = 'Fund Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ------------------------------------------------------------------ #
    # Sequence & identity
    # ------------------------------------------------------------------ #
    transfer_number = fields.Char(
        string='Transfer Number', required=True, readonly=True, copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('fund.transfer')
    )
    source_budget_line_id = fields.Many2one(
        'fund.budget.line', string='Source Budget Line', required=True, tracking=True
    )
    destination_budget_line_id = fields.Many2one(
        'fund.budget.line', string='Destination Budget Line', required=True, tracking=True
    )
    amount = fields.Monetary(
        string='Amount', currency_field='currency_id', required=True, tracking=True
    )
    reason = fields.Text(string='Reason', tracking=True)
    requested_by = fields.Many2one(
        'res.users', string='Requested By', required=True,
        default=lambda self: self.env.user, tracking=True
    )
    request_date = fields.Date(
        string='Request Date', required=True,
        default=fields.Date.context_today, tracking=True
    )

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id
    )

    # ------------------------------------------------------------------ #
    # Approval workflow state
    # ------------------------------------------------------------------ #
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('gm_approval', 'GM Approval'),
        ('md_approval', 'MD Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='Status', required=True, default='draft', tracking=True)

    # ------------------------------------------------------------------ #
    # Constraint: source and destination must differ
    # ------------------------------------------------------------------ #
    @api.constrains('source_budget_line_id', 'destination_budget_line_id')
    def _check_source_destination_different(self):
        for transfer in self:
            if transfer.source_budget_line_id and transfer.destination_budget_line_id:
                if transfer.source_budget_line_id.id == transfer.destination_budget_line_id.id:
                    raise ValidationError(_(
                        "Source and Destination Budget Lines must be different."
                    ))

    # ------------------------------------------------------------------ #
    # Pre-submit guard: block if amount > source.available
    # ------------------------------------------------------------------ #
    @api.constrains('amount', 'source_budget_line_id', 'state')
    def _check_sufficient_source_available(self):
        for transfer in self:
            if transfer.state == 'draft' and transfer.source_budget_line_id and transfer.amount:
                source = transfer.source_budget_line_id
                if transfer.amount > source.available:
                    raise ValidationError(_(
                        "Insufficient available balance on Source Budget Line '%s'. "
                        "Available: %s, Transfer Amount: %s."
                    ) % (source.name, source.available, transfer.amount))

    # ------------------------------------------------------------------ #
    # Approval mixin hooks
    # ------------------------------------------------------------------ #
    def _on_submit(self, **kwargs):
        """Hold amount from source.available → source.transfer_hold.

        No direct write — state change drives the computed fields.
        """
        self.ensure_one()

    def _on_gm_approve(self, **kwargs):
        """Hold persists — progressing toward final approval."""
        self.ensure_one()

    def _on_md_approve(self, **kwargs):
        """Final approval — transfer is executed.

        The state transition to 'approved' automatically:
        - clears source.transfer_hold (hold states no longer include 'approved')
        - increases destination.total_allocated / destination.available
        - updates source.outgoing_transfers / destination.incoming_transfers
        """
        self.ensure_one()

    def _on_reject(self, **kwargs):
        """Release source.transfer_hold back to source.available."""
        self.ensure_one()

    def _on_cancel(self, **kwargs):
        """Cancel — release any hold on source."""
        self.ensure_one()

    def unlink(self):
        """Prevent deletion of approved/cancelled transfers."""
        for rec in self:
            if rec.state in ('approved', 'cancelled'):
                raise UserError(_(
                    "Cannot delete transfer '%s' in state '%s'. "
                    "Use Cancel action to reverse."
                ) % (rec.transfer_number, rec.state))
        return super().unlink()
