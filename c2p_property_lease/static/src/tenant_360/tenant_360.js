/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Tenant 360 — the tenancy dossier.
 *
 * All data arrives from a single `get_tenant_profile` call. Every summary
 * figure carries the domain that produced it, so clicking a number opens the
 * exact record set it was computed from: a figure nobody can open is a figure
 * nobody can check, and this module has shipped two that were quietly wrong.
 */
export class C2pTenant360 extends Component {
    static template = "c2p_property_lease.Tenant360";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, error: null, data: null });

        const params = this.props.action.params || {};
        this.partnerId = params.partner_id || this.props.action.context?.active_id;

        onWillStart(async () => {
            if (!this.partnerId) {
                this.state.error = "No tenant selected.";
                this.state.loading = false;
                return;
            }
            try {
                this.state.data = await this.orm.call("res.partner", "get_tenant_profile", [
                    [this.partnerId],
                ]);
            } catch (error) {
                this.state.error =
                    error.message?.data?.message || "Could not load this tenant's dossier.";
            }
            this.state.loading = false;
        });
    }

    // --- formatting ---------------------------------------------------
    // Kept here rather than in the template because OWL expressions cannot
    // reach Intl, and a half-formatted number is worse than none.

    get currency() {
        return this.state.data?.currency || "AED";
    }

    amount(value) {
        const number = Number(value || 0);
        return `${this.currency} ${number.toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        })}`;
    }

    /** One decimal, and never the percentage widget: it expects a 0-1
     *  fraction and these are already 0-100. That mismatch is what put
     *  "8200%" on the Command Center. */
    percent(value) {
        return `${Number(value || 0).toFixed(1)}%`;
    }

    years(days) {
        if (days === null || days === undefined) {
            return "";
        }
        if (days < 365) {
            return `${days} days`;
        }
        const value = days / 365;
        return `${value.toFixed(value < 10 ? 1 : 0)} years`;
    }

    countdown(days) {
        if (days === null || days === undefined) {
            return "";
        }
        if (days < 0) {
            return `${Math.abs(days)} days ago`;
        }
        if (days === 0) {
            return "today";
        }
        return `in ${days} days`;
    }

    /** Computed here rather than in the template: OWL rewrites identifiers
     *  when it compiles an expression, which can catch an arrow function's
     *  own parameter. */
    get hasInstruments() {
        return (this.state.data?.cheques?.buckets || []).some((bucket) => bucket.count > 0);
    }

    // --- the flags, ordered by how much they should worry the reader ---

    get flags() {
        const risk = this.state.data?.risk;
        if (!risk) {
            return [];
        }
        const flags = [];
        if (risk.breached_exception) {
            flags.push({
                tone: "danger",
                text: "A cheque exception passed its deadline with cheques still outstanding.",
            });
        }
        if (risk.bounced_now) {
            flags.push({ tone: "danger", text: "A cheque is currently returned unpaid." });
        }
        if (risk.cheques_short) {
            flags.push({
                tone: "warning",
                text: "A running tenancy does not have its full cheque set.",
            });
        }
        if (risk.open_exception) {
            flags.push({ tone: "warning", text: "A cheque exception is open on this tenant." });
        }
        if (risk.expiring_soon) {
            flags.push({
                tone: "warning",
                text: `Tenancy expires ${this.countdown(risk.expiring_days)}.`,
            });
        }
        if (risk.ever_bounced && !risk.bounced_now) {
            flags.push({ tone: "muted", text: "Has bounced a cheque before." });
        }
        if (risk.no_live_tenancy) {
            flags.push({ tone: "muted", text: "No running tenancy." });
        }
        return flags;
    }

    // --- drill-through -------------------------------------------------

    openList(model, domain, name) {
        if (!domain) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            domain,
            view_mode: "list,form",
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }

    openRecord(model, resId) {
        if (!resId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: resId,
            view_mode: "form",
            views: [[false, "form"]],
        });
    }

    openLeases() {
        this.openList("c2p.lease", this.state.data?.domains?.leases, "Tenancies");
    }

    openInstruments() {
        this.openList("account.payment", this.state.data?.domains?.instruments, "Cheques");
    }

    openBucket(bucket) {
        this.openList("account.payment", bucket.domain, bucket.label);
    }

    openEverBounced() {
        this.openList(
            "account.payment",
            this.state.data?.cheques?.ever_bounced_domain,
            "Ever bounced"
        );
    }
}

registry.category("actions").add("c2p_tenant_360", C2pTenant360);
