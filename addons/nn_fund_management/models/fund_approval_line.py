from odoo import models, fields

class FundApprovalLine(models.Model):
    _name = 'fund.approval.line'
    _description = 'Fund Approval History'
    _order = 'date desc, id desc'

    res_model = fields.Char(string='Resource Model', required=True)
    res_id = fields.Integer(string='Resource ID', required=True)
    approver_id = fields.Many2one(
        'res.users', string='Approver', required=True,
        default=lambda self: self.env.user
    )
    approval_level = fields.Selection([
        ('gm', 'GM'),
        ('md', 'MD'),
        ('other', 'Other'),
    ], string='Approval Level', required=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    comment = fields.Text(string='Comment')
    result = fields.Selection([
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('submitted', 'Submitted'),
        ('cancelled', 'Cancelled'),
    ], string='Result', required=True)
