#!/usr/bin/env sh



while true; do
    counter=3
    while true; do
        echo "${line}: aaa"
        sleep 1
        if [[ ${counter} -eq 0 ]]; then
            break
        fi
        counter=${counter}-1
    done
    echo "> "
done
