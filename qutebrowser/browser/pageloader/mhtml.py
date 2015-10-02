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


_File = collections.namedtuple('_File',
                               ['content', 'content_type', 'content_location',
                                'transfer_encoding'])


MHTMLPolicy = email.policy.default.clone(linesep='\r\n', max_line_length=0)


E_BASE64 = email.encoders.encode_base64
"""Encode the file using base64 encoding"""

E_QUOPRI = email.encoders.encode_quopri
"""Encode the file using MIME quoted-printable encoding."""


class MHTMLWriter():

    """A class for outputting multiple files to a MHTML document.

    Attributes:
        root_content: The root content as bytes.
        content_location: The url of the page as str.
        content_type: The MIME-type of the root content as str.
        _files: Mapping of location->_File struct.
    """

    suggested_ext = '.mht'

    def __init__(self, root_content, content_location, content_type, dest):
        self.root_content = root_content
        self.content_location = content_location
        self.content_type = content_type
        self.dest = dest

        self._files = {}

    def rewrite_url(self, url, base=None):
        """Rewrite a URL to point at the (future) resource location.

        Args:
            url: The url to rewrite as QUrl.
            base: The URL of the file that references url (needed for CSS).

        Returns the modified URL.
        """
        return url

    def add_file(self, location, content, content_type=None):
        """Add a file to the given MHTML collection.

        Args:
            location: The original location (URL) of the file.
            content: The binary content of the file.
            content_type: The MIME-type of the content (if available)
            transfer_encoding: The transfer encoding to use for this file.
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

        Args:
            location: The URL that identifies the file.
        """
        del self._files[location]

    def write(self):
        """Output the MHTML file."""
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
