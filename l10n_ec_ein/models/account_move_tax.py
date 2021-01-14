from odoo import fields, models, api


class AccountMoveTax(models.Model):
    _name = 'account.move.tax'
    _description = 'Storage Values of tax invoice'

    move_id = fields.Many2one('account.move')
    tax_id = fields.Many2one('account.tax')
    base_tax = fields.Float()
    tax_percent = fields.Float()
    tax_total = fields.Float()


class AccountMoveTaxTransient(models.TransientModel):
    _name = 'account.move.tax.transient'
    _description = 'Storage Values of tax invoice'

    move_id = fields.Many2one('account.move')
    tax_id = fields.Many2one('account.tax')
    base_tax = fields.Float()
    tax_percent = fields.Float()
    tax_total = fields.Float()

