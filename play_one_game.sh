#!/bin/sh

./playgame.py --verbose --fill --log_input --log_output --log_error \
--log_dir game_logs  --log_stderr --turns 200 --turntime 500 --loadtime 1500 --nolaunch \
--map_file maps/map_03.txt \
"python starter/python/main.py" \
"python starter/python/main.py"
