#!/usr/bin/env python3

import sys
import struct
import os.path
import argparse
import xml.etree.ElementTree as ET
import gzip
from zipfile import ZipFile
import json
from PyPDF2 import PdfFileReader

# Size
default_x_width = 1404
default_y_width = 1872

# Mappings
stroke_colour = {
    0 : [0, 0, 0],
    1 : [125, 125, 125],
    2 : [255, 255, 255]
}


def main():
    parser = argparse.ArgumentParser(prog=__prog_name__)
    parser.add_argument('--height',
                        help='Desired height of image',
                        type=float,
                        default=default_y_width)
    parser.add_argument('--width',
                        help='Desired width of image',
                        type=float,
                        default=default_x_width)
    parser.add_argument("-i",
                        "--input",
                        help=".rm input file",
                        required=True,
                        metavar="FILENAME",
                        )
    parser.add_argument("-o",
                        "--output",
                        help="prefix for output files",
                        required=True,
                        metavar="NAME",
                        )
    parser.add_argument("-c",
                        "--coloured_annotations",
                        help="Colour annotations for document markup.",
                        action='store_true',
                        )
    parser.add_argument('--version',
                        action='version',
                        version='%(prog)s {version}'.format(version=__version__))
    args = parser.parse_args()

    if not os.path.exists(args.input):
        parser.error('The file "{}" does not exist!'.format(args.input))
    if args.coloured_annotations:
        set_coloured_annots()
    zip2xopp(args.input, args.output, args.coloured_annotations)

def set_coloured_annots():
    global stroke_colour
    stroke_colour = {
        0: [0, 0, 0],
        1: [255, 0, 0],
        2: [255,255,255],
        3: [255, 255, 0],
        4: [0,0,125],
    }

def abort(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def zip2xopp(input_file, output_name, coloured_annotations=False):

    if coloured_annotations:
        set_coloured_annots()

    with ZipFile(input_file, 'r') as zip:

        # Generate xopp
        xop = ET.Element('xournal')
        ET.SubElement(xop, 'title').text = 'Test'

        # Validate content
        with zip.open([n for n in zip.namelist() if n.endswith('.content')][0], 'r') as cfile:
            content = json.load(cfile)
        if content['fileType'] == 'pdf':
            # Parse and copy pdf
            pdfname = [n for n in zip.namelist() if n.endswith('.pdf')][0]
            sizes = []
            with zip.open(pdfname, 'r') as pfile:
                pdf = PdfFileReader(pfile)
                pagecnt = pdf.getNumPages()
                for p in range(pagecnt):
                    box = pdf.getPage(p).mediaBox
                    sizes.append((float(box.getHeight()),float(box.getWidth())))
            with zip.open(pdfname, 'r') as pfile:
                data = pfile.read()
                output = open(output_name+'.pdf', 'wb')
                output.write(data)
                output.close()
        elif content['fileType'] == 'notebook':
            pagecnt = int(content['pageCount'])
            sizes = [(675.4, 506.5) for i in range(pagecnt)]
        else:
            raise NotImplementedError('unsupported file type')

        for p in range(pagecnt):
            height,width = sizes[p]

            page = ET.SubElement(xop, 'page')
            page.set('width', str(width))
            page.set('height', str(height))

            bg = ET.SubElement(page, 'background')
            if content['fileType'] == 'pdf':
                bg.set('type', 'pdf')
                bg.set('domain', 'absolute')
                bg.set('filename', output_name+'.pdf')
                bg.set('pageno', '%dll'%(p+1))
            elif content['fileType'] == 'notebook':
                bg.set('type', 'solid')
                bg.set('color', '#ffffffff')
                bg.set('style', 'lined')

            pages = [n for n in zip.namelist() if n.endswith('/%d.rm'%p)]

            if len(pages)>0:
                with zip.open(pages[0], 'r') as f:
                    rm2xopp(f.read(), page, coloured_annotations=coloured_annotations, x_width=width, y_width=height)

    output = gzip.open(output_name+'.xopp', 'w')
    output.write(ET.tostring(xop))
    output.close()


def rm2xopp(data, page, coloured_annotations=False,
              x_width=default_x_width, y_width=default_y_width):

    offset = 0

    # Is this a reMarkable .lines file?
    expected_header_v3=b'reMarkable .lines file, version=3          '
    expected_header_v5=b'reMarkable .lines file, version=5          '
    if len(data) < len(expected_header_v5) + 4:
        abort('File too short to be a valid file')

    fmt = '<{}sI'.format(len(expected_header_v5))
    header, nlayers = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
    is_v3 = (header == expected_header_v3)
    is_v5 = (header == expected_header_v5)
    if (not is_v3 and not is_v5) or  nlayers < 1:
        abort('Not a valid reMarkable file: <header={}><nlayers={}>'.format(header, nlayers))
        return

    for layer in range(nlayers):
        olayer = ET.SubElement(page, 'layer')

        fmt = '<I'
        (nstrokes,) = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)

        # Iterate through the strokes in the layer (If there is any)
        for stroke in range(nstrokes):
            if is_v3:
                fmt = '<IIIfI'
                pen_nr, colour, i_unk, width, nsegments = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
            if is_v5:
                fmt = '<IIIffI'
                pen_nr, colour, i_unk, width, unknown, nsegments = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
                #print('Stroke {}: pen_nr={}, colour={}, width={}, unknown={}, nsegments={}'.format(stroke, pen_nr, colour, width, unknown, nsegments))

            last_width = 0
            #print(pen_nr)
            # Brush
            if (pen_nr == 0 or pen_nr == 12):
                pen = Brush(width, colour)
            # caligraphy
            elif pen_nr == 21:
                if coloured_annotations:
                    colour = 4
                pen = Caligraphy(width, colour)
            # Marker
            elif (pen_nr == 3 or pen_nr == 16):
                if coloured_annotations:
                    colour = 1
                pen = Marker(width, colour)
            # BallPoint
            elif (pen_nr == 2 or pen_nr == 15):
                pen = Ballpoint(width, colour)
            # Fineliner
            elif (pen_nr == 4 or pen_nr == 17):
                if coloured_annotations:
                    colour = 1
                pen = Fineliner(width, colour)
            # pencil
            elif (pen_nr == 1 or pen_nr == 14):
                pen = Pencil(width, colour)
            # mech
            elif (pen_nr == 7 or pen_nr == 13):
                pen = Mechanical_Pencil(width, colour)
            # Highlighter
            elif (pen_nr == 5 or pen_nr == 18):
                width = 30
                opacity = 0.2
                if coloured_annotations:
                    colour = 3
                pen = Highlighter(width, colour)
            elif (pen_nr == 8): # Erase area
               pen = Erase_Area(width, colour)
            elif (pen_nr == 6): # Eraser
                colour = 2
                pen = Eraser(width, colour)
            else:
                print('Unknown pen_nr: {}'.format(pen_nr))

            # Iterate through the segments to form a polyline
            coords = []
            widths = []
            for segment in range(nsegments):
                fmt = '<ffffff'
                xpos, ypos, speed, tilt, width, pressure = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
                xpos = (xpos*x_width)/1404
                ypos = (ypos*y_width)/1872
                """
                ratio = (y_width/x_width)/(1872/1404)
                if ratio > 1:
                    xpos = ratio*((xpos*x_width)/1404)
                    ypos = (ypos*y_width)/1872
                else:
                    xpos = (xpos*x_width)/1404
                    ypos = (1/ratio)*(ypos*y_width)/1872
                """
                if segment % pen.segment_length == 0:
                    segment_color = pen.get_segment_color(speed, tilt, width, pressure, last_width)
                    segment_width = pen.get_segment_width(speed, tilt, width, pressure, last_width)
                    segment_opacity = pen.get_segment_opacity(speed, tilt, width, pressure, last_width)
                    segment_width = segment_width/1404*x_width

                widths.append(str(segment_width))
                coords.append(str(xpos))
                coords.append(str(ypos))

            if segment_opacity<0:
                segment_opacity = 0

            if pen.tool:
                stroke = ET.SubElement(olayer, 'stroke')
                stroke.set('tool', pen.tool)
                stroke.set('ts', '0ll')
                stroke.set('fn','')
                stroke.set('color','#%02x%02x%02x%02x'%(segment_color[0], segment_color[1], segment_color[2], int(segment_opacity*255)))
                stroke.set('width', ' '.join(widths))
                stroke.text = ' '.join(coords)
                
class Pen:
    def __init__(self, base_width, base_color):
        self.base_width = base_width
        self.base_color = stroke_colour[base_color]
        self.segment_length = 1000
        self.stroke_cap = "round"
        self.base_opacity = 1
        self.name = "Basic Pen"
        self.tool = 'pen'

    def get_segment_width(self, speed, tilt, width, pressure, last_width):
        return self.base_width

    def get_segment_color(self, speed, tilt, width, pressure, last_width):
        return self.base_color

    def get_segment_opacity(self, speed, tilt, width, pressure, last_width):
        return self.base_opacity

    def cutoff(self, value):
        """must be between 1 and 0"""
        value = 1 if value > 1 else value
        value = 0 if value < 0 else value
        return value


class Fineliner(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.base_width = (base_width ** 2.1) * 1.1
        self.name = "Fineliner"


class Ballpoint(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.segment_length = 5
        self.name = "Ballpoint"

    def get_segment_width(self, speed, tilt, width, pressure, last_width):
        segment_width = (0.5 + pressure) + (1 * width) - 0.5*(speed/50)
        return segment_width

    def get_segment_color(self, speed, tilt, width, pressure, last_width):
        intensity = (0.1 * -(speed / 35)) + (1.2 * pressure) + 0.5
        intensity = self.cutoff(intensity)
        # using segment color not opacity because the dots interfere with each other.
        # Color must be 255 rgb
        segment_color = [int(abs(intensity - 1) * 255)] * 3
        return segment_color

    # def get_segment_opacity(self, speed, tilt, width, pressure, last_width):
    #     segment_opacity = (0.2 * -(speed / 35)) + (0.8 * pressure)
    #     segment_opacity *= segment_opacity
    #     segment_opacity = self.cutoff(segment_opacity)
    #     return segment_opacity

class Marker(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.segment_length = 3
        self.name = "Marker"

    def get_segment_width(self, speed, tilt, width, pressure, last_width):
        segment_width = 0.7 * (((1 * width)) - 0.4 * tilt) + (0.1 * last_width)
        return segment_width


class Pencil(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.segment_length = 2
        self.name = "Pencil"

    def get_segment_width(self, speed, tilt, width, pressure, last_width):
        segment_width = 0.7 * ((((0.8*self.base_width) + (0.5 * pressure)) * (1 * width)) - (0.25 * tilt**1.8) - (0.6 * speed / 50))
        #segment_width = 1.3*(((self.base_width * 0.4) * pressure) - 0.5 * ((tilt ** 0.5)) + (0.5 * last_width))
        max_width = self.base_width * 10
        segment_width = segment_width if segment_width < max_width else max_width
        return segment_width

    def get_segment_opacity(self, speed, tilt, width, pressure, last_width):
        segment_opacity = (0.1 * -(speed / 35)) + (1 * pressure)
        segment_opacity = self.cutoff(segment_opacity) - 0.1
        return segment_opacity


class Mechanical_Pencil(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.base_width = self.base_width ** 2
        self.base_opacity = 0.7
        self.name = "Machanical Pencil"


class Brush(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.segment_length = 2
        self.stroke_cap = "round"
        self.opacity = 1
        self.name = "Brush"

    def get_segment_width(self, speed, tilt, width, pressure, last_width):
        segment_width = 0.7 * (((1 + (1.4 * pressure)) * (1 * width)) - (0.5 * tilt) - (0.5 * speed / 50))  #+ (0.2 * last_width)
        return segment_width

    def get_segment_color(self, speed, tilt, width, pressure, last_width):
        intensity = (pressure ** 1.5  - 0.2 * (speed / 50))*1.5
        intensity = self.cutoff(intensity)
        # using segment color not opacity because the dots interfere with each other.
        # Color must be 255 rgb
        rev_intensity = abs(intensity - 1)
        segment_color = [int(rev_intensity * (255-self.base_color[0])),
                         int(rev_intensity * (255-self.base_color[1])),
                         int(rev_intensity * (255-self.base_color[2]))]

        return segment_color


class Highlighter(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.stroke_cap = "square"
        self.base_opacity = 0.3
        self.name = "Highlighter"
        self.tool = "highlighter"


class Eraser(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.stroke_cap = "square"
        self.base_width = self.base_width * 2
        self.name = "Eraser"
        self.tool = None

class Erase_Area(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.stroke_cap = "square"
        self.base_opacity = 0
        self.name = "Erase Area"
        self.tool = None


class Caligraphy(Pen):
    def __init__(self, base_width, base_color):
        super().__init__(base_width, base_color)
        self.segment_length = 2
        self.name = "Calligraphy"

    def get_segment_width(self, speed, tilt, width, pressure, last_width):
        segment_width = 0.5 * (((1 + pressure) * (1 * width)) - 0.3 * tilt) + (0.1 * last_width)
        return segment_width

if __name__ == "__main__":
    main()
