def handler(event,context):
	log_it('one')
	log_it('two')

	return 'Called my handler!'

def log_it(number):
	print('Log line: {0}'.format(number))
