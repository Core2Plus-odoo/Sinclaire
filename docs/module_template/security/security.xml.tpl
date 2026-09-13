<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">

        <!-- Multi-company isolation. Required for every model carrying a
             company_id; without it records leak across companies. -->
        <record id="sinclaire_model_name_company_rule" model="ir.rule">
            <field name="name">sinclaire.model.name: multi-company</field>
            <field name="model_id" ref="model_sinclaire_model_name"/>
            <field name="global" eval="True"/>
            <field name="domain_force">
                ['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]
            </field>
        </record>

    </data>
</odoo>
