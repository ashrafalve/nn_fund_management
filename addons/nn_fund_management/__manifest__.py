# -*- coding: utf-8 -*-
{
    'name': 'NN Fund Management',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Fund Management',
    'summary': 'Fund management, allocation, requisition, and billing system.',
    'description': (
        "NN Fund Management\n"
        "==================\n"
        "Comprehensive fund management module for handling incoming funds,\n"
        "budget allocations, requisitions, billing, and fund transfers.\n"
        "Includes multi-level approval workflows (GM / MD) and full audit trail.\n"
    ),
    'author': 'Assessment Candidate',
    'depends': ['base', 'mail', 'project'],
    'data': [
        'security/fund_security_groups.xml',
        'security/ir.model.access.csv',
        'security/fund_security_rules.xml',
        'data/ir_sequence_data.xml',
        'views/fund_account_views.xml',
        'views/fund_expense_head_views.xml',
        'views/fund_budget_line_views.xml',
        'views/fund_incoming_views.xml',
        'views/fund_allocation_views.xml',
        'views/fund_requisition_views.xml',
        'views/fund_bill_views.xml',
        'views/fund_transfer_views.xml',
        'views/fund_menu.xml',
    ],
    'demo': [],
    'test': [],
    'installable': True,
    'application': True,
}
