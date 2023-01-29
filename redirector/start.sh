#!/usr/bin/env sh


while true; do
    echo "> "
    read line < "${1:-/dev/stdin}"
    counter=3
    while true; do
        echo "${line}: test"
        sleep 1
        if [[ ${counter} -eq 0 ]]; then
            break
        fi
        counter=${counter}-1
    done
done
