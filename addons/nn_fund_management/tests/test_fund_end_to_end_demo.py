from odoo import tests
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestFundEndToEndDemo(TransactionCase):
    """Full end-to-end demonstration scenario from the assessment spec.

    Scenario:
    1. Receive 1,000,000 into fund account
    2. Allocate 600,000 to Project A
    3. Reject that allocation
    4. Resubmit and approve the allocation
    5. Transfer 200,000 from Project A to Project B
    6. Approve the transfer
    7. Create 150,000 requisition on Project B
    8. Post 100,000 bill against it
    9. Attempt 60,000 bill — blocked (only 50,000 remaining)
    10. Attempt cross-project requisition use — blocked
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.env.company.currency_id

        # Create a fund account and fund it with 1,000,000
        cls.fund_account = cls.env['fund.account'].create({
            'name': 'Main Fund Account',
            'account_type': 'bank',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })
        inc = cls.env['fund.incoming'].create({
            'fund_account_id': cls.fund_account.id,
            'date': '2026-06-15',
            'amount': 1000000.0,
            'state': 'draft',
        })
        inc.action_confirm()
        cls.fund_account.invalidate_recordset(['total_received', 'unassigned_balance'])
        cls.assertEqual(cls.fund_account.total_received, 1000000.0)
        cls.assertEqual(cls.fund_account.unassigned_balance, 1000000.0)

        # Create two budget lines
        cls.project_a = cls.env['fund.budget.line'].create({
            'name': 'Project A',
            'target_type': 'project',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })
        cls.project_b = cls.env['fund.budget.line'].create({
            'name': 'Project B',
            'target_type': 'project',
            'company_id': cls.company.id,
            'currency_id': cls.currency.id,
        })

    def test_01_full_demo_scenario(self):
        """End-to-end: 1M receive -> 600k allocate -> reject -> resubmit -> approve -> transfer 200k A->B -> 150k requisition B -> 100k bill -> 50k remaining -> 60k bill blocked."""

        # Step 2: Allocate 600,000 to Project A
        alloc = self.env['fund.allocation'].create({
            'fund_account_id': self.fund_account.id,
            'budget_line_id': self.project_a.id,
            'amount': 600000.0,
            'purpose': 'Project A allocation',
            'request_date': '2026-06-15',
        })
        alloc.action_submit(comment='Please approve')
        self.assertEqual(alloc.state, 'submitted')
        self.fund_account.invalidate_recordset(['held_amount', 'unassigned_balance'])
        self.assertEqual(self.fund_account.held_amount, 600000.0)
        self.assertEqual(self.fund_account.unassigned_balance, 0.0)

        # Step 3: Reject the allocation
        alloc.action_reject(comment='Budget review')
        self.assertEqual(alloc.state, 'rejected')
        self.fund_account.invalidate_recordset(['held_amount', 'unassigned_balance'])
        self.assertEqual(self.fund_account.held_amount, 0.0)
        self.assertEqual(self.fund_account.unassigned_balance, 1000000.0)

        # Step 4: Resubmit and approve
        alloc.write({'state': 'draft'})
        alloc.action_submit(comment='Resubmitted')
        alloc.action_gm_approve(comment='GM approved')
        alloc.action_md_approve(comment='MD approved')
        self.assertEqual(alloc.state, 'approved')
        self.project_a.invalidate_recordset(['total_allocated', 'available'])
        self.assertEqual(self.project_a.total_allocated, 600000.0)
        self.assertEqual(self.project_a.available, 600000.0)
        self.fund_account.invalidate_recordset(['assigned_amount', 'held_amount', 'unassigned_balance'])
        self.assertEqual(self.fund_account.assigned_amount, 600000.0)
        self.assertEqual(self.fund_account.held_amount, 0.0)
        self.assertEqual(self.fund_account.unassigned_balance, 0.0)

        # Step 5: Transfer 200,000 from Project A to Project B
        transfer = self.env['fund.transfer'].create({
            'source_budget_line_id': self.project_a.id,
            'destination_budget_line_id': self.project_b.id,
            'amount': 200000.0,
            'reason': 'Reallocate to Project B',
            'request_date': '2026-06-15',
        })
        transfer.action_submit()
        self.project_a.invalidate_recordset(['available', 'transfer_hold'])
        self.assertEqual(self.project_a.transfer_hold, 200000.0)
        self.assertEqual(self.project_a.available, 400000.0)  # 600k - 200k held

        # Step 6: Approve the transfer
        transfer.action_gm_approve()
        transfer.action_md_approve()
        self.assertEqual(transfer.state, 'approved')
        self.project_a.invalidate_recordset(['transfer_hold', 'outgoing_transfers', 'available'])
        self.project_b.invalidate_recordset(['incoming_transfers', 'total_allocated', 'available'])
        self.assertEqual(self.project_a.transfer_hold, 0.0)
        self.assertEqual(self.project_a.outgoing_transfers, 200000.0)
        self.assertEqual(self.project_a.available, 400000.0)
        self.assertEqual(self.project_b.incoming_transfers, 200000.0)
        self.assertEqual(self.project_b.total_allocated, 200000.0)
        self.assertEqual(self.project_b.available, 200000.0)

        # Step 7: Create 150,000 requisition on Project B
        req = self.env['fund.requisition'].create({
            'budget_line_id': self.project_b.id,
            'requested_amount': 150000.0,
            'purpose': 'Project B requisition',
            'request_date': '2026-06-15',
        })
        req.action_submit()
        self.project_b.invalidate_recordset(['requisition_hold', 'available'])
        self.assertEqual(self.project_b.requisition_hold, 150000.0)
        self.assertEqual(self.project_b.available, 50000.0)  # 200k - 150k held

        req.action_gm_approve()
        req.action_md_approve()
        self.assertEqual(req.state, 'approved')
        self.assertEqual(req.remaining_billable_amount, 150000.0)
        self.project_b.invalidate_recordset(['approved_unspent'])
        self.assertEqual(self.project_b.approved_unspent, 150000.0)

        # Step 8: Post 100,000 bill against requisition
        bill1 = self.env['fund.bill'].create({
            'requisition_id': req.id,
            'amount': 100000.0,
            'date': '2026-06-15',
        })
        bill1.action_post()
        self.assertEqual(bill1.state, 'posted')
        req.invalidate_recordset(['remaining_billable_amount'])
        self.project_b.invalidate_recordset(['total_spent', 'available', 'approved_unspent'])
        self.assertEqual(req.remaining_billable_amount, 50000.0)
        self.assertEqual(self.project_b.total_spent, 100000.0)
        self.assertEqual(self.project_b.available, 100000.0)  # 200k - 150k hold - 100k spent
        self.assertEqual(self.project_b.approved_unspent, 50000.0)

        # Step 9: Attempt 60,000 bill — blocked
        bill2 = self.env['fund.bill'].create({
            'requisition_id': req.id,
            'amount': 60000.0,
            'date': '2026-06-15',
        })
        with self.assertRaises(ValidationError):
            bill2.action_post()

        # Step 10: Cross-project requisition use blocked
        req_a = self.env['fund.requisition'].create({
            'budget_line_id': self.project_a.id,
            'requested_amount': 100000.0,
            'purpose': 'Project A req',
            'request_date': '2026-06-15',
        })
        req_a.action_submit()
        req_a.action_md_approve()

        bill_cross = self.env['fund.bill'].create({
            'requisition_id': req_a.id,
            'budget_line_id': self.project_b.id,  # mismatched
            'amount': 10000.0,
            'date': '2026-06-15',
        })
        with self.assertRaises(ValidationError):
            bill_cross._check_budget_line_match()
