# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:
import pytest

from qutebrowser.browser.pageloader import loader


@pytest.mark.parametrize('has_cssutils', [True, False])
@pytest.mark.parametrize('inline, style, expected_urls', [
    (False, "@import 'default.css'", ['default.css']),
    (False, '@import "default.css"', ['default.css']),
    (False, "@import \t 'tabbed.css'", ['tabbed.css']),
    (False, "@import url('default.css')", ['default.css']),
    (False, """body {
    background: url("/bg-img.png")
    }""", ['/bg-img.png']),
    (True, 'background: url(folder/file.png) no-repeat', ['folder/file.png']),
    (True, 'content: url()', []),
])
def test_css_url_scanner(monkeypatch, has_cssutils, inline, style,
                         expected_urls):
    if has_cssutils:
        assert loader.cssutils is not None
    else:
        monkeypatch.setattr('qutebrowser.browser.pageloader.loader.cssutils',
                            None)
    expected_urls.sort()
    urls = loader._get_css_imports(style, inline=inline)
    urls.sort()
    assert urls == expected_urls


class TestNoCloseBytesIO:
    # WORKAROUND for https://bitbucket.org/logilab/pylint/issues/540/
    # pylint: disable=no-member

    def test_fake_close(self):
        fp = loader._NoCloseBytesIO()
        fp.write(b'Value')
        fp.close()
        assert fp.getvalue() == b'Value'
        fp.write(b'Eulav')
        assert fp.getvalue() == b'ValueEulav'

    def test_actual_close(self):
        fp = loader._NoCloseBytesIO()
        fp.write(b'Value')
        fp.actual_close()
        with pytest.raises(ValueError) as excinfo:
            fp.getvalue()
        assert str(excinfo.value) == 'I/O operation on closed file.'
        with pytest.raises(ValueError) as excinfo:
            fp.write(b'Closed')
        assert str(excinfo.value) == 'I/O operation on closed file.'
