from odoo import models, fields

class FundBudgetLine(models.Model):
    _name = 'fund.budget.line'
    _description = 'Fund Budget Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']

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
    total_allocated = fields.Monetary(
        string='Total Allocated', currency_field='currency_id', default=0.0
    )
    available = fields.Monetary(
        string='Available', currency_field='currency_id', default=0.0
    )
    requisition_hold = fields.Monetary(
        string='Requisition Hold', currency_field='currency_id', default=0.0
    )
    transfer_hold = fields.Monetary(
        string='Transfer Hold', currency_field='currency_id', default=0.0
    )
    approved_unspent = fields.Monetary(
        string='Approved Unspent', currency_field='currency_id', default=0.0
    )
    total_spent = fields.Monetary(
        string='Total Spent', currency_field='currency_id', default=0.0
    )
    incoming_transfers = fields.Monetary(
        string='Incoming Transfers', currency_field='currency_id', default=0.0
    )
    outgoing_transfers = fields.Monetary(
        string='Outgoing Transfers', currency_field='currency_id', default=0.0
    )
