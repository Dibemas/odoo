from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # 'payment_state' became a condition of is_ready_for_payment: recompute the stored values.
    env = api.Environment(cr, SUPERUSER_ID, {})
    moves = env['account.move'].search([('move_type', 'in', ('in_invoice', 'in_receipt'))])
    env.add_to_compute(moves._fields['is_ready_for_payment'], moves)
    env.flush_all()
