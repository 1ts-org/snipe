NOSE=nosetests3
NOSETESTS=$(NOSE) -v -w tests

all check: flake8 nosetests

flake8:
	flake8 snipe tests

nosetests:
	$(NOSETESTS)

coverage:
	$(NOSETESTS) --with-coverage
	python3-coverage html

clean:
	$(RM) -r .coverage profiling htmlcov parser.out tests/parser.out

install:

.PHONY: all clean install check flake8 nosetests
