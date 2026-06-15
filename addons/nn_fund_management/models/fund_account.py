from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class FundAccount(models.Model):
    _name = 'fund.account'
    _description = 'Fund Account'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ------------------------------------------------------------------ #
    # Core fields
    # ------------------------------------------------------------------ #
    name = fields.Char(string='Account Name', required=True, tracking=True)
    account_type = fields.Selection([
        ('bank', 'Bank'),
        ('cash', 'Cash'),
        ('other', 'Other'),
    ], string='Account Type', required=True, default='bank', tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id
    )

    # ------------------------------------------------------------------ #
    # Reverse relations so computed fields can be re-evaluated when
    # related records change.
    # ------------------------------------------------------------------ #
    incoming_ids = fields.One2many('fund.incoming', 'fund_account_id', string='Incoming Funds')
    allocation_ids = fields.One2many('fund.allocation', 'fund_account_id', string='Allocations')

    # ------------------------------------------------------------------ #
    # Computed balance fields
    #
    # Dependency rationale
    # --------------------
    # total_received
    #   Sum of CONFIRMED incoming funds only.  Draft incoming records
    #   are not counted until confirmed.
    #
    # held_amount
    #   Sum of allocation amounts in submitted / gm_approval / md_approval.
    #   These funds have left unassigned_balance but have not yet been
    #   approved to a budget line.
    #
    # assigned_amount
    #   Sum of allocation amounts in 'approved' state — money that has
    #   been committed to a specific budget line.
    #
    # unassigned_balance
    #   total_received minus everything that has been held or assigned.
    #   This is the pool of money available for new allocations.
    # ------------------------------------------------------------------ #
    total_received = fields.Monetary(
        string='Total Received', currency_field='currency_id',
        compute='_compute_total_received', store=True, readonly=True
    )
    held_amount = fields.Monetary(
        string='Held Amount', currency_field='currency_id',
        compute='_compute_held_amount', store=True, readonly=True
    )
    assigned_amount = fields.Monetary(
        string='Assigned Amount', currency_field='currency_id',
        compute='_compute_assigned_amount', store=True, readonly=True
    )
    unassigned_balance = fields.Monetary(
        string='Unassigned Balance', currency_field='currency_id',
        compute='_compute_unassigned_balance', store=True, readonly=True
    )

    # ------------------------------------------------------------------ #
    # Compute methods
    # ------------------------------------------------------------------ #
    @api.depends('incoming_ids.amount', 'incoming_ids.state')
    def _compute_total_received(self):
        for account in self:
            account.total_received = sum(
                inc.amount for inc in account.incoming_ids
                if inc.state == 'confirmed'
            )

    @api.depends('allocation_ids.amount', 'allocation_ids.state')
    def _compute_held_amount(self):
        hold_states = ('submitted', 'gm_approval', 'md_approval')
        for account in self:
            account.held_amount = sum(
                alloc.amount for alloc in account.allocation_ids
                if alloc.state in hold_states
            )

    @api.depends('allocation_ids.amount', 'allocation_ids.state')
    def _compute_assigned_amount(self):
        for account in self:
            account.assigned_amount = sum(
                alloc.amount for alloc in account.allocation_ids
                if alloc.state == 'approved'
            )

    @api.depends('total_received', 'held_amount', 'assigned_amount')
    def _compute_unassigned_balance(self):
        for account in self:
            account.unassigned_balance = (
                account.total_received - account.held_amount - account.assigned_amount
            )

    # ------------------------------------------------------------------ #
    # Safety-net constraints
    # ------------------------------------------------------------------ #
    @api.constrains('total_received', 'held_amount', 'assigned_amount', 'unassigned_balance')
    def _check_negative_balances(self):
        for account in self:
            for field_name in ['total_received', 'held_amount', 'assigned_amount', 'unassigned_balance']:
                value = getattr(account, field_name)
                if value < 0:
                    raise ValidationError(_(
                        "Negative balance detected on Fund Account '%s' "
                        "for field '%s': %s.  This indicates a workflow bug."
                    ) % (account.name, field_name, value))
