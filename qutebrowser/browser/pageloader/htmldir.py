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

"""Utils for writing a HTML file and a assets-containing folder."""

import os
import os.path
import re

from PyQt5.QtCore import QUrl


def _inc_filename(filename):
    """Take a filename and increases its number."""
    num = 1
    name, ext = os.path.splitext(filename)
    match = re.search(r'-(\d+)$', name)
    if match:
        num = int(match.group(1)) + 1
        name = name[match.start(1):]
    if ext:
        return '{}-{}.{}'.format(name, num, ext)
    else:
        return '{}-{}'.format(name, num)


def _get_asset_folder_path(dest):
    """Return the path for the asset folder.

    Args:
        dest: Path of the root HTML document.
    """
    base_folder, filename = os.path.split(dest)
    filename, ext = os.path.splitext(filename)
    if ext == '':
        filename = filename + ' - assets'
    return os.path.join(base_folder, filename)


class HTMLDirWriter():

    """A class for writing multiple files to a HTML file and an assets folder.

    Attributes:
        root_content: The root content as bytes.
        content_location: The url of the page as str.
        content_type: The MIME-type of the root content as str.
        folder_path: The path of the assets folder.
        folder_name: The name of the assets folder.
        file_mapping: A original url->new filename mapping.
    """

    suggested_ext = '.html'

    def __init__(self, root_content, content_location, content_type, dest):
        self.root_content = root_content
        self.content_location = content_location
        self.dest = dest
        self.folder_path = _get_asset_folder_path(dest)
        self.file_mapping = {}

    @property
    def folder_name(self):
        folder_path = self.folder_path.rstrip(os.path.sep)
        return os.path.basename(folder_path)

    def rewrite_url(self, url, base=None):
        """Rewrite a URL to point at the (future) resource location.

        Args:
            url: The url to rewrite as QUrl.
            base: The URL of the file that references url (needed for CSS).

        Returns the modified URL.
        """
        if url.scheme() == 'data':
            return url
        if base is not None:
            url = base.resolved(url)
        else:
            url = QUrl(self.content_location).resolved(url)
        if url in self.file_mapping:
            return QUrl(self.file_mapping[url])
        new_filename = url.fileName()
        if not new_filename:
            new_filename = 'asset'
        while new_filename in self.file_mapping.values():
            new_filename = _inc_filename(new_filename)
        self.file_mapping[url] = new_filename
        if base is None or base == QUrl(self.content_location):
            return QUrl(os.path.join(self.folder_name, new_filename))
        else:
            return QUrl(new_filename)

    def add_file(self, location, content, content_type=None):
        """Add a file to the given MHTML collection.

        Args:
            location: The original location (URL) of the file.
            content: The binary content of the file.
            content_type: The MIME-type of the content (if available)
            transfer_encoding: The transfer encoding to use for this file.
        """
        filename = self.file_mapping[QUrl(location)]
        filepath = os.path.join(self.folder_path, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as fp:
            fp.write(content)

    def remove_file(self, location):
        """Remove a file.

        Args:
            location: The URL that identifies the file.
        """
        raise NotImplementedError

    def write(self):
        """Output the HTML file."""
        with open(self.dest, 'wb') as fp:
            fp.write(self.root_content)
