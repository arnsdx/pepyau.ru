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

if [ "$#" -ne 1 ]; then
    echo "Usage: install-tls SOURCE_DIR | --rollback" >&2
    exit 2
fi

candidate=$(mktemp "$tls_dir/.current.XXXXXX")
check_config=$(mktemp "$tls_dir/.check.XXXXXX")
if [ "$1" = --rollback ]; then
    cp "$tls_dir/previous.conf" "$candidate"
else
    if [ ! -s "$1/fullchain.pem" ] || [ ! -s "$1/privkey.pem" ]; then
        echo "SOURCE_DIR must contain fullchain.pem and privkey.pem" >&2
        exit 2
    fi
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

if [ -f "$tls_dir/current.conf" ]; then
    previous=$(mktemp "$tls_dir/.previous.XXXXXX")
    cp "$tls_dir/current.conf" "$previous"
    mv -f "$previous" "$tls_dir/previous.conf"
fi
keep_release=true
mv -f "$candidate" "$tls_dir/current.conf"
echo "TLS configuration activated. Reload nginx to serve the selected certificate."
