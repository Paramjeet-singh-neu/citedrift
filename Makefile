PYTHON ?= .venv/bin/python

.PHONY: collect parse normalize analyze drift report test

collect:
	$(PYTHON) -m citedrift.collect

parse:
	$(PYTHON) -m citedrift.parse

normalize:
	$(PYTHON) -m citedrift.normalize

analyze:
	$(PYTHON) -m citedrift.analyze

drift: analyze

report:
	$(PYTHON) -m citedrift.report

test:
	$(PYTHON) -m unittest discover -s tests -v
