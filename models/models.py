# -*- coding: utf-8 -*-
"""
    s3-storage.models
    ~~~~~~~~~~~~~~~~~

    Use s3 as file storage mechanism

    :copyright: (c) 2020 by Gabriel Martínez.
    :license: MIT License, see LICENSE for more details.
"""

import hashlib
import base64
import hashlib
import io
import itertools
import logging
import mimetypes
import os
import re
import uuid
import mimetypes


from odoo import models
from . import s3_helper
from odoo import api, fields, models, SUPERUSER_ID, tools, _

_logger = logging.getLogger(__name__)

class S3Attachment(models.Model):
    """Extends ir.attachment to implement the S3 storage engine
    """
    _inherit = "ir.attachment"
    aws_image_url = fields.Char(string="AWS Image URL", help="URL of the image stored in AWS S3")
    
    def _get_datas_related_values(self, data, mimetype):
        checksum = self._compute_checksum(data)
        try:
            index_content = self._index(data, mimetype, checksum=checksum)
        except TypeError:
            index_content = self._index(data, mimetype)
        values = {
            'file_size': len(data),
            'checksum': checksum,
            'index_content': index_content,
            'store_fname': False,
            'db_datas': data,
        }
        if data and self._storage() != 'db':
            values['store_fname'] = self._file_write_s3(data, values['checksum'], mimetype, values)
            values['db_datas'] = False
        return values


    @api.model
    def _file_read(self, file_name, bin_size=False):
        _logger.info(f"self readdddd == {self}  and filename = {file_name}")
        _, file_extension = os.path.splitext(file_name)
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg']
        data_from_s3 = False
        if file_extension in allowed_extensions:
            data_from_s3 = True
        s3, bucket_name = s3_helper.get_s3_connection(self)
        if s3 is not None and data_from_s3:
            file_exists = s3_helper.s3_object_exists(s3, bucket_name, file_name)
            if file_exists:
                read = s3.get_object(Bucket=bucket_name, Key=file_name)['Body'].read()
                return read
        try: # falling back on Odoo's local filestore
            read = super(S3Attachment, self)._file_read(file_name, bin_size=False)
        except Exception:
            return False
        return read

    @api.model
    def _file_write_s3(self, value, checksum, mimetype, obj_value):
        _logger.info(f"self == {self} , mimetype == {mimetype}")
        s3, bucket_name = s3_helper.get_s3_connection(self)
        if s3 is not None:
            #bin_value = base64.b64decode(value)
            bin_value = value
            file_name_only = hashlib.sha1(bin_value).hexdigest()
            # Get the file extension based on the mimetype
            file_extension = mimetypes.guess_extension(mimetype) or ''  # Guess the extension, default to empty string if None

             # Allowed image file extensions
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg']
            
            # Check if the file extension is allowed
            if file_extension not in allowed_extensions:
                return self._local_file_write(value=value, checksum=checksum)
        
            # Append the file extension to the file name
            file_name = f"{file_name_only}{file_extension}"
            icp_sudo = self.env['ir.config_parameter'].sudo()
            aws_prefix_file_name = icp_sudo.get_param('aws_prefix_file_name')
            if aws_prefix_file_name:
                file_name = f"{aws_prefix_file_name}{file_name}"
            _logger.info(f"file_name to write to AWS : {file_name}")
            s3.put_object(Body=bin_value, ContentType=mimetype, Key=file_name, Bucket=bucket_name)
        else: # falling back on Odoo's local filestore
            self._local_file_write(value=value, checksum=checksum)
        return file_name

    def _local_file_write(self, value, checksum):
        file_name = super(S3Attachment, self)._file_write(value, checksum)
        return file_name
