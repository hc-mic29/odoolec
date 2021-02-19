from odoo import fields, models, api


class ForeignIncomeType(models.Model):
    _name = 'ats.foreign.income.type'
    _description = 'Foreign Income Type'

    value = fields.Char(string='Value', required=True, )
    name = fields.Char(string='Name', required=True)
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
