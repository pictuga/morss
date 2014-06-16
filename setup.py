from setuptools import setup, find_packages
from morss import __version__

if __name__ == '__main__':
    package_name = 'morss'
    setup(name=package_name,
          description='Get full-text RSS feeds',
          author='pictuga, Samuel Marks',
          author_email='contact at pictuga dot com',
          url='http://morss.it/',
          license='GPL 3+',
          version=__version__,
          package_dir={package_name: package_name},
          packages=find_packages(),
          package_data={package_name: ['feedify.ini']},
          test_suite=package_name + '.tests')
