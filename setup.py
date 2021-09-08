from glob import glob

from setuptools import setup

package_name = 'morss'

setup(
    name = package_name,
    description = 'Get full-text RSS feeds',
    author = 'pictuga, Samuel Marks',
    author_email = 'contact at pictuga dot com',
    url = 'http://morss.it/',
    download_url = 'https://git.pictuga.com/pictuga/morss',
    license = 'AGPL v3',
    packages = [package_name],
    install_requires = ['lxml', 'bs4', 'python-dateutil', 'chardet', 'pymysql'],
    package_data = {package_name: ['feedify.ini']},
    data_files = [
        ('share/' + package_name, ['README.md', 'LICENSE']),
        ('share/' + package_name + '/www', glob('www/*.*')),
        ('share/' + package_name + '/www/cgi', [])
    ],
    entry_points = {
        'console_scripts': [package_name + '=' + package_name + '.__main__:main']
    })
