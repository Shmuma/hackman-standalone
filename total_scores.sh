#!/bin/sh

report=$1
if [ "a$report" = "a" ]; then
  echo Usage: $0 report.txt
  exit
fi

count=$(grep '^score' $report | wc -l)
s1=$(echo `grep '^score' $report | cut -d ' ' -f 2` | sed 's/ /+/g' | bc -l)
s2=$(echo `grep '^score' $report | cut -d ' ' -f 3` | sed 's/ /+/g' | bc -l)

echo rounds $count
echo player1 $s1
echo player2 $s2
