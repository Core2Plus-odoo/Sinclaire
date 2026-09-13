<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="sinclaire_model_name_view_list" model="ir.ui.view">
        <field name="name">sinclaire.model.name.list</field>
        <field name="model">sinclaire.model.name</field>
        <field name="arch" type="xml">
            <list>
                <field name="sequence" widget="handle"/>
                <field name="name"/>
                <field name="company_id" groups="base.group_multi_company"/>
            </list>
        </field>
    </record>

    <record id="sinclaire_model_name_view_form" model="ir.ui.view">
        <field name="name">sinclaire.model.name.form</field>
        <field name="model">sinclaire.model.name</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="sequence"/>
                        <field name="active" invisible="1"/>
                        <field name="company_id" groups="base.group_multi_company"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="sinclaire_model_name_action" model="ir.actions.act_window">
        <field name="name">Model Name</field>
        <field name="res_model">sinclaire.model.name</field>
        <field name="view_mode">list,form</field>
    </record>

</odoo>
