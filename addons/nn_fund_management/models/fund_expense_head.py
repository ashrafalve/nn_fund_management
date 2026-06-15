from odoo import models, fields

class FundExpenseHead(models.Model):
    _name = 'fund.expense.head'
    _description = 'Fund Expense Head'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, tracking=True)
    code = fields.Char(string='Code', tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company
    )
    active = fields.Boolean(string='Active', default=True)
