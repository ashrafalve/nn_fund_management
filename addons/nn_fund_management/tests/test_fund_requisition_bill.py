from odoo import tests
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestFundRequisitionBill(TransactionCase):
    """Tests covering requisition and bill workflows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.env.company.currency_id

        # Create a fund account and fund it
        cls.fund_account = cls.env['fund.account'].create({
            'name': 'Main Account',
            'account_type': 'bank',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })
        inc = cls.env['fund.incoming'].create({
            'fund_account_id': cls.fund_account.id,
            'date': '2026-06-15',
            'amount': 200000.0,
            'state': 'draft',
        })
        inc.action_confirm()
        cls.fund_account.invalidate_recordset(['unassigned_balance'])

        # Create two budget lines (Project A and Project B)
        cls.budget_a = cls.env['fund.budget.line'].create({
            'name': 'Project A',
            'target_type': 'project',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })
        cls.budget_b = cls.env['fund.budget.line'].create({
            'name': 'Project B',
            'target_type': 'project',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })

    def test_01_requisition_blocks_insufficient_budget(self):
        """Submitting a requisition with amount > available must fail."""
        req = self.env['fund.requisition'].create({
            'budget_line_id': self.budget_a.id,
            'requested_amount': 999999.0,
            'purpose': 'Too much',
        })
        with self.assertRaises(ValidationError):
            req.action_submit()

    def test_02_requisition_full_workflow(self):
        """Requisition: draft -> submitted -> gm_approval -> approved."""
        req = self.env['fund.requisition'].create({
            'budget_line_id': self.budget_a.id,
            'requested_amount': 150000.0,
            'purpose': 'Project A cap-ex',
        })
        req.action_submit()
        self.assertEqual(req.state, 'submitted')
        self.budget_a.invalidate_recordset(['requisition_hold'])
        self.assertEqual(self.budget_a.requisition_hold, 150000.0)

        req.action_gm_approve(comment='GM ok')
        self.assertEqual(req.state, 'gm_approval')
        req.action_md_approve(comment='MD ok')
        self.assertEqual(req.state, 'approved')
        self.assertEqual(req.remaining_billable_amount, 150000.0)
        self.budget_a.invalidate_recordset(['approved_unspent'])
        self.assertEqual(self.budget_a.approved_unspent, 150000.0)

    def test_03_bill_post_blocks_excess_amount(self):
        """Posting a 60,000 bill against a 50,000 remaining must fail."""
        req = self.env['fund.requisition'].create({
            'budget_line_id': self.budget_a.id,
            'requested_amount': 150000.0,
            'purpose': 'Project A',
        })
        req.action_submit()
        req.action_gm_approve()
        req.action_md_approve()
        req.invalidate_recordset(['remaining_billable_amount'])

        # Post first bill for 100,000
        bill1 = self.env['fund.bill'].create({
            'requisition_id': req.id,
            'amount': 100000.0,
        })
        bill1.action_post()
        req.invalidate_recordset(['remaining_billable_amount'])
        self.assertEqual(req.remaining_billable_amount, 50000.0)

        # Attempt to post 60,000 — should be blocked
        bill2 = self.env['fund.bill'].create({
            'requisition_id': req.id,
            'amount': 60000.0,
        })
        with self.assertRaises(ValidationError):
            bill2.action_post()

    def test_04_bill_budget_line_mismatch_blocked(self):
        """Bill budget_line_id must equal requisition's budget_line_id."""
        req_b = self.env['fund.requisition'].create({
            'budget_line_id': self.budget_b.id,
            'requested_amount': 100000.0,
            'purpose': 'Project B',
        })
        req_b.action_submit()
        req_b.action_gm_approve()
        req_b.action_md_approve()

        bill = self.env['fund.bill'].create({
            'requisition_id': req_b.id,
            'budget_line_id': self.budget_a.id,  # mismatched
            'amount': 10000.0,
        })
        with self.assertRaises(ValidationError):
            bill._check_budget_line_match()

    def test_05_bill_cancel_reverses_balances(self):
        """Cancelling a posted bill returns remaining_billable_amount."""
        req = self.env['fund.requisition'].create({
            'budget_line_id': self.budget_a.id,
            'requested_amount': 50000.0,
            'purpose': 'Project A',
        })
        req.action_submit()
        req.action_md_approve()
        req.invalidate_recordset(['remaining_billable_amount'])

        bill = self.env['fund.bill'].create({
            'requisition_id': req.id,
            'amount': 20000.0,
        })
        bill.action_post()
        req.invalidate_recordset(['remaining_billable_amount'])
        self.assertEqual(req.remaining_billable_amount, 30000.0)

        bill.action_cancel()
        req.invalidate_recordset(['remaining_billable_amount'])
        self.assertEqual(req.remaining_billable_amount, 50000.0)

    def test_06_close_without_release_blocks_if_unused(self):
        """Closing an approved requisition with remaining funds requires release_unused."""
        req = self.env['fund.requisition'].create({
            'budget_line_id': self.budget_a.id,
            'requested_amount': 80000.0,
            'purpose': 'Project A',
        })
        req.action_submit()
        req.action_md_approve()
        with self.assertRaises(UserError):
            req.action_close()
        # Now close with release_unused
        req.action_close(release_unused=True)
        self.assertEqual(req.state, 'closed')
