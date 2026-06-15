from odoo import tests
from odoo.tests.common import TransactionCase, Form
from odoo.exceptions import UserError, ValidationError


class TestFundBalanceLogic(TransactionCase):
    """Tests confirming incoming funds and allocation workflow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ensure we have a company with a currency (multi-company safe)
        cls.company = cls.env.company
        cls.currency = cls.env.company.currency_id

        # Create a fund account to work with
        cls.fund_account = cls.env['fund.account'].create({
            'name': 'Main Account',
            'account_type': 'bank',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })

    def test_01_confirm_incoming_increases_unassigned(self):
        """Confirming an incoming fund increases unassigned_balance."""
        rec = self.env['fund.incoming'].create({
            'fund_account_id': self.fund_account.id,
            'date': '2026-06-15',
            'amount': 1000.0,
            'state': 'draft',
        })
        self.assertEqual(self.fund_account.unassigned_balance, 0.0)
        rec.action_confirm()
        self.fund_account.invalidate_recordset(['total_received', 'unassigned_balance'])
        self.assertEqual(self.fund_account.total_received, 1000.0)
        self.assertEqual(self.fund_account.unassigned_balance, 1000.0)

    def test_02_submit_allocation_blocks_on_insufficient_funds(self):
        """Submitting an allocation with amount > unassigned_balance must fail."""
        # No money in the account yet
        alloc = self.env['fund.allocation'].create({
            'fund_account_id': self.fund_account.id,
            'requested_amount': 500.0,
            'purpose': 'Test',
        })
        with self.assertRaises(ValidationError):
            alloc.action_submit()

    def test_03_full_allocation_happy_path(self):
        """Allocation: draft -> submitted -> gm_approval -> approved."""
        # Fund the account
        inc = self.env['fund.incoming'].create({
            'fund_account_id': self.fund_account.id,
            'date': '2026-06-15',
            'amount': 2000.0,
            'state': 'draft',
        })
        inc.action_confirm()
        self.fund_account.invalidate_recordset(['unassigned_balance'])

        # Create a budget line
        budget_line = self.env['fund.budget.line'].create({
            'name': 'Operations',
            'target_type': 'expense_head',
            'company_id': self.company.id,
            'currency_id': self.currency.id,
        })

        # Submit allocation
        alloc = self.env['fund.allocation'].create({
            'fund_account_id': self.fund_account.id,
            'budget_line_id': budget_line.id,
            'amount': 1000.0,
            'purpose': 'Ops budget',
        })
        alloc.action_submit(comment='Please approve')
        self.assertEqual(alloc.state, 'submitted')
        # Held amount should now reflect 1000 out of 2000 unassigned
        self.fund_account.invalidate_recordset(['held_amount', 'unassigned_balance'])
        self.assertEqual(self.fund_account.held_amount, 1000.0)
        self.assertEqual(self.fund_account.unassigned_balance, 0.0)

        # GM approve
        alloc.action_gm_approve(comment='OK')
        self.assertEqual(alloc.state, 'gm_approval')

        # MD approve
        alloc.action_md_approve(comment='Final sign-off')
        self.assertEqual(alloc.state, 'approved')

        # Budget line should now show 1000 in total_allocated / available
        budget_line.invalidate_recordset(['total_allocated', 'available'])
        self.assertEqual(budget_line.total_allocated, 1000.0)
        self.assertEqual(budget_line.available, 1000.0)

    def test_04_reject_returns_to_unassigned(self):
        """Rejecting an approved allocation releases funds."""
        inc = self.env['fund.incoming'].create({
            'fund_account_id': self.fund_account.id,
            'date': '2026-06-15',
            'amount': 1500.0,
            'state': 'draft',
        })
        inc.action_confirm()
        self.fund_account.invalidate_recordset(['unassigned_balance'])

        budget_line = self.env['fund.budget.line'].create({
            'name': 'Marketing',
            'target_type': 'expense_head',
            'company_id': self.company.id,
            'currency_id': self.currency.id,
        })

        alloc = self.env['fund.allocation'].create({
            'fund_account_id': self.fund_account.id,
            'budget_line_id': budget_line.id,
            'amount': 800.0,
            'purpose': 'Marketing',
        })
        alloc.action_submit()
        alloc.action_gm_approve()
        alloc.action_reject(comment='Budget cut')

        self.assertEqual(alloc.state, 'rejected')
        self.fund_account.invalidate_recordset(['held_amount', 'unassigned_balance'])
        self.assertEqual(self.fund_account.held_amount, 0.0)
        self.assertEqual(self.fund_account.unassigned_balance, 1500.0)

    def test_05_idempotent_actions(self):
        """Calling action_submit twice must not double-count."""
        inc = self.env['fund.incoming'].create({
            'fund_account_id': self.fund_account.id,
            'date': '2026-06-15',
            'amount': 500.0,
            'state': 'draft',
        })
        inc.action_confirm()
        self.fund_account.invalidate_recordset(['unassigned_balance'])

        alloc = self.env['fund.allocation'].create({
            'fund_account_id': self.fund_account.id,
            'amount': 200.0,
            'purpose': 'Test',
        })
        alloc.action_submit()
        self.fund_account.invalidate_recordset(['held_amount'])
        self.assertEqual(self.fund_account.held_amount, 200.0)

        # Second submit should raise
        with self.assertRaises(UserError):
            alloc.action_submit()
        self.fund_account.invalidate_recordset(['held_amount'])
        self.assertEqual(self.fund_account.held_amount, 200.0)
