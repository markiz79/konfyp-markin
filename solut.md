## Задание 1

```bash
grep -o '^[^:]*' /etc/passwd | sort
```

## Задание 2
```
awk '{print $2,$3}' protocols | sort -nr | head -5
```

