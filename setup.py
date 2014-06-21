from setuptools import setup, find_packages

package_name = 'morss'
setup(    name=package_name,
    description='Get full-text RSS feeds',
    author='pictuga',
    author_email='contact at author name dot com',
    url='http://morss.it/',
    license='GPL 3+',
    package_dir={package_name: package_name},
    packages=find_packages(),
    package_data={package_name: ['feedify.ini']},
    test_suite=package_name + '.tests')
