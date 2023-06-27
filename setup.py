from datetime import datetime
from glob import glob

from setuptools import setup


def get_version():
    with open('morss/__init__.py', 'r+') as file:
        lines = file.readlines()

        # look for hard coded version number
        for i in range(len(lines)):
            if lines[i].startswith('__version__'):
                version = lines[i].split('"')[1]
                break

        # create (& save) one if none found
        if version == '':
            version = datetime.now().strftime('%Y%m%d.%H%M')
            lines[i] = '__version__ = "' + version + '"\n'

            file.seek(0)
            file.writelines(lines)

        # return version number
        return version

package_name = 'morss'

setup(
    name = package_name,
    version = get_version(),
    description = 'Get full-text RSS feeds',
    long_description = open('README.md').read(),
    long_description_content_type = 'text/markdown',
    author = 'pictuga',
    author_email = 'contact@pictuga.com',
    url = 'http://morss.it/',
    project_urls = {
        'Source': 'https://git.pictuga.com/pictuga/morss',
        'Bug Tracker': 'https://github.com/pictuga/morss/issues',
    },
    license = 'AGPL v3',
    packages = [package_name],
    install_requires = ['lxml', 'bs4', 'python-dateutil', 'chardet'],
    extras_require = {
        'full': ['redis', 'diskcache', 'gunicorn', 'setproctitle'],
        'dev': ['pylint', 'pyenchant', 'pytest', 'pytest-cov'],
    },
    python_requires = '>=2.7',
    package_data = {package_name: ['feedify.ini']},
    data_files = [
        ('share/' + package_name, ['README.md', 'LICENSE']),
        ('share/' + package_name + '/www', glob('www/*.*')),
    ],
    entry_points = {
        'console_scripts': [package_name + '=' + package_name + '.__main__:main'],
    },
    scripts = ['morss-helper'],
)
