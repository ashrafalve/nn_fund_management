from odoo import tests
from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError, UserError


class TestFundSecurity(TransactionCase):
    """Tests for server-side approval guards and basic access checks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.env.company.currency_id

        # Create a fund account
        cls.fund_account = cls.env['fund.account'].create({
            'name': 'Security Test Account',
            'account_type': 'bank',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })

        # Create a budget line
        cls.budget_line = cls.env['fund.budget.line'].create({
            'name': 'Security Test Budget',
            'target_type': 'expense_head',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })

        # Create a regular user without approver groups
        cls.regular_user = cls.env['res.users'].create({
            'name': 'Regular User',
            'login': 'regular_user',
            'company_ids': [(4, cls.company.id)],
            'company_id': cls.company.id,
            'groups_id': [(4, cls.env.ref('fund.group_fund_user').id)],
        })

    def test_01_non_gm_cannot_gm_approve(self):
        """Non-GM user calling action_gm_approve must raise AccessError."""
        allocation = self.env['fund.allocation'].create({
            'fund_account_id': self.fund_account.id,
            'budget_line_id': self.budget_line.id,
            'amount': 1000.0,
            'purpose': 'Security test',
            'request_date': '2026-06-15',
        })
        allocation.with_user(self.regular_user).action_submit()
        self.assertEqual(allocation.state, 'submitted')

        with self.assertRaises(AccessError):
            allocation.with_user(self.regular_user).action_gm_approve()

    def test_02_non_md_cannot_md_approve(self):
        """Non-MD user calling action_md_approve must raise AccessError."""
        gm_user = self.env['res.users'].create({
            'name': 'GM User',
            'login': 'gm_user',
            'company_ids': [(4, self.company.id)],
            'company_id': self.company.id,
            'groups_id': [(4, self.env.ref('fund.group_gm_approver').id)],
        })

        allocation = self.env['fund.allocation'].create({
            'fund_account_id': self.fund_account.id,
            'budget_line_id': self.budget_line.id,
            'amount': 1000.0,
            'purpose': 'Security test',
            'request_date': '2026-06-15',
        })
        allocation.with_user(self.regular_user).action_submit()
        allocation.with_user(gm_user).action_gm_approve()
        self.assertEqual(allocation.state, 'gm_approval')

        with self.assertRaises(AccessError):
            allocation.with_user(self.regular_user).action_md_approve()

    def test_03_non_gm_cannot_reject_after_submit(self):
        """Non-GM user cannot reject a submitted record."""
        allocation = self.env['fund.allocation'].create({
            'fund_account_id': self.fund_account.id,
            'budget_line_id': self.budget_line.id,
            'amount': 1000.0,
            'purpose': 'Security test',
            'request_date': '2026-06-15',
        })
        allocation.with_user(self.regular_user).action_submit()

        with self.assertRaises(AccessError):
            allocation.with_user(self.regular_user).action_reject()

    def test_04_gm_approved_by_non_gm_cannot_md_approve(self):
        """If somehow a non-GD approved at GM stage, MD approval still blocked."""
        allocation = self.env['fund.allocation'].create({
            'fund_account_id': self.fund_account.id,
            'budget_line_id': self.budget_line.id,
            'amount': 1000.0,
            'purpose': 'Security test',
            'request_date': '2026-06-15',
        })
        # Directly set state to gm_approval to simulate bypass
        allocation.write({'state': 'gm_approval'})

        with self.assertRaises(AccessError):
            allocation.with_user(self.regular_user).action_md_approve()
