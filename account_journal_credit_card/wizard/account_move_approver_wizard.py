from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountMoveApproverWizard(models.TransientModel):
    _name = 'account.move.approver.wizard'
    _description = 'Account Move Approve or Disapprove Wizard'

    state = fields.Selection([
        ('approved', "Approved"),
        ('disapproved', "Disapproved"),
    ], string='New Status', required=True, default='approved')
    reason = fields.Char('Disapprove Reason')

    def action_approve_or_disapprove_bill(self):
        if self.state:
            if self.state == 'disapproved' and not self.reason:
                raise UserError("You must enter a Reason!")
            else:
                self.env['account.move'].browse(self.env.context.get('active_id')).update_validation_status(
                    self.state, self.reason)
        return {'type': 'ir.actions.act_window_close'}
