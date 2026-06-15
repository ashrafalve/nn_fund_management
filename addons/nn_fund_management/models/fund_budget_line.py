from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class FundBudgetLine(models.Model):
    """Unified allocation target — either a project or an expense head.

    Balance fields are fully computed (store=True) and read-only.  The
    dependency chain is documented in each compute method so the logic
    can be explained clearly in an interview.
    """

    _name = 'fund.budget.line'
    _description = 'Fund Budget Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ------------------------------------------------------------------ #
    # Core fields
    # ------------------------------------------------------------------ #
    name = fields.Char(string='Name', required=True, tracking=True)
    target_type = fields.Selection([
        ('project', 'Project'),
        ('expense_head', 'Expense Head'),
    ], string='Target Type', required=True, default='project', tracking=True)
    project_id = fields.Many2one('project.project', string='Project', tracking=True)
    expense_head_id = fields.Many2one('fund.expense.head', string='Expense Head', tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id
    )

    # ------------------------------------------------------------------ #
    # Reverse One2manys so @api.depends can track cross-model changes.
    #
    # These are *not* shown in the UI by default; they exist purely so
    # the stored computed fields below are re-evaluated automatically
    # when related records are written.
    # ------------------------------------------------------------------ #
    allocation_ids = fields.One2many('fund.allocation', 'budget_line_id', string='Allocations')
    requisition_ids = fields.One2many('fund.requisition', 'budget_line_id', string='Requisitions')
    bill_ids = fields.One2many('fund.bill', 'budget_line_id', string='Bills')
    transfer_out_ids = fields.One2many(
        'fund.transfer', 'source_budget_line_id', string='Outgoing Transfers'
    )
    transfer_in_ids = fields.One2many(
        'fund.transfer', 'destination_budget_line_id', string='Incoming Transfers'
    )

    # ------------------------------------------------------------------ #
    # Computed balance fields
    #
    # Dependency rationale
    # --------------------
    # total_allocated
    #   Only APPROVED allocations count.  Draft/submitted/approved/rejected
    #   allocations are ignored because the money has not been committed
    #   to this budget line yet.
    #
    # requisition_hold
    #   Once a requisition is submitted it reserves budget.  The hold
    #   persists through gm_approval, md_approval, and approved.  It is
    #   only released on reject / cancel / close.
    #
    # transfer_hold
    #   An outgoing transfer in submitted / gm_approval / md_approval
    #   temporarily locks the source budget line.  On approve the hold
    #   clears; on reject/cancel it is released.
    #
    # total_spent
    #   Only POSTED bills consume budget.  Draft/cancelled bills do not.
    #
    # approved_unspent
    #   For each APPROVED requisition, requested_amount minus the sum of
    #   POSTED bills on that requisition.  This tells us how much of the
    #   approved authority is still available to bill.
    #
    # incoming_transfers / outgoing_transfers
    #   Only APPROVED transfers move money between budget lines.
    # ------------------------------------------------------------------ #
    total_allocated = fields.Monetary(
        string='Total Allocated', currency_field='currency_id',
        compute='_compute_total_allocated', store=True, readonly=True
    )
    requisition_hold = fields.Monetary(
        string='Requisition Hold', currency_field='currency_id',
        compute='_compute_requisition_hold', store=True, readonly=True
    )
    transfer_hold = fields.Monetary(
        string='Transfer Hold', currency_field='currency_id',
        compute='_compute_transfer_hold', store=True, readonly=True
    )
    total_spent = fields.Monetary(
        string='Total Spent', currency_field='currency_id',
        compute='_compute_total_spent', store=True, readonly=True
    )
    approved_unspent = fields.Monetary(
        string='Approved Unspent', currency_field='currency_id',
        compute='_compute_approved_unspent', store=True, readonly=True
    )
    incoming_transfers = fields.Monetary(
        string='Incoming Transfers', currency_field='currency_id',
        compute='_compute_incoming_transfers', store=True, readonly=True
    )
    outgoing_transfers = fields.Monetary(
        string='Outgoing Transfers', currency_field='currency_id',
        compute='_compute_outgoing_transfers', store=True, readonly=True
    )
    available = fields.Monetary(
        string='Available', currency_field='currency_id',
        compute='_compute_available', store=True, readonly=True
    )

    # ------------------------------------------------------------------ #
    # Compute methods
    # ------------------------------------------------------------------ #
    @api.depends(
        'allocation_ids.amount', 'allocation_ids.state',
        'transfer_in_ids.amount', 'transfer_in_ids.state'
    )
    def _compute_total_allocated(self):
        # total_allocated = approved allocations + approved incoming transfers.
        # When a transfer is approved, the destination's total_allocated
        # and available increase by the transfer amount.
        for line in self:
            line.total_allocated = (
                sum(
                    alloc.amount for alloc in line.allocation_ids
                    if alloc.state == 'approved'
                )
                + sum(
                    tr.amount for tr in line.transfer_in_ids
                    if tr.state == 'approved'
                )
            )

    @api.depends('requisition_ids.requested_amount', 'requisition_ids.state')
    def _compute_requisition_hold(self):
        hold_states = ('submitted', 'gm_approval', 'md_approval', 'approved')
        for line in self:
            line.requisition_hold = sum(
                req.requested_amount for req in line.requisition_ids
                if req.state in hold_states
            )

    @api.depends('transfer_out_ids.amount', 'transfer_out_ids.state')
    def _compute_transfer_hold(self):
        hold_states = ('submitted', 'gm_approval', 'md_approval')
        for line in self:
            line.transfer_hold = sum(
                tr.amount for tr in line.transfer_out_ids
                if tr.state in hold_states
            )

    @api.depends('bill_ids.amount', 'bill_ids.state')
    def _compute_total_spent(self):
        for line in self:
            line.total_spent = sum(
                bill.amount for bill in line.bill_ids
                if bill.state == 'posted'
            )

    @api.depends(
        'requisition_ids.requested_amount', 'requisition_ids.state',
        'bill_ids.amount', 'bill_ids.state'
    )
    def _compute_approved_unspent(self):
        """Approved requisition amount minus posted bills against it."""
        for line in self:
            unspent = 0.0
            for req in line.requisition_ids.filtered(lambda r: r.state == 'approved'):
                posted_bills = sum(
                    bill.amount for bill in req.bill_ids if bill.state == 'posted'
                )
                unspent += req.requested_amount - posted_bills
            line.approved_unspent = unspent

    @api.depends('transfer_in_ids.amount', 'transfer_in_ids.state')
    def _compute_incoming_transfers(self):
        for line in self:
            line.incoming_transfers = sum(
                tr.amount for tr in line.transfer_in_ids
                if tr.state == 'approved'
            )

    @api.depends('transfer_out_ids.amount', 'transfer_out_ids.state')
    def _compute_outgoing_transfers(self):
        for line in self:
            line.outgoing_transfers = sum(
                tr.amount for tr in line.transfer_out_ids
                if tr.state == 'approved'
            )

    @api.depends(
        'total_allocated', 'requisition_hold', 'transfer_hold',
        'total_spent', 'incoming_transfers', 'outgoing_transfers'
    )
    def _compute_available(self):
        for line in self:
            line.available = (
                line.total_allocated
                + line.incoming_transfers
                - line.outgoing_transfers
                - line.requisition_hold
                - line.transfer_hold
                - line.total_spent
            )

    # ------------------------------------------------------------------ #
    # Safety-net constraints
    # ------------------------------------------------------------------ #
    @api.constrains(
        'total_allocated', 'available', 'requisition_hold', 'transfer_hold',
        'total_spent', 'incoming_transfers', 'outgoing_transfers'
    )
    def _check_negative_balances(self):
        for line in self:
            for field_name in [
                'total_allocated', 'available', 'requisition_hold',
                'transfer_hold', 'total_spent', 'incoming_transfers', 'outgoing_transfers'
            ]:
                value = getattr(line, field_name)
                if value < 0:
                    raise ValidationError(_(
                        "Negative balance detected on Budget Line '%s' "
                        "for field '%s': %s.  This indicates a workflow bug."
                    ) % (line.name, field_name, value))
