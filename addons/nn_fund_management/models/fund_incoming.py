from odoo import models, fields, api

class FundIncoming(models.Model):
    _name = 'fund.incoming'
    _description = 'Fund Incoming'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    fund_account_id = fields.Many2one(
        'fund.account', string='Fund Account', required=True, tracking=True
    )
    date = fields.Date(
        string='Date', required=True,
        default=fields.Date.context_today, tracking=True
    )
    amount = fields.Monetary(
        string='Amount', currency_field='currency_id', required=True, tracking=True
    )
    transaction_reference = fields.Char(
        string='Transaction Reference', tracking=True
    )
    partner_id = fields.Many2one(
        'res.partner', string='Sender/Source', tracking=True
    )
    description = fields.Text(string='Description', tracking=True)
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
        ('confirmed', 'Confirmed'),
    ], string='State', required=True, default='draft', tracking=True)

    def action_confirm(self):
        """Placeholder confirm action — balance side-effects come in Phase 3."""
        self.write({'state': 'confirmed'})
