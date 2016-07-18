parser: cnmrstarparsermodule.c
#	gcc -o parser cnmrstarparsermodule.c -O3 -std=gnu99 -lm -g
	python setup.py build
	cp build/*/*.so ..
clean:
	rm -rfv parser build/ ../cnmrstarparser.so