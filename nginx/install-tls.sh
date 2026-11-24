#!/bin/sh
set -eu

tls_dir=${TLS_DIR:-/etc/nginx/tls}
umask 077
release=
candidate=
check_config=
previous=
keep_release=false

cleanup() {
    for file in "$candidate" "$check_config" "$previous"; do
        [ -z "$file" ] || rm -f -- "$file"
    done
    if [ -n "$release" ] && [ "$keep_release" = false ]; then
        rm -f -- "$release/fullchain.pem" "$release/privkey.pem"
        rmdir -- "$release"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

check_source() {
    if [ ! -d "$1" ] || [ ! -x "$1" ]; then
        printf 'Cannot access TLS source directory inside the container: %s\n' "$1" >&2
        return 1
    fi

    for pem_name in fullchain.pem privkey.pem; do
        pem_path=$1/$pem_name
        if [ -L "$pem_path" ] && [ ! -e "$pem_path" ]; then
            printf 'TLS symlink target is unavailable inside the container: %s\n' "$pem_path" >&2
        elif [ ! -e "$pem_path" ]; then
            printf 'TLS file is missing inside the container: %s\n' "$pem_path" >&2
        elif [ ! -f "$pem_path" ] || [ ! -r "$pem_path" ] || [ ! -s "$pem_path" ]; then
            printf 'TLS file must be a readable, nonempty regular file: %s\n' "$pem_path" >&2
        else
            continue
        fi
        return 1
    done
    return 0
}

if [ "$#" -ne 1 ]; then
    echo "Usage: install-tls SOURCE_DIR | --ensure | --rollback" >&2
    exit 2
fi

if [ "$1" = --ensure ]; then
    if [ -s "$tls_dir/current.conf" ]; then
        exit 0
    fi
    if ! check_source "$tls_dir"; then
        echo "TLS volume is not initialized. Import fullchain.pem and privkey.pem with docker compose run --rm --no-deps -v /absolute/path/to/certs:/incoming:ro tls-import /incoming." >&2
        exit 2
    fi
    set -- "$tls_dir"
elif [ "$1" != --rollback ] && ! check_source "$1"; then
    exit 2
fi

candidate=$(mktemp "$tls_dir/.current.XXXXXX")
check_config=$(mktemp "$tls_dir/.check.XXXXXX")
if [ "$1" = --rollback ]; then
    cp "$tls_dir/previous.conf" "$candidate"
else
    release=$(mktemp -d "$tls_dir/release.XXXXXX")
    cp "$1/fullchain.pem" "$release/fullchain.pem"
    cp "$1/privkey.pem" "$release/privkey.pem"
    chmod 600 "$release/privkey.pem"
    printf 'ssl_certificate "%s/fullchain.pem";\nssl_certificate_key "%s/privkey.pem";\n' \
        "$release" "$release" > "$candidate"
fi

printf 'events {}\nhttp { server { listen 443 ssl; include "%s"; } }\n' \
    "$candidate" > "$check_config"
nginx -t -c "$check_config" </dev/null

if [ -s "$tls_dir/current.conf" ]; then
    previous=$(mktemp "$tls_dir/.previous.XXXXXX")
    cp "$tls_dir/current.conf" "$previous"
    mv -f "$previous" "$tls_dir/previous.conf"
fi
keep_release=true
mv -f "$candidate" "$tls_dir/current.conf"
echo "TLS configuration activated."
