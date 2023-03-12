"""
A micropython driver for TM74HC595-based 7-segment displays modules.

The main drawback to this module design is that you have to keep
refreshing it, can't just update when you want the display to change.

This isn't a problem for simple projects, but for more complex stuff,
you'll end up turning the display off whenever you wait on blocking I/O
or do any processing. (The Sinclair SLOW command says "Hi!")

You could probably make the thing slightly nicer to use on a threaded
controller, or maybe the PIO stuff on RP2040.

Note that the module commonly available on Aliexpress has no resistors,
so power it with 3.3V and minimise the time any one LED is illuminated.

Copyright (c) 2022 'robtinkers'

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from micropython import const
from machine import Pin
import time
# ubinascii is only used for '#'-coding, feel free to disable if required
import ubinascii

# flip these two values if the LEDs are lit where they shouldn't be, and vice versa
LIT = const(0b0)
UNLIT = const(0b1)

# either '.' or ':'
SEGMENT8 = const('.')

# all my own work, inasmuch as there is any originality in a 7-segment font
TINKER_FONT = {
    # just a little bit of personality in the '7' 'J' 'T' 'Y' and 'Z'
    # some letters are unusual by necessity, particularly 'K' 'M' 'R' 'V' and 'W'
    '0': 0x3F, '1': 0x06, '2': 0x5B, '3': 0x4F, '4': 0x66,
    '5': 0x6D, '6': 0x7D, '7': 0x27, '8': 0x7F, '9': 0x6F,
    'A': 0x77, 'B': 0x7F, 'C': 0x39, 'D': 0x3F, 'E': 0x79, 'F': 0x71, 'G': 0x3D,
    'H': 0x76, 'I': 0x06, 'J': 0x1E, 'K': 0x75, 'L': 0x38, 'M': 0x55, 'N': 0x37,
    'O': 0x3F, 'P': 0x73, 'Q': 0x67, 'R': 0x33, 'S': 0x6D, 'T': 0x07, 'U': 0x3E,
    'V': 0x2A, 'W': 0x6A, 'X': 0x76, 'Y': 0x6E, 'Z': 0x1B,
    'b': 0x7C, 'c': 0x58, 'd': 0x5E, 'h': 0x74, 'i': 0x04,
    'j': 0x0C, 'l': 0x30, 'n': 0x54, 'o': 0x5C, 'r': 0x50,
    't': 0x78, 'u': 0x1C, 'v': 0x14, 'w': 0x1D,
    ' ': 0x00, '_': 0x08, '-': 0x40, '‾': 0x01, '^': 0x01,
    '(': 0x39, ')': 0x0F, '[': 0x39, ']': 0x0F,
    '"': 0x22, '`': 0x02, "'": 0x20,
    '?': 0x53, '!': 0x82, '°': 0x63,
    # some lower-case options that I don't like, but maybe you do...
#    'a': 0x5F,
#    'g': 0x6F,
}

BLANK = const(' ')
UNDEF = const('_')



class Display:

    sclk = None
    rclk = None
    dio = None
    _displays = None
    _font = None

    def __init__(self, sclk, rclk, dio, displays=1, font=TINKER_FONT):
        if not isinstance(sclk, Pin):
            sclk = Pin(sclk, Pin.OUT)
        self.sclk = sclk

        if not isinstance(rclk, Pin):
            rclk = Pin(rclk, Pin.OUT)
        self.rclk = rclk

        if not isinstance(dio, Pin):
            dio = Pin(dio, Pin.OUT)
        self.dio = dio

        if isinstance(displays, int):
            d = []
            for i in range(displays):
                d.append(1<<(displays-i-1))
            displays = d
        self._displays = tuple(displays)

        self._font = font #ATTN: no .copy()



    # ~50% speed-up with viper, so brighter LEDs and less flickering
    @micropython.viper
    def _update_displays(self, b:uint, d:uint):
        m = uint(0b10000000)
        while m != uint(0):
            self.dio.value(LIT if b & m else UNLIT)
            self.sclk.value(0)
            self.sclk.value(1)
            m >>= 1
        m = uint(0b10000000)
        while m != uint(0):
            self.dio.value(1 if d & m else 0) # 1/0 not LIT/UNLIT
            self.sclk.value(0)
            self.sclk.value(1)
            m >>= 1
        self.rclk.value(0)
        self.rclk.value(1)



    def _clear_displays(self, displays):
        self._update_displays(self._font[BLANK], displays)

    def clear(self, duration=0):
        self._clear_displays(-1)
        if duration > 0:
            time.sleep(duration)


    # do the font lookup to turn text into a bunch of LED values
    # `padding` can add blanks before and after (useful for a scroller)
    def encode(self, text, padding=0):
        if padding is True:
            padding = len(self._displays)
        if padding > 0:
            text = (BLANK * padding) + text + (BLANK * padding)

        result = []
        i = 0
        while i < len(text):
            try:
                c = text[i]
                if c == SEGMENT8:
                    if i:
                        result[-1] |= 0b10000000
                elif c == '#':
                    if text[i+1] == '#':
                        i += 1
                        result.append(self._font['#'])
                    else:
                        i += 2
                        result.append(ubinascii.unhexlify(text[i-1:i+1])[0])
                elif c == '?' and '?' in self._font and self._font['?'] == 0x53 and SEGMENT8 == '.':
                    if i:
                        result[-1] |= 0b10000000
                    result.append(self._font[c])
                else:
                    result.append(self._font[c])
            except:
                if UNDEF is not None:
                    result.append(self._font[UNDEF])
            i += 1
        return tuple(result)


    # set multiple displays (default: all of them) to show the same thing
    # if `msg` is more than one character, it will run through them all
    def blast(self, msg, displays=-1, duration=1, clear=None): # that is duration *per character*
        if isinstance(msg, str):
            msg = self.encode(msg)
        if clear is None:
            clear = bool(len(msg)>1)

        for i in range(len(msg)):
            self._update_displays(msg[i], displays)
            if duration > 0:
                time.sleep(duration)

        if clear:
            self._clear_displays(displays)


    # print a message on the displays, this is probably the function you want
    def print(self, msg, pos=0, duration=1, fade=(0b11111111,), clear=None):
        if isinstance(msg, str):
            msg = self.encode(msg)
        if clear is None:
            clear = bool(len(msg)>1)

        used_displays = 0

        for f in fade:
            t0 = time.ticks_ms()
            while True:
                for i in range(len(msg)):
                    displays = 0
                    if pos >= 0:
                        j = pos + i
                        try: displays = self._displays[j]
                        except IndexError: break # slight optimisation over 'pass'
                    else:
                        j = len(self._displays) - len(msg) + pos + i + 1
                        if j >= 0:
                            try: displays = self._displays[j]
                            except IndexError: pass
                    if displays:
                        if duration > 0:
                            self._update_displays(msg[i] & f, displays)
                        used_displays |= displays
                t = time.ticks_ms()
                if not (duration > 0) or (t - t0 >= duration * 1000) or (t < t0):
                    break

        if clear and used_displays:
            self._clear_displays(used_displays)


    #### could split into a seperate sub-class here

    #
    def vbars(self, n, duration=1):
        if n >= 0:
            msg = ''
            while n > 1.999:
                msg = msg + '#36'
                n -= 2
            if n > 1.499:
                msg = msg + '#32'
            elif n > 0.999:
                msg = msg + '#30'
            elif n > 0.499:
                msg = msg + '#20'
            self.print(msg, duration=duration, clear=True)
        else:
            n = -n
            msg = ''
            while n > 1.999:
                msg = '#36' + msg
                n -= 2
            if n > 1.499:
                msg = '#16' + msg
            elif n > 0.999:
                msg = '#06' + msg
            elif n > 0.499:
                msg = '#04' + msg
            self.print(msg, pos=-1, duration=duration, clear=True)


    #
    def flash(self, msg, pos=0, on=0.5, off=0.5, count=3):
        if isinstance(msg, str):
            msg = self.encode(msg)
        self.clear()
        for _ in range(count):
            self.print(msg, pos, duration=on, clear=True)
            time.sleep(off)



    _scroll_encoded = None
    _scroll_cursor = 0

    def scroll_init(self, msg, start=0):
        if isinstance(msg, str):
            msg = self.encode(msg)
        while len(msg) < len(self._displays):
            msg.insert(0, self._font[BLANK])
        self._scroll_encoded = msg
        if start >= 0:
            self._scroll_cursor = start
        else:
            self._scroll_cursor = len(msg) - len(self._displays) + start + 1

    def scroll(self, amount=+1, duration=1):
        t0 = time.ticks_ms()
        while True:
            for i in range(len(self._displays)):
                try: b = self._scroll_encoded[(self._scroll_cursor + i) % len(self._scroll_encoded)]
                except IndexError: break
                if duration > 0:
                    self._update_displays(b, 1<<(len(self._displays) - 1 - i))
            t = time.ticks_ms()
            if not (duration > 0) or (t - t0 >= duration * 1000) or (t < t0):
                break
        self.clear()

        if (self._scroll_cursor + amount + len(self._displays)) <= len(self._scroll_encoded) and self._scroll_cursor + amount >= 0:
            self._scroll_cursor = (self._scroll_cursor + amount) % len(self._scroll_encoded)
            return True
        else:
            self._scroll_cursor = (self._scroll_cursor + amount) % len(self._scroll_encoded)
            return False



    def demo(self):
        self.clear()

        self.print('dEMO')

        for i in range(len(self._displays)*4+1):
            self.vbars(i/2, duration=0.25)

        self.blast('1234567890'+BLANK, duration=0.5)

        self.print('YO!', duration=2)

        msg = self.encode('WASS' + ('U'*len(self._displays)) + 'P?', padding=True)
        self.scroll_init(msg)
        while self.scroll(duration=0.5):
            pass

        self.scroll_init(BLANK*(len(self._displays)-1) + "CHILLIN'")
        while self.scroll(duration=0.5):
            pass
        self.scroll(amount=-1, duration=0) # required because changing scroll direction
        while self.scroll(amount=-1, duration=0.5):
            pass
        self.clear(duration=0.5)

        self.print('FADE', fade=(0b00000001, 0b00100011, 0b01100011, 0b01110111, 0b11111111), duration=0.5)
        self.print('FADE', fade=(0b11111110, 0b11011100, 0b10011100, 0b10001000, 0b00000000), duration=0.5)

        self.flash('LOOK')

        self.blast('#01#02#40#10#08#04#40#20#01', duration=0.5)

        msg = self.encode('ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz', padding=True)
        self.scroll_init(msg)
        while self.scroll(duration=0.25):
            pass

        self.print('dONE')
