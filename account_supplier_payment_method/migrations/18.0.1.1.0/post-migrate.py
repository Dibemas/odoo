from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # The payment methods are noupdate data, so the new flag is not loaded on upgrade.
    env = api.Environment(cr, SUPERUSER_ID, {})
    bank_transfer = env.ref('account_supplier_payment_method.payment_method_bank_transfer', raise_if_not_found=False)
    if bank_transfer:
        bank_transfer.include_in_payment_run = True
