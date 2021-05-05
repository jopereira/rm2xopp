# reMarkable to Xournal++ converter

Convert a PDF file annotated with reMarkable and extracted as a .zip to a .pdf/.xopp pair. There is no conversion back from .xopp to reMarkable. Notepads are not (yet) supported. 

A lot of the code has been copied from rM2svg.py in https://github.com/lschwetlick/maxio

## Usage

Download your file with [rmapi](https://github.com/juruen/rmapi):

	$ rmapi
	ReMarkable Cloud API Shell
	[/]> get myfile

Convert it:

	$ ./rm2xopp.py -i myfile.zip -o myfile

You get both the pdf and xopp files, that you can then open and edit:

	$ ls myfile.*
	myfile.pdf  myfile.xopp  myfile.zip
	$ xournalpp myfile.xopp
