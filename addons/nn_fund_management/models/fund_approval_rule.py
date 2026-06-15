from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class FundApprovalRule(models.Model):
    """Configurable approval rule prototype.

    Rules dynamically determine how many approval steps are required
    based on request type and amount.  If no rule matches, the system
    falls back to the standard GM -> MD two-step approval.

    Example tiers (seeded as demo data):
    - Tier 1: <= 50,000  → GM only
    - Tier 2: 50,001 - 200,000 → GM + MD
    - Tier 3: > 200,000 → GM + MD (same as Tier 2 in this prototype;
      a production version could add Finance Director as an extra step)
    """

    _name = 'fund.approval.rule'
    _description = 'Fund Approval Rule'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Rule Name', required=True, tracking=True)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company
    )
    request_type = fields.Selection([
        ('allocation', 'Fund Allocation'),
        ('requisition', 'Fund Requisition'),
        ('transfer', 'Fund Transfer'),
    ], string='Request Type', required=True, tracking=True)
    min_amount = fields.Monetary(
        string='Minimum Amount', currency_field='currency_id', default=0.0
    )
    max_amount = fields.Monetary(
        string='Maximum Amount', currency_field='currency_id',
        help="Leave empty for no upper bound."
    )
    gm_required = fields.Boolean(string='GM Approval Required', default=True)
    md_required = fields.Boolean(string='MD Approval Required', default=True)
    sequence = fields.Integer(string='Sequence', default=10)

    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id
    )

    @api.constrains('min_amount', 'max_amount')
    def _check_amount_range(self):
        for rule in self:
            if rule.max_amount and rule.min_amount > rule.max_amount:
                raise ValidationError(_(
                    "Minimum amount (%s) cannot exceed maximum amount (%s)."
                ) % (rule.min_amount, rule.max_amount))

    def get_required_levels(self):
        """Return a list of approval levels required by this rule, in sequence."""
        self.ensure_one()
        levels = []
        if self.gm_required:
            levels.append('gm')
        if self.md_required:
            levels.append('md')
        return levels
