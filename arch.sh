#!/bin/bash

find . -type f -name "*.$1" > files.txt

tar -cf archive.tar -T files.txt
