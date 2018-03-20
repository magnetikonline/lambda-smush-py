#!/bin/bash -e

DIRNAME=$(dirname "$0")


"$DIRNAME/../lambdasmushpy.py" \
	--source "$DIRNAME/function.py" \
	--handler-name handler \
	--strip-comments \
	--strip-empty-lines \
	--template "$DIRNAME/template.yaml" \
	--template-placeholder SMUSH_FUNCTION \
	--output "$DIRNAME/output.yaml"
