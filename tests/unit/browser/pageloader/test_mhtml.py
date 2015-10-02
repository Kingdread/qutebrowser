# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:
import io
import textwrap
import re
import pytest

from PyQt5.QtCore import QUrl

from qutebrowser.browser.pageloader import mhtml

@pytest.fixture(autouse=True)
def patch_uuid(monkeypatch):
    monkeypatch.setattr("uuid.uuid4", lambda: "UUID")


class Checker:

    """A helper to check mhtml output.

    Attrs:
        filename: The filename that you should write the output to.
    """

    def __init__(self, tmpdir):
        self.filename = tmpdir.join('test-mhtml-output').strpath

    @property
    def value(self):
        with open(self.filename, 'rb') as f:
            return f.read()

    def expect(self, expected):
        with open(self.filename, 'rb') as f:
            actual = f.read()
        actual = actual.decode('ascii').replace('\r\n', '\n')
        expected = textwrap.dedent(expected).lstrip('\n')
        assert expected == actual


@pytest.fixture
def checker(tmpdir):
    return Checker(tmpdir)


def test_quoted_printable_umlauts(checker):
    content = 'Die süße Hündin läuft in die Höhle des Bären'
    content = content.encode('iso-8859-1')
    writer = mhtml.MHTMLWriter(root_content=content,
                               content_location='localhost',
                               content_type='text/plain',
                               dest=checker.filename)
    writer.write()
    checker.expect("""
        Content-Type: multipart/related; boundary="---=_qute-UUID"
        MIME-Version: 1.0

        -----=_qute-UUID
        Content-Location: localhost
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        Die=20s=FC=DFe=20H=FCndin=20l=E4uft=20in=20die=20H=F6hle=20des=20B=E4ren
        -----=_qute-UUID--
        """)


@pytest.mark.parametrize('header, value', [
    ('content_location', 'http://brötli.com'),
    ('content_type', 'text/pläin'),
])
def test_refuses_non_ascii_header_value(checker, header, value):
    defaults = {
        'root_content': b'',
        'content_location': 'http://example.com',
        'content_type': 'text/plain',
    }
    defaults[header] = value
    writer = mhtml.MHTMLWriter(dest=checker.filename, **defaults)
    with pytest.raises(UnicodeEncodeError) as excinfo:
        writer.write()
    assert "'ascii' codec can't encode" in str(excinfo.value)


def test_file_encoded_as_base64(checker):
    content = b'Image file attached'
    writer = mhtml.MHTMLWriter(root_content=content, content_type='text/plain',
                               content_location='http://example.com',
                               dest=checker.filename)
    writer.add_file(location='http://a.example.com/image.png',
                    content='\U0001F601 image data'.encode('utf-8'),
                    content_type='image/png')
    writer.write()
    checker.expect("""
        Content-Type: multipart/related; boundary="---=_qute-UUID"
        MIME-Version: 1.0

        -----=_qute-UUID
        Content-Location: http://example.com
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        Image=20file=20attached
        -----=_qute-UUID
        Content-Location: http://a.example.com/image.png
        MIME-Version: 1.0
        Content-Type: image/png
        Content-Transfer-Encoding: base64

        8J+YgSBpbWFnZSBkYXRh

        -----=_qute-UUID--
        """)


@pytest.mark.parametrize('content_type', ['text/plain', 'image/png'])
def test_payload_lines_wrap(checker, content_type):
    payload = b'1234567890' * 10
    writer = mhtml.MHTMLWriter(root_content=b'', content_type='text/plain',
                               content_location='http://example.com',
                               dest=checker.filename)
    writer.add_file(location='http://example.com/payload', content=payload,
                    content_type=content_type)
    writer.write()
    for line in checker.value.split(b'\r\n'):
        assert len(line) < 77


def test_files_appear_sorted(checker):
    writer = mhtml.MHTMLWriter(root_content=b'root file',
                               content_type='text/plain',
                               content_location='http://www.example.com/',
                               dest=checker.filename)
    for subdomain in 'ahgbizt':
        writer.add_file(location='http://{}.example.com/'.format(subdomain),
                        content='file {}'.format(subdomain).encode('utf-8'),
                        content_type='text/plain')
    writer.write()
    checker.expect("""
        Content-Type: multipart/related; boundary="---=_qute-UUID"
        MIME-Version: 1.0

        -----=_qute-UUID
        Content-Location: http://www.example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        root=20file
        -----=_qute-UUID
        Content-Location: http://a.example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        file=20a
        -----=_qute-UUID
        Content-Location: http://b.example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        file=20b
        -----=_qute-UUID
        Content-Location: http://g.example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        file=20g
        -----=_qute-UUID
        Content-Location: http://h.example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        file=20h
        -----=_qute-UUID
        Content-Location: http://i.example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        file=20i
        -----=_qute-UUID
        Content-Location: http://t.example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        file=20t
        -----=_qute-UUID
        Content-Location: http://z.example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        file=20z
        -----=_qute-UUID--
        """)


def test_empty_content_type(checker):
    writer = mhtml.MHTMLWriter(root_content=b'',
                               content_location='http://example.com/',
                               content_type='text/plain',
                               dest=checker.filename)
    writer.add_file('http://example.com/file', b'file content')
    writer.write()
    checker.expect("""
        Content-Type: multipart/related; boundary="---=_qute-UUID"
        MIME-Version: 1.0

        -----=_qute-UUID
        Content-Location: http://example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable


        -----=_qute-UUID
        MIME-Version: 1.0
        Content-Location: http://example.com/file
        Content-Transfer-Encoding: base64

        ZmlsZSBjb250ZW50

        -----=_qute-UUID--
        """)


def test_removing_file_from_mhtml(checker):
    writer = mhtml.MHTMLWriter(root_content=b'root',
                               content_location='http://example.com/',
                               content_type='text/plain',
                               dest=checker.filename)
    writer.add_file('http://evil.com/', b'file content')
    writer.remove_file('http://evil.com/')
    writer.write()
    checker.expect("""
        Content-Type: multipart/related; boundary="---=_qute-UUID"
        MIME-Version: 1.0

        -----=_qute-UUID
        Content-Location: http://example.com/
        MIME-Version: 1.0
        Content-Type: text/plain
        Content-Transfer-Encoding: quoted-printable

        root
        -----=_qute-UUID--
        """)

def test_rewrite_url():
    writer = mhtml.MHTMLWriter(root_content=b'',
                               content_location='localhost',
                               content_type='text/plain',
                               dest='/dev/null')
    url = QUrl('http://example.com/url?query=yes#anchor')
    assert writer.rewrite_url(url) == url
