@echo off
python "%~dp0playgame.py" --verbose --fill --log_input --log_output --log_error --log_dir game_logs  --log_stderr --turns 81 --turntime 1000  %* "python ""%~dp0starter\python\main.py""" "python ""%~dp0starter\python\main.py""" 

