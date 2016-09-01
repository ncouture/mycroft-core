# Copyright 2016 Mycroft AI, Inc.
#
# This file is part of Mycroft Core.
#
# Mycroft Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Mycroft Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Mycroft Core.  If not, see <http://www.gnu.org/licenses/>.


import subprocess
from os.path import join
import re
import os
import string
import time
# import serial
import sys
import random

from mycroft import MYCROFT_ROOT_PATH
from mycroft.tts import TTS, TTSValidator
from mycroft.configuration import ConfigurationManager

__author__ = 'jdorleans'

# Mapping based on Jeffers phoneme to viseme map, seen in table 1 from:
# http://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.221.6377&rep=rep1&type=pdf
#
# Mycroft unit visemes based on images found at:
#   http://www.web3.lu/wp-content/uploads/2014/09/visemes.jpg
# and mapping was created partially based on the "12 mouth shapes" visuals seen at
#   https://wolfpaulus.com/journal/software/lipsynchronization/
# with final viseme group to image mapping by Steve Penrod
#
def PhonemeToViseme(pho):
	return {
		# /A viseme group
		'v': 5,
		'f': 5,

		# /B viseme group
		'uh': 2,
		'w': 2,
		'uw': 2,
		'er': 2,
		'r': 2,
		'ow': 2,

		# /C viseme group
		'b': 4,
		'p': 4,
		'm': 4,

		# /D viseme group
		'aw': 1,

		# /E viseme group
		'th': 3,
		'dh': 3,

		# /F viseme group
		'zh': 3,
		'ch': 3,
		'sh': 3,
		'jh': 3,

		# /G viseme group
		'oy': 6,
		'ao': 6,		

		# /H viseme group
		'z': 3,
		's': 3,

		# /I viseme group
		'ae': 0,
		'eh': 0,
		'ey': 0,
		'ah': 0,
		'ih': 0,
		'y': 0,
		'iy': 0,
		'aa': 0,
		'ay': 0,
		'ax': 0,
		'hh': 0,

		# /J viseme group
		'n': 3,
		't': 3,
		'd': 3,
		'l': 3,

		# /K viseme group
		'g': 3,
		'ng': 3,
		'k': 3,

		'pau': 4,
	}.get(pho, 4)    # 4 is default if phoneme not found

##############################################################################


config = ConfigurationManager.get().get("tts", {})

NAME = 'mimic'
BIN = config.get(
    "mimic.path", join(MYCROFT_ROOT_PATH, 'mimic', 'bin', 'mimic'))


class Mimic(TTS):
    def __init__(self, lang, voice):
        super(Mimic, self).__init__(lang, voice)

    def execute(self, sentence, client):
	# Before speaking, blink 20% of the time
	random.seed()
	# port = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=3.0)
	if (random.random() < 0.5):
		client.emit(Message("enclosure.eyes.blink");
		# port.write("eyes.blink")

	# invoke mimic, generating phoneme list and a WAV file
#        subprocess.call([BIN, '-voice', self.voice, '-t', sentence])
	outMimic = subprocess.check_output([BIN, '-voice', self.voice, '-t', sentence, '-psdur',"-o","/tmp/mimic.wav"])

	# split into parts
	lisParts = outMimic.split(" ");
	# covert phonemes to visemes
	lisVis = []	# list of visemes and when to stop showing them (in seconds)	
	for s in lisParts:
		phoDur = s.split(":")
		if len(phoDur) != 2:
			continue
		lisVis.append([PhonemeToViseme(phoDur[0]), float(phoDur[1])])

	# play WAV, then walk thru visemes while it plays
	subprocess.Popen(['/usr/bin/aplay', '/tmp/mimic.wav'])
	timeStart = time.time()
	for vis in lisVis:
		# port.write("mouth.viseme="+str(vis[0])+"\n")
		elap = time.time()-timeStart
		if (elap < vis[1]):
			time.sleep( vis[1]-elap)

	# After speaking, blink 20% of the time
	if (random.random() < 0.2):
		client.emit(Message("enclosure.eyes.blink");
		# port.write("eyes.blink")

	# delete WAV
	os.remove("/tmp/mimic.wav")


class MimicValidator(TTSValidator):
    def __init__(self):
        super(MimicValidator, self).__init__()

    def validate_lang(self, lang):
        pass

    def validate_connection(self, tts):
        try:
            subprocess.call([BIN, '--version'])
        except:
            raise Exception(
                'Mimic is not installed. Make sure install-mimic.sh ran '
                'properly.')

    def get_instance(self):
        return Mimic
