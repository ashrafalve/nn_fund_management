from odoo import models, fields

class FundAccount(models.Model):
    _name = 'fund.account'
    _description = 'Fund Account'
    _inherit = ['mail.thread', 'mail.activity.mixin']

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
    total_received = fields.Monetary(
        string='Total Received', currency_field='currency_id', default=0.0
    )
    unassigned_balance = fields.Monetary(
        string='Unassigned Balance', currency_field='currency_id', default=0.0
    )
    held_amount = fields.Monetary(
        string='Held Amount', currency_field='currency_id', default=0.0
    )
    assigned_amount = fields.Monetary(
        string='Assigned Amount', currency_field='currency_id', default=0.0
    )
