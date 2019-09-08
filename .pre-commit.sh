#!/bin/sh -e
# cribbed from
# https://codeinthehole.com/tips/tips-for-using-a-git-pre-commit-hook/
STASH_NAME="pre-commit-$(date +%s)"
git stash save --keep-index $STASH_NAME

# the tests take too long for each commit
make flake8 mypy

TOPSTASH=$(git stash list | head -1 | awk '{print $NF}')
if [ "$TOPSTASH" = "$STASH_NAME" ]; then
  git stash pop
fi
