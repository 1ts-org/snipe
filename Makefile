NOSETESTS=nosetests3 -w tests

all:
	$(NOSETESTS)

coverage:
	$(NOSETESTS) --with-coverage
	python3-coverage html

clean:
	$(RM) -r .coverage profiling htmlcov parser.out tests/parser.out

install:

.PHONY: all clean install
