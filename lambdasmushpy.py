#!/usr/bin/env python

import argparse
import base64
import os.path
import re
import sys
import zlib

GZIP_COMPRESS_LEVEL = 9
SOURCE_LINE_LENGTH = 160


def exit_error(message):
	sys.stderr.write('Error: {0}\n'.format(message))
	sys.exit(1)

def read_arguments():
	# create parser
	parser = argparse.ArgumentParser(
		description =
			'Generates compressed Python based AWS Lambda functions to fit within the '
			'maximum 4KB codesize limit of a CloudFormation template'
	)

	parser.add_argument(
		'--source',
		help = 'Path to Lambda function',
		required = True
	)

	parser.add_argument(
		'--handler-name',
		help = 'Name of handler Lambda calls to invoke function',
		required = True
	)

	parser.add_argument(
		'--strip-comments',
		action = 'store_true',
		help = 'Remove comment only lines to further reduce function size'
	)

	parser.add_argument(
		'--strip-empty-lines',
		action = 'store_true',
		help = 'Remove empty lines to further reduce function size'
	)

	parser.add_argument(
		'--template',
		help = 'Merge generated code into given YAML CloudFormation template',
		metavar = 'YAML'
	)

	parser.add_argument(
		'--template-placeholder',
		help = 'Place holder text within CloudFormation template',
		metavar = 'PLACEHOLDER'
	)

	parser.add_argument(
		'--output',
		help = 'Write output to given filename, otherwise send to console',
		metavar = 'FILE'
	)

	arg_list = parser.parse_args()

	def get_file_content(file_path):
		fh = open(file_path,'r')
		content = fh.read()
		fh.close()

		return content

	# validate source Lambda function
	if (not os.path.isfile(arg_list.source)):
		exit_error('unable to locate function [{0}]'.format(arg_list.source))

	handler_name = arg_list.handler_name.strip()
	if (not handler_name):
		exit_error('given --handler-name can\'t be empty')

	# contains given handler name?
	lambda_source = get_file_content(arg_list.source)
	match = re.search(
		r'^def +{0}\([^\)]+\) *:[ \t]*$'.format(handler_name),
		lambda_source,
		re.MULTILINE
	)

	if (not match):
		exit_error('unable to locate handler [{0}] within [{1}] source function'.format(
			handler_name,
			arg_list.source
		))

	# validate CloudFormation merge template/placeholder if provided
	template_yaml = None
	template_placeholder = (
		None if (arg_list.template_placeholder is None)
		else arg_list.template_placeholder.strip()
	)

	if (arg_list.template is not None):
		if (not os.path.isfile(arg_list.template)):
			exit_error('unable to locate CloudFormation YAML template [{0}]'.format(arg_list.template))

		if (
			(template_placeholder is None) or
			(not template_placeholder)
		):
			exit_error('argument --template-placeholder must be supplied with --template')


		# confirm given placeholder can be located in template
		template_path = os.path.realpath(arg_list.template)
		template_yaml = get_file_content(template_path)

		if (template_yaml.find('%%{0}%%'.format(template_placeholder)) < 0):
			exit_error('unable to locate placeholder [%%{0}%%] within template [{1}]'.format(
				template_placeholder,
				template_path
			))

	else:
		# no merge template requested
		if (template_placeholder is not None):
			exit_error('argument --template-placeholder only works with --template')

	# return arguments
	return (
		lambda_source,
		handler_name,
		arg_list.strip_comments,
		arg_list.strip_empty_lines,
		template_yaml,
		template_placeholder,
		(
			os.path.realpath(arg_list.output)
			if (arg_list.output is not None)
			else None
		)
	)

def get_source_compressed(
	lambda_source,
	strip_comments,strip_empty_lines
):
	# split source into lines
	source_line_list = lambda_source.split('\n')

	if (strip_comments):
		# remove comment lines
		source_line_list = [
			item
			for item in source_line_list
			if (not re.search(r'^[ \t]*#',item))
		]

	if (strip_empty_lines):
		# remove empty lines
		source_line_list = [
			item
			for item in source_line_list
			if (not item.strip() == '')
		]

	# merge transformed source lines and gzip
	return zlib.compress(
		'\n'.join(source_line_list),
		GZIP_COMPRESS_LEVEL
	)

def build_bootloader(lambda_handler_name,source_compressed):
	def build_base64_source():
		source_base64 = base64.b64encode(source_compressed)

		# split base64 stream by desired line length and quote/indent
		return '\n'.join([
			source_base64[index:index + SOURCE_LINE_LENGTH]
			for index in range(0,len(source_base64),SOURCE_LINE_LENGTH)
		])

	# loader steps:
	# - create temporary directory and file to hold Lambda code as a module
	# - base64 decode and un-gzip Lambda code into temporary file
	# - load module
	# - define wrapper Lambda handler function, to proxy calls to module

	# note: single character variables, all non essential space removed to save size
	return '''\
import base64,imp,tempfile,zlib
_=\'\'\'\\
{0}\\
\'\'\'
l=tempfile.mkdtemp()+'/l.py'
h=open(l,'w')
h.write(zlib.decompress(base64.b64decode(_)))
h.close()
m=imp.load_source('l',l)
def {1}(e,c):
	return m.{1}(e,c)
'''.format(
		build_base64_source(),
		lambda_handler_name
	)

def build_template_embed(template_yaml,template_placeholder,bootloader):
	# split YAML template into lines
	template_line_list = template_yaml.split('\n')

	# work over template lines to determine embed location and indent level
	target = '%%{0}%%'.format(template_placeholder)
	for insert_index,template_line_item in enumerate(template_line_list):
		if (template_line_item.find(target) >= 0):
			# found target insert location
			break

	# determine indent required (leading spaces and tabs) then transform bootloader source to this indent
	indent_payload = re.search('^[ \t]*',template_line_item).group(0)
	bootloader_line_list = [
		indent_payload + bootloader_line_item
		for bootloader_line_item in bootloader.split('\n')
	]

	# insert indented bootloader source at correct line location within template and re-join
	return '\n'.join(
		template_line_list[:insert_index] +
		bootloader_line_list +
		template_line_list[insert_index + 1:]
	)

def main():
	# read CLI arguments
	(
		lambda_source,
		lambda_handler_name,
		strip_comments,
		strip_empty_lines,
		template_yaml,
		template_placeholder,
		output_filename
	) = read_arguments()

	# strip (optional) and compress source
	source_compressed = get_source_compressed(
		lambda_source,
		strip_comments,strip_empty_lines
	)

	# create bootloader source
	bootloader = build_bootloader(
		lambda_handler_name,
		source_compressed
	)

	# if requested, embed generated bootloader into CloudFormation template
	result = (
		build_template_embed(template_yaml,template_placeholder,bootloader)
		if (template_yaml)
		else bootloader
	)

	# write generated function to either file, or direct to console
	if (output_filename):
		fh = open(output_filename,'w')
		fh.write(result)
		fh.close()

		print('Generated Lambda function written to [{0}]'.format(output_filename))

	else:
		print(result)


if (__name__ == '__main__'):
	main()
