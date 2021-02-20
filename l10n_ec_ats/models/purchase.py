# -*- coding: utf-8 -*-
###############################################################################
#
#    INGEINT SA.
#    Copyright (C) 2020 INGEINT SA-(<http://www.ingeint.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    auth_date = fields.Date('Fecha de autorizacion')
    sustento_id = fields.Many2one('sustents.tax', 'Sustento Tributario')
    payment_info = fields.Selection([('non-resident', 'Payment To Non-resident'),
                                     ('resident', 'Payment To Resident')])
    is_tax_havens = fields.Boolean(string='Tax Havens')
    tax_heavens_id = fields.Many2one('ats.tax.havens', string='Tax Havens List', ondelete='restrict')

    # @api.onchange('sri_authorization_po')
    # def _sri_authorization_po(self):
    #     if self.sri_authorization_po:
    #         if len(self.sri_authorization_po) != 10 or len(self.sri_authorization_po) != 49:
    #             raise ValidationError("Error the code is not valid")

    @api.constrains('l10n_latam_document_number')
    def validate_number_invoice(self):
        count = 0
        moves = self.env['account.move'].search([
            ('l10n_latam_document_number', '=', self.l10n_latam_document_number),
            ('partner_id', '=', self.partner_id.id),
            ('state', '=', 'posted')
        ])
        for move in moves:
            credit_note = self.env['account.move'].search([
                ('reversed_entry_id', '=', move.id),
                ('state', '=', 'posted')
            ])
            if not credit_note:
                count += 1
        if count > 1:
            raise ValidationError('El numero de factura del proveedor ya esta registrada')

    @api.onchange('l10n_latam_document_number')
    def create_number(self):
        if self.l10n_latam_document_number:
            if len(self.l10n_latam_document_number) != 17 and 'FACTU' not in self.l10n_latam_document_number:
                if self.l10n_latam_document_number.isdigit() and len(self.l10n_latam_document_number) == 15:
                    first = self.l10n_latam_document_number[0:3] + '-'
                    two = self.l10n_latam_document_number[3:6] + '-'
                    three = self.l10n_latam_document_number[6:17]
                    self.l10n_latam_document_number = str(first) + str(two) + str(three)
                else:
                    raise ValidationError(_('Error the document number is incorrect'))
