odoo.define('account_journal_credit_card.credit_card_toggle', function (require) {
    "use strict";

    const { onMounted } = owl.hooks;
    const KanbanRecord = require('account.DashboardKanbanRecord');

    const patch = require('web.patch');
    patch(KanbanRecord.prototype, {
        setup() {
            this._super(...arguments);
            onMounted(() => {
                const el = this.el;
                const isCC = el.querySelector('input[name="is_credit_card"]');
                if (isCC && isCC.checked) {
                    const box = el.querySelector('.o_cc_upload_box');
                    if (box) {
                        box.classList.remove('d-none');
                    }
                }
            });
        },
    });
});
