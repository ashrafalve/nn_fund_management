from odoo import tests
from odoo.tests.common import TransactionCase, Form
from odoo.exceptions import UserError
from datetime import date


class TestFundApprovalMixin(TransactionCase):
    """Unit tests for the fund.approval.mixin state machine."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create a transient test model on the fly so we do not pollute
        # the production registry.  We register it dynamically inside the
        # test database only.
        cls._register_test_model()

    @classmethod
    def _register_test_model(cls):
        from odoo import api, models, fields

        class TestApprovalRecord(models.Model):
            _name = 'test.approval.record'
            _description = 'Test Approval Record'
            _inherit = ['fund.approval.mixin']

            name = fields.Char()

        cls.TestApprovalRecord = TestApprovalRecord

    def test_01_draft_submitted_gm_md_approved(self):
        """Happy path: draft -> submitted -> gm_approval -> approved."""
        rec = self.TestApprovalRecord.create({'name': 'Test 1'})
        self.assertEqual(rec.state, 'draft')

        rec.action_submit(comment='Please review')
        self.assertEqual(rec.state, 'submitted')
        self.assertEqual(len(rec.approval_ids), 1)
        self.assertEqual(rec.approval_ids[0].result, 'submitted')

        rec.action_gm_approve(comment='Looks good')
        self.assertEqual(rec.state, 'gm_approval')
        self.assertEqual(rec.approval_ids[1].result, 'approved')

        rec.action_md_approve(comment='Final sign-off')
        self.assertEqual(rec.state, 'approved')
        self.assertEqual(rec.approval_ids[2].result, 'approved')
        self.assertEqual(rec.approval_ids[2].approval_level, 'md')

    def test_02_reject_at_gm_stage(self):
        """Reject a submitted record — should land in rejected."""
        rec = self.TestApprovalRecord.create({'name': 'Test 2'})
        rec.action_submit()
        rec.action_reject(comment='Not aligned with budget')
        self.assertEqual(rec.state, 'rejected')

    def test_03_cancel_from_submitted(self):
        """Cancel from submitted state."""
        rec = self.TestApprovalRecord.create({'name': 'Test 3'})
        rec.action_submit()
        rec.action_cancel(comment='Request withdrawn')
        self.assertEqual(rec.state, 'cancelled')

    def test_04_gm_cannot_approve_draft(self):
        """GM approval blocked on draft — must submit first."""
        rec = self.TestApprovalRecord.create({'name': 'Test 4'})
        with self.assertRaises(UserError):
            rec.action_gm_approve()

    def test_05_md_cannot_approve_draft(self):
        """MD approval blocked on draft."""
        rec = self.TestApprovalRecord.create({'name': 'Test 5'})
        with self.assertRaises(UserError):
            rec.action_md_approve()

    def test_06_state_transitions_are_idempotent(self):
        """Calling action_submit twice must not crash nor double-create."""
        rec = self.TestApprovalRecord.create({'name': 'Test 6'})
        rec.action_submit()
        lines_before = len(rec.approval_ids)
        with self.assertRaises(UserError):
            rec.action_submit()
        self.assertEqual(len(rec.approval_ids), lines_before)
