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

"""Base class for output formats."""


class PageWriter:

    """Base class for output formats.

    Each method does nothing and should be overwritten by a subclass.

    Attributes:
        root_content: The root content as bytes.
        content_location: The url of the page as str.
        content_type: The MIME-type of the root content as str.
        dest: The output filename.
    """

    suggested_ext = ''
    """Suggested filename extension for the output file."""

    def __init__(self, root_content, content_location, content_type, dest):
        """Set the attributes to the given values."""
        self.root_content = root_content
        self.content_location = content_location
        self.content_type = content_type
        self.dest = dest

    def rewrite_url(self, url, base=None):
        """Return the future URL for the given URL.

        Some file formats need to change the URL for a given asset. This is
        possible by overwriting this function. If you rewrite a URL referenced
        inside a stylesheet, you have to use the base argument, since URLs are
        relative to the stylesheet itself.

        Args:
            url: The url to rewrite as QUrl.
            base: The URL relative to which url should be rewritten as QUrl.

        Returns the modified URL.
        """
        # pylint: disable=unused-argument
        return url

    def add_file(self, location, content, content_type=None):
        """Add a file to the output.

        Args:
            location: The original location of the file (not rewritten).
            content: The binary content of the file.
            content_type: The MIME-type of the content (if available).
        """
        raise NotImplementedError

    def remove_file(self, location):
        """Remove the given file.

        Args:
            location: The URL of the file.
        """
        raise NotImplementedError

    def write(self):
        """Output the file to the destination given in __init__."""
        raise NotImplementedError
