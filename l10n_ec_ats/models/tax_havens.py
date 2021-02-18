from odoo import fields, models, api


class TaxHavens(models.Model):
    _name = 'ats.tax.havens'
    _description = 'Tax Havens'

    value = fields.Char(string='Value', required=True,)
    name = fields.Char(string='Name', required=True)
    country_id = fields.Many2one('res.country', string='Country', ondelete='restrict')
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
