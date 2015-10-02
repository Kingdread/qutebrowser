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

"""Classes for searching webpages for referenced assets."""

import functools
import io
import os
import re
import enum

from PyQt5.QtCore import QUrl
from PyQt5.QtWebKit import QWebElement

from qutebrowser.browser import webelem
from qutebrowser.browser.pageloader import mhtml, htmldir
from qutebrowser.utils import log, objreg, message, usertypes

try:
    import cssutils
except ImportError:
    cssutils = None


_CSS_URL_PATTERNS = [re.compile(x) for x in [
    r"@import\s+'(?P<url>[^']+)'",
    r'@import\s+"(?P<url>[^"]+)"',
    r'''url\((?P<url>[^'"][^)]*)\)''',
    r'url\("(?P<url>[^"]+)"\)',
    r"url\('(?P<url>[^']+)'\)",
]]


def _get_css_imports_regex(data, callback=None):
    urls = []

    def cb_wrapper(match):
        url = match.group('url')
        whole = match.group(0)
        urls.append(url)
        if callback is not None:
            new_url = callback(QUrl(url)).toString()
            start, stop = match.span('url')
            # .span returns the position relative to the whole string, but we
            # want the position relative to the match start instead.
            start -= match.start(0)
            stop -= match.start(0)
            return whole[:start] + new_url + whole[stop:]
        return whole

    for pattern in _CSS_URL_PATTERNS:
        data = pattern.sub(cb_wrapper, data)
    return (data, urls)


def _handle_css_declaration(declaration, callback):
    """Return URLs in the declaration and rewrite them if callback is given."""
    urls = []
    # prop = background, color, margin, ...
    for prop in declaration:
        # value = red, 10px, url(foobar), ...
        for value in prop.propertyValue:
            if isinstance(value, cssutils.css.URIValue):
                if value.uri:
                    urls.append(value.uri)
                    if callback is not None:
                        new_url = callback(QUrl(value.uri)).toString()
                        value.uri = new_url
    return urls


def _get_css_imports_cssutils(data, inline=False, callback=None):
    # We don't care about invalid CSS data, this will only litter the log
    # output with CSS errors
    parser = cssutils.CSSParser(loglevel=100,
                                fetcher=lambda url: (None, ""), validate=False)
    if not inline:
        urls = []
        sheet = parser.parseString(data)
        for rule in sheet.cssRules:
            if isinstance(rule, cssutils.css.CSSImportRule):
                url = rule.href
                urls.append(url)
                if callback is not None:
                    new_url = callback(QUrl(url)).toString()
                    rule.href = new_url
            elif isinstance(rule, cssutils.css.CSSStyleRule):
                new_urls = _handle_css_declaration(rule.style, callback)
                urls.extend(new_urls)
        return (sheet.cssText.decode(sheet.encoding), urls)
    else:
        declaration = parser.parseStyle(data)
        urls = _handle_css_declaration(declaration, callback)
        return (declaration.cssText, urls)


def _get_css_imports(data, inline=False, callback=None):
    """Return all assets that are referenced in the given CSS document.

    The returned URLs are relative to the stylesheet's URL.

    Args:
        data: The content of the stylesheet to scan as string.
        inline: True if the argument is a inline HTML style attribute.
        callback: The URL rewrite callback.
    """
    if cssutils is None:
        return _get_css_imports_regex(data, callback)
    else:
        return _get_css_imports_cssutils(data, inline, callback)


class _Downloader():

    """A class to download whole websites.

    Attributes:
        web_view: The QWebView which contains the website that will be saved.
        dest: Destination filename.
        writer_factory: The class to use for creating a writer object.
        writer: The writer object which is used to save the page.
        loaded_urls: A set of QUrls of finished asset downloads.
        pending_downloads: A set of unfinished (url, DownloadItem) tuples.
        _finished: A flag indicating if the file has already been written.
        _used: A flag indicating if the downloader has already been used.
    """

    def __init__(self, web_view, dest, writer_factory):
        self.web_view = web_view
        self.dest = dest
        self.writer_factory = writer_factory
        self.writer = None
        self.loaded_urls = {web_view.url()}
        self.pending_downloads = set()
        self._finished = False
        self._used = False

    def run(self):
        """Download and save the page.

        The object must not be reused, you should create a new one if
        you want to download another page.
        """
        if self._used:
            raise ValueError("Downloader already used")
        self._used = True
        web_url = self.web_view.url()
        web_frame = self.web_view.page().mainFrame()
        # We clone the document because we might rewrite URLs
        document = QWebElement(web_frame.documentElement())

        self.writer = self.writer_factory(
            # We need the writer, but we don't know the content yet, as URLs
            # still need to be rewritten.
            b'',
            content_location=web_url.toString(),
            # I've found no way of getting the content type of a QWebView, but
            # since we're using .toHtml, it's probably safe to say that the
            # content-type is HTML
            content_type='text/html; charset="UTF-8"',
            dest=self.dest,
        )
        # Currently only downloading <link> (stylesheets), <script>
        # (javascript) and <img> (image) elements.
        elements = document.findAll('link, script, img')

        for element in elements:
            element = webelem.WebElementWrapper(element)
            if 'src' in element:
                element_url = element['src']
                attrib = 'src'
            elif 'href' in element:
                element_url = element['href']
                attrib = 'href'
            else:
                # Might be a local <script> tag or something else
                continue
            absolute_url = web_url.resolved(QUrl(element_url))
            new_url = self.writer.rewrite_url(absolute_url)
            element[attrib] = new_url.toString()
            self.fetch_url(absolute_url)

        styles = document.findAll('style')
        for style in styles:
            style = webelem.WebElementWrapper(style)
            if 'type' in style and style['type'] != 'text/css':
                continue
            new_style, urls = _get_css_imports(
                str(style), callback=functools.partial(self.writer.rewrite_url,
                                                       base=web_url))
            style.setInnerXml(new_style)
            for element_url in urls:
                self.fetch_url(web_url.resolved(QUrl(element_url)))

        # Search for references in inline styles
        for element in document.findAll('[style]'):
            element = webelem.WebElementWrapper(element)
            style = element['style']
            new_style, urls = _get_css_imports(
                style, inline=True, callback=functools.partial(
                    self.writer.rewrite_url, base=web_url))
            element['style'] = new_style
            for element_url in urls:
                self.fetch_url(web_url.resolved(QUrl(element_url)))

        self.writer.root_content = document.toOuterXml().encode('utf-8')
        # Shortcut if no assets need to be downloaded, otherwise the file would
        # never be saved. Also might happen if the downloads are fast enough to
        # complete before connecting their finished signal.
        self.collect_zombies()
        if not self.pending_downloads and not self._finished:
            self.finish_file()

    def fetch_url(self, url):
        """Download the given url and add the file to the collection.

        Args:
            url: The file to download as QUrl.
        """
        if url.scheme() == 'data':
            return
        # Prevent loading an asset twice
        if url in self.loaded_urls:
            return
        self.loaded_urls.add(url)

        log.downloads.debug("loading asset at %s", url)

        download_manager = objreg.get('download-manager', scope='window',
                                      window='current')
        item = download_manager.get(url, fileobj=_NoCloseBytesIO(),
                                    auto_remove=True)
        self.pending_downloads.add((url, item))
        item.finished.connect(
            functools.partial(self.finished, url, item))
        item.error.connect(
            functools.partial(self.error, url, item))
        item.cancelled.connect(
            functools.partial(self.error, url, item))

    def finished(self, url, item):
        """Callback when a single asset is downloaded.

        Args:
            url: The original url of the asset as QUrl.
            item: The DownloadItem given by the DownloadManager
        """
        self.pending_downloads.remove((url, item))
        mime = item.raw_headers.get(b'Content-Type', b'')

        # Note that this decoding always works and doesn't produce errors
        # RFC 7230 (https://tools.ietf.org/html/rfc7230) states:
        # Historically, HTTP has allowed field content with text in the
        # ISO-8859-1 charset [ISO-8859-1], supporting other charsets only
        # through use of [RFC2047] encoding.  In practice, most HTTP header
        # field values use only a subset of the US-ASCII charset [USASCII].
        # Newly defined header fields SHOULD limit their field values to
        # US-ASCII octets.  A recipient SHOULD treat other octets in field
        # content (obs-text) as opaque data.
        mime = mime.decode('iso-8859-1')

        if mime.lower() == 'text/css':
            # We can't always assume that CSS files are UTF-8, but CSS files
            # shouldn't contain many non-ASCII characters anyway (in most
            # cases). Using "ignore" lets us decode the file even if it's
            # invalid UTF-8 data.
            # The file written to the MHTML file won't be modified by this
            # decoding, since there we're taking the original bytestream.
            try:
                css_string = item.fileobj.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                log.downloads.warning("Invalid UTF-8 data in %s", url)
                css_string = item.fileobj.getvalue().decode('utf-8', 'ignore')
            new_css, import_urls = _get_css_imports(
                css_string, callback=functools.partial(self.writer.rewrite_url,
                                                       base=url))
            item.fileobj.seek(0)
            item.fileobj.write(new_css.encode('utf-8'))
            item.fileobj.truncate()
            for import_url in import_urls:
                absolute_url = url.resolved(QUrl(import_url))
                self.fetch_url(absolute_url)

        self.writer.add_file(url.toString(), item.fileobj.getvalue(), mime)
        item.fileobj.actual_close()
        if self.pending_downloads:
            return
        self.finish_file()

    def error(self, url, item, *_args):
        """Callback when a download error occurred.

        Args:
            url: The orignal url of the asset as QUrl.
            item: The DownloadItem given by the DownloadManager.
        """
        try:
            self.pending_downloads.remove((url, item))
        except KeyError:
            # This might happen if .collect_zombies() calls .finished() and the
            # error handler will be called after .collect_zombies
            log.downloads.debug("Oops! Download already gone: %s", item)
            return
        item.fileobj.actual_close()
        self.writer.add_file(url.toString(), b'')
        if self.pending_downloads:
            return
        self.finish_file()

    def finish_file(self):
        """Save the file to the filename given in __init__."""
        if self._finished:
            log.downloads.debug("finish_file called twice, ignored!")
            return
        self._finished = True
        log.downloads.debug("All assets downloaded, ready to finish off!")
        self.writer.write()
        message.info('current', "Page saved as {}".format(self.dest))

    def collect_zombies(self):
        """Collect done downloads and add their data to the MHTML file.

        This is needed if a download finishes before attaching its
        finished signal.
        """
        items = set((url, item) for url, item in self.pending_downloads
                    if item.done)
        log.downloads.debug("Zombie downloads: %s", items)
        for url, item in items:
            self.finished(url, item)


class _NoCloseBytesIO(io.BytesIO):  # pylint: disable=no-init

    """BytesIO that can't be .closed().

    This is needed to prevent the DownloadManager from closing the stream, thus
    discarding the data.
    """

    def close(self):
        """Do nothing."""
        pass

    def actual_close(self):
        """Close the stream."""
        super().close()


class Format(enum.Enum):
    mhtml = mhtml.MHTMLWriter
    htmldir = htmldir.HTMLDirWriter


def start_download(dest, format):
    """Start downloading the current page and all assets to a MHTML file.

    This will overwrite dest if it already exists.

    Args:
        dest: The filename where the resulting file should be saved.
        format: The Format to use for the output.
    """
    dest = os.path.expanduser(dest)
    web_view = objreg.get('webview', scope='tab', tab='current')
    loader = _Downloader(web_view, dest, format.value)
    loader.run()


def start_download_checked(dest, format):
    """First check if dest is already a file, then start the download.

    Args:
        dest: The filename where the resulting file should be saved.
        format: The Format to use for the output.
    """
    if not os.path.isfile(dest):
        start_download(dest, format)
        return

    q = usertypes.Question()
    q.mode = usertypes.PromptMode.yesno
    q.text = "{} exists. Overwrite?".format(dest)
    q.completed.connect(q.deleteLater)
    q.answered_yes.connect(functools.partial(start_download, dest, format))
    message_bridge = objreg.get('message-bridge', scope='window', window='current')
    message_bridge.ask(q, blocking=False)
