from odoo import tests
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestFundTransfer(TransactionCase):
    """Tests covering fund.transfer workflow and balance guards."""

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

        # Create two budget lines and allocate funds to each
        cls.source_line = cls.env['fund.budget.line'].create({
            'name': 'Source Budget',
            'target_type': 'expense_head',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })
        cls.dest_line = cls.env['fund.budget.line'].create({
            'name': 'Destination Budget',
            'target_type': 'project',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })

        # Allocate 100,000 to source and 50,000 to destination
        for line, amt in [(cls.source_line, 100000.0), (cls.dest_line, 50000.0)]:
            alloc = cls.env['fund.allocation'].create({
                'fund_account_id': cls.fund_account.id,
                'budget_line_id': line.id,
                'amount': amt,
                'purpose': 'Initial allocation',
            })
            alloc.action_submit()
            alloc.action_gm_approve()
            alloc.action_md_approve()
            line.invalidate_recordset(['available', 'total_allocated'])

    def test_01_submit_blocks_insufficient_funds(self):
        """Submitting a transfer with amount > source.available must fail."""
        transfer = self.env['fund.transfer'].create({
            'source_budget_line_id': self.source_line.id,
            'destination_budget_line_id': self.dest_line.id,
            'amount': 999999.0,
            'reason': 'Too much',
        })
        with self.assertRaises(ValidationError):
            transfer.action_submit()

    def test_02_transfer_full_workflow(self):
        """Transfer: draft -> submitted -> gm_approval -> approved."""
        transfer = self.env['fund.transfer'].create({
            'source_budget_line_id': self.source_line.id,
            'destination_budget_line_id': self.dest_line.id,
            'amount': 30000.0,
            'reason': 'Reallocate',
        })

        # Confirm source available before submit
        self.source_line.invalidate_recordset(['available', 'transfer_hold'])
        self.assertEqual(self.source_line.available, 100000.0)
        self.assertEqual(self.source_line.transfer_hold, 0.0)

        transfer.action_submit()
        self.assertEqual(transfer.state, 'submitted')
        self.source_line.invalidate_recordset(['available', 'transfer_hold'])
        self.assertEqual(self.source_line.transfer_hold, 30000.0)
        self.assertEqual(self.source_line.available, 70000.0)

        transfer.action_gm_approve()
        self.assertEqual(transfer.state, 'gm_approval')

        transfer.action_md_approve()
        self.assertEqual(transfer.state, 'approved')

        # After approval: source transferred, destination increased
        self.source_line.invalidate_recordset(['transfer_hold', 'outgoing_transfers', 'available'])
        self.dest_line.invalidate_recordset(['incoming_transfers', 'total_allocated', 'available'])
        self.assertEqual(self.source_line.transfer_hold, 0.0)
        self.assertEqual(self.source_line.outgoing_transfers, 30000.0)
        self.assertEqual(self.source_line.available, 70000.0)
        self.assertEqual(self.dest_line.incoming_transfers, 30000.0)
        self.assertEqual(self.dest_line.total_allocated, 80000.0)  # 50k + 30k
        self.assertEqual(self.dest_line.available, 80000.0)

    def test_03_reject_returns_hold_to_source(self):
        """Rejecting an approved transfer releases source.transfer_hold."""
        transfer = self.env['fund.transfer'].create({
            'source_budget_line_id': self.source_line.id,
            'destination_budget_line_id': self.dest_line.id,
            'amount': 25000.0,
            'reason': 'Test reject',
        })
        transfer.action_submit()
        transfer.action_gm_approve()
        self.source_line.invalidate_recordset(['transfer_hold', 'available'])
        self.assertEqual(self.source_line.transfer_hold, 25000.0)

        transfer.action_reject(comment='No longer needed')
        self.assertEqual(transfer.state, 'rejected')
        self.source_line.invalidate_recordset(['transfer_hold', 'available'])
        self.assertEqual(self.source_line.transfer_hold, 0.0)
        self.assertEqual(self.source_line.available, 100000.0)

    def test_04_transfer_hold_blocks_simultaneous_requisition(self):
        """Transfer hold must reduce source.available so requisitions cannot overdraw."""
        # Source has 100,000 available
        self.source_line.invalidate_recordset(['available'])
        self.assertEqual(self.source_line.available, 100000.0)

        # Submit a transfer for 40,000
        transfer = self.env['fund.transfer'].create({
            'source_budget_line_id': self.source_line.id,
            'destination_budget_line_id': self.dest_line.id,
            'amount': 40000.0,
            'reason': 'Hold test',
        })
        transfer.action_submit()
        self.source_line.invalidate_recordset(['available', 'transfer_hold'])
        self.assertEqual(self.source_line.transfer_hold, 40000.0)
        self.assertEqual(self.source_line.available, 60000.0)  # 100k - 40k held

        # Now attempting a requisition for 80,000 should fail
        req = self.env['fund.requisition'].create({
            'budget_line_id': self.source_line.id,
            'requested_amount': 80000.0,
            'purpose': 'Cannot afford',
        })
        with self.assertRaises(ValidationError):
            req.action_submit()

    def test_05_source_destination_same_blocked(self):
        """Source and destination must be different budget lines."""
        transfer = self.env['fund.transfer'].create({
            'source_budget_line_id': self.source_line.id,
            'destination_budget_line_id': self.source_line.id,
            'amount': 1000.0,
        })
        with self.assertRaises(ValidationError):
            transfer._check_source_destination_different()
