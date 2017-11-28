NOSE=nosetests3
NOSETESTS=TZ=GMT $(NOSE) -v -w tests

all check: flake8 nosetests

flake8:
	flake8 snipe tests

nosetests:
	$(NOSETESTS)

coverage:
	python3-coverage erase
	$(NOSETESTS) --with-coverage
	python3-coverage html

clean:
	$(RM) -r .coverage profiling htmlcov parser.out tests/parser.out

install:

.PHONY: all clean install check flake8 nosetests
