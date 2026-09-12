PYTHON ?= .venv/bin/python

.PHONY: collect parse normalize test

collect:
	$(PYTHON) -m citedrift.collect

parse:
	$(PYTHON) -m citedrift.parse

normalize:
	$(PYTHON) -m citedrift.normalize

test:
	$(PYTHON) -m unittest discover -s tests -v
