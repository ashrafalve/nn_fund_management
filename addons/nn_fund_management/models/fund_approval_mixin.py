from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError, AccessError

class FundApprovalMixin(models.AbstractModel):
    """Abstract mixin that provides a standardized multi-level approval workflow.

    Concrete models should inherit this mixin (in addition to mail.thread /
    mail.activity.mixin) and override the ``_on_*`` hook methods to apply
    model-specific side-effects (e.g. moving balances).  The mixin guarantees
    idempotent transitions by checking the current state before any action.
    """

    _name = 'fund.approval.mixin'
    _description = 'Fund Approval Mixin'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ------------------------------------------------------------------ #
    # Approval state
    # ------------------------------------------------------------------ #
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('gm_approval', 'GM Approval'),
        ('md_approval', 'MD Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='Status', required=True, default='draft', tracking=True, readonly=False)

    approval_ids = fields.One2many(
        'fund.approval.line', 'res_id', string='Approval History',
        domain=lambda self: [('res_model', '=', self._name)],
        readonly=True
    )

    # ------------------------------------------------------------------ #
    # Dynamic rule lookup (prototype — configurable approval tiers)
    #
    # Concrete models can define a class attribute `_approval_request_type`
    # matching the `request_type` selection on fund.approval.rule (e.g.
    # 'allocation', 'requisition', 'transfer').  If no rule matches the
    # record's company and amount range, the mixin falls back to the
    # standard GM -> MD two-step approval.
    # ------------------------------------------------------------------ #
    _approval_request_type = None

    def _get_applicable_rule(self):
        """Find the active approval rule matching this record's type, company and amount."""
        self.ensure_one()
        if not self._approval_request_type:
            return False
        amount = getattr(self, 'amount', 0.0) or getattr(self, 'requested_amount', 0.0) or 0.0
        domain = [
            ('active', '=', True),
            ('request_type', '=', self._approval_request_type),
            ('company_id', 'in', [False, self.company_id.id]),
            ('min_amount', '<=', amount),
        ]
        # Max amount can be empty (no upper bound)
        rules = self.env['fund.approval.rule'].search(domain)
        matching = rules.filtered(
            lambda r: not r.max_amount or amount <= r.max_amount
        )
        # Return highest priority (lowest sequence)
        return matching.sorted('sequence')[0] if matching else False

    def _get_required_approval_levels(self):
        """Return ordered list of approval levels required for this record."""
        self.ensure_one()
        rule = self._get_applicable_rule()
        if rule:
            return rule.get_required_levels()
        # Default fallback: GM then MD
        return ['gm', 'md']

    # ------------------------------------------------------------------ #
    # Transition helpers
    # ------------------------------------------------------------------ #
    def _check_approver_allowed(self, level):
        """Return ``True`` if the current user may approve at *level*.

        Rules
        -----
        1. User must belong to the group matching *level*:
           - ``fund.group_gm_approver`` for ``gm_approval``
           - ``fund.group_md_approver`` for ``md_approval``
        2. Self-approval is blocked unless the user has
           ``fund.group_self_approval_allowed``.
        3. For ``fund.allocation`` the creator (``requested_by``) is the
           submitter; for other models we fall back to ``create_uid``.
        """
        self.ensure_one()
        user = self.env.user
        group_map = {
            'gm': 'nn_fund_management.group_gm_approver',
            'md': 'nn_fund_management.group_md_approver',
            'other': 'nn_fund_management.group_other_approver',
        }
        required_group = group_map.get(level)
        if not required_group:
            return True

        if not user.has_group(required_group):
            raise AccessError(_(
                "You do not have permission to perform %s approvals."
            ) % level.upper())

        # Self-approval guard
        if user.has_group('nn_fund_management.group_self_approval_allowed'):
            return True

        creator = self.env.user
        if self._name == 'fund.allocation' and self.requested_by:
            creator = self.requested_by
        elif self.create_uid:
            creator = self.create_uid

        if user.id == creator.id:
            raise AccessError(_(
                "Self-approval is not allowed. Please ask another %s approver."
            ) % level.upper())

        return True

    def _append_approval_line(self, level, result, comment=None):
        """Append an audit line recording *level* decision by current user."""
        self.ensure_one()
        self.env['fund.approval.line'].create({
            'res_model': self._name,
            'res_id': self.id,
            'approver_id': self.env.user.id,
            'approval_level': level,
            'date': fields.Date.today(),
            'comment': comment or '',
            'result': result,
        })

    # ------------------------------------------------------------------ #
    # Public state transitions
    # ------------------------------------------------------------------ #
    def action_submit(self, comment=None):
        """Draft -> Submitted."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Only draft records can be submitted."))
        self._check_approver_allowed('gm')
        self._on_submit(comment=comment)
        self.state = 'submitted'
        self._append_approval_line('gm', 'submitted', comment)
        msg = _("Record submitted by %s.") % self.env.user.name
        if comment:
            msg += _(" Comment: %s") % comment
        self.message_post(body=msg)

    def action_gm_approve(self, comment=None):
        """Submitted -> GM Approval, or directly to Approved if MD not required."""
        self.ensure_one()
        required_levels = self._get_required_approval_levels()
        is_gm_only = 'md' not in required_levels

        if is_gm_only:
            # GM-only approval: submitted -> approved directly
            if self.state != 'submitted':
                raise UserError(_("Only submitted records can be approved by GM."))
            self._check_approver_allowed('gm')
            self._on_gm_approve(comment=comment)
            self.state = 'approved'
            self._append_approval_line('gm', 'approved', comment)
        else:
            # Standard two-step: submitted -> gm_approval
            if self.state != 'submitted':
                raise UserError(_("Only submitted records can be approved by GM."))
            self._check_approver_allowed('gm')
            self._on_gm_approve(comment=comment)
            self.state = 'gm_approval'
            self._append_approval_line('gm', 'approved', comment)

        msg = _("GM approved by %s.") % self.env.user.name
        if comment:
            msg += _(" Comment: %s") % comment
        self.message_post(body=msg)

    def action_md_approve(self, comment=None):
        """GM Approval -> Approved."""
        self.ensure_one()
        required_levels = self._get_required_approval_levels()
        if 'md' not in required_levels:
            raise UserError(_("MD approval is not required for this request."))
        if self.state != 'gm_approval':
            raise UserError(_("Only GM-approved records can be approved by MD."))
        self._check_approver_allowed('md')
        self._on_md_approve(comment=comment)
        self.state = 'approved'
        self._append_approval_line('md', 'approved', comment)
        msg = _("MD approved by %s.") % self.env.user.name
        if comment:
            msg += _(" Comment: %s") % comment
        self.message_post(body=msg)

    def action_reject(self, comment=None):
        """Current -> Rejected."""
        self.ensure_one()
        if self.state not in ('submitted', 'gm_approval'):
            raise UserError(_("Only submitted or GM-approved records can be rejected."))
        level = 'gm' if self.state == 'submitted' else 'md'
        self._check_approver_allowed(level)
        self._on_reject(comment=comment)
        self.state = 'rejected'
        self._append_approval_line(level, 'rejected', comment)
        msg = _("Rejected by %s at %s level.") % (self.env.user.name, level.upper())
        if comment:
            msg += _(" Comment: %s") % comment
        self.message_post(body=msg)

    def action_cancel(self, comment=None):
        """Draft/Submitted/GM Approval -> Cancelled."""
        self.ensure_one()
        if self.state not in ('draft', 'submitted', 'gm_approval'):
            raise UserError(_("Only draft, submitted or GM-approved records can be cancelled."))
        self._on_cancel(comment=comment)
        self.state = 'cancelled'
        self._append_approval_line('other', 'cancelled', comment)
        msg = _("Cancelled by %s.") % self.env.user.name
        if comment:
            msg += _(" Comment: %s") % comment
        self.message_post(body=msg)

    # ------------------------------------------------------------------ #
    # Hook methods — override in concrete models
    # ------------------------------------------------------------------ #
    def _on_submit(self, **kwargs):
        """Override to apply balance side-effects on submit."""
        self.ensure_one()

    def _on_gm_approve(self, **kwargs):
        """Override to apply balance side-effects on GM approval."""
        self.ensure_one()

    def _on_md_approve(self, **kwargs):
        """Override to apply balance side-effects on MD approval."""
        self.ensure_one()

    def _on_reject(self, **kwargs):
        """Override to release holds / reverse side-effects on rejection."""
        self.ensure_one()

    def _on_cancel(self, **kwargs):
        """Override to release holds / reverse side-effects on cancellation."""
        self.ensure_one()
