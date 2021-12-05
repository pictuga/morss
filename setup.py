from datetime import datetime
from glob import glob

from setuptools import setup

package_name = 'morss'

setup(
    name = package_name,
    version = datetime.now().strftime('%Y%m%d.%H%M'),
    description = 'Get full-text RSS feeds',
    long_description = open('README.md').read(),
    long_description_content_type = 'text/markdown',
    author = 'pictuga',
    author_email = 'contact@pictuga.com',
    url = 'http://morss.it/',
    download_url = 'https://git.pictuga.com/pictuga/morss',
    license = 'AGPL v3',
    packages = [package_name],
    install_requires = ['lxml', 'bs4', 'python-dateutil', 'chardet'],
    extras_require = {
        'full': ['pymysql', 'redis', 'diskcache', 'gunicorn'],
        'dev': ['pylint']
    },
    package_data = {package_name: ['feedify.ini']},
    data_files = [
        ('share/' + package_name, ['README.md', 'LICENSE']),
        ('share/' + package_name + '/www', glob('www/*.*')),
        ('share/' + package_name + '/www/cgi', [])
    ],
    entry_points = {
        'console_scripts': [package_name + '=' + package_name + '.__main__:main']
    })
