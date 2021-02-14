import base64
import os
import logging
import itertools
from datetime import datetime

from odoo.addons.account import report
from jinja2 import Environment, FileSystemLoader, Template

from odoo import api, models, fields
from odoo.exceptions import Warning as UserError

from odoo.addons.account_test import report
from odoo.addons.base.models.ir_attachment import IrAttachment
from odoo.tools import safe_eval

from . import utils
from . import edocument

from ..xades.sri import DocumentXML, SriService
import os.path
from os import path


class Invoice(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'account.edocument']
    _logger = logging.getLogger('account.edocument')
    TEMPLATES = {
        'out_invoice': 'out_invoice.xml',
        'out_refund': 'out_refund.xml'
    }

    SriServiceObj = SriService()

    sri_authorization = fields.Many2one('sri.authorization', copy=False)
    sri_payment_type = fields.Many2one('sri.payment_type', copy=False)
    account_tax_ids = fields.One2many('account.move.tax', 'move_id')

    def _info_invoice(self):
        """
        """
        company = self.company_id
        partner = self.partner_id
        infoFactura = {
            'fechaEmision': self.invoice_date.strftime("%d/%m/%Y"),
            'dirEstablecimiento': company.street,
            'obligadoContabilidad': company.is_force_keep_accounting,
            'tipoIdentificacionComprador': partner.taxid_type.code,
            'razonSocialComprador': partner.name,
            'identificacionComprador': partner.vat,
            'direccionComprador': partner.street,
            'totalSinImpuestos': '%.2f' % (self.amount_untaxed),
            'totalDescuento': '0.00',
            'propina': '0.00',
            'importeTotal': '{:.2f}'.format(self.amount_total),
            'moneda': 'USD',
            'formaPago': self.sri_payment_type.code,
            'valorRetIva': '0.00',
            'valorRetRenta': '0.00',
            'contribuyenteEspecial': company.is_special_taxpayer
        }

        totalConImpuestos = []
        for line in self.account_tax_ids:
            totalImpuesto = {
                'codigo': line.tax_id.sri_code.code,
                'codigoPorcentaje': line.tax_id.sri_rate.code,
                'baseImponible': '{:.2f}'.format(line.base_tax),
                'tarifa': line.tax_percent,
                'valor': '{:.2f}'.format(line.tax_total)
            }
            totalConImpuestos.append(totalImpuesto)

        infoFactura.update({'totalConImpuestos': totalConImpuestos})

        if self.move_type == 'out_refund':
            inv = self.search([('name', '=', self.origin)], limit=1)
            inv_number = self.name
            notacredito = {
                'codDocModificado': inv.auth_inv_id.type_id.code,
                'numDocModificado': inv_number,
                'motivo': self.name,
                'fechaEmisionDocSustento': (inv.invoice_date),
                'valorModificacion': self.amount_total
            }
            infoFactura.update(notacredito)
        return infoFactura

    def _detalles(self, invoice):
        """
        """

        def fix_chars(code):
            special = [
                [u'%', ' '],
                [u'º', ' '],
                [u'Ñ', 'N'],
                [u'ñ', 'n']
            ]
            for f, r in special:
                code = code.replace(f, r)
            return code

        detalle_adicional = {
            'nombre': 'Unidad',
            'valor': 1
        }

        detalles = []
        for line in invoice.invoice_line_ids:
            codigoPrincipal = line.product_id and \
                              line.product_id.default_code and \
                              fix_chars(line.product_id.default_code) or '001'
            priced = line.price_unit * (1 - (line.discount or 0.00) / 100.0)
            discount = (line.price_unit - priced) * line.quantity
            detalle = {
                'codigoPrincipal': codigoPrincipal,
                'descripcion': fix_chars(line.name.strip()),
                'cantidad': '%.6f' % line.quantity,
                'precioUnitario': '%.6f' % line.price_unit,
                'descuento': '%.2f' % discount,
                'precioTotalSinImpuesto': '%.2f' % line.price_subtotal,
                'detalle_adicional': detalle_adicional
            }
            impuestos = []
            for tax_line in line:
                percent = int(tax_line.tax_ids.amount)
                impuesto = {
                    'codigo': tax_line.tax_ids.sri_code.code,
                    'codigoPorcentaje': tax_line.tax_ids.sri_rate.code,
                    'tarifa': percent,
                    'baseImponible': '{:.2f}'.format(tax_line.price_subtotal),
                    'valor': '{:.2f}'.format(tax_line.price_subtotal * (tax_line.tax_ids.amount / 100))
                }
                impuestos.append(impuesto)
            detalle.update({'impuestos': impuestos})
            detalles.append(detalle)
        return {'detalles': detalles}

    def render_authorized_einvoice(self, autorizacion):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        einvoice_tmpl = env.get_template('authorized_einvoice.xml')
        auth_xml = {
            'estado': autorizacion.estado,
            'numeroAutorizacion': autorizacion.numeroAutorizacion,
            'ambiente': autorizacion.ambiente,
            'fechaAutorizacion': str(autorizacion.fechaAutorizacion),
            'comprobante': autorizacion.comprobante
        }
        auth_invoice = einvoice_tmpl.render(auth_xml)
        return auth_invoice

    def action_generate_einvoice(self):
        for obj in self:
            if obj.move_type not in ['out_invoice', 'out_refund'] and not obj.journal_id.is_electronic_document:
                continue
            access_key, emission_code = self._get_codes(name='account.move')
            einvoice = self.render_document(obj, access_key, emission_code)
            inv_xml = DocumentXML(einvoice, obj.move_type)
            is_error, message = inv_xml.validate_xml()
            if is_error:
                raise UserError("Not Valid Schema" + message)
            xades = self.env['sri.key.type'].search([
                ('company_id', '=', self.company_id.id)
            ])
            x_path = obj.company_id.log_path
            if not path.exists(x_path):
                os.mkdir(x_path)
            to_sign_file = open(x_path + 'FACTURA_SRI_' + self.name + ".xml", 'w')
            to_sign_file.write(einvoice)
            to_sign_file.close()
            signed_document = xades.action_sign(to_sign_file)
            ok, errores = inv_xml.send_receipt(signed_document)
            if ('REGISTRADA') in errores or ok:

                sri_auth = self.env['sri.authorization'].create({
                    'sri_authorization_code': access_key,
                    'sri_create_date': self.write_date,
                    'account_move': self.id,
                    'env_service': self.company_id.env_service
                })
                self.write({'sri_authorization': sri_auth.id})
            else:
                raise UserError(errores)

    def get_auth(self):
        to_process = self.env['sri.authorization'].search([
            ('processed', '=', False),
            ('is_error', '=', False)
        ])

        SriService.set_active_env(self.company_id.env_service)

        for data in to_process:
            xml = DocumentXML()
            auth, m = xml.request_authorization(data)
            if auth:
                invoice_id = data.account_move
                data.write({'sri_authorization_date': m['fechaAutorizacion']})
                data.write({'processed': True})
                auth_einvoice = self.render_authorized_einvoice(m)
                encoded = self.encode_file(auth_einvoice)
                data.write({'xml_binary': encoded})
                pdf = self.env.ref('l10n_ec_ein.account_invoices_elec').sudo()._render_qweb_pdf(invoice_id.ids)
                message = """
                            DOCUMENTO ELECTRONICO GENERADO <br><br>
                            CLAVE DE ACCESO: %s <br>
                            NUMERO DE AUTORIZACION %s <br>
                            FECHA AUTORIZACION: %s <br>
                            ESTADO DE AUTORIZACION: %s <br>
                            AMBIENTE: %s <br>
                            """ % (
                    m['numeroAutorizacion'],
                    m['numeroAutorizacion'],
                    m['fechaAutorizacion'],
                    m['estado'],
                    'PRUEBAS' if data.company_id.env_service == '1' else 'PRODUCCION'
                )
                data.account_move.message_post(body=message, subject="Factura electronica generada "
                                                                     + data.account_move.name,
                                               email_send=True,
                                               message_type='comment', email_from=data.company_id.email,
                                               author_id=data.company_id.partner_id.id,
                                               attachments=[[invoice_id.name + '.xml', auth_einvoice],
                                                            [invoice_id.name + '.pdf', pdf[0]]],
                                               partner_ids=[invoice_id.partner_id.id, data.company_id.partner_id.id],
                                               subtype='mail.mt_comment')
            else:
                print("error:"+str(m))

    def add_attachment(self, xml_element, auth, sri_auth):
        x_path = auth.company_id.log_path
        if not path.exists(x_path):
            os.mkdir(x_path)
        document = open(x_path + 'FACTURA_SRI_' + auth['numeroAutorizacion'] + ".xml", 'w')
        document.write(xml_element)
        encoded = self.encode_file(xml_element)
        document.close()

        attach = self.env['ir.attachment'].create(
            {
                'name': '{0}.xml'.format(auth['numeroAutorizacion']),
                'datas': encoded,
                'res_model': 'account.move',
                'res_id': sri_auth.account_move.id,
                'type': 'binary'
            },
        )
        return attach

    def _compute_discount(self, detalles):
        total = sum([float(det['descuento']) for det in detalles['detalles']])
        return {'totalDescuento': total}

    def render_document(self, invoice, access_key, emission_code):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        einvoice_tmpl = env.get_template(self.TEMPLATES[self.move_type])
        data = {}
        data.update(self._info_tributaria(invoice, access_key, emission_code))
        data.update(self._info_invoice())
        detalles = self._detalles(invoice)

        data.update(detalles)
        data.update(self._compute_discount(detalles))
        einvoice = einvoice_tmpl.render(data)
        return einvoice

    @staticmethod
    def _read_template(type):
        with open(os.path.join(os.path.dirname(__file__), 'templates', type + ".xml")) as template:
            return template

    @staticmethod
    def render(self, template_path, **kwargs):
        return Template(
            self._read_template(template_path)
        ).substitute(**kwargs)

    @staticmethod
    def encode_file(text):
        encode = text.encode('utf-8')
        encoded = base64.b64encode(encode)
        return encoded

    def action_post(self):
        res = super(Invoice, self).action_post()
        if self.move_type in ('out_invoice', 'in_invoice', 'in_refund', 'out_refund', 'out_receipt', 'in_receipt'):
            for lines in self.invoice_line_ids:
                if lines.tax_ids:
                    for tax in lines.tax_ids:
                        tax_total = (lines.price_subtotal * tax.amount) / 100
                        self.create_account_move_tax_transient(self.id, tax.id, lines.price_subtotal, tax.amount, tax_total)

            self._cr.execute(
                ' select move_id, tax_id, sum(base_tax) as base_tax , tax_percent, sum(tax_total) '
                ' from account_move_tax_transient '
                ' where move_id = %s '
                ' group by move_id, tax_id, tax_percent',
                [self.id])
            value = self._cr.fetchall()

            if value:
                for sql_value in value:
                    move_id = sql_value[0]
                    tax_id = sql_value[1]
                    base_tax = sql_value[2]
                    tax_percent = sql_value[3]
                    tax_total = sql_value[4]
                    self.create_account_move_tax(move_id, tax_id, base_tax, tax_percent, tax_total)

            return res

    def create_account_move_tax(self, move_id, tax_id, base_tax, tax_percent, tax_total):
        taxes = self.env['account.move.tax'].create({'move_id': move_id,
                                                     'tax_id': tax_id,
                                                     'base_tax': base_tax,
                                                     'tax_percent': tax_percent,
                                                     'tax_total': tax_total
                                                     })
        return taxes

    def create_account_move_tax_transient(self, move_id, tax_id, base_tax, tax_percent, tax_total):
        taxes_transient = self.env['account.move.tax.transient'].create({'move_id': move_id,
                                                                         'tax_id': tax_id,
                                                                         'base_tax': base_tax,
                                                                         'tax_percent': tax_percent,
                                                                         'tax_total': tax_total
                                                                         })
        return taxes_transient
