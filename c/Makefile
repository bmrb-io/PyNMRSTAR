python2: cnmrstarmodule.c
	python setup.py build
	cp build/*/*.so ..
	rm -rf build
python3: cnmrstarmodule.c
	python3 setup.py build
	cp build/*/*.so ..
	rm -rf build
clean:
	rm -rfv build/ ../*.so ./*.so
