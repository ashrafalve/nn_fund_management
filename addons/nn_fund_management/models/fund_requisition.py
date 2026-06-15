from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class FundRequisition(models.Model):
    """Fund requisition — reserves budget for a specific budget line.

    Workflow (via inherited fund.approval.mixin + extra 'closed' state):
        draft -> submitted -> gm_approval -> md_approval -> approved
                                           -> rejected / cancelled -> closed

    Balance side-effects (all handled via computed fields, no direct writes):
        - submit:   amount placed on budget_line.requisition_hold (blocked if insufficient)
        - approve:  hold persists; remaining_billable_amount = requested_amount
        - reject / cancel: hold released back to available
        - close:    rec removed from approved_unspent (releasing unused funds)
    """

    _name = 'fund.requisition'
    _description = 'Fund Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ------------------------------------------------------------------ #
    # Sequence & identity
    # ------------------------------------------------------------------ #
    requisition_number = fields.Char(
        string='Requisition Number', required=True, readonly=True, copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('fund.requisition')
    )
    budget_line_id = fields.Many2one(
        'fund.budget.line', string='Budget Line', required=True, tracking=True
    )
    requested_amount = fields.Monetary(
        string='Requested Amount', currency_field='currency_id', required=True, tracking=True
    )
    purpose = fields.Text(string='Purpose', tracking=True)
    request_date = fields.Date(
        string='Request Date', required=True,
        default=fields.Date.context_today, tracking=True
    )
    required_date = fields.Date(string='Required Date', tracking=True)
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

    # ------------------------------------------------------------------ #
    # Approval workflow state — extended with 'closed'
    # ------------------------------------------------------------------ #
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('gm_approval', 'GM Approval'),
        ('md_approval', 'MD Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('closed', 'Closed'),
    ], string='Status', required=True, default='draft', tracking=True)

    # ------------------------------------------------------------------ #
    # Remaining billable amount
    #
    # Derives from the approved amount minus the sum of POSTED bills
    # against this requisition.  Stored so the "post bill" guard can
    # read it directly without recomputing the whole tree.
    # ------------------------------------------------------------------ #
    remaining_billable_amount = fields.Monetary(
        string='Remaining Billable Amount', currency_field='currency_id',
        compute='_compute_remaining_billable_amount', store=True, readonly=True
    )

    bill_ids = fields.One2many('fund.bill', 'requisition_id', string='Bills')

    # ------------------------------------------------------------------ #
    # Compute methods
    # ------------------------------------------------------------------ #
    @api.depends('requested_amount', 'bill_ids.amount', 'bill_ids.state')
    def _compute_remaining_billable_amount(self):
        for req in self:
            if req.state == 'approved':
                posted_total = sum(
                    bill.amount for bill in req.bill_ids if bill.state == 'posted'
                )
                req.remaining_billable_amount = req.requested_amount - posted_total
            else:
                req.remaining_billable_amount = 0.0

    # ------------------------------------------------------------------ #
    # Pre-transition guard: block submit if amount exceeds budget available
    # ------------------------------------------------------------------ #
    @api.constrains('requested_amount', 'budget_line_id', 'state')
    def _check_sufficient_budget_available(self):
        for req in self:
            if req.state == 'draft' and req.budget_line_id and req.requested_amount:
                if req.requested_amount > req.budget_line_id.available:
                    raise ValidationError(_(
                        "Insufficient available budget on Budget Line '%s'. "
                        "Available: %s, Requested: %s."
                    ) % (
                        req.budget_line_id.name,
                        req.budget_line_id.available,
                        req.requested_amount,
                    ))

    # ------------------------------------------------------------------ #
    # Approval mixin hooks
    # ------------------------------------------------------------------ #
    def _on_submit(self, **kwargs):
        """Place requested_amount on budget line requisition_hold."""
        self.ensure_one()

    def _on_gm_approve(self, **kwargs):
        """Hold persists — moving toward final approval."""
        self.ensure_one()

    def _on_md_approve(self, **kwargs):
        """Final approval — remaining_billable_amount becomes active."""
        self.ensure_one()

    def _on_reject(self, **kwargs):
        """Release requisition_hold back to budget line available."""
        self.ensure_one()

    def _on_cancel(self, **kwargs):
        """Cancel — release any hold."""
        self.ensure_one()

    # ------------------------------------------------------------------ #
    # Close action
    # ------------------------------------------------------------------ #
    def action_close(self, release_unused=False):
        """Close an approved requisition.

        Two paths:
        1. remaining_billable_amount == 0: simply close.
        2. release_unused=True: close AND release the unused portion back
           to budget line available (by changing state, the compute
           formulas remove this requisition from approved_unspent /
           requisition_hold automatically).
        """
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_("Only approved requisitions can be closed."))

        if self.remaining_billable_amount > 0 and not release_unused:
            raise UserError(_(
                "Requisition still has %s billable remaining. "
                "Check 'Release Unused' to return funds to available."
            ) % self.remaining_billable_amount)

        self.write({'state': 'closed'})
        self.message_post(body=_("Requisition closed by %s.") % self.env.user.name)

    def unlink(self):
        """Prevent deletion of approved/closed/cancelled requisitions."""
        for rec in self:
            if rec.state in ('approved', 'closed', 'cancelled'):
                raise UserError(_(
                    "Cannot delete requisition '%s' in state '%s'. "
                    "Use Cancel/Close actions to manage workflow."
                ) % (rec.requisition_number, rec.state))
        return super().unlink()
