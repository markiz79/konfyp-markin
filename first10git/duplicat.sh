#!/bin/bash

find "$1" -type f -exec md5sum {} \; | sort | awk ' 
{
	hash=$1
	file=$2

	files[hash] = files[hash] "\n" file
	count[hash]++
}

END{
	for (hash in count){
		if (count[hash] > 1){
			print "Дубликаты:"
			print files[hash]
		}
	}
}'
