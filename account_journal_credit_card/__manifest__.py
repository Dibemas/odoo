
{
    'name': 'Credit Card - Module',
    'version': '17.0',
    'category': 'Tools',
    'description': "Simplify the administration and Follow up of credit card payments",
    'license': 'LGPL-3',
    'author': "Marco Silva, Johan Camp",
    'depends': ['base', 'account', 'account_accountant'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_journal_views.xml',
        'wizard/account_journal_credit_card_wizard.xml',
    ],
    "assets": {
        "web.assets_backend": [
            "account_journal_credit_card/static/src/js/credit_card_toggle.js"
            "account_journal_credit_card/static/src/js/credit_card_kanban.js"
        ]
    },
    'installable': True,
    'application': False,
}
