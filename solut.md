## Задание 1

```bash
grep -o '^[^:]*' /etc/passwd | sort
```

## Задание 2
```bash
awk '{print $2,$3}' protocols | sort -nr | head -5
```

## Задание 3
```bash
#!/bin/bash

text="$1"

len=${#text}
border=$((len + 2))

echo -n "+"

for i in $(seq 1 $border)
do
        echo -n "-"
done

echo "+"
echo "| $text |"
echo -n "+"

for i in $(seq 1 $border)
do
        echo -n "-"
done

echo "+"
```

## Задание 4
```bash
grep -o '[a-zA-Z_][a-zA-Z0-9_]*' hello.c | sort -u

```

## Задание 5
```bash
#!/bin/bash

if [ -f "$1" ]
then
        chmod +x "$1"
        sudo cp "$1" /usr/local/bin/
else
        echo "Файл не найден"
fi
```

## Задание 6
```bash
#!/bin/bash

find . -type f | grep -E "\.(c|js|py)$" | while read file
do
        echo "Файл: $file"
        head -n 1 "$file" | grep -E "^#|^//"
done
```

## Задание 7
```bash
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

```

## Задание 8
```bash
#!/bin/bash

find . -type f -name "*.$1" > files.txt

tar -cf archive.tar -T files.txt
```

## Задание 9
```bash
#!/bin/bash

sed 's/    /\t/g' "$1" > "$2"
```

## Задание 10
```bash
#!/bin/bash

find "$1" -maxdepth 1 -type f -empty

```
