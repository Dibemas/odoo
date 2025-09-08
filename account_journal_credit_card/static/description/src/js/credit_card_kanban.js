odoo.define('account_journal_credit_card.cc_upload_button', function (require) {
    "use strict";

    const KanbanRecord = require('account.DashboardKanbanRecord');
    const patch = require('web.patch');
    const { onMounted } = owl.hooks;

    patch(KanbanRecord.prototype, {
        setup() {
            this._super(...arguments);
            onMounted(() => {
                const el = this.el;
                const isCC = el.querySelector('input[name="is_credit_card"]');
                const btn = el.querySelector('.o_cc_upload_button');
                if (isCC?.checked && btn) {
                    btn.classList.remove('d-none');
                }
            });
        },
    });

});
