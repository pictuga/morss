from distutils.core import setup

setup(	name='morss',
	description='Get full-text RSS feeds',
	author='pictuga',
	author_email='contact at author name dot com',
	url='http://morss.it/',
	license='GPL 3+',
	packages=['morss'],
	package_data={'':['feedify.ini']},
	install_requires=[
		'readability-lxml',
		'python-dateutil <= 1.5',
		'lxml'
	]
	)
