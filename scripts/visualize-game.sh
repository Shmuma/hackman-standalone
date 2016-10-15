#!/bin/sh

BOT=0

if [ "$1" != "" ]; then
	BOT=$1
fi

if [ ! -d tmp ]; then
    mkdir tmp
fi

rm -f tmp/*.png
sbcl --script bin/bot-input2avi.sbcl game_logs/0.bot${BOT}.input
ffmpeg -f image2 -i tmp/tmp-%04d.png tmp.mpg
