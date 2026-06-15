from odoo import tests
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestFundApprovalRule(TransactionCase):
    """Tests for the configurable approval rule prototype."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.env.company.currency_id

    def test_01_gm_only_rule_for_small_amount(self):
        """Amount <= 50,000 should match a GM-only rule and approve directly."""
        rule = self.env['fund.approval.rule'].create({
            'name': 'Small Allocation',
            'request_type': 'allocation',
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'min_amount': 0,
            'max_amount': 50000,
            'gm_required': True,
            'md_required': False,
        })

        fund_account = self.env['fund.account'].create({
            'name': 'Test Account',
            'account_type': 'bank',
            'company_id': self.company.id,
            'currency_id': self.currency.id,
        })
        inc = self.env['fund.incoming'].create({
            'fund_account_id': fund_account.id,
            'date': '2026-06-15',
            'amount': 20000.0,
            'state': 'draft',
        })
        inc.action_confirm()
        fund_account.invalidate_recordset(['unassigned_balance'])

        budget_line = self.env['fund.budget.line'].create({
            'name': 'Test Budget',
            'target_type': 'expense_head',
            'company_id': self.company.id,
            'currency_id': self.currency.id,
        })

        alloc = self.env['fund.allocation'].create({
            'fund_account_id': fund_account.id,
            'budget_line_id': budget_line.id,
            'amount': 20000.0,
            'purpose': 'Small',
            'request_date': '2026-06-15',
        })

        # Verify rule lookup
        applicable = alloc._get_applicable_rule()
        self.assertEqual(applicable.id, rule.id)
        required = alloc._get_required_approval_levels()
        self.assertEqual(required, ['gm'])

        # GM only -> submit -> gm_approve -> should go directly to approved
        alloc.action_submit()
        alloc.action_gm_approve()
        self.assertEqual(alloc.state, 'approved')

    def test_02_no_rule_falls_back_to_default(self):
        """Missing rule falls back to GM -> MD."""
        fund_account = self.env['fund.account'].create({
            'name': 'Test Account 2',
            'account_type': 'bank',
            'company_id': self.company.id,
            'currency_id': self.currency.id,
        })
        inc = self.env['fund.incoming'].create({
            'fund_account_id': fund_account.id,
            'date': '2026-06-15',
            'amount': 30000.0,
            'state': 'draft',
        })
        inc.action_confirm()
        fund_account.invalidate_recordset(['unassigned_balance'])

        budget_line = self.env['fund.budget.line'].create({
            'name': 'Test Budget 2',
            'target_type': 'expense_head',
            'company_id': self.company.id,
            'currency_id': self.currency.id,
        })

        alloc = self.env['fund.allocation'].create({
            'fund_account_id': fund_account.id,
            'budget_line_id': budget_line.id,
            'amount': 30000.0,
            'purpose': 'Default',
            'request_date': '2026-06-15',
        })

        self.assertFalse(alloc._get_applicable_rule())
        required = alloc._get_required_approval_levels()
        self.assertEqual(required, ['gm', 'md'])
