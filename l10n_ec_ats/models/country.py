from odoo import fields, models, api


class Country(models.Model):
    _inherit = 'res.country'

    ats_code = fields.Char()
