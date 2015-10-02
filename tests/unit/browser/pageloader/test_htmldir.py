# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

import os
import pytest

from PyQt5.QtCore import QUrl

from qutebrowser.browser.pageloader import htmldir

@pytest.mark.parametrize('filename, expected', [
    ('file', 'file-1'), ('file.html', 'file-1.html'), ('file-1', 'file-2'),
    ('file-1.html', 'file-2.html'), ('1-file', '1-file-1'),
    ('1-file-1', '1-file-2'), ('1-file-1.html', '1-file-2.html'),
    ('file-', 'file--1'), ('file--1', 'file--2'), ('file-23', 'file-24'),
    ('file-23.html', 'file-24.html'),
])
def test_inc_filename(filename, expected):
    assert htmldir._inc_filename(filename) == expected

@pytest.mark.parametrize('dest, expected', [
    ('Webpage Title.html', 'Webpage Title'),
    ('Webpage Title', 'Webpage Title - assets'),
    ('/home/downloads/webpage.html', '/home/downloads/webpage'),
    ('/home/downloads/webpage', '/home/downloads/webpage - assets'),
])
def test_get_asset_folder_path(dest, expected):
    assert htmldir._get_asset_folder_path(dest) == expected


@pytest.fixture
def instance(tmpdir):
    dest = tmpdir.join('test-htmldir.html').strpath
    return htmldir.HTMLDirWriter(root_content=b"root content",
                                 content_location=None,
                                 content_type=None,
                                 dest=dest)

def test_folder_name(instance):
    assert instance.folder_name == 'test-htmldir'

@pytest.mark.parametrize('url, base, expected', [
    ('assets/image.png', None, 'test-htmldir/image.png'),
    ('http://example.com/folder/file.css', None, 'test-htmldir/file.css'),
    ('http://example.com/', None, 'test-htmldir/asset'),
    # With base URL
    ('css/default.css', 'css/main.css', 'default.css'),
    # Special case data urls
    ('data:test', None, 'data:test'),
])
def test_rewrite_url(instance, url, base, expected):
    if base is not None:
        base = QUrl(base)
    assert instance.rewrite_url(QUrl(url), base) == QUrl(expected)

def test_rewrite_remembers(instance):
    url = QUrl('http://example.com/file')
    instance.rewrite_url(url)
    # We want something more than just the filename, so we're using a URL that
    # has a number increased
    url = QUrl('http://example.com/folder/file')
    assert instance.rewrite_url(url) == instance.rewrite_url(url)

def test_rewrite_increases_number(instance):
    hosts = "abcdefghijkl"
    for i, host in enumerate(hosts):
        url = QUrl('http://{}/file'.format(host))
        new_url = instance.rewrite_url(url).toString()
        if i >= 1:
            assert new_url.endswith('-{}'.format(i))

def test_htmldir_output(instance):
    files = [
        ('assets/image.png', 'Imäge cöntent'.encode('utf-8')),
        ('http://example.com/main.js', b'alert("Hello")'),
        ('accidental.css', b'this should be removed'),
    ]
    for file_url, content in files:
        instance.rewrite_url(QUrl(file_url))
        instance.add_file(file_url, content)
    instance.remove_file('accidental.css')
    instance.write()

    assert read(instance.dest) == b'root content'
    assert read(fn(instance, 'image.png')) == 'Imäge cöntent'.encode('utf-8')
    assert read(fn(instance, 'main.js')) == b'alert("Hello")'
    assert not os.path.isfile(fn(instance, 'accidental.css'))

def read(path):
    with open(path, 'rb') as f:
        return f.read()

def fn(instance, filename):
    return os.path.join(instance.folder_path, filename)
