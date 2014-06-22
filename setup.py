from setuptools import setup, find_packages

package_name = 'morss'
setup(
    name=package_name,
    description='Get full-text RSS feeds',
    author='pictuga, Samuel Marks',
    author_email='contact at pictuga dot com',
    url='http://morss.it/',
    license='GPL 3+',
    package_dir={package_name: package_name},
    packages=find_packages(),
    package_data={package_name: ['feedify.ini', 'reader.html.template']},
    test_suite=package_name + '.tests')
