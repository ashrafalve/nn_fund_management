__manifest__ = {
    'name': 'NN Fund Management',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Fund Management',
    'summary': 'Fund management, allocation, requisition, and billing system.',
    'description': """
NN Fund Management
==================
Comprehensive fund management module for handling incoming funds,
budget allocations, requisitions, billing, and fund transfers.
Includes multi-level approval workflows (GM / MD) and full audit trail.
""",
    'author': 'Assessment Candidate',
    'depends': ['base', 'mail', 'project'],
    'data': [
        'security/fund_security_groups.xml',
        'data/ir_sequence_data.xml',
        'views/fund_menu.xml',
        'views/fund_account_views.xml',
        'views/fund_expense_head_views.xml',
        'views/fund_budget_line_views.xml',
        'views/fund_incoming_views.xml',
    ],
    'demo': [],
    'test': ['tests/test_fund_approval_mixin.py'],
    'installable': True,
    'application': True,
}
