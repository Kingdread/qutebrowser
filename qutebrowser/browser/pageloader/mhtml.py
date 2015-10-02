# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2015 Daniel Schadt
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Utils for writing a MHTML file."""

import collections
import uuid
import email.policy
import email.generator
import email.encoders
import email.mime.multipart

from qutebrowser.browser.pageloader import writer


_File = collections.namedtuple('_File',
                               ['content', 'content_type', 'content_location',
                                'transfer_encoding'])


MHTMLPolicy = email.policy.default.clone(linesep='\r\n', max_line_length=0)


E_BASE64 = email.encoders.encode_base64
"""Encode the file using base64 encoding"""

E_QUOPRI = email.encoders.encode_quopri
"""Encode the file using MIME quoted-printable encoding."""


class MHTMLWriter(writer.PageWriter):

    """A class for outputting multiple files to a MHTML document.

    Attributes:
        (see writer.PageWriter)
        _files: Mapping of location->_File struct.
    """

    suggested_ext = '.mht'

    def __init__(self, root_content, content_location, content_type, dest):
        super().__init__(root_content, content_location, content_type, dest)
        self._files = {}

    def add_file(self, location, content, content_type=None):
        """Add a file to the given MHTML collection.

        Overwritten PageWriter.add_file.
        """
        transfer_encoding = E_BASE64
        if content_type is not None and content_type.startswith('text/'):
            transfer_encoding = E_QUOPRI
        self._files[location] = _File(
            content=content, content_type=content_type,
            content_location=location, transfer_encoding=transfer_encoding,
        )

    def remove_file(self, location):
        """Remove a file.

        Overwritten PageWriter.remove_file.
        """
        del self._files[location]

    def write(self):
        """Output the MHTML file.

        Overwritten PageWrite.write.
        """
        msg = email.mime.multipart.MIMEMultipart(
            'related', '---=_qute-{}'.format(uuid.uuid4()))

        root = self._create_root_file()
        msg.attach(root)

        for _, file_data in sorted(self._files.items()):
            msg.attach(self._create_file(file_data))

        with open(self.dest, 'wb') as fp:
            gen = email.generator.BytesGenerator(fp, policy=MHTMLPolicy)
            gen.flatten(msg)

    def _create_root_file(self):
        """Return the root document as MIMEMultipart."""
        root_file = _File(
            content=self.root_content, content_type=self.content_type,
            content_location=self.content_location, transfer_encoding=E_QUOPRI,
        )
        return self._create_file(root_file)

    def _create_file(self, f):
        """Return the single given file as MIMEMultipart."""
        msg = email.mime.multipart.MIMEMultipart()
        msg['Content-Location'] = f.content_location
        # Get rid of the default type multipart/mixed
        del msg['Content-Type']
        if f.content_type:
            msg.set_type(f.content_type)
        msg.set_payload(f.content)
        f.transfer_encoding(msg)
        return msg
