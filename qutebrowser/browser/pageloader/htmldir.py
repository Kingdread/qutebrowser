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

from qutebrowser.browser.pageloader import writer


def _inc_filename(filename):
    """Take a filename and increases its number."""
    num = 1
    name, ext = os.path.splitext(filename)
    match = re.search(r'-(\d+)$', name)
    if match:
        num = int(match.group(1)) + 1
        name = name[:match.start(0)]
    return '{}-{}{}'.format(name, num, ext)


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


class HTMLDirWriter(writer.PageWriter):

    """A class for writing multiple files to a HTML file and an assets folder.

    Attributes:
        (see writer.PageWriter)
        folder_path: The path of the assets folder.
        folder_name (readonly): The name of the assets folder.
        file_mapping: A original url->new filename mapping.
    """

    suggested_ext = '.html'

    def __init__(self, root_content, content_location, content_type, dest):
        super().__init__(root_content, content_location, content_type, dest)
        self.folder_path = _get_asset_folder_path(dest)
        self.file_mapping = {}

    @property
    def folder_name(self):
        folder_path = self.folder_path.rstrip(os.path.sep)
        return os.path.basename(folder_path)

    def rewrite_url(self, url, base=None):
        """Return the filename in the assets folder for a given URL.

        Overwritten PageWriter.rewrite_url
        """
        if url.scheme() == 'data':
            return url
        if base is not None:
            url = base.resolved(url)
        else:
            url = QUrl(self.content_location).resolved(url)
        if url in self.file_mapping:
            new_filename = self.file_mapping[url]
        else:
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
        """Add a file to the asset folder.

        Overwritten PageWriter.add_file.
        """
        filename = self.file_mapping[QUrl(location)]
        filepath = os.path.join(self.folder_path, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as fp:
            fp.write(content)

    def remove_file(self, location):
        """Remove a file.

        Overwritten PageWriter.remove_file.
        """
        filename = self.file_mapping[QUrl(location)]
        filepath = os.path.join(self.folder_path, filename)
        os.unlink(filepath)

    def write(self):
        """Output the HTML file.

        Overwritten PageWriter.write.
        """
        with open(self.dest, 'wb') as fp:
            fp.write(self.root_content)
