# Lambda smush py
Utility with the sole aim to squeeze that little bit more code out of Python based [AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html) functions defined in-line to [CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-lambda-function.html) templates.

- [How it works](#how-it-works)
- [Usage](#usage)
- [Examples](#examples)

## How it works
CloudFormation offers the ability to define Lambda function code _directly within templates_ for Python and Node.js runtimes via the [`Code:` property](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-lambda-function.html#cfn-lambda-function-code) - negating the need for an S3 code bucket and great for keeping smaller functions tightly coupled with a stack.

Unfortunately the allowed code size - including whitespace, is limited to [4096 characters](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-lambda-function-code.html#cfn-lambda-function-code-zipfile). With this utility a Python based Lambda function is transformed to a compressed equivalent which is inflated at runtime to gain additional kilobytes of usable space for in-lined functions.

At time of invoke the following steps are executed:
- Temporary file created within the Lambda container.
- File populated with Base64 _decoded_ and _inflated_ function source.
- Python then loads the source as a new module (`imp.load_source()`).
- Proxy function acting as the handler then calls module handler, executing the original source.
- Additional [function invokes](https://aws.amazon.com/blogs/compute/container-reuse-in-lambda/) for the lifetime of the container will simply call the proxy function - the decode and inflate steps only **occur once**, adding very little additional overhead.

The bootloader ends up being nothing more than:

```py
import base64,imp,tempfile,zlib
_='''\
SOURCE_FUNCTION_BASE64_ENCODED_AND_COMPRESSED\
'''
l=tempfile.mkdtemp()+'/l.py'
h=open(l,'w')
h.write(zlib.decompress(base64.b64decode(_)))
h.close()
m=imp.load_source('l',l)
def HANDLER_NAME(e,c):
	return m.HANDLER_NAME(e,c)
```

## Usage

```
usage: lambdasmushpy.py [-h] --source SOURCE --handler-name HANDLER_NAME
                        [--strip-comments] [--strip-empty-lines]
                        [--template YAML] [--template-placeholder PLACEHOLDER]
                        [--output FILE]

Generates compressed Python based AWS Lambda functions to fit within the
maximum 4KB codesize limit of a CloudFormation template

optional arguments:
  -h, --help            show this help message and exit
  --source SOURCE       Path to Lambda function
  --handler-name HANDLER_NAME
                        Name of handler Lambda calls to invoke function
  --strip-comments      Remove comment only lines to further reduce function
                        size
  --strip-empty-lines   Remove empty lines to further reduce function size
  --template YAML       Merge generated code into given YAML CloudFormation
                        template
  --template-placeholder PLACEHOLDER
                        Place holder text within CloudFormation template
  --output FILE         Write output to given filename, otherwise send to
                        console
```

## Examples
Source function `/path/to/lambda.py` with handler `my_handler()` is compressed, with the result sent to console:

```sh
$ ./lambdasmushpy.py" \
	--source "/path/to/lambda.py" \
	--handler-name "my_handler"
```

Generated functions can also be embedded directly into CloudFormation YAML templates through the use of a placeholder.

For this example the compressed source is further reduced by removing comment and empty lines, the final embedded result is written to `/path/to/final/template.yaml`:

```sh
$ ./lambdasmushpy.py" \
	--source "/path/to/lambda.py" \
	--handler-name "my_handler" \
	--strip-comments \
	--strip-empty-lines \
	--template "/path/to/source/template.yaml" \
	--template-placeholder SMUSH_FUNCTION \
	--output "/path/to/final/template.yaml"
```

The bundled [`example/`](example) shows this process end-to-end in detail.
